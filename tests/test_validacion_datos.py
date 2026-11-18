"""Pruebas del contrato de datos: los datos buenos pasan y cada defecto se detecta."""
import numpy as np
import pytest

from demanda_ia.train import construir_dataset
from demanda_ia.validacion_datos import huella, resumen, validar


@pytest.fixture(scope="module")
def datos():
    return construir_dataset(["SUC-003", "SUC-004"]).iloc[:20000].copy()


def _fallas(df):
    return {r.regla for r in validar(df) if not r.paso and r.severidad == "critica"}


def test_datos_limpios_aprobados(datos):
    rep = resumen(validar(datos))
    assert rep["aprobado"] and rep["fallas_criticas"] == 0


def test_detecta_columna_faltante(datos):
    assert "esquema_columnas" in _fallas(datos.drop(columns=["lag_7"]))


def test_detecta_nulos(datos):
    d = datos.copy()
    d.loc[d.index[5], "media_28"] = np.nan
    assert "sin_nulos" in _fallas(d)


def test_detecta_duplicados(datos):
    import pandas as pd
    assert "llave_unica" in _fallas(pd.concat([datos, datos.iloc[:3]]))


def test_detecta_ventas_negativas(datos):
    d = datos.copy()
    d.loc[d.index[0], "y"] = -4
    assert "ventas_no_negativas" in _fallas(d)


def test_detecta_sku_desconocido(datos):
    d = datos.copy()
    d.loc[d.index[0], "sku"] = "SKU-9999"
    assert "catalogo_skus" in _fallas(d)


def test_detecta_precio_fuera_de_rango(datos):
    d = datos.copy()
    d.loc[d.index[0], "precio_relativo"] = 3.0
    assert "precio_relativo_rango" in _fallas(d)


def test_detecta_huecos_en_series(datos):
    d = datos.drop(index=datos.index[100:103])
    assert "series_continuas" in _fallas(d)


def test_huella_cambia_si_cambian_los_datos(datos):
    d = datos.copy()
    d.loc[d.index[0], "y"] += 1
    assert huella(datos) == huella(datos.copy()) != huella(d)
