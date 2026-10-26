"""Pruebas del modelo: consistencia de variables, determinismo, desempeño y comportamiento."""
import json
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from demanda_ia.config import FEATURES, PRODUCTOS
from demanda_ia.data import simular_serie
from demanda_ia.features import es_festivo, fila_features, ventanas_desde_historial
from demanda_ia.model import ModeloDemanda
from demanda_ia.train import construir_dataset

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def modelo():
    return ModeloDemanda()


@pytest.fixture(scope="module")
def evaluacion():
    return {e["conjunto"]: e for e in json.loads((RAIZ / "reports" / "metricas.json").read_text(encoding="utf-8"))}


def test_variables_entrenamiento_igual_a_inferencia():
    """La fila que arma la API debe ser idéntica a la del dataset de entrenamiento."""
    df = construir_dataset(["SUC-007"])
    for _, fila in df.sample(25, random_state=1).iterrows():
        f = fila["fecha"].date()
        p = PRODUCTOS[fila["sku"]]
        api = fila_features("SUC-007", fila["sku"], f, fila["precio_relativo"] * p.precio_lista,
                            bool(fila["en_promocion"]), fila["lag_7"], fila["media_7"], fila["media_28"])
        np.testing.assert_allclose(api, fila[FEATURES].to_numpy(dtype=float), rtol=1e-9)


def test_ventanas_historial():
    h = list(range(1, 29))  # 1..28, el último es ayer
    lag7, m7, m28 = ventanas_desde_historial(h)
    assert lag7 == 22 and m7 == np.mean(range(22, 29)) and m28 == 14.5


def test_simulacion_determinista_entre_rangos():
    a = simular_serie("SUC-020", "SKU-0003", date(2025, 1, 1), date(2025, 3, 31))["ventas"]
    b = simular_serie("SUC-020", "SKU-0003", date(2025, 3, 1), date(2025, 3, 31))["ventas"]
    np.testing.assert_array_equal(a[-31:], b)


def test_festivos_mexico_2026():
    assert es_festivo(date(2026, 9, 16)) and es_festivo(date(2026, 2, 2)) and es_festivo(date(2026, 11, 16))
    assert not es_festivo(date(2026, 9, 15))


def test_inferencia_determinista(modelo):
    r = {"sucursal_id": "SUC-050", "sku": "SKU-0013", "fecha": date(2026, 5, 15), "lag_7": 8, "media_7": 7, "media_28": 7.5}
    assert modelo.predecir([r])[0].p50 == modelo.predecir([r])[0].p50


def test_modelo_supera_baselines(evaluacion):
    for conj in ("prueba_temporal", "sucursales_no_vistas"):
        e = evaluacion[conj]
        assert e["modelo_p50"]["wape_pct"] < e["baseline_lag7"]["wape_pct"]
        assert e["modelo_p50"]["wape_pct"] < e["baseline_media28"]["wape_pct"]
        assert e["semanal"]["modelo_p50"]["wape_pct"] < e["semanal"]["baseline_lag7"]["wape_pct"]


def test_cobertura_p90_calibrada(evaluacion):
    for e in evaluacion.values():
        assert 85 <= e["cobertura_p90_pct"] <= 93


def test_generaliza_a_sucursales_no_vistas(evaluacion):
    diff = abs(evaluacion["sucursales_no_vistas"]["modelo_p50"]["wape_pct"] - evaluacion["prueba_temporal"]["modelo_p50"]["wape_pct"])
    assert diff < 3


def _p50(modelo, **kw):
    base = {"sucursal_id": "SUC-001", "sku": "SKU-0005", "fecha": date(2026, 11, 4), "lag_7": 10, "media_7": 10, "media_28": 10}
    base.update(kw)
    return modelo.predecir([base])[0].p50


def test_promocion_aumenta_pronostico(modelo):
    assert _p50(modelo, en_promocion=True, precio=PRODUCTOS["SKU-0005"].precio_lista * 0.85) > _p50(modelo)


def test_festivo_reduce_pronostico(modelo):
    # 16 de noviembre de 2026 es lunes festivo (Revolución); se compara contra el lunes 9
    assert _p50(modelo, fecha=date(2026, 11, 16)) < _p50(modelo, fecha=date(2026, 11, 9))


def test_quincena_eleva_cronicos(modelo):
    kw = dict(sku="SKU-0012", lag_7=8, media_7=8, media_28=8)
    assert _p50(modelo, fecha=date(2026, 10, 15), **kw) > _p50(modelo, fecha=date(2026, 10, 8), **kw)


def test_antigripales_suben_en_invierno(modelo):
    assert _p50(modelo, fecha=date(2027, 1, 13)) > _p50(modelo, fecha=date(2026, 7, 15))
