"""Carga del artefacto entrenado e inferencia (puntual, por lote y reabasto)."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import joblib
import numpy as np

from .config import MODEL_PATH, PRODUCTOS, cargar_umbrales
from .features import fila_features, ventanas_desde_historial
from .registro import sha256

# Rango de precio relativo visto en entrenamiento: descuentos de 8 a 20 % y precio de lista.
# Fuera de él (con un margen pequeño) el modelo no tiene evidencia, así que se acota y se avisa.
PRECIO_REL_MIN, PRECIO_REL_MAX = 0.75, 1.05


@dataclass
class Prediccion:
    p50: float
    p90: float
    advertencias: list[str]
    media: float | None = None  # demanda esperada (v1.1); None con artefactos v1.0


class ModeloDemanda:
    def __init__(self, ruta: Path = MODEL_PATH):
        artefacto = joblib.load(ruta)
        self._p50 = artefacto["p50"]
        self._p90 = artefacto["p90"]
        self._media = artefacto.get("media")  # ausente en v1.0
        self.meta = artefacto["meta"]
        self.version = self.meta["version"]
        self.ruta = Path(ruta)
        self.sha256 = sha256(self.ruta)  # se registra en cada evento de auditoría
        self.factor_seguridad = float(cargar_umbrales()["politica_reabasto"]["factor_seguridad"])

    def _predecir_matriz(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
        p50 = np.clip(self._p50.predict(X), 0, None)
        p90 = np.maximum(np.clip(self._p90.predict(X), 0, None), p50)
        media = np.clip(self._media.predict(X), 0, None) if self._media is not None else None
        return p50, p90, media

    @staticmethod
    def _revisar_entrada(sku: str, precio: float | None, lag_7: float, media_7: float, media_28: float):
        p = PRODUCTOS[sku]
        avisos: list[str] = []
        precio = p.precio_lista if precio is None else precio
        rel = precio / p.precio_lista
        if not PRECIO_REL_MIN <= rel <= PRECIO_REL_MAX:
            avisos.append(
                f"Precio relativo {rel:.2f} fuera del rango de entrenamiento "
                f"[{PRECIO_REL_MIN}, {PRECIO_REL_MAX}]; se acoto para el calculo."
            )
            rel = min(max(rel, PRECIO_REL_MIN), PRECIO_REL_MAX)
        if lag_7 == 0 and media_7 == 0 and media_28 == 0:
            avisos.append("Historial en ceros: posible SKU nuevo o quiebre de stock prolongado. Revisar manualmente.")
        tope = 10 * p.demanda_base * 3
        if max(lag_7, media_7, media_28) > tope:
            avisos.append(
                f"Ventas recientes muy por encima de lo habitual para el SKU (>{tope:.0f} u/dia). "
                "El pronostico extrapola poco; validar si hubo venta institucional o error de captura."
            )
        return rel * p.precio_lista, avisos

    def predecir(self, registros: list[dict]) -> list[Prediccion]:
        filas, avisos = [], []
        for r in registros:
            precio, a = self._revisar_entrada(r["sku"], r.get("precio"), r["lag_7"], r["media_7"], r["media_28"])
            filas.append(fila_features(r["sucursal_id"], r["sku"], r["fecha"], precio,
                                       r.get("en_promocion", False), r["lag_7"], r["media_7"], r["media_28"]))
            avisos.append(a)
        p50, p90, media = self._predecir_matriz(np.asarray(filas, dtype=float))
        medias = media if media is not None else [None] * len(p50)
        return [Prediccion(float(a), float(b), w, None if m is None else float(m))
                for a, b, w, m in zip(p50, p90, avisos, medias)]

    def reabasto(self, sucursal_id: str, sku: str, fecha_inicio: date, horizonte: int,
                 historial: list[float], existencia: float, precio: float | None = None,
                 dias_promocion: set[date] | None = None) -> dict:
        """Pronóstico recursivo día a día y pedido sugerido para cubrir el horizonte.

        Solo el P50 alimenta las ventanas de los días siguientes, así que el bucle recursivo
        predice únicamente el P50; el P90 y la media se calculan después en un solo lote.
        Optimización v1.1: de 3 llamadas por día a 1 por día + 2 por horizonte (ver ADR-005)."""
        dias_promocion = dias_promocion or set()
        h = list(map(float, historial[-28:]))
        filas, fechas, avisos_totales = [], [], set()
        for i in range(horizonte):
            f = fecha_inicio + timedelta(days=i)
            lag7, m7, m28 = ventanas_desde_historial(h)
            precio_ok, avisos = self._revisar_entrada(sku, precio, lag7, m7, m28)
            avisos_totales.update(avisos)
            fila = fila_features(sucursal_id, sku, f, precio_ok, f in dias_promocion, lag7, m7, m28)
            p50 = max(float(self._p50.predict(np.asarray([fila], dtype=float))[0]), 0.0)
            filas.append(fila)
            fechas.append(f)
            h.append(p50)  # el pronóstico alimenta los días siguientes
        X = np.asarray(filas, dtype=float)
        p50s, p90s, medias = self._predecir_matriz(X)
        dias = [{"fecha": f, "p50": round(float(a), 2), "p90": round(float(b), 2),
                 "media": None if medias is None else round(float(medias[j]), 2)}
                for j, (f, a, b) in enumerate(zip(fechas, p50s, p90s))]
        suma50 = sum(d["p50"] for d in dias)
        # Stock de seguridad: suma en cuadratura de los márgenes diarios (supone independencia)
        # El factor viene de config/umbrales.toml (ADR-004: se mantiene en 1.0)
        seguridad = self.factor_seguridad * math.sqrt(sum((d["p90"] - d["p50"]) ** 2 for d in dias))
        pedido = max(0, math.ceil(suma50 + seguridad - existencia))
        media_total = None if dias[0]["media"] is None else round(sum(d["media"] for d in dias), 2)
        return {
            "dias": dias,
            "demanda_esperada": round(suma50, 2),
            "demanda_media": media_total,
            "stock_seguridad": round(seguridad, 2),
            "existencia_actual": existencia,
            "pedido_sugerido": pedido,
            "advertencias": sorted(avisos_totales),
        }
