"""Backend REST de DEMANDA-IA (FastAPI).

Endpoints principales (prefijo /api/v1):
  GET  /salud                 estado del servicio y del modelo
  GET  /modelo                metadatos y métricas del modelo cargado
  GET  /catalogo              sucursales y SKUs válidos
  GET  /historial             historial simulado de 28 días (solo demostración)
  POST /pronostico            pronóstico de un día para un par sucursal-SKU
  POST /pronostico/lote       hasta MAX_LOTE pronósticos en una llamada (corrida nocturna)
  POST /reabasto              pronóstico de 1 a 14 días y pedido sugerido
La interfaz web se sirve en "/" y la documentación OpenAPI en /docs.
"""
from __future__ import annotations

import logging
import math
import os
import time
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import MAX_HORIZONTE, MAX_LOTE, PRODUCTOS, RAIZ, SUCURSALES, VENTANA_HISTORIAL
from .data import simular_serie
from .model import ModeloDemanda
from .schemas import (
    RespuestaLote, RespuestaPronostico, RespuestaReabasto, SolicitudLote,
    SolicitudPronostico, SolicitudReabasto,
)

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("demanda_ia")
ESTADO: dict = {}


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    t0 = time.perf_counter()
    ESTADO["modelo"] = ModeloDemanda()
    ESTADO["inicio"] = time.time()
    log.info("Modelo %s cargado en %.2f s", ESTADO["modelo"].version, time.perf_counter() - t0)
    yield
    ESTADO.clear()


app = FastAPI(
    title="DEMANDA-IA API",
    description="Pronóstico de demanda diaria por SKU y sucursal para Farmacias Occidente Salud.",
    version="1.0.0",
    lifespan=ciclo_de_vida,
)
origenes = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origenes, allow_methods=["GET", "POST"], allow_headers=["*"])


@app.middleware("http")
async def medir_latencia(request: Request, call_next):
    t0 = time.perf_counter()
    respuesta = await call_next(request)
    ms = (time.perf_counter() - t0) * 1000
    respuesta.headers["X-Tiempo-Respuesta-ms"] = f"{ms:.1f}"
    if request.url.path.startswith("/api"):
        log.info("%s %s -> %s (%.1f ms)", request.method, request.url.path, respuesta.status_code, ms)
    return respuesta


@app.exception_handler(Exception)
async def error_no_controlado(request: Request, exc: Exception):
    log.exception("Error no controlado en %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Error interno. Revise los logs del contenedor."})


def _modelo() -> ModeloDemanda:
    m = ESTADO.get("modelo")
    if m is None:
        raise HTTPException(status_code=503, detail="Modelo no cargado")
    return m


def _respuesta(req: SolicitudPronostico, p50: float, p90: float, avisos: list[str]) -> RespuestaPronostico:
    return RespuestaPronostico(
        sucursal_id=req.sucursal_id, sku=req.sku, fecha=req.fecha,
        pronostico_p50=round(p50, 2), pronostico_p90=round(p90, 2),
        unidades_sugeridas=math.ceil(p90), advertencias=avisos, modelo_version=_modelo().version,
    )


@app.get("/api/v1/salud", tags=["operacion"])
def salud():
    m = ESTADO.get("modelo")
    return {
        "estado": "ok" if m else "degradado",
        "modelo_cargado": m is not None,
        "modelo_version": m.version if m else None,
        "segundos_activo": round(time.time() - ESTADO.get("inicio", time.time()), 1),
    }


@app.get("/api/v1/modelo", tags=["operacion"])
def info_modelo():
    meta = _modelo().meta
    return {k: meta[k] for k in ("nombre", "version", "algoritmo", "features", "sklearn_version",
                                  "entrenado_en", "periodo_entrenamiento", "periodo_prueba", "evaluacion")}


@app.get("/api/v1/catalogo", tags=["catalogo"])
def catalogo():
    return {
        "sucursales": [s.__dict__ for s in SUCURSALES.values()],
        "productos": [p.__dict__ for p in PRODUCTOS.values()],
        "limites": {"max_lote": MAX_LOTE, "max_horizonte_dias": MAX_HORIZONTE, "ventana_historial": VENTANA_HISTORIAL},
    }


@app.get("/api/v1/historial", tags=["catalogo"])
def historial(
    sucursal_id: str = Query(examples=["SUC-001"]),
    sku: str = Query(examples=["SKU-0001"]),
    hasta: date = Query(description="Último día del historial (incluido)"),
    dias: int = Query(default=VENTANA_HISTORIAL, ge=VENTANA_HISTORIAL, le=180),
):
    """Historial simulado para la demostración. En producción este dato sale del ERP."""
    sucursal_id, sku = sucursal_id.strip().upper(), sku.strip().upper()
    if sucursal_id not in SUCURSALES or sku not in PRODUCTOS:
        raise HTTPException(status_code=404, detail="Sucursal o SKU no encontrado")
    try:
        serie = simular_serie(sucursal_id, sku, hasta - timedelta(days=dias - 1), hasta)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {
        "sucursal_id": sucursal_id, "sku": sku, "origen": "simulado",
        "fechas": [f.isoformat() for f in serie["fecha"]],
        "ventas": serie["ventas"].astype(int).tolist(),
    }


@app.post("/api/v1/pronostico", response_model=RespuestaPronostico, tags=["inferencia"])
def pronostico(req: SolicitudPronostico):
    pred = _modelo().predecir([req.model_dump()])[0]
    return _respuesta(req, pred.p50, pred.p90, pred.advertencias)


@app.post("/api/v1/pronostico/lote", response_model=RespuestaLote, tags=["inferencia"])
def pronostico_lote(req: SolicitudLote):
    t0 = time.perf_counter()
    preds = _modelo().predecir([r.model_dump() for r in req.registros])
    resultados = [_respuesta(r, p.p50, p.p90, p.advertencias) for r, p in zip(req.registros, preds)]
    return RespuestaLote(total=len(resultados), resultados=resultados,
                         milisegundos=round((time.perf_counter() - t0) * 1000, 1))


@app.post("/api/v1/reabasto", response_model=RespuestaReabasto, tags=["inferencia"])
def reabasto(req: SolicitudReabasto):
    res = _modelo().reabasto(
        req.sucursal_id, req.sku, req.fecha_inicio, req.horizonte_dias, req.historial_ventas,
        req.existencia_actual, req.precio, set(req.dias_promocion),
    )
    return RespuestaReabasto(sucursal_id=req.sucursal_id, sku=req.sku, horizonte_dias=req.horizonte_dias,
                             modelo_version=_modelo().version, **res)


# Frontend estático (se monta al final para no tapar las rutas de la API)
FRONTEND_DIR = Path(os.getenv("FRONTEND_DIR", RAIZ / "frontend"))
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
