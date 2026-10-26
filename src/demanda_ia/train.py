"""Entrenamiento offline de DEMANDA-IA.

Uso:  python -m demanda_ia.train
Genera models/demanda_ia_v1.joblib (modelos P50 y P90) y reports/metricas.json.
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timezone

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor

from .config import (
    CATEGORIAS, ESTADOS, FEATURES, FEATURES_CATEGORICAS, METADATA_PATH, MODEL_PATH,
    MODEL_VERSION, PRODUCTOS, RAIZ, SEMILLA, SUCURSALES, TIPOS_SUCURSAL,
)
from .data import simular_serie
from .features import es_festivo, es_quincena

INICIO = date(2024, 1, 1)
FIN = date(2025, 12, 31)
CORTE = pd.Timestamp("2025-09-30")  # train <= corte < test
N_SUC_TRAIN = 40
N_SUC_HOLDOUT = 10


def elegir_sucursales() -> tuple[list[str], list[str]]:
    rng = np.random.default_rng(SEMILLA)
    ids = sorted(SUCURSALES)
    perm = rng.permutation(ids)
    return sorted(perm[:N_SUC_TRAIN]), sorted(perm[N_SUC_TRAIN:N_SUC_TRAIN + N_SUC_HOLDOUT])


def construir_dataset(sucursales: list[str]) -> pd.DataFrame:
    bloques = []
    for sid in sucursales:
        s = SUCURSALES[sid]
        for sku, p in PRODUCTOS.items():
            serie = simular_serie(sid, sku, INICIO, FIN)
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


def metricas(y: np.ndarray, yhat: np.ndarray) -> dict[str, float]:
    err = yhat - y
    return {
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(np.sqrt(np.mean(err**2))),
        "wape_pct": float(100 * np.abs(err).sum() / max(y.sum(), 1e-9)),
        "sesgo_pct": float(100 * err.sum() / max(y.sum(), 1e-9)),
    }


def nuevo_modelo(cuantil: float) -> HistGradientBoostingRegressor:
    mask = np.zeros(len(FEATURES), dtype=bool)
    mask[FEATURES_CATEGORICAS] = True
    return HistGradientBoostingRegressor(
        loss="quantile", quantile=cuantil, learning_rate=0.08, max_iter=300,
        max_leaf_nodes=63, min_samples_leaf=40, l2_regularization=1.0,
        categorical_features=mask, early_stopping=True, validation_fraction=0.1,
        n_iter_no_change=20, random_state=SEMILLA,
    )


def evaluar(nombre: str, df: pd.DataFrame, p50: np.ndarray, p90: np.ndarray) -> dict:
    y = df["y"].to_numpy()
    res = {
        "conjunto": nombre,
        "filas": int(len(df)),
        "modelo_p50": metricas(y, p50),
        "baseline_lag7": metricas(y, df["lag_7"].to_numpy()),
        "baseline_media28": metricas(y, df["media_28"].to_numpy()),
        "oraculo_media_teorica": metricas(y, df["mu"].to_numpy()),
        "cobertura_p90_pct": float(100 * np.mean(y <= p90)),
        "semanal": {},
        "por_categoria": {},
    }
    # Error agregado por semana y par sucursal-SKU (horizonte real del reabasto)
    sem = df.assign(p50=p50, lag7=df["lag_7"].to_numpy()).assign(
        semana=df["fecha"].dt.to_period("W")
    ).groupby(["sucursal_id", "sku", "semana"])[["y", "p50", "lag7", "mu"]].sum()
    res["semanal"] = {
        "modelo_p50": metricas(sem["y"].to_numpy(), sem["p50"].to_numpy()),
        "baseline_lag7": metricas(sem["y"].to_numpy(), sem["lag7"].to_numpy()),
        "oraculo_media_teorica": metricas(sem["y"].to_numpy(), sem["mu"].to_numpy()),
    }
    for i, cat in enumerate(CATEGORIAS):
        m = df["categoria"].to_numpy() == i
        res["por_categoria"][cat] = {
            "wape_modelo_pct": metricas(y[m], p50[m])["wape_pct"],
            "wape_lag7_pct": metricas(y[m], df["lag_7"].to_numpy()[m])["wape_pct"],
            "cobertura_p90_pct": float(100 * np.mean(y[m] <= p90[m])),
        }
    return res


def main() -> None:
    t0 = time.time()
    suc_train, suc_holdout = elegir_sucursales()
    print(f"Sucursales entrenamiento: {len(suc_train)} | holdout: {len(suc_holdout)}")
    df = construir_dataset(suc_train)
    df_hold = construir_dataset(suc_holdout)
    entrenamiento = df[df["fecha"] <= CORTE]
    prueba = df[df["fecha"] > CORTE]
    holdout = df_hold[df_hold["fecha"] > CORTE]
    print(f"Filas: train={len(entrenamiento):,} test={len(prueba):,} holdout={len(holdout):,}")

    X = entrenamiento[FEATURES].to_numpy(dtype=float)
    y = entrenamiento["y"].to_numpy()
    modelos = {}
    for q in (0.5, 0.9):
        m = nuevo_modelo(q)
        m.fit(X, y)
        modelos[q] = m
        print(f"  cuantil {q}: {m.n_iter_} iteraciones")

    def pred(d):
        Xd = d[FEATURES].to_numpy(dtype=float)
        p50 = np.clip(modelos[0.5].predict(Xd), 0, None)
        p90 = np.maximum(np.clip(modelos[0.9].predict(Xd), 0, None), p50)
        return p50, p90

    resultados = [evaluar("prueba_temporal", prueba, *pred(prueba)),
                  evaluar("sucursales_no_vistas", holdout, *pred(holdout))]

    # Muestra de predicciones para gráficas del documento de validación
    p50, p90 = pred(prueba)
    muestra = prueba.assign(p50=p50, p90=p90)[["sucursal_id", "sku", "fecha", "y", "p50", "p90", "lag_7", "media_28", "mu", "categoria", "en_promocion", "es_festivo"]]
    (RAIZ / "reports").mkdir(exist_ok=True)
    muestra = muestra.sample(n=min(30000, len(muestra)), random_state=SEMILLA)
    muestra.to_csv(RAIZ / "reports" / "predicciones_prueba.csv.gz", index=False, compression="gzip")

    meta = {
        "nombre": "DEMANDA-IA",
        "version": MODEL_VERSION,
        "algoritmo": "HistGradientBoostingRegressor (regresion por cuantiles P50 y P90)",
        "features": FEATURES,
        "sklearn_version": sklearn.__version__,
        "entrenado_en": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "periodo_entrenamiento": [str(INICIO), str(CORTE.date())],
        "periodo_prueba": [str((CORTE + pd.Timedelta(days=1)).date()), str(FIN)],
        "sucursales_entrenamiento": suc_train,
        "sucursales_holdout": suc_holdout,
        "evaluacion": resultados,
        "segundos_entrenamiento": round(time.time() - t0, 1),
    }
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"p50": modelos[0.5], "p90": modelos[0.9], "meta": meta}, MODEL_PATH, compress=3)
    METADATA_PATH.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    (RAIZ / "reports" / "metricas.json").write_text(json.dumps(resultados, indent=2, ensure_ascii=False), encoding="utf-8")
    for r in resultados:
        print(f"[{r['conjunto']}] WAPE modelo={r['modelo_p50']['wape_pct']:.1f}% "
              f"lag7={r['baseline_lag7']['wape_pct']:.1f}% media28={r['baseline_media28']['wape_pct']:.1f}% "
              f"oraculo={r['oraculo_media_teorica']['wape_pct']:.1f}% cobertura P90={r['cobertura_p90_pct']:.1f}% | "
              f"semanal modelo={r['semanal']['modelo_p50']['wape_pct']:.1f}% oraculo={r['semanal']['oraculo_media_teorica']['wape_pct']:.1f}%")
    print(f"Modelo guardado en {MODEL_PATH} ({meta['segundos_entrenamiento']} s)")


if __name__ == "__main__":
    main()
