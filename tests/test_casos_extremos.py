"""Casos extremos y entradas inválidas: la API debe rechazar con 422 o responder con advertencias,
nunca con 500 ni con pronósticos negativos."""
import random

import pytest


@pytest.mark.parametrize("cambio,campo", [
    ({"sucursal_id": "SUC-999"}, "sucursal_id"),
    ({"sku": "SKU-9999"}, "sku"),
    ({"lag_7": -1}, "lag_7"),
    ({"media_28": "muchas"}, "media_28"),
    ({"fecha": "2031-01-01"}, "fecha"),
    ({"fecha": "2026-02-30"}, "fecha"),
    ({"precio": 0}, "precio"),
    ({"campo_extra": 1}, "campo_extra"),
])
def test_entradas_invalidas_dan_422(cliente, base, cambio, campo):
    r = cliente.post("/api/v1/pronostico", json={**base, **cambio})
    assert r.status_code == 422
    assert campo in str(r.json()["detail"])


def test_campo_faltante(cliente, base):
    base.pop("media_7")
    assert cliente.post("/api/v1/pronostico", json=base).status_code == 422


def test_json_malformado(cliente):
    r = cliente.post("/api/v1/pronostico", content=b"{sucursal: SUC-001", headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_ids_en_minusculas_se_normalizan(cliente, base):
    r = cliente.post("/api/v1/pronostico", json={**base, "sucursal_id": " suc-001 ", "sku": "sku-0001"})
    assert r.status_code == 200 and r.json()["sucursal_id"] == "SUC-001"


def test_historial_en_ceros(cliente, base):
    r = cliente.post("/api/v1/pronostico", json={**base, "lag_7": 0, "media_7": 0, "media_28": 0})
    d = r.json()
    assert r.status_code == 200 and d["pronostico_p50"] >= 0
    assert any("ceros" in a for a in d["advertencias"])


def test_valores_atipicos_altos(cliente, base):
    r = cliente.post("/api/v1/pronostico", json={**base, "lag_7": 5000, "media_7": 4800, "media_28": 4000})
    d = r.json()
    assert r.status_code == 200
    assert any("por encima" in a for a in d["advertencias"])
    assert d["pronostico_p90"] < 1e6


@pytest.mark.parametrize("precio", [1.0, 500.0])
def test_precio_fuera_de_rango_se_acota(cliente, base, precio):
    d = cliente.post("/api/v1/pronostico", json={**base, "precio": precio}).json()
    assert any("Precio relativo" in a for a in d["advertencias"])


def test_lote_vacio_y_lote_excedido(cliente, base):
    assert cliente.post("/api/v1/pronostico/lote", json={"registros": []}).status_code == 422
    assert cliente.post("/api/v1/pronostico/lote", json={"registros": [base] * 1001}).status_code == 422


def test_lote_con_un_registro_invalido_rechaza_todo(cliente, base):
    r = cliente.post("/api/v1/pronostico/lote", json={"registros": [base, {**base, "sku": "X"}]})
    assert r.status_code == 422
    assert "registros" in str(r.json()["detail"])


@pytest.mark.parametrize("horizonte", [0, 15])
def test_horizonte_fuera_de_limite(cliente, historial, horizonte):
    cuerpo = {"sucursal_id": "SUC-001", "sku": "SKU-0009", "fecha_inicio": "2026-11-02",
              "horizonte_dias": horizonte, "existencia_actual": 0, "historial_ventas": historial}
    assert cliente.post("/api/v1/reabasto", json=cuerpo).status_code == 422


def test_historial_corto_o_negativo(cliente, historial):
    cuerpo = {"sucursal_id": "SUC-001", "sku": "SKU-0009", "fecha_inicio": "2026-11-02",
              "existencia_actual": 0, "historial_ventas": historial[:27]}
    assert cliente.post("/api/v1/reabasto", json=cuerpo).status_code == 422
    cuerpo["historial_ventas"] = historial[:27] + [-3]
    assert cliente.post("/api/v1/reabasto", json=cuerpo).status_code == 422


def test_existencia_suficiente_pedido_cero(cliente, historial):
    cuerpo = {"sucursal_id": "SUC-001", "sku": "SKU-0009", "fecha_inicio": "2026-11-02",
              "horizonte_dias": 14, "existencia_actual": 100000, "historial_ventas": historial}
    assert cliente.post("/api/v1/reabasto", json=cuerpo).json()["pedido_sugerido"] == 0


def test_horizonte_maximo_14_dias(cliente, historial):
    cuerpo = {"sucursal_id": "SUC-001", "sku": "SKU-0009", "fecha_inicio": "2026-12-20",
              "horizonte_dias": 14, "existencia_actual": 0, "historial_ventas": historial}
    d = cliente.post("/api/v1/reabasto", json=cuerpo).json()
    assert len(d["dias"]) == 14 and d["dias"][-1]["fecha"] == "2027-01-02"


def test_historial_fuera_del_periodo_simulado(cliente):
    r = cliente.get("/api/v1/historial", params={"sucursal_id": "SUC-001", "sku": "SKU-0001", "hasta": "2028-03-01"})
    assert r.status_code == 422


def test_propiedad_p90_mayor_igual_p50_y_no_negativo(cliente):
    """2 000 entradas aleatorias válidas: nunca negativo y siempre P90 >= P50."""
    rnd = random.Random(7)
    registros = []
    for _ in range(2000):
        m28 = rnd.uniform(0, 80)
        registros.append({
            "sucursal_id": f"SUC-{rnd.randint(1, 140):03d}", "sku": f"SKU-{rnd.randint(1, 30):04d}",
            "fecha": f"2026-{rnd.randint(1, 12):02d}-{rnd.randint(1, 28):02d}",
            "en_promocion": rnd.random() < 0.2, "lag_7": rnd.uniform(0, 100),
            "media_7": rnd.uniform(0, 90), "media_28": m28,
        })
    for i in range(0, 2000, 1000):
        res = cliente.post("/api/v1/pronostico/lote", json={"registros": registros[i:i + 1000]}).json()["resultados"]
        assert all(0 <= x["pronostico_p50"] <= x["pronostico_p90"] for x in res)
