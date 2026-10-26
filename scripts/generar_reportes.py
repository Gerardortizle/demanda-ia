"""Genera las figuras y tablas del documento de validación a partir del modelo entrenado.
Uso: PYTHONPATH=src python scripts/generar_reportes.py"""
import json
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from demanda_ia.config import CATEGORIAS, FEATURES, PRODUCTOS  # noqa: E402
from demanda_ia.model import ModeloDemanda  # noqa: E402
from demanda_ia.train import CORTE, construir_dataset  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
FIG = RAIZ / "reports" / "figuras"
FIG.mkdir(parents=True, exist_ok=True)
VERDE, AMBAR, GRIS, AZUL = "#0f6e5c", "#c98a1a", "#9fb3ad", "#3b5b92"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})

modelo = ModeloDemanda()
evaluacion = {e["conjunto"]: e for e in json.loads((RAIZ / "reports" / "metricas.json").read_text(encoding="utf-8"))}

# 1. Series de ejemplo en el periodo de prueba
df = construir_dataset(["SUC-001"])
fig, ejes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
for ax, sku in zip(ejes, ["SKU-0005", "SKU-0012"]):
    d = df[(df["sku"] == sku) & (df["fecha"] > CORTE)]
    X = d[FEATURES].to_numpy(dtype=float)
    p50 = np.clip(modelo._p50.predict(X), 0, None)
    p90 = np.maximum(np.clip(modelo._p90.predict(X), 0, None), p50)
    ax.fill_between(d["fecha"], 0, p90, color=AMBAR, alpha=0.18, label="Banda hasta P90")
    ax.plot(d["fecha"], d["y"], color=GRIS, lw=1, marker="o", ms=2.5, label="Venta real")
    ax.plot(d["fecha"], p50, color=VERDE, lw=2, label="Pronóstico P50")
    ax.set_title(f"SUC-001 · {PRODUCTOS[sku].nombre}", loc="left", fontsize=10)
    ax.set_ylabel("Piezas/día")
ejes[0].legend(ncol=3, frameon=False, loc="upper right")
fig.tight_layout()
fig.savefig(FIG / "series_prueba.png", dpi=160)
plt.close(fig)

# 2. WAPE contra baselines, diario y semanal
fig, ejes = plt.subplots(1, 2, figsize=(10, 3.8))
for ax, conj, titulo in zip(ejes, ["prueba_temporal", "sucursales_no_vistas"], ["Prueba temporal (oct-dic 2025)", "Sucursales no vistas"]):
    e = evaluacion[conj]
    nombres = ["Modelo P50", "Ingenuo lag 7", "Media 28 días", "Oráculo*"]
    diario = [e["modelo_p50"]["wape_pct"], e["baseline_lag7"]["wape_pct"], e["baseline_media28"]["wape_pct"], e["oraculo_media_teorica"]["wape_pct"]]
    semanal = [e["semanal"]["modelo_p50"]["wape_pct"], e["semanal"]["baseline_lag7"]["wape_pct"], np.nan, e["semanal"]["oraculo_media_teorica"]["wape_pct"]]
    x = np.arange(4)
    b1 = ax.bar(x - 0.2, diario, 0.4, color=[VERDE, GRIS, GRIS, AZUL], label="Diario")
    b2 = ax.bar(x + 0.2, semanal, 0.4, color=[VERDE, GRIS, GRIS, AZUL], alpha=0.5, hatch="//", label="Semanal")
    ax.bar_label(b1, fmt="%.1f", fontsize=8)
    ax.bar_label(b2, labels=[f"{v:.1f}" if not np.isnan(v) else "" for v in semanal], fontsize=8)
    ax.set_xticks(x, nombres, fontsize=8.5)
    ax.set_title(titulo, loc="left", fontsize=10)
    ax.set_ylabel("WAPE %")
ejes[0].legend(frameon=False)
fig.text(0.01, 0.01, "*Oráculo: usa la media teórica del simulador; marca el error mínimo alcanzable por el ruido de la demanda.", fontsize=7.5)
fig.tight_layout(rect=(0, 0.04, 1, 1))
fig.savefig(FIG / "wape_comparativo.png", dpi=160)
plt.close(fig)

