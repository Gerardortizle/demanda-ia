"""Figuras de la Fase III (documento técnico y portfolio) a partir de los resultados del pipeline.

    PYTHONPATH=src python scripts/generar_reportes_fase3.py

Requiere haber corrido: demanda_ia.pipeline (registro) y demanda_ia.monitoreo para los 4 escenarios.
Salida: reports/figuras/fase3/*.png y reports/frontera_reabasto.json
"""
import json
import subprocess

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from demanda_ia import registro  # noqa: E402
from demanda_ia.config import MODELS_DIR, REPORTS_DIR  # noqa: E402
from demanda_ia.evaluacion import semanal  # noqa: E402
from demanda_ia.train import datos_entrenamiento, predecir  # noqa: E402

VERDE, AMBAR, GRIS, ROJO, AZUL, TINTA = "#0f6e5c", "#c98a1a", "#9aa8a4", "#c62828", "#1f5f8b", "#1e2a2f"
OUT = REPORTS_DIR / "figuras" / "fase3"
OUT.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})

reg = registro.leer()
m10, m11 = reg["modelos"]["1.0.0"]["metricas"], reg["modelos"]["1.1.0"]["metricas"]
conj = [("prueba_temporal", "Prueba temporal\n(oct-dic 2025)"), ("sucursales_no_vistas", "10 sucursales\nno vistas")]

# 1. Campeón vs retador
fig, ax = plt.subplots(1, 2, figsize=(10, 3.8))
x = np.arange(2)
for i, (k, titulo, lim) in enumerate([("wape_semanal_pct", "WAPE semanal (%)", 22), ("sesgo_semanal_pct", "Sesgo semanal (%)", None)]):
    a = [m10[c][k] for c, _ in conj]
    b = [m11[c][k] for c, _ in conj]
    ax[i].bar(x - 0.18, a, 0.36, color=GRIS, label="v1.0.0 (Fase II)")
    ax[i].bar(x + 0.18, b, 0.36, color=VERDE, label="v1.1.0 (Fase III)")
    for xi, v in zip(x - 0.18, a):
        ax[i].text(xi, v + (0.4 if v >= 0 else -1.2), f"{v:.1f}", ha="center", fontsize=9)
    for xi, v in zip(x + 0.18, b):
        ax[i].text(xi, v + (0.4 if v >= 0 else -1.2), f"{v:.1f}", ha="center", fontsize=9, color=VERDE, weight="bold")
    if lim:
        ax[i].axhline(lim, color=AMBAR, ls="--", lw=1)
        ax[i].text(1.45, lim + 0.3, "meta 22 %", color=AMBAR, fontsize=8, ha="right")
    ax[i].axhline(0, color=TINTA, lw=0.6)
    ax[i].set_xticks(x, [t for _, t in conj]); ax[i].set_title(titulo, fontsize=10)
ax[0].legend(fontsize=8, loc="lower left")
fig.suptitle("Campeón vs retador evaluados con los mismos datos", fontsize=11, weight="bold")
fig.tight_layout(); fig.savefig(OUT / "campeon_vs_retador.png", dpi=150); plt.close(fig)

# 2. Frontera nivel de servicio vs excedente (decisión de política, ADR-004)
datos = datos_entrenamiento()
art = joblib.load(MODELS_DIR / reg["modelos"]["1.1.0"]["artefacto"])
mods = {"p50": art["p50"], "p90": art["p90"], "media": art["media"]}
frontera = {}
fig, ax = plt.subplots(1, 2, figsize=(10, 3.9), sharey=True)
for j, (c, titulo) in enumerate(conj):
    d = datos[c]
    p50, p90, media = predecir(mods, d)
    s = semanal(d, p50, p90, media)
    ss = np.sqrt(s["margen2"])
    frontera[c] = {}
    for base, color, nombre in [("p50", VERDE, "P50 + k·SS (política vigente)"), ("media", AZUL, "media + k·SS (alternativa)")]:
        pts = []
        for k in np.round(np.arange(0.4, 1.61, 0.1), 1):
            q = np.ceil(s[base] + k * ss)
            pts.append((float(k), float(100 * np.maximum(q - s["y"], 0).sum() / s["y"].sum()),
                        float(100 * np.minimum(s["y"], q).sum() / s["y"].sum())))
        frontera[c][base] = [{"k": k, "excedente_pct": e, "fill_rate_pct": f} for k, e, f in pts]
        ax[j].plot([p[1] for p in pts], [p[2] for p in pts], marker="o", ms=3, color=color, label=nombre)
        if base == "p50":
            k1 = [p for p in pts if p[0] == 1.0][0]
            ax[j].scatter([k1[1]], [k1[2]], s=90, facecolor="none", edgecolor=ROJO, lw=1.8, zorder=5)
            ax[j].annotate(f"k = 1.0\n{k1[2]:.1f} % servicio", (k1[1], k1[2]), (k1[1] + 4, k1[2] - 2.2), fontsize=8,
                           arrowprops=dict(arrowstyle="-", color=ROJO))
    ax[j].axhline(96, color=AMBAR, ls="--", lw=1); ax[j].text(9, 96.15, "meta 96 %", color=AMBAR, fontsize=8)
    ax[j].set_title(titulo.replace("\n", " "), fontsize=10); ax[j].set_xlabel("Excedente de inventario (% de la venta)")
