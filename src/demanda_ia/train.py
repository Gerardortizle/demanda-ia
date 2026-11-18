"""Entrenamiento offline de DEMANDA-IA.

Uso directo:   python -m demanda_ia.train --version 1.1.0
Uso normal:    python -m demanda_ia.pipeline   (valida datos, entrena, evalúa, aplica compuertas y registra)

Genera models/demanda_ia_<version>.joblib con tres modelos:
  - P50 y P90 (regresión por cuantiles): base del pedido sugerido y del stock de seguridad.
  - media (pérdida Poisson, nuevo en v1.1): demanda esperada sin sesgo para planear compras.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, date, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor

from .config import (
    CATEGORIAS,
    ESTADOS,
    FEATURES,
    FEATURES_CATEGORICAS,
    MODEL_VERSION,
    MODELS_DIR,
    PRODUCTOS,
    REPORTS_DIR,
    SEMILLA,
    SUCURSALES,
    TIPOS_SUCURSAL,
    cargar_umbrales,
)
from .data import simular_serie
from .evaluacion import evaluar, metricas  # noqa: F401  (metricas se re-exporta por compatibilidad)
from .features import es_festivo, es_quincena

INICIO = date(2024, 1, 1)
FIN = date(2025, 12, 31)
CORTE = pd.Timestamp("2025-09-30")  # train <= corte < test
N_SUC_TRAIN = 40
N_SUC_HOLDOUT = 10

PARAMS_CUANTIL = dict(learning_rate=0.08, max_iter=300, max_leaf_nodes=63, min_samples_leaf=40, l2_regularization=1.0)
# Elegidos con scripts/experimentos.py (ver reports/experimentos.json y docs/adr/ADR-004)
PARAMS_MEDIA = dict(learning_rate=0.1, max_iter=600, max_leaf_nodes=31, min_samples_leaf=80, l2_regularization=1.0)


def elegir_sucursales() -> tuple[list[str], list[str]]:
    rng = np.random.default_rng(SEMILLA)
    ids = sorted(SUCURSALES)
    perm = rng.permutation(ids)
    return sorted(perm[:N_SUC_TRAIN]), sorted(perm[N_SUC_TRAIN:N_SUC_TRAIN + N_SUC_HOLDOUT])


def construir_dataset(sucursales: list[str], inicio: date = INICIO, fin: date = FIN) -> pd.DataFrame:
    bloques = []
    for sid in sucursales:
        s = SUCURSALES[sid]
        for sku, p in PRODUCTOS.items():
            serie = simular_serie(sid, sku, inicio, fin)
            y = pd.Series(serie["ventas"])
            df = pd.DataFrame(
                {
                    "sucursal_id": sid,
                    "sku": sku,
                    "fecha": pd.to_datetime(serie["fecha"]),
                    "y": y,
                    "mu": serie["esperado"],
                    "categoria": CATEGORIAS.index(p.categoria),
                    "tipo_sucursal": TIPOS_SUCURSAL.index(s.tipo),
                    "estado": ESTADOS.index(s.estado),
                    "factor_tamano": s.factor_tamano,
                    "demanda_base_sku": p.demanda_base,
                    "precio_relativo": serie["precio"] / p.precio_lista,
                    "en_promocion": serie["promo"],
                    # mismas ventanas que features.ventanas_desde_historial
                    "lag_7": y.shift(7),
                    "media_7": y.shift(1).rolling(7).mean(),
                    "media_28": y.shift(1).rolling(28).mean(),
                }
            )
            bloques.append(df.iloc[28:])
    df = pd.concat(bloques, ignore_index=True)
    fechas = df["fecha"].dt.date
    df["dia_semana"] = df["fecha"].dt.weekday
    df["mes"] = df["fecha"].dt.month
    df["dia_mes"] = df["fecha"].dt.day
    unicas = {d: (es_quincena(d), es_festivo(d)) for d in fechas.unique()}
    df["es_quincena"] = fechas.map(lambda d: unicas[d][0])
    df["es_festivo"] = fechas.map(lambda d: unicas[d][1])
    return df


def _mascara_categoricas() -> np.ndarray:
    mask = np.zeros(len(FEATURES), dtype=bool)
    mask[FEATURES_CATEGORICAS] = True
    return mask


def nuevo_modelo(cuantil: float, **params) -> HistGradientBoostingRegressor:
    p = {**PARAMS_CUANTIL, **params}
    return HistGradientBoostingRegressor(
        loss="quantile", quantile=cuantil, categorical_features=_mascara_categoricas(),
        early_stopping=True, validation_fraction=0.1, n_iter_no_change=20, random_state=SEMILLA, **p,
    )


def nuevo_modelo_media(**params) -> HistGradientBoostingRegressor:
    p = {**PARAMS_MEDIA, **params}
    return HistGradientBoostingRegressor(
        loss="poisson", categorical_features=_mascara_categoricas(),
        early_stopping=True, validation_fraction=0.1, n_iter_no_change=20, random_state=SEMILLA, **p,
    )


def predecir(modelos: dict, d: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    X = d[FEATURES].to_numpy(dtype=float)
    p50 = np.clip(modelos["p50"].predict(X), 0, None)
    p90 = np.maximum(np.clip(modelos["p90"].predict(X), 0, None), p50)
    media = np.clip(modelos["media"].predict(X), 0, None) if modelos.get("media") is not None else None
    return p50, p90, media


def datos_entrenamiento() -> dict[str, pd.DataFrame]:
    suc_train, suc_holdout = elegir_sucursales()
    df = construir_dataset(suc_train)
    df_hold = construir_dataset(suc_holdout)
    return {
        "entrenamiento": df[df["fecha"] <= CORTE],
        "prueba_temporal": df[df["fecha"] > CORTE],
        "sucursales_no_vistas": df_hold[df_hold["fecha"] > CORTE],
        "suc_train": suc_train,
        "suc_holdout": suc_holdout,
    }


def entrenar(datos: dict, con_media: bool = True, params_media: dict | None = None) -> dict:
    ent = datos["entrenamiento"]
    X = ent[FEATURES].to_numpy(dtype=float)
    y = ent["y"].to_numpy()
    modelos: dict = {}
    for q, clave in ((0.5, "p50"), (0.9, "p90")):
        modelos[clave] = nuevo_modelo(q).fit(X, y)
        print(f"  cuantil {q}: {modelos[clave].n_iter_} iteraciones")
    modelos["media"] = None
    if con_media:
        modelos["media"] = nuevo_modelo_media(**(params_media or {})).fit(X, y)
        print(f"  media (Poisson): {modelos['media'].n_iter_} iteraciones")
    return modelos


def evaluar_modelos(modelos: dict, datos: dict) -> list[dict]:
    pol = cargar_umbrales()["politica_reabasto"]
    return [
        evaluar(nombre, datos[nombre], *predecir(modelos, datos[nombre]),
                factor_seguridad=pol["factor_seguridad"], esenciales=pol["categorias_esenciales"])
        for nombre in ("prueba_temporal", "sucursales_no_vistas")
    ]


def guardar(modelos: dict, meta: dict, version: str, models_dir: Path = MODELS_DIR) -> Path:
    models_dir.mkdir(parents=True, exist_ok=True)
    ruta = models_dir / f"demanda_ia_{version}.joblib"
    joblib.dump({**modelos, "meta": meta}, ruta, compress=3)
    ruta.with_suffix(".json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return ruta


def construir_meta(version: str, datos: dict, resultados: list[dict], con_media: bool, segundos: float,
                   params_media: dict | None = None) -> dict:
    return {
        "nombre": "DEMANDA-IA",
        "version": version,
        "algoritmo": "HistGradientBoostingRegressor: cuantiles P50/P90"
                     + (" + media con perdida Poisson" if con_media else ""),
        "features": FEATURES,
        "sklearn_version": sklearn.__version__,
        "entrenado_en": datetime.now(UTC).isoformat(timespec="seconds"),
        "periodo_entrenamiento": [str(INICIO), str(CORTE.date())],
        "periodo_prueba": [str((CORTE + pd.Timedelta(days=1)).date()), str(FIN)],
        "sucursales_entrenamiento": datos["suc_train"],
        "sucursales_holdout": datos["suc_holdout"],
        "hiperparametros": {"cuantiles": PARAMS_CUANTIL, "media": ({**PARAMS_MEDIA, **(params_media or {})} if con_media else None)},
        "evaluacion": resultados,
        "segundos_entrenamiento": round(segundos, 1),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Entrena DEMANDA-IA (sin compuertas; para eso usar demanda_ia.pipeline)")
    ap.add_argument("--version", default=MODEL_VERSION)
    ap.add_argument("--sin-media", action="store_true", help="Reproduce la arquitectura v1.0 (solo P50/P90)")
    args = ap.parse_args()
    t0 = time.time()
    datos = datos_entrenamiento()
    print(f"Filas: train={len(datos['entrenamiento']):,} test={len(datos['prueba_temporal']):,} "
          f"holdout={len(datos['sucursales_no_vistas']):,}")
    modelos = entrenar(datos, con_media=not args.sin_media)
    resultados = evaluar_modelos(modelos, datos)
    meta = construir_meta(args.version, datos, resultados, not args.sin_media, time.time() - t0)
    ruta = guardar(modelos, meta, args.version)
    REPORTS_DIR.mkdir(exist_ok=True)
    (REPORTS_DIR / "metricas.json").write_text(json.dumps(resultados, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Modelo guardado en {ruta}")


if __name__ == "__main__":
    main()
