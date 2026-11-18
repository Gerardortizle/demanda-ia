"""Registro de modelos (versionado) y funciones de monitoreo."""
import json
from datetime import date

import numpy as np
import pytest

from demanda_ia import registro
from demanda_ia.config import MODELS_DIR
from demanda_ia.monitoreo import aplicar_escenario, psi
from demanda_ia.train import construir_dataset


def test_registro_integro():
    """Cada artefacto campeón/archivado existe y su SHA-256 coincide (lo revisa también el CI)."""
    assert registro.verificar_integridad() == []


def test_registro_tiene_un_solo_campeon():
    reg = registro.leer()
    campeones = [v for v, m in reg["modelos"].items() if m["etapa"] == "campeon"]
    assert campeones == [reg["campeon"]]
    assert (MODELS_DIR / reg["modelos"][reg["campeon"]]["artefacto"]).exists()


def test_promocion_y_rollback(tmp_path):
    art = tmp_path / "m.joblib"
    art.write_bytes(b"modelo")
    ruta = tmp_path / "registro.json"
    registro.registrar("9.0.0", art, {"metricas": {}}, ruta=ruta)
    registro.registrar("9.1.0", art, {"metricas": {}}, ruta=ruta)
    registro.promover("9.0.0", "inicial", ruta=ruta)
    registro.promover("9.1.0", "mejor", ruta=ruta)
    reg = registro.promover("9.0.0", "rollback", ruta=ruta)
    assert reg["campeon"] == "9.0.0" and reg["modelos"]["9.1.0"]["etapa"] == "archivado"
    assert [e["accion"] for e in json.loads(ruta.read_text())["historial"]][-1] == "promocion"
    with pytest.raises(KeyError):
        registro.promover("0.0.1", "no existe", ruta=ruta)


def test_psi_detecta_deriva():
    rng = np.random.default_rng(1)
    ref = rng.normal(10, 2, 20000)
    assert psi(ref, rng.normal(10, 2, 20000)) < 0.02
    assert psi(ref, rng.normal(13, 2, 20000)) > 0.25


def test_psi_variable_binaria():
    ref = np.r_[np.zeros(9000), np.ones(1000)]
    assert psi(ref, ref) < 1e-6
    assert psi(ref, np.r_[np.zeros(5000), np.ones(5000)]) > 0.25


def test_escenario_alza_precios_mueve_precio_y_recalcula_ventanas():
    df = construir_dataset(["SUC-010"], date(2026, 6, 1), date(2026, 8, 31))
    out = aplicar_escenario(df, "alza_precios", date(2026, 8, 1))
    despues = out["fecha"] >= "2026-08-01"
    assert (out.loc[despues, "precio_relativo"] > 1.1).mean() > 0.8
    assert out.loc[despues, "y"].sum() < df.loc[df["fecha"] >= "2026-08-01", "y"].sum()
    assert out["lag_7"].notna().sum() > 0