ax[0].set_ylabel("Nivel de servicio simulado (%)"); ax[0].legend(fontsize=8, loc="lower right")
fig.suptitle("Con el mismo inventario, la media no da más servicio (y en sucursales nuevas da menos): se mantiene P50 con k = 1", fontsize=10.5, weight="bold")
fig.tight_layout(); fig.savefig(OUT / "frontera_reabasto.png", dpi=150); plt.close(fig)
(REPORTS_DIR / "frontera_reabasto.json").write_text(json.dumps(frontera, indent=2), encoding="utf-8")

# 3. Equidad por quintil
meta11 = json.loads((MODELS_DIR / "demanda_ia_1.1.0.json").read_text(encoding="utf-8"))
fig, ax = plt.subplots(figsize=(6.4, 3.5))
for e, color, mk in zip(meta11["evaluacion"], [VERDE, AZUL], ["o", "s"]):
    q = e["equidad"]["quintiles"]
    ax.plot(list(q), [v["wape_semanal_pct"] for v in q.values()], marker=mk, color=color,
            label=f"{e['conjunto'].replace('_', ' ')} (razón {e['equidad']['razon_peor_mejor']:.2f})")
ax.set_ylabel("WAPE semanal (%)"); ax.set_xlabel("Quintil de volumen de sucursal (Q1 = las que menos venden)")
ax.set_title("Equidad entre sucursales (R02): razón peor/mejor ≤ 1.25", fontsize=10); ax.legend(fontsize=8)
fig.tight_layout(); fig.savefig(OUT / "equidad_quintiles.png", dpi=150); plt.close(fig)

# 4. Escenarios de monitoreo
fig, ax = plt.subplots(figsize=(10, 4))
colores = {"base": VERDE, "brote_respiratorio": ROJO, "competidor_jalisco": AMBAR, "alza_precios": AZUL}
for esc, color in colores.items():
    rep = json.loads((REPORTS_DIR / "monitoreo" / esc / "reporte.json").read_text(encoding="utf-8"))
    sem = [w["semana"][5:] for w in rep["por_semana"]]
    ax.plot(sem, [w["wape_semanal_pct"] for w in rep["por_semana"]], marker="o", ms=4, color=color,
            label=f"{esc.replace('_', ' ')} · {rep['estado']}")
ax.axhline(22, color=VERDE, ls=":", lw=1); ax.axhline(26, color=ROJO, ls="--", lw=1)
ax.text(11.2, 26.4, "alerta 26 %", color=ROJO, fontsize=8, ha="right"); ax.text(11.2, 22.4, "meta 22 %", color=VERDE, fontsize=8, ha="right")
ax.axvline(4, color=GRIS, lw=1); ax.text(4.1, 36, "inicio del cambio", fontsize=8, color=TINTA)
ax.set_ylabel("WAPE semanal (%)"); ax.set_title("Monitoreo semanal ago-oct 2026 bajo cuatro escenarios", fontsize=10)
ax.tick_params(axis="x", rotation=45, labelsize=8); ax.legend(fontsize=8, ncol=2); ax.set_ylim(10, 40)
fig.tight_layout(); fig.savefig(OUT / "monitoreo_escenarios.png", dpi=150); plt.close(fig)

# 5. Optimización de latencia de /reabasto
fig, ax = plt.subplots(figsize=(5.6, 3.2))
vals = [("Fase II\nv1.0", 96.1, GRIS), ("v1.1 antes\n(3 modelos)", 144.6, AMBAR), ("v1.1 optimizado\n(lote)", 54.7, VERDE)]
ax.bar([v[0] for v in vals], [v[1] for v in vals], color=[v[2] for v in vals])
for i, v in enumerate(vals):
    ax.text(i, v[1] + 3, f"{v[1]:.0f} ms", ha="center", fontsize=9)
