"""Construcción de variables. Se usa igual en entrenamiento y en la API
para evitar diferencias entre lo que el modelo vio y lo que recibe en producción."""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

import numpy as np

from .config import CATEGORIAS, ESTADOS, FEATURES, PRODUCTOS, SUCURSALES, TIPOS_SUCURSAL


def _n_esimo_lunes(anio: int, mes: int, n: int) -> date:
    d = date(anio, mes, 1)
    while d.weekday() != 0:
        d += timedelta(days=1)
    return d + timedelta(weeks=n - 1)


@lru_cache(maxsize=64)
def festivos(anio: int) -> frozenset[date]:
    """Días de descanso obligatorio en México (LFT art. 74) más 24 y 31 de diciembre."""
    return frozenset(
        {
            date(anio, 1, 1),
            _n_esimo_lunes(anio, 2, 1),
            _n_esimo_lunes(anio, 3, 3),
            date(anio, 5, 1),
            date(anio, 9, 16),
            _n_esimo_lunes(anio, 11, 3),
            date(anio, 12, 24),
            date(anio, 12, 25),
            date(anio, 12, 31),
        }
    )


def es_festivo(d: date) -> int:
    return int(d in festivos(d.year))


def es_quincena(d: date) -> int:
    return int(d.day in (1, 14, 15, 16, 29, 30, 31))


def fila_features(
    sucursal_id: str,
    sku: str,
    fecha: date,
    precio: float,
    en_promocion: bool,
    lag_7: float,
    media_7: float,
    media_28: float,
) -> list[float]:
    s = SUCURSALES[sucursal_id]
    p = PRODUCTOS[sku]
    fila = [
        CATEGORIAS.index(p.categoria),
        TIPOS_SUCURSAL.index(s.tipo),
        ESTADOS.index(s.estado),
        s.factor_tamano,
        p.demanda_base,
        precio / p.precio_lista,
        int(en_promocion),
        fecha.weekday(),
        fecha.month,
        fecha.day,
        es_quincena(fecha),
        es_festivo(fecha),
        float(lag_7),
        float(media_7),
        float(media_28),
    ]
    assert len(fila) == len(FEATURES)
    return fila


def ventanas_desde_historial(historial: list[float] | np.ndarray) -> tuple[float, float, float]:
    """Devuelve (lag_7, media_7, media_28) a partir de las últimas 28 ventas diarias.
    historial[-1] es el día inmediato anterior a la fecha a pronosticar."""
    h = np.asarray(historial, dtype=float)
    return float(h[-7]), float(h[-7:].mean()), float(h[-28:].mean())
