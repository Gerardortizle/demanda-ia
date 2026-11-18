"""Pruebas automáticas de datos (data contracts) antes de entrenar o monitorear.

Cada regla devuelve un resultado con nombre, severidad, si pasó y el detalle.
Severidad "critica" detiene el pipeline; "advertencia" queda en el reporte.
En producción el DataFrame vendría de la extracción nocturna del ERP; aquí sale del simulador.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .config import CATEGORIAS, ESTADOS, FEATURES, PRODUCTOS, SUCURSALES, TIPOS_SUCURSAL

COLUMNAS_REQUERIDAS = ["sucursal_id", "sku", "fecha", "y", *FEATURES]


@dataclass
class Resultado:
    regla: str
    severidad: str  # "critica" | "advertencia"
    paso: bool
    detalle: str


def _r(regla, severidad, paso, detalle) -> Resultado:
    return Resultado(regla, severidad, bool(paso), detalle)


def validar(df: pd.DataFrame, tasa_ceros_max: float = 0.35) -> list[Resultado]:
    res: list[Resultado] = []
    faltan = [c for c in COLUMNAS_REQUERIDAS if c not in df.columns]
    res.append(_r("esquema_columnas", "critica", not faltan, f"faltan: {faltan}" if faltan else "15 variables + llaves"))
    if faltan:
        return res

    n = len(df)
    res.append(_r("no_vacio", "critica", n > 0, f"{n:,} filas"))
    nulos = int(df[COLUMNAS_REQUERIDAS].isna().sum().sum())
    res.append(_r("sin_nulos", "critica", nulos == 0, f"{nulos} valores nulos"))

    dup = int(df.duplicated(["sucursal_id", "sku", "fecha"]).sum())
    res.append(_r("llave_unica", "critica", dup == 0, f"{dup} filas duplicadas sucursal-sku-fecha"))

    neg = int((df["y"] < 0).sum())
    res.append(_r("ventas_no_negativas", "critica", neg == 0, f"{neg} ventas negativas"))

    suc_desc = sorted(set(df["sucursal_id"]) - set(SUCURSALES))
    sku_desc = sorted(set(df["sku"]) - set(PRODUCTOS))
    res.append(_r("catalogo_sucursales", "critica", not suc_desc, f"desconocidas: {suc_desc[:5]}"))
    res.append(_r("catalogo_skus", "critica", not sku_desc, f"desconocidos: {sku_desc[:5]}"))

    codigos_ok = (
        df["categoria"].between(0, len(CATEGORIAS) - 1).all()
        and df["tipo_sucursal"].between(0, len(TIPOS_SUCURSAL) - 1).all()
        and df["estado"].between(0, len(ESTADOS) - 1).all()
    )
    res.append(_r("codigos_categoricos", "critica", codigos_ok, "categoria, tipo_sucursal y estado dentro del catalogo"))

    rel = df["precio_relativo"]
    fuera = float(((rel < 0.5) | (rel > 1.5)).mean())
    res.append(_r("precio_relativo_rango", "critica", fuera == 0, f"{fuera:.2%} fuera de [0.5, 1.5]"))

    cal_ok = (df["dia_semana"].between(0, 6).all() and df["mes"].between(1, 12).all()
              and df["dia_mes"].between(1, 31).all())
    res.append(_r("calendario_valido", "critica", cal_ok, "dia_semana, mes y dia_mes en rango"))

    ventanas = df[["lag_7", "media_7", "media_28"]]
    res.append(_r("ventanas_no_negativas", "critica", bool((ventanas >= 0).all().all()), "lag_7, media_7, media_28 >= 0"))

    # Continuidad: cada serie debe tener un registro por día (huecos = falla de extracción)
    span = df.groupby(["sucursal_id", "sku"])["fecha"].agg(["min", "max", "count"])
    esperados = (span["max"] - span["min"]).dt.days + 1
    huecos = int((esperados - span["count"]).clip(lower=0).sum())
    res.append(_r("series_continuas", "critica", huecos == 0, f"{huecos} dias faltantes en {len(span)} series"))

    # Advertencias: patrones que no detienen el proceso pero deben revisarse
    tasa_ceros = float((df["y"] == 0).mean())
    res.append(_r("tasa_dias_sin_venta", "advertencia", tasa_ceros <= tasa_ceros_max,
                  f"{tasa_ceros:.1%} de dias con venta cero (limite {tasa_ceros_max:.0%}); posible desabasto (R01)"))
    p999 = float(np.percentile(df["y"], 99.9))
    extremos = int((df["y"] > 10 * max(p999, 1)).sum())
    res.append(_r("ventas_extremas", "advertencia", extremos == 0, f"{extremos} ventas > 10x el percentil 99.9 ({p999:.0f})"))
    return res


def resumen(resultados: list[Resultado]) -> dict:
    criticas = [r for r in resultados if not r.paso and r.severidad == "critica"]
    advert = [r for r in resultados if not r.paso and r.severidad == "advertencia"]
    return {
        "aprobado": not criticas,
        "reglas": len(resultados),
        "fallas_criticas": len(criticas),
        "advertencias": len(advert),
        "detalle": [asdict(r) for r in resultados],
    }


def huella(df: pd.DataFrame) -> str:
    """Huella SHA-256 del contenido (llaves, objetivo y variables) para trazar qué datos entrenaron cada modelo."""
    columnas = ["sucursal_id", "sku", "fecha", "y", *FEATURES]
    h = pd.util.hash_pandas_object(df[columnas], index=False).to_numpy()
    return hashlib.sha256(h.tobytes()).hexdigest()