ax.set_ylabel("Latencia p50 (ms)"); ax.set_title("POST /reabasto, horizonte 14 días", fontsize=10)
fig.tight_layout(); fig.savefig(OUT / "latencia_reabasto.png", dpi=150); plt.close(fig)

# 6. Diagrama del pipeline MLOps/GitOps (Graphviz)
dot = r"""
digraph G {
  rankdir=TB; bgcolor="white"; fontname="Helvetica"; nodesep=0.3; ranksep=0.55; newrank=true;
  node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=10, color="#0f6e5c", fillcolor="#eef6f3", penwidth=1.4];
  edge [color="#1e2a2f", fontname="Helvetica", fontsize=8.5];
  subgraph cluster_git { label="GitHub (fuente de verdad)"; fontsize=11; color="#9aa8a4"; style="dashed,rounded";
    dev [label="Desarrollador\npush / pull request", fillcolor="#ffffff"];
    repo [label="Repositorio\ncódigo · umbrales.toml\nregistro.json · deploy/*.yaml"];
  }
  subgraph cluster_ci { label="ci.yml (cada push y PR)"; fontsize=11; color="#0f6e5c"; style="rounded";
    lint [label="Lint\nruff"]; tests [label="Pruebas\n69 pytest\ncódigo · API · datos"]; gate [label="Compuerta\nmodelo\nSHA-256 + 15 reglas"];
    img [label="Contenedor\nbuild · healthcheck\nhumo · Trivy"]; ghcr [label="GHCR\n1.1.0 · sha · latest", fillcolor="#fff5e6", color="#c98a1a"];
  }
  subgraph cluster_ct { label="entrenamiento.yml (mensual o por alerta)"; fontsize=11; color="#1f5f8b"; style="rounded";
    datos [label="Contrato\nde datos\n14 reglas", color="#1f5f8b", fillcolor="#eef3f8"];
    train [label="Entrenar retador\nP50 · P90 · media", color="#1f5f8b", fillcolor="#eef3f8"];
    evalu [label="Evaluar\ntécnica · negocio\nequidad", color="#1f5f8b", fillcolor="#eef3f8"];
    champ [label="Campeón vs\nretador", color="#1f5f8b", fillcolor="#eef3f8"];
    mlf [label="MLflow\nparámetros · métricas\nartefactos", color="#1f5f8b", fillcolor="#ffffff"];
    pr [label="Pull request\ncon el modelo", color="#1f5f8b", fillcolor="#ffffff"];
  }
  subgraph cluster_cd { label="cd.yml (GitOps)"; fontsize=11; color="#c98a1a"; style="rounded";
    stg [label="Cloud Run\nstaging\nhumo + rollback", color="#c98a1a", fillcolor="#fff5e6"];
    prod [label="Cloud Run\nproducción\naprobación manual", color="#c98a1a", fillcolor="#fff5e6"];
  }
  subgraph cluster_ops { label="Operación"; fontsize=11; color="#c62828"; style="rounded";
    api [label="API v1.1\nauditoría · /monitoreo\n/metrics", color="#c62828", fillcolor="#fdeeee"];
    mon [label="monitoreo.yml\nsemanal: WAPE · sesgo\nPSI · equidad", color="#c62828", fillcolor="#fdeeee"];
    issue [label="Issue de alerta", color="#c62828", fillcolor="#ffffff"];
  }
  {rank=same; dev; repo;} {rank=same; lint; tests; gate; img; ghcr;} {rank=same; datos; train; evalu; champ; pr;}
  {rank=same; stg; prod; api; mon; issue;} mlf;
  dev -> repo; repo -> lint -> tests -> gate -> img -> ghcr;
  datos -> train -> evalu -> champ -> pr; evalu -> mlf [style=dashed];
  pr -> repo [label="revisión\ny merge"];
  ghcr -> stg [label="manifiesto\ncambia"]; stg -> prod; prod -> api; api -> mon [style=dashed, label="ventas reales"];
  mon -> issue; mon -> datos [label="degradación:\nreentrenar", color="#c62828", fontcolor="#c62828"];
}
"""
(OUT / "pipeline_mlops.dot").write_text(dot, encoding="utf-8")
subprocess.run(["dot", "-Tpng", "-Gdpi=170", str(OUT / "pipeline_mlops.dot"), "-o", str(OUT / "pipeline_mlops.png")], check=True)
print("Figuras en", OUT)
