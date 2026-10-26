"""Dibuja el diagrama de arquitectura usado en la documentación."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

VERDE, AMBAR, GRIS, TINTA = "#0f6e5c", "#c98a1a", "#d3dcd9", "#1e2a2f"
fig, ax = plt.subplots(figsize=(11, 5.6))
ax.set_xlim(0, 110); ax.set_ylim(0, 56); ax.axis("off")


def caja(x, y, w, h, titulo, texto, color, relleno="#ffffff"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.2", fc=relleno, ec=color, lw=1.8))
    ax.text(x + 1.2, y + h - 2.2, titulo, fontsize=10.5, weight="bold", color=color, va="top")
    ax.text(x + 1.2, y + h - 6.2, texto, fontsize=8.6, color=TINTA, va="top", linespacing=1.45)


def flecha(a, b, texto="", dy=1.2):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=14, lw=1.4, color=TINTA))
    if texto:
        ax.text((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 + dy, texto, fontsize=8, ha="center", color=TINTA)


# Contenedor
ax.add_patch(FancyBboxPatch((30, 8), 50, 41, boxstyle="round,pad=0.5,rounding_size=2", fc="#f5f8f7", ec=VERDE, lw=1.5, ls="--"))
ax.text(31.5, 47.5, "Contenedor Docker demanda-ia:1.0.0 (python:3.12-slim, sin root)", fontsize=8.6, color=VERDE, va="top")

caja(2, 30, 22, 15, "Frontend web", "HTML + CSS + JavaScript\nFormulario de pedido\nGráfica P50/P90", VERDE)
caja(2, 9, 22, 15, "ERP / corrida nocturna", "Cliente por lotes\n140 sucursales x 30 SKU\nhasta 1000 registros/llamada", AMBAR)
caja(33, 27, 21, 17, "Backend FastAPI", "Uvicorn  :8000\nValidación Pydantic\nCORS, logs, latencia\nOpenAPI en /docs", VERDE)
caja(57, 27, 21, 17, "Servicio de modelo", "ModeloDemanda\nfeatures.py (mismas\nvariables que train.py)\nreabasto recursivo", VERDE)
caja(57, 10, 21, 13, "Artefacto", "demanda_ia_v1.joblib\nHGB cuantil P50 y P90\n+ metadatos y métricas", TINTA)
caja(33, 10, 21, 13, "Archivos estáticos", "/frontend servido en  /\nmismo origen que la API", TINTA)
caja(86, 30, 22, 15, "CI/CD GitHub Actions", "pytest (45 pruebas)\ndocker build + healthcheck\nprueba de humo\npush a GHCR", AMBAR)
caja(86, 9, 22, 15, "Nube (PaaS)", "Google Cloud Run\n(alternativas: Render,\nAzure Container Apps)\nHTTPS + autoescalado", AMBAR)

flecha((24.6, 38), (32.6, 38), "REST/JSON")
flecha((24.6, 16.5), (32.6, 31))
ax.text(26.2, 20.5, "POST /lote", rotation=60, fontsize=8, color=TINTA)
flecha((54.6, 35.5), (56.6, 35.5))
flecha((67.5, 26.6), (67.5, 23.6))
flecha((43.5, 26.6), (43.5, 23.6))
flecha((97, 29.6), (97, 24.6), "imagen")
ax.text(55.6, 2.5, "Flujo: el usuario o el ERP envía datos → la API valida → el modelo calcula P50/P90 → la API responde JSON con pronóstico y pedido sugerido",
        fontsize=8.4, ha="center", color=TINTA)
fig.tight_layout()
salida = Path(__file__).resolve().parents[1] / "reports" / "figuras" / "arquitectura.png"
fig.savefig(salida, dpi=170)
print(salida)
