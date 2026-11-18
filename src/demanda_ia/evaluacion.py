"""Métricas técnicas y de negocio con las que se decide si un modelo pasa a producción.

- Técnicas: MAE, RMSE, WAPE y sesgo (diario y semanal), cobertura del P90.
- Negocio: simulación (backtest) de la política de pedido semanal -> nivel de servicio
  (fill rate) y excedente de inventario, total y para medicamentos esenciales.
- Equidad (riesgo R02 de la Fase I): WAPE semanal por quintil de volumen de sucursal.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import CATEGORIAS


def metricas(y: np.ndarray, yhat: np.ndarray) -> dict[str, float]:
    err = yhat - y
    return {
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(np.sqrt(np.mean(err**2))),
        "wape_pct": float(100 * np.abs(err).sum() / max(y.sum(), 1e-9)),
        "sesgo_pct": float(100 * err.sum() / max(y.sum(), 1e-9)),
    }


def semanal(df: pd.DataFrame, p50: np.ndarray, p90: np.ndarray, media: np.ndarray | None) -> pd.DataFrame:
    """Agrega a semana x sucursal x SKU (horizonte real del pedido). Solo semanas completas."""
    d = df.assign(
        p50=p50, lag7=df["lag_7"].to_numpy(), margen2=(p90 - p50) ** 2,
        media=media if media is not None else p50, semana=df["fecha"].dt.to_period("W"),
    )
    g = d.groupby(["sucursal_id", "sku", "semana"]).agg(
        y=("y", "sum"), p50=("p50", "sum"), media=("media", "sum"), lag7=("lag7", "sum"),
        mu=("mu", "sum"), margen2=("margen2", "sum"), categoria=("categoria", "first"), dias=("y", "size"),
    )
    return g[g["dias"] == 7].reset_index()


def backtest_reabasto(sem: pd.DataFrame, factor: float, esenciales: list[str]) -> dict:
    """Pedido semanal = ceil(suma P50 + factor * raiz(suma (P90-P50)^2)), igual que /reabasto.
    Supuesto conservador: cada semana arranca sin existencia (no se arrastra sobrante)."""
    pedido = np.ceil(sem["p50"] + factor * np.sqrt(sem["margen2"]))
    regla = np.ceil(sem["lag7"] * 1.2)  # regla sin IA: semana anterior + 20 % de colchón
    ids_es = [CATEGORIAS.index(c) for c in esenciales]
    es = sem["categoria"].isin(ids_es).to_numpy()

    def kpis(q, m):
        y = sem["y"].to_numpy()[m]
        qq = np.asarray(q)[m]
        return {
            "fill_rate_pct": float(100 * np.minimum(y, qq).sum() / y.sum()),
            "excedente_pct": float(100 * np.maximum(qq - y, 0).sum() / y.sum()),
            "semanas_con_faltante_pct": float(100 * np.mean(qq < y)),
        }

    todo = np.ones(len(sem), dtype=bool)
    return {
        "factor_seguridad": factor,
        "semanas_simuladas": int(len(sem)),
        "modelo": {"total": kpis(pedido, todo), "esenciales": kpis(pedido, es), "resto": kpis(pedido, ~es)},
        "regla_lag7_mas_20pct": {"total": kpis(regla, todo), "esenciales": kpis(regla, es)},
    }


def equidad_por_quintil(sem: pd.DataFrame, columna: str = "media") -> dict:
    """WAPE semanal por quintil de volumen de sucursal. Razón = peor / mejor (meta <= 1.25)."""
    vol = sem.groupby("sucursal_id")["y"].sum()
    q = pd.qcut(vol.rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    d = sem.assign(quintil=sem["sucursal_id"].map(q))
    tabla = {}
    for k, g in d.groupby("quintil"):
        tabla[f"Q{k}"] = {
            "sucursales": int(g["sucursal_id"].nunique()),
            "venta_semanal_media": float(g["y"].mean()),
            "wape_semanal_pct": float(100 * np.abs(g[columna] - g["y"]).sum() / g["y"].sum()),
        }
    w = [v["wape_semanal_pct"] for v in tabla.values()]
    return {"pronostico": columna, "quintiles": tabla, "razon_peor_mejor": float(max(w) / min(w))}


def evaluar(nombre: str, df: pd.DataFrame, p50: np.ndarray, p90: np.ndarray, media: np.ndarray | None = None,
            factor_seguridad: float = 1.0, esenciales: list[str] | None = None) -> dict:
    """Evaluación completa. `media` es el pronóstico de demanda esperada (v1.1); si no hay, se usa el P50."""
    y = df["y"].to_numpy()
    esenciales = esenciales or ["cronicos", "sueros_antidiarreicos", "infantil"]
    res = {
        "conjunto": nombre,
        "filas": int(len(df)),
        "modelo_p50": metricas(y, p50),
        "baseline_lag7": metricas(y, df["lag_7"].to_numpy()),
        "baseline_media28": metricas(y, df["media_28"].to_numpy()),
        "oraculo_media_teorica": metricas(y, df["mu"].to_numpy()),
        "cobertura_p90_pct": float(100 * np.mean(y <= p90)),
    }
    if media is not None:
        res["modelo_media"] = metricas(y, media)
    sem = semanal(df, p50, p90, media)
    ys = sem["y"].to_numpy()
    res["semanal"] = {
        "modelo_p50": metricas(ys, sem["p50"].to_numpy()),
        "baseline_lag7": metricas(ys, sem["lag7"].to_numpy()),
        "oraculo_media_teorica": metricas(ys, sem["mu"].to_numpy()),
    }
    if media is not None:
        res["semanal"]["modelo_media"] = metricas(ys, sem["media"].to_numpy())
    pron = media if media is not None else p50
    res["por_categoria"] = {}
    for i, cat in enumerate(CATEGORIAS):
        m = df["categoria"].to_numpy() == i
        res["por_categoria"][cat] = {
            "wape_modelo_pct": metricas(y[m], pron[m])["wape_pct"],
            "wape_lag7_pct": metricas(y[m], df["lag_7"].to_numpy()[m])["wape_pct"],
            "cobertura_p90_pct": float(100 * np.mean(y[m] <= p90[m])),
        }
    res["reabasto"] = backtest_reabasto(sem, factor_seguridad, esenciales)
    res["equidad"] = equidad_por_quintil(sem, "media")
    return res


def pronostico_semanal(e: dict) -> dict:
    """Métricas semanales del pronóstico de demanda que publica el modelo (media si existe, si no P50)."""
    return e["semanal"].get("modelo_media", e["semanal"]["modelo_p50"])
