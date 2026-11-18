"""Pruebas funcionales: cada endpoint responde con el contrato esperado."""


def test_salud(cliente):
    r = cliente.get("/api/v1/salud")
    assert r.status_code == 200
    assert r.json()["estado"] == "ok" and r.json()["modelo_cargado"] is True


def test_metadatos_modelo(cliente):
    meta = cliente.get("/api/v1/modelo").json()
    assert meta["nombre"] == "DEMANDA-IA"
    assert len(meta["features"]) == 15
    assert {e["conjunto"] for e in meta["evaluacion"]} == {"prueba_temporal", "sucursales_no_vistas"}


def test_catalogo_completo(cliente):
    c = cliente.get("/api/v1/catalogo").json()
    assert len(c["sucursales"]) == 140
    assert len(c["productos"]) == 30
    assert c["limites"]["max_lote"] == 1000


def test_historial_28_dias(cliente):
    r = cliente.get("/api/v1/historial", params={"sucursal_id": "SUC-010", "sku": "SKU-0012", "hasta": "2026-10-25"})
    assert r.status_code == 200
    d = r.json()
    assert len(d["ventas"]) == 28 and d["fechas"][-1] == "2026-10-25"


def test_pronostico_puntual(cliente, base):
    r = cliente.post("/api/v1/pronostico", json=base)
    assert r.status_code == 200
    d = r.json()
    assert 0 <= d["pronostico_p50"] <= d["pronostico_p90"]
    assert d["unidades_sugeridas"] >= d["pronostico_p90"]
    assert d["advertencias"] == []
    assert "X-Tiempo-Respuesta-ms" in r.headers


def test_pronostico_lote(cliente, base):
    registros = [dict(base, sku=f"SKU-{i:04d}") for i in range(1, 31)]
    r = cliente.post("/api/v1/pronostico/lote", json={"registros": registros})
    assert r.status_code == 200
    d = r.json()
    assert d["total"] == 30
    assert [x["sku"] for x in d["resultados"]] == [f"SKU-{i:04d}" for i in range(1, 31)]


def test_reabasto(cliente, historial):
    cuerpo = {"sucursal_id": "SUC-001", "sku": "SKU-0009", "fecha_inicio": "2026-11-02",
              "horizonte_dias": 7, "existencia_actual": 15, "historial_ventas": historial}
    r = cliente.post("/api/v1/reabasto", json=cuerpo)
    assert r.status_code == 200
    d = r.json()
    assert len(d["dias"]) == 7
    esperado = max(0, -(-(d["demanda_esperada"] + d["stock_seguridad"] - 15) // 1))
    assert d["pedido_sugerido"] == int(esperado)


def test_frontend_servido(cliente):
    r = cliente.get("/")
    assert r.status_code == 200 and "DEMANDA-IA" in r.text
    assert cliente.get("/app.js").status_code == 200


def test_openapi_documenta_endpoints(cliente):
    rutas = cliente.get("/openapi.json").json()["paths"]
    for ruta in ["/api/v1/pronostico", "/api/v1/pronostico/lote", "/api/v1/reabasto", "/api/v1/salud"]:
        assert ruta in rutas


def test_request_id_y_auditoria(cliente, base):
    r = cliente.post("/api/v1/pronostico", json=base, headers={"X-Request-ID": "prueba-auditoria-001"})
    assert r.headers["X-Request-ID"] == "prueba-auditoria-001"
    eventos = cliente.get("/api/v1/auditoria", params={"n": 50}).json()["eventos"]
    ev = next(e for e in eventos if e["id_peticion"] == "prueba-auditoria-001")
    assert ev["modelo_version"] == r.json()["modelo_version"] and len(ev["modelo_sha256"]) == 12
    assert ev["entrada"]["sku"] == base["sku"] and ev["salida"]["pronostico_p50"] == r.json()["pronostico_p50"]


def test_pronostico_incluye_media(cliente, base):
    d = cliente.post("/api/v1/pronostico", json=base).json()
    assert d["pronostico_media"] is not None and d["pronostico_media"] >= 0


def test_monitoreo_operativo(cliente, base):
    for _ in range(3):
        cliente.post("/api/v1/pronostico", json=base)
    m = cliente.get("/api/v1/monitoreo").json()
    assert m["pronosticos"] >= 3 and "/api/v1/pronostico" in m["latencia_por_ruta"]
    assert m["estado"] in {"ok", "alerta"}


def test_metricas_prometheus(cliente, base):
    cliente.post("/api/v1/pronostico", json=base)
    r = cliente.get("/metrics")
    assert r.status_code == 200
    assert "demanda_ia_predicciones_total" in r.text and "demanda_ia_latencia_segundos_bucket" in r.text


def test_salud_reporta_hash_del_modelo(cliente):
    d = cliente.get("/api/v1/salud").json()
    assert d["app_version"] == "1.1.0" and len(d["modelo_sha256"]) == 12