# 3. Por categoría
e = evaluacion["prueba_temporal"]["por_categoria"]
fig, ax = plt.subplots(figsize=(10, 3.6))
x = np.arange(len(CATEGORIAS))
ax.bar(x - 0.2, [e[c]["wape_modelo_pct"] for c in CATEGORIAS], 0.4, color=VERDE, label="WAPE modelo")
ax.bar(x + 0.2, [e[c]["wape_lag7_pct"] for c in CATEGORIAS], 0.4, color=GRIS, label="WAPE ingenuo lag 7")
ax2 = ax.twinx()
ax2.plot(x, [e[c]["cobertura_p90_pct"] for c in CATEGORIAS], color=AMBAR, marker="D", lw=0, label="Cobertura P90")
ax2.axhline(90, color=AMBAR, ls=":", lw=1)
ax2.set_ylim(80, 95)
ax2.set_ylabel("Cobertura P90 %")
ax.set_xticks(x, [c.replace("_", " ") for c in CATEGORIAS], fontsize=8.5)
ax.set_ylabel("WAPE diario %")
h1, l1 = ax.get_legend_handles_labels()
h2, l2 = ax2.get_legend_handles_labels()
ax.legend(h1 + h2, l1 + l2, frameon=False, ncol=3, loc="upper left", fontsize=8.5)
fig.tight_layout()
fig.savefig(FIG / "por_categoria.png", dpi=160)
plt.close(fig)

# 4. Análisis de sensibilidad (escenarios de negocio)
def p(**kw):
    r = {"sucursal_id": "SUC-001", "sku": "SKU-0005", "fecha": date(2026, 11, 4), "lag_7": 10, "media_7": 10, "media_28": 10}
    r.update(kw)
    x = modelo.predecir([r])[0]
    return round(x.p50, 2), round(x.p90, 2), x.advertencias

lista = PRODUCTOS["SKU-0005"].precio_lista
escenarios = [
    ("Base: antigripal, miércoles 4-nov-2026, historial 10 u/día", {}),
    ("Promoción con 15 % de descuento", {"en_promocion": True, "precio": lista * 0.85}),
    ("Precio 20 % arriba de lista", {"precio": lista * 1.2}),
    ("Invierno: miércoles 13-ene-2027", {"fecha": date(2027, 1, 13)}),
    ("Verano: miércoles 15-jul-2026", {"fecha": date(2026, 7, 15)}),
    ("Festivo: lunes 16-nov-2026 (Revolución)", {"fecha": date(2026, 11, 16)}),
    ("Lunes normal 9-nov-2026", {"fecha": date(2026, 11, 9)}),
    ("Historial en ceros (SKU nuevo o quiebre)", {"lag_7": 0, "media_7": 0, "media_28": 0}),
    ("Pico atípico: historial 5 000 u/día", {"lag_7": 5000, "media_7": 4800, "media_28": 4000}),
    ("Precio extremo: 1 peso", {"precio": 1.0}),
    ("Crónico (metformina) día 15, quincena", {"sku": "SKU-0012", "fecha": date(2026, 10, 15), "lag_7": 8, "media_7": 8, "media_28": 8}),
    ("Crónico (metformina) día 8", {"sku": "SKU-0012", "fecha": date(2026, 10, 8), "lag_7": 8, "media_7": 8, "media_28": 8}),
]
tabla = [{"escenario": n, "p50": a, "p90": b, "advertencias": w} for n, kw in escenarios for a, b, w in [p(**kw)]]
(RAIZ / "reports" / "sensibilidad.json").write_text(json.dumps(tabla, indent=2, ensure_ascii=False), encoding="utf-8")
for t in tabla:
    print(f"{t['escenario']:<60} P50={t['p50']:>7} P90={t['p90']:>7} {'; '.join(t['advertencias'])[:60]}")
print("Figuras en", FIG)
