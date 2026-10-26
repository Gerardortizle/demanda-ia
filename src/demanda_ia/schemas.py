"""Contratos de entrada y salida de la API (validados con Pydantic)."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import MAX_HORIZONTE, MAX_LOTE, PRODUCTOS, SUCURSALES, VENTANA_HISTORIAL

FECHA_MIN, FECHA_MAX = date(2024, 2, 1), date(2027, 12, 31)


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("sucursal_id", check_fields=False)
    @classmethod
    def _sucursal(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in SUCURSALES:
            raise ValueError(f"Sucursal desconocida: {v}. Consulte /api/v1/catalogo")
        return v

    @field_validator("sku", check_fields=False)
    @classmethod
    def _sku(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in PRODUCTOS:
            raise ValueError(f"SKU desconocido: {v}. Consulte /api/v1/catalogo")
        return v

    @field_validator("fecha", "fecha_inicio", check_fields=False)
    @classmethod
    def _fecha(cls, v: date) -> date:
        if not FECHA_MIN <= v <= FECHA_MAX:
            raise ValueError(f"Fecha fuera del rango soportado ({FECHA_MIN} a {FECHA_MAX})")
        return v


class SolicitudPronostico(_Base):
    sucursal_id: str = Field(examples=["SUC-001"])
    sku: str = Field(examples=["SKU-0001"])
    fecha: date = Field(examples=["2026-11-02"])
    precio: float | None = Field(default=None, gt=0, le=100_000, description="Si se omite se usa el precio de lista")
    en_promocion: bool = False
    lag_7: float = Field(ge=0, le=100_000, description="Ventas del mismo día de la semana anterior")
    media_7: float = Field(ge=0, le=100_000, description="Promedio de ventas de los últimos 7 días")
    media_28: float = Field(ge=0, le=100_000, description="Promedio de ventas de los últimos 28 días")


class RespuestaPronostico(BaseModel):
    sucursal_id: str
    sku: str
    fecha: date
    pronostico_p50: float
    pronostico_p90: float
    unidades_sugeridas: int
    advertencias: list[str]
    modelo_version: str


class SolicitudLote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    registros: list[SolicitudPronostico] = Field(min_length=1, max_length=MAX_LOTE)


class RespuestaLote(BaseModel):
    total: int
    resultados: list[RespuestaPronostico]
    milisegundos: float


class SolicitudReabasto(_Base):
    sucursal_id: str = Field(examples=["SUC-001"])
    sku: str = Field(examples=["SKU-0009"])
    fecha_inicio: date = Field(examples=["2026-11-02"])
    horizonte_dias: int = Field(default=7, ge=1, le=MAX_HORIZONTE)
    existencia_actual: float = Field(ge=0, le=1_000_000)
    historial_ventas: list[float] = Field(
        min_length=VENTANA_HISTORIAL, max_length=366,
        description="Ventas diarias previas a fecha_inicio, de la más antigua a la más reciente (mínimo 28)",
    )
    precio: float | None = Field(default=None, gt=0, le=100_000)
    dias_promocion: list[date] = Field(default_factory=list, max_length=MAX_HORIZONTE)

    @field_validator("historial_ventas")
    @classmethod
    def _historial(cls, v: list[float]) -> list[float]:
        if any(x < 0 for x in v):
            raise ValueError("El historial no admite ventas negativas")
        return v


class DiaPronostico(BaseModel):
    fecha: date
    p50: float
    p90: float


class RespuestaReabasto(BaseModel):
    sucursal_id: str
    sku: str
    horizonte_dias: int
    dias: list[DiaPronostico]
    demanda_esperada: float
    stock_seguridad: float
    existencia_actual: float
    pedido_sugerido: int
    advertencias: list[str]
    modelo_version: str
