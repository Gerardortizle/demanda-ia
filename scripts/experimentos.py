"""Búsqueda de hiperparámetros del modelo de media (Poisson) con validación temporal interna.

    PYTHONPATH=src python scripts/experimentos.py [--mlflow]

Para no elegir con los datos de prueba, se separa el propio periodo de entrenamiento:
  - ajuste:     2024-01-01 a 2025-06-30
  - validación: 2025-07-01 a 2025-09-30
La prueba temporal (oct-dic 2025) y las sucursales no vistas no se tocan aquí.
Resultado: reports/experimentos.json (y una corrida por configuración en MLflow).
"""
from __future__ import annotations

import argparse
import json
import os
import time

import numpy as np
import pandas as pd

from demanda_ia.config import FEATURES, REPORTS_DIR
from demanda_ia.evaluacion import metricas
from demanda_ia.train import construir_dataset, elegir_sucursales, nuevo_modelo_media

GRID = [
    {"learning_rate": 0.08, "max_iter": 300, "max_leaf_nodes": 63, "min_samples_leaf": 40},   # igual a v1.0
    {"learning_rate": 0.10, "max_iter": 600, "max_leaf_nodes": 63, "min_samples_leaf": 40},
    {"learning_rate": 0.10, "max_iter": 600, "max_leaf_nodes": 31, "min_samples_leaf": 80},
    {"learning_rate": 0.05, "max_iter": 1000, "max_leaf_nodes": 127, "min_samples_leaf": 40},
]
FIN_AJUSTE = pd.Timestamp("2025-06-30")
FIN_VALID = pd.Timestamp("2025-09-30")


def semanal_wape(d: pd.DataFrame, pred: np.ndarray) -> dict:
    g = d.assign(p=pred, semana=d["fecha"].dt.to_period("W")).groupby(["sucursal_id", "sku", "semana"]).agg(
        y=("y", "sum"), p=("p", "sum"), n=("y", "size"))
    g = g[g["n"] == 7]
    return metricas(g["y"].to_numpy(), g["p"].to_numpy())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mlflow", action="store_true")
    args = ap.parse_args()
    suc_train, _ = elegir_sucursales()
    df = construir_dataset(suc_train)
    aj, va = df[df["fecha"] <= FIN_AJUSTE], df[(df["fecha"] > FIN_AJUSTE) & (df["fecha"] <= FIN_VALID)]
    print(f"ajuste={len(aj):,} validacion={len(va):,}")
    mlf = None
    if args.mlflow:
        import mlflow as mlf
        mlf.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", f"sqlite:///{(REPORTS_DIR.parent / 'mlflow.db').as_posix()}"))
        mlf.set_experiment("demanda-ia-hiperparametros")
    filas = []
    for i, params in enumerate(GRID, 1):
        t0 = time.time()
        m = nuevo_modelo_media(**params).fit(aj[FEATURES].to_numpy(float), aj["y"].to_numpy())
        p = np.clip(m.predict(va[FEATURES].to_numpy(float)), 0, None)
        sem = semanal_wape(va, p)
        fila = {"config": i, **params, "iteraciones": int(m.n_iter_), "segundos": round(time.time() - t0, 1),
                "wape_diario_pct": metricas(va["y"].to_numpy(), p)["wape_pct"],
                "wape_semanal_pct": sem["wape_pct"], "sesgo_semanal_pct": sem["sesgo_pct"]}
        filas.append(fila)
        print(json.dumps(fila))
        if mlf:
            with mlf.start_run(run_name=f"media-config-{i}"):
                mlf.log_params(params)
                mlf.log_metrics({k: fila[k] for k in ("wape_diario_pct", "wape_semanal_pct", "sesgo_semanal_pct", "iteraciones", "segundos")})
    mejor = min(filas, key=lambda f: f["wape_semanal_pct"])
    out = {"criterio": "menor WAPE semanal en validacion interna (jul-sep 2025)", "mejor_config": mejor["config"], "resultados": filas}
    REPORTS_DIR.mkdir(exist_ok=True)
    (REPORTS_DIR / "experimentos.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Mejor configuracion: {mejor}")


if __name__ == "__main__":
    main()
