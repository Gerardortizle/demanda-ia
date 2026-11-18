"""Auditoría y métricas operativas del servicio en línea.

- Bitácora de auditoría: un evento JSON por inferencia con id de petición, fecha, endpoint,
  versión y hash del modelo, entrada, salida y advertencias. Responde a R06 (transparencia)
  y R14 (trazabilidad para auditorías internas y de COFEPRIS) de la Fase I.
  Se escribe en el log estándar (Cloud Logging lo conserva) y, si AUDIT_LOG_PATH está
  definido, también en un archivo JSONL. Las últimas N quedan en memoria para /api/v1/auditoria.
- Métricas operativas: contadores y latencias por endpoint para /api/v1/monitoreo y /metrics (Prometheus).
No se registran datos personales: la API solo recibe ventas agregadas por sucursal y SKU (R05).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from collections import Counter, deque
from datetime import UTC, datetime

import numpy as np
from prometheus_client import CollectorRegistry, Histogram
from prometheus_client import Counter as PCounter

log = logging.getLogger("demanda_ia.auditoria")
MAX_EVENTOS = int(os.getenv("AUDIT_MAX_EVENTOS", "1000"))

REGISTRO_PROM = CollectorRegistry()
PETICIONES = PCounter("demanda_ia_peticiones_total", "Peticiones HTTP a la API", ["ruta", "codigo"], registry=REGISTRO_PROM)
LATENCIA = Histogram("demanda_ia_latencia_segundos", "Latencia por petición", ["ruta"],
                     buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5), registry=REGISTRO_PROM)
PREDICCIONES = PCounter("demanda_ia_predicciones_total", "Pronósticos generados", ["endpoint", "modelo_version"], registry=REGISTRO_PROM)
ADVERTENCIAS = PCounter("demanda_ia_advertencias_total", "Pronósticos con advertencias de entrada", ["tipo"], registry=REGISTRO_PROM)
PRON_P50 = Histogram("demanda_ia_pronostico_p50_unidades", "Distribución del P50 servido (deriva de predicción)",
                     buckets=(0.5, 1, 2, 5, 10, 20, 50, 100, 250), registry=REGISTRO_PROM)


def huella_entrada(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _tipo_advertencia(texto: str) -> str:
    t = texto.lower()
    if "precio" in t:
        return "precio_fuera_de_rango"
    if "ceros" in t:
        return "historial_en_ceros"
    if "encima" in t:
        return "pico_atipico"
    return "otra"


class Monitor:
    """Estado en memoria del proceso (cada instancia de Cloud Run lleva el suyo; el agregado
    entre instancias se obtiene de Prometheus/Cloud Monitoring)."""

    def __init__(self):
        self._lock = threading.Lock()
        self.eventos: deque = deque(maxlen=MAX_EVENTOS)
        self.latencias: dict[str, deque] = {}
        self.codigos: Counter = Counter()
        self.n_pronosticos = 0
        self.n_con_advertencia = 0
        self.tipos_advertencia: Counter = Counter()
        self.suma_p50 = 0.0
        self.inicio = datetime.now(UTC)
        self.archivo = os.getenv("AUDIT_LOG_PATH")

    def peticion(self, ruta: str, codigo: int, ms: float) -> None:
        with self._lock:
            self.latencias.setdefault(ruta, deque(maxlen=2000)).append(ms)
            self.codigos[f"{codigo // 100}xx"] += 1
        PETICIONES.labels(ruta, str(codigo)).inc()
        LATENCIA.labels(ruta).observe(ms / 1000)

    def auditar(self, request_id: str, endpoint: str, modelo, entrada, salidas: list[dict]) -> dict:
        avisos = [a for s in salidas for a in s.get("advertencias", [])]
        evento = {
            "tipo": "auditoria_inferencia",
            "id_peticion": request_id,
            "fecha_utc": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "endpoint": endpoint,
            "modelo_version": modelo.version,
            "modelo_sha256": modelo.sha256[:12],
            "huella_entrada": huella_entrada(entrada),
            "entrada": entrada if not isinstance(entrada, list) else {"registros": len(entrada)},
            "salida": salidas[0] if len(salidas) == 1 else {"resultados": len(salidas)},
            "advertencias": sorted(set(avisos)),
        }
        with self._lock:
            self.eventos.append(evento)
            for s in salidas:
                self.n_pronosticos += 1
                p50 = s.get("pronostico_p50", s.get("demanda_esperada", 0.0)) or 0.0
                self.suma_p50 += p50
                PRON_P50.observe(p50)
                if s.get("advertencias"):
                    self.n_con_advertencia += 1
                    for a in s["advertencias"]:
                        t = _tipo_advertencia(a)
                        self.tipos_advertencia[t] += 1
                        ADVERTENCIAS.labels(t).inc()
        PREDICCIONES.labels(endpoint, modelo.version).inc(len(salidas))
        log.info(json.dumps(evento, ensure_ascii=False, default=str))
        if self.archivo:
            with open(self.archivo, "a", encoding="utf-8") as f:
                f.write(json.dumps(evento, ensure_ascii=False, default=str) + "\n")
        return evento

    def resumen(self, umbrales: dict) -> dict:
        with self._lock:
            lat = {}
            for ruta, v in self.latencias.items():
                a = np.asarray(v)
                lat[ruta] = {"n": int(a.size), "p50_ms": round(float(np.percentile(a, 50)), 1),
                             "p95_ms": round(float(np.percentile(a, 95)), 1)}
            tasa = 100 * self.n_con_advertencia / self.n_pronosticos if self.n_pronosticos else 0.0
            alertas = []
            for ruta, m in lat.items():
                if ruta.startswith("/api") and m["n"] >= 20 and m["p95_ms"] > umbrales["latencia_p95_alerta_ms"]:
                    alertas.append(f"Latencia p95 de {ruta} = {m['p95_ms']} ms (> {umbrales['latencia_p95_alerta_ms']} ms)")
            if self.n_pronosticos >= 50 and tasa > umbrales["tasa_advertencias_api_alerta_pct"]:
                alertas.append(f"{tasa:.1f} % de pronosticos con advertencias (> {umbrales['tasa_advertencias_api_alerta_pct']} %): "
                               "posible cambio en los datos de entrada")
            return {
                "desde_utc": self.inicio.isoformat(timespec="seconds"),
                "peticiones_por_codigo": dict(self.codigos),
                "latencia_por_ruta": lat,
                "pronosticos": self.n_pronosticos,
                "pronostico_p50_promedio": round(self.suma_p50 / self.n_pronosticos, 3) if self.n_pronosticos else None,
                "tasa_advertencias_pct": round(tasa, 2),
                "advertencias_por_tipo": dict(self.tipos_advertencia),
                "eventos_auditoria_en_memoria": len(self.eventos),
                "alertas": alertas,
                "estado": "alerta" if alertas else "ok",
            }

    def ultimos(self, n: int) -> list[dict]:
        with self._lock:
            return list(self.eventos)[-n:]
