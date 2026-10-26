"""Configuración central de DEMANDA-IA: catálogos, rutas y constantes del modelo.

El catálogo es sintético pero estable (semilla fija) y representa la red de
140 sucursales de Farmacias Occidente Salud en el occidente de México.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

MODEL_VERSION = "1.0.0"
SEMILLA = 2026

RAIZ = Path(__file__).resolve().parents[2]
MODEL_PATH = Path(os.getenv("MODEL_PATH", RAIZ / "models" / "demanda_ia_v1.joblib"))
METADATA_PATH = MODEL_PATH.with_suffix(".json")

# Límites operativos de la API
MAX_LOTE = int(os.getenv("MAX_LOTE", "1000"))
MAX_HORIZONTE = 14
VENTANA_HISTORIAL = 28

CATEGORIAS = [
    "analgesicos",
    "antigripales",
    "sueros_antidiarreicos",
    "cronicos",
    "vitaminas",
    "dermocosmetica",
    "infantil",
]
TIPOS_SUCURSAL = ["urbana", "periferia", "hospitalaria"]
ESTADOS = ["Jalisco", "Michoacan", "Colima", "Nayarit", "Aguascalientes"]

CIUDADES = {
    "Jalisco": ["Guadalajara", "Zapopan", "Tlaquepaque", "Tonala", "Puerto Vallarta", "Lagos de Moreno"],
    "Michoacan": ["Morelia", "Uruapan", "Zamora"],
    "Colima": ["Colima", "Manzanillo"],
    "Nayarit": ["Tepic", "Bahia de Banderas"],
    "Aguascalientes": ["Aguascalientes"],
}


@dataclass(frozen=True)
class Sucursal:
    id: str
    ciudad: str
    estado: str
    tipo: str
    factor_tamano: float


@dataclass(frozen=True)
class Producto:
    sku: str
    nombre: str
    categoria: str
    precio_lista: float
    demanda_base: float


_PRODUCTOS_BASE = [
    ("Paracetamol 500 mg 20 tab", "analgesicos", 38.0, 14.0),
    ("Ibuprofeno 400 mg 10 tab", "analgesicos", 45.0, 11.0),
    ("Naproxeno 250 mg 30 tab", "analgesicos", 62.0, 6.0),
    ("Diclofenaco gel 60 g", "analgesicos", 89.0, 4.0),
    ("Antigripal compuesto 12 caps", "antigripales", 75.0, 9.0),
    ("Jarabe para la tos 120 ml", "antigripales", 98.0, 6.0),
    ("Loratadina 10 mg 10 tab", "antigripales", 55.0, 7.0),
    ("Pastillas para garganta 24 pz", "antigripales", 42.0, 8.0),
    ("Suero oral 625 ml", "sueros_antidiarreicos", 28.0, 16.0),
    ("Electrolitos sabor coco 500 ml", "sueros_antidiarreicos", 32.0, 10.0),
    ("Loperamida 2 mg 12 tab", "sueros_antidiarreicos", 49.0, 4.0),
    ("Metformina 850 mg 30 tab", "cronicos", 72.0, 9.0),
    ("Losartan 50 mg 30 tab", "cronicos", 115.0, 7.0),
    ("Glibenclamida 5 mg 50 tab", "cronicos", 58.0, 5.0),
    ("Atorvastatina 20 mg 30 tab", "cronicos", 180.0, 4.0),
    ("Tiras reactivas glucosa 50 pz", "cronicos", 420.0, 2.0),
    ("Vitamina C 1 g 10 tab efervescentes", "vitaminas", 68.0, 6.0),
    ("Complejo B 30 tab", "vitaminas", 95.0, 3.5),
    ("Multivitaminico adulto 60 tab", "vitaminas", 240.0, 2.0),
    ("Bloqueador solar FPS 50 120 ml", "dermocosmetica", 310.0, 2.5),
    ("Crema humectante 400 ml", "dermocosmetica", 135.0, 3.0),
    ("Gel antibacterial 250 ml", "dermocosmetica", 39.0, 7.0),
    ("Shampoo anticaspa 375 ml", "dermocosmetica", 118.0, 2.5),
    ("Panales etapa 4 40 pz", "infantil", 285.0, 4.0),
    ("Toallitas humedas 80 pz", "infantil", 52.0, 6.0),
    ("Paracetamol infantil gotas 15 ml", "infantil", 48.0, 5.0),
    ("Formula lactea etapa 1 800 g", "infantil", 395.0, 1.8),
    ("Termometro digital", "infantil", 120.0, 0.8),
    ("Cubrebocas tricapa 50 pz", "antigripales", 85.0, 3.0),
    ("Omeprazol 20 mg 14 caps", "analgesicos", 66.0, 8.0),
]


def _construir_catalogo() -> tuple[dict[str, Sucursal], dict[str, Producto]]:
    rng = np.random.default_rng(SEMILLA)
    # Distribución aproximada de la red: Jalisco concentra la mayoría
    pesos = np.array([0.55, 0.17, 0.10, 0.10, 0.08])
    sucursales: dict[str, Sucursal] = {}
    for i in range(1, 141):
        estado = ESTADOS[rng.choice(len(ESTADOS), p=pesos)]
        ciudad = rng.choice(CIUDADES[estado])
        tipo = TIPOS_SUCURSAL[rng.choice(3, p=[0.55, 0.33, 0.12])]
        factor = float(np.round(rng.lognormal(mean=0.0, sigma=0.35), 3))
        if tipo == "hospitalaria":
            factor = float(np.round(factor * 1.3, 3))
        sid = f"SUC-{i:03d}"
        sucursales[sid] = Sucursal(sid, str(ciudad), estado, tipo, factor)

    productos: dict[str, Producto] = {}
    for j, (nombre, cat, precio, base) in enumerate(_PRODUCTOS_BASE, start=1):
        sku = f"SKU-{j:04d}"
        productos[sku] = Producto(sku, nombre, cat, precio, base)
    return sucursales, productos


SUCURSALES, PRODUCTOS = _construir_catalogo()

# Orden fijo de las variables de entrada al modelo
FEATURES = [
    "categoria",          # categórica
    "tipo_sucursal",      # categórica
    "estado",             # categórica
    "factor_tamano",
    "demanda_base_sku",
    "precio_relativo",
    "en_promocion",
    "dia_semana",
    "mes",
    "dia_mes",
    "es_quincena",
    "es_festivo",
    "lag_7",
    "media_7",
    "media_28",
]
FEATURES_CATEGORICAS = [0, 1, 2]
