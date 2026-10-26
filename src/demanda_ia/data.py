"""Simulador de ventas diarias por sucursal y SKU.

Los datos reales del ERP de Farmacias Occidente Salud no están disponibles para el
proyecto académico, así que se genera un histórico sintético con los patrones que
se describieron en la Fase I: estacionalidad por categoría, efecto quincena, días
festivos, promociones, elasticidad al precio, crecimiento anual y quiebres de stock.
"""
from __future__ import annotations

import hashlib
from datetime import date, timedelta

import numpy as np

from .config import PRODUCTOS, SUCURSALES
from .features import es_festivo, es_quincena

# (amplitud, mes pico) de la estacionalidad anual por categoría
ESTACIONALIDAD = {
    "analgesicos": (0.10, 1),
    "antigripales": (0.60, 1),
    "sueros_antidiarreicos": (0.45, 5),
    "cronicos": (0.0, 1),
    "vitaminas": (0.15, 1),
    "dermocosmetica": (0.25, 4),
    "infantil": (0.20, 1),
}
EFECTO_DIA_SEMANA = np.array([1.05, 0.97, 0.95, 0.97, 1.03, 1.12, 0.91])  # lun..dom
FECHA_ORIGEN = date(2024, 1, 1)
FECHA_FIN_SIM = date(2027, 12, 31)


_CALENDARIO: dict | None = None


def _calendario() -> dict[str, np.ndarray | list]:
    """Variables de calendario del periodo simulado (se calculan una sola vez)."""
    global _CALENDARIO
    if _CALENDARIO is None:
        n = (FECHA_FIN_SIM - FECHA_ORIGEN).days + 1
        fechas = [FECHA_ORIGEN + timedelta(days=i) for i in range(n)]
        _CALENDARIO = {
            "fechas": fechas,
            "mes": np.array([f.month for f in fechas]),
            "dow": np.array([f.weekday() for f in fechas]),
            "quincena": np.array([es_quincena(f) for f in fechas]),
            "festivo": np.array([es_festivo(f) for f in fechas]),
            "t_anios": np.array([(f - FECHA_ORIGEN).days / 365.25 for f in fechas]),
        }
    return _CALENDARIO


def _semilla(sucursal_id: str, sku: str) -> int:
    h = hashlib.sha256(f"{sucursal_id}|{sku}".encode()).hexdigest()
    return int(h[:8], 16)


def simular_serie(sucursal_id: str, sku: str, inicio: date, fin: date) -> dict[str, np.ndarray]:
    """Serie diaria determinista para un par sucursal-SKU entre inicio y fin (inclusive).
    Siempre se simula el periodo completo FECHA_ORIGEN..FECHA_FIN_SIM y luego se recorta,
    así la misma fecha da el mismo valor sin importar el rango solicitado."""
    s = SUCURSALES[sucursal_id]
    p = PRODUCTOS[sku]
    if inicio < FECHA_ORIGEN or fin > FECHA_FIN_SIM or fin < inicio:
        raise ValueError(
            f"Rango invalido: la simulacion cubre {FECHA_ORIGEN.isoformat()} a {FECHA_FIN_SIM.isoformat()}"
        )
    origen = FECHA_ORIGEN
    n = (FECHA_FIN_SIM - origen).days + 1
    rng = np.random.default_rng(_semilla(sucursal_id, sku))

    cal = _calendario()
    fechas, mes, dow = cal["fechas"], cal["mes"], cal["dow"]
    quincena, festivo, t_anios = cal["quincena"], cal["festivo"], cal["t_anios"]

    amp, pico = ESTACIONALIDAD[p.categoria]
    estacional = 1 + amp * np.cos(2 * np.pi * (mes - pico) / 12)

    efecto_quincena = np.where(quincena == 1, 1.30 if p.categoria == "cronicos" else 1.10, 1.0)
    efecto_festivo = np.where(festivo == 1, 0.75, 1.0)
    efecto_tipo = {"urbana": 1.0, "periferia": 0.85, "hospitalaria": 1.25}[s.tipo]
    if s.tipo == "hospitalaria" and p.categoria == "cronicos":
        efecto_tipo *= 1.2

    # Promociones en bloques de 7 días (~8 % de los días)
    promo = np.zeros(n, dtype=int)
    for inicio_bloque in np.where(rng.random(n) < 0.012)[0]:
        promo[inicio_bloque : inicio_bloque + 7] = 1
    descuento = rng.uniform(0.80, 0.92, size=n)
    precio = np.where(promo == 1, p.precio_lista * descuento, p.precio_lista)
    precio = np.round(precio, 2)
    elasticidad = (precio / p.precio_lista) ** -1.5
    efecto_promo = np.where(promo == 1, 1.25, 1.0)

    crecimiento = 1.05 ** t_anios

    mu = (
        p.demanda_base
        * s.factor_tamano
        * efecto_tipo
        * estacional
        * EFECTO_DIA_SEMANA[dow]
        * efecto_quincena
        * efecto_festivo
        * efecto_promo
        * elasticidad
        * crecimiento
    )
    # Binomial negativa (sobredispersión típica de ventas al menudeo)
    r = 5.0
    ventas = rng.negative_binomial(r, r / (r + mu)).astype(float)
    # Quiebres de stock: ~1.5 % de los días sin venta registrada
    ventas[rng.random(n) < 0.015] = 0.0

    a = (inicio - origen).days
    b = (fin - origen).days + 1
    return {
        "fecha": np.array(fechas[a:b]),
        "ventas": ventas[a:b],
        "precio": precio[a:b],
        "promo": promo[a:b],
        "esperado": mu[a:b],  # media teórica, solo para medir el piso de error
    }
