"""Monitoreo por lotes del modelo en operación (corre cada semana en GitHub Actions).

    python -m demanda_ia.monitoreo --desde 2026-08-03 --semanas 12 [--escenario brote_respiratorio]

Compara la venta "real" de una ventana de operación contra lo que el modelo campeón pronosticó y revisa:
  1. Desempeño: WAPE y sesgo semanal, cobertura P90 y nivel de servicio simulado, por semana.
  2. Deriva de datos: PSI de cada variable de entrada contra la distribución de entrenamiento.
  3. Deriva de predicción: PSI del pronóstico servido.
  4. Equidad: WAPE semanal por quintil de volumen de sucursal (R02).
Las alertas usan config/umbrales.toml. Si hay alerta, el workflow abre un issue y puede disparar
el reentrenamiento. Como no hay ventas reales, la "operación" se toma del simulador
(2026, un año después del entrenamiento). Los escenarios inyectan cambios controlados
para comprobar que el monitoreo los detecta.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import date, timedelta

import joblib
import numpy as np
import pandas as pd

from .config import CATEGORIAS, ESTADOS, MODEL_PATH, REPORTS_DIR, SEMILLA, SUCURSALES, cargar_umbrales
from .evaluacion import backtest_reabasto, equidad_por_quintil, metricas, semanal
from .train import construir_dataset, datos_entrenamiento, predecir

# Solo variables dinámicas: los atributos fijos de sucursal/SKU dependen de qué sucursales entran en la
# muestra (composición), no de un cambio en el comportamiento; esos los cubre el contrato de datos.
VARIABLES_PSI = ["precio_relativo", "en_promocion", "dia_semana", "es_quincena", "lag_7", "media_7", "media_28"]

ESCENARIOS = {
    "base": "Operación normal un año después del entrenamiento",
    "brote_respiratorio": "Brote respiratorio: antigripales y analgésicos +80 % desde la semana 5",
    "competidor_jalisco": "Apertura de competidor: -35 % en todas las categorías de sucursales de Jalisco desde la semana 5",
    "alza_precios": "Alza general de precios de 15 % desde la semana 5 (fuera del rango de entrenamiento)",
}


def psi(ref: np.ndarray, act: np.ndarray, bins: int = 10) -> float:
    """Population Stability Index con cortes por cuantiles de la referencia."""
    ref, act = np.asarray(ref, float), np.asarray(act, float)
    cortes = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if cortes.size < 3:  # variable casi constante o binaria: usar sus valores
        cortes = np.unique(np.concatenate([ref, act]))
        cortes = np.append(cortes, cortes[-1] + 1)
    cortes[0], cortes[-1] = -np.inf, np.inf
    r = np.histogram(ref, cortes)[0] / ref.size
    a = np.histogram(act, cortes)[0] / act.size
    r, a = np.clip(r, 1e-4, None), np.clip(a, 1e-4, None)
    return float(np.sum((a - r) * np.log(a / r)))


def _recalcular_ventanas(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["sucursal_id", "sku", "fecha"]).copy()
    g = df.groupby(["sucursal_id", "sku"])["y"]
    df["lag_7"] = g.shift(7)
    df["media_7"] = g.transform(lambda s: s.shift(1).rolling(7).mean())
    df["media_28"] = g.transform(lambda s: s.shift(1).rolling(28).mean())
    return df


def aplicar_escenario(df: pd.DataFrame, escenario: str, inicio_choque: date) -> pd.DataFrame:
    if escenario == "base":
        return df
    df = df.copy()
    m = df["fecha"] >= pd.Timestamp(inicio_choque)
    if escenario == "brote_respiratorio":
        cats = [CATEGORIAS.index(c) for c in ("antigripales", "analgesicos")]
        m &= df["categoria"].isin(cats)
        df.loc[m, "y"] = np.round(df.loc[m, "y"] * 1.8)
        df.loc[m, "mu"] *= 1.8
    elif escenario == "competidor_jalisco":
        m &= df["estado"] == ESTADOS.index("Jalisco")
        df.loc[m, "y"] = np.round(df.loc[m, "y"] * 0.65)
        df.loc[m, "mu"] *= 0.65
    elif escenario == "alza_precios":
        df.loc[m, "precio_relativo"] *= 1.15
        efecto = 1.15 ** -1.5  # misma elasticidad que el simulador
        df.loc[m, "y"] = np.round(df.loc[m, "y"] * efecto)
        df.loc[m, "mu"] *= efecto
    else:
        raise ValueError(f"Escenario desconocido: {escenario}")
    return _recalcular_ventanas(df)


def datos_operacion(desde: date, semanas: int, n_sucursales: int, escenario: str) -> pd.DataFrame:
    rng = np.random.default_rng(SEMILLA + 7)
    sucursales = sorted(rng.choice(sorted(SUCURSALES), size=n_sucursales, replace=False))
    fin = desde + timedelta(weeks=semanas) - timedelta(days=1)
    df = construir_dataset(list(sucursales), desde - timedelta(days=70), fin)
    df = aplicar_escenario(df, escenario, desde + timedelta(weeks=4))
    return df[df["fecha"] >= pd.Timestamp(desde)].reset_index(drop=True)


def monitorear(desde: date, semanas: int = 12, n_sucursales: int = 30, escenario: str = "base",
               modelo_path=MODEL_PATH) -> dict:
    u = cargar_umbrales()
    um, pol = u["monitoreo"], u["politica_reabasto"]
    art = joblib.load(modelo_path)
    modelos = {"p50": art["p50"], "p90": art["p90"], "media": art.get("media")}
    version = art["meta"]["version"]

    op = datos_operacion(desde, semanas, n_sucursales, escenario)
    p50, p90, media = predecir(modelos, op)
    pron = media if media is not None else p50
    sem = semanal(op, p50, p90, media)

    # 1. Desempeño por semana
    por_semana = []
    op_w = op.assign(semana=op["fecha"].dt.to_period("W"), p90=p90)
    for s, g in sem.groupby("semana"):
        y, mask_d = g["y"].to_numpy(), op_w["semana"] == s
        m = metricas(y, g["media"].to_numpy())
        rb = backtest_reabasto(g, pol["factor_seguridad"], pol["categorias_esenciales"])["modelo"]["total"]
        por_semana.append({
            "semana": str(s.start_time.date()),
            "wape_semanal_pct": round(m["wape_pct"], 2), "sesgo_semanal_pct": round(m["sesgo_pct"], 2),
            "cobertura_p90_pct": round(float(100 * np.mean(op_w.loc[mask_d, "y"] <= op_w.loc[mask_d, "p90"])), 2),
            "fill_rate_pct": round(rb["fill_rate_pct"], 2),
        })
    total = metricas(sem["y"].to_numpy(), sem["media"].to_numpy())

    # 2 y 3. Deriva de datos y de predicción contra la referencia de entrenamiento
    ref = datos_entrenamiento()["entrenamiento"]
    ref = ref.sample(n=min(200_000, len(ref)), random_state=SEMILLA)
    ref_pron = predecir(modelos, ref)
    ref_pron = ref_pron[2] if ref_pron[2] is not None else ref_pron[0]
    deriva = {v: round(psi(ref[v].to_numpy(), op[v].to_numpy()), 4) for v in VARIABLES_PSI}
    deriva["pronostico"] = round(psi(ref_pron, pron), 4)
    deriva["venta_real"] = round(psi(ref["y"].to_numpy(), op["y"].to_numpy()), 4)

    # 4. Equidad
    eq = equidad_por_quintil(sem, "media")

    # Alertas
    alertas = []
    ultimas = por_semana[-4:]
    for w in por_semana:
        if w["wape_semanal_pct"] > um["wape_semanal_alerta_pct"]:
            alertas.append({"tipo": "desempeno", "semana": w["semana"],
                            "detalle": f"WAPE semanal {w['wape_semanal_pct']} % > {um['wape_semanal_alerta_pct']} %"})
        if abs(w["sesgo_semanal_pct"]) > um["sesgo_semanal_alerta_pct"]:
            alertas.append({"tipo": "sesgo", "semana": w["semana"],
                            "detalle": f"Sesgo semanal {w['sesgo_semanal_pct']} % (limite +/-{um['sesgo_semanal_alerta_pct']} %)"})
    cob4 = float(np.mean([w["cobertura_p90_pct"] for w in ultimas]))
    if cob4 < um["cobertura_p90_alerta_pct"]:
        alertas.append({"tipo": "calibracion", "semana": "ultimas 4",
                        "detalle": f"Cobertura P90 promedio {cob4:.1f} % < {um['cobertura_p90_alerta_pct']} %"})
    for v, val in deriva.items():
        if val > um["psi_alerta"]:
            alertas.append({"tipo": "deriva_datos", "semana": "ventana", "detalle": f"PSI de {v} = {val} > {um['psi_alerta']}"})
    if eq["razon_peor_mejor"] > u["compuertas_entrenamiento"]["razon_equidad_max"]:
        alertas.append({"tipo": "equidad", "semana": "ventana",
                        "detalle": f"Razon de WAPE peor/mejor quintil {eq['razon_peor_mejor']:.3f} > {u['compuertas_entrenamiento']['razon_equidad_max']}"})

    advertencias = [f"PSI de {v} = {val} (vigilar)" for v, val in deriva.items() if um["psi_advertencia"] < val <= um["psi_alerta"]]
    accion = "ninguna"
    if any(a["tipo"] in ("desempeno", "sesgo", "calibracion") for a in alertas):
        accion = "reentrenar: lanzar el workflow 'entrenamiento' y evaluar al retador contra el campeon"
    elif alertas:
        accion = "investigar: hay deriva o inequidad sin degradacion confirmada del error"
    return {
        "modelo_version": version,
        "escenario": escenario,
        "descripcion_escenario": ESCENARIOS[escenario],
        "ventana": [str(desde), str(desde + timedelta(weeks=semanas) - timedelta(days=1))],
        "sucursales": int(op["sucursal_id"].nunique()),
        "filas": int(len(op)),
        "resumen": {"wape_semanal_pct": round(total["wape_pct"], 2), "sesgo_semanal_pct": round(total["sesgo_pct"], 2),
                    "cobertura_p90_ultimas4_pct": round(cob4, 2)},
        "por_semana": por_semana,
        "psi": deriva,
        "equidad": eq,
        "alertas": alertas,
        "advertencias": advertencias,
        "estado": "alerta" if alertas else ("vigilar" if advertencias else "ok"),
        "accion_recomendada": accion,
    }


def grafica(rep: dict, ruta, um: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.2), gridspec_kw={"width_ratios": [1.6, 1]})
    sem = [w["semana"][5:] for w in rep["por_semana"]]
    ax[0].plot(sem, [w["wape_semanal_pct"] for w in rep["por_semana"]], marker="o", color="#1f5f8b", label="WAPE semanal")
    ax[0].axhline(um["wape_semanal_meta_pct"], color="#2e7d32", ls="--", lw=1, label=f"Meta {um['wape_semanal_meta_pct']:.0f} %")
    ax[0].axhline(um["wape_semanal_alerta_pct"], color="#c62828", ls="--", lw=1, label=f"Alerta {um['wape_semanal_alerta_pct']:.0f} %")
    ax[0].set_title(f"Desempeño semanal · escenario {rep['escenario']}", fontsize=10)
    ax[0].set_ylabel("%"); ax[0].tick_params(axis="x", rotation=45, labelsize=8); ax[0].legend(fontsize=8)
    ax[0].set_ylim(0, max(40, max(w["wape_semanal_pct"] for w in rep["por_semana"]) + 5))
    nombres = list(rep["psi"].keys()); vals = list(rep["psi"].values())
    colores = ["#c62828" if v > um["psi_alerta"] else "#f9a825" if v > um["psi_advertencia"] else "#1f5f8b" for v in vals]
    ax[1].barh(nombres, vals, color=colores)
    ax[1].axvline(um["psi_alerta"], color="#c62828", ls="--", lw=1)
    ax[1].axvline(um["psi_advertencia"], color="#f9a825", ls="--", lw=1)
    ax[1].set_title("Deriva (PSI) vs entrenamiento", fontsize=10); ax[1].tick_params(labelsize=8)
    fig.tight_layout(); fig.savefig(ruta, dpi=130); plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--desde", type=date.fromisoformat, default=date(2026, 8, 3), help="Lunes de inicio de la ventana")
    ap.add_argument("--semanas", type=int, default=12)
    ap.add_argument("--sucursales", type=int, default=30)
    ap.add_argument("--escenario", choices=sorted(ESCENARIOS), default="base")
    args = ap.parse_args(argv)
    rep = monitorear(args.desde, args.semanas, args.sucursales, args.escenario)
    salida = REPORTS_DIR / "monitoreo" / args.escenario
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "reporte.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    um = cargar_umbrales()["monitoreo"]
    grafica(rep, salida / "monitoreo.png", um)
    md = [f"## Monitoreo DEMANDA-IA · modelo {rep['modelo_version']} · escenario `{rep['escenario']}`", "",
          f"{rep['descripcion_escenario']}. Ventana {rep['ventana'][0]} a {rep['ventana'][1]}, {rep['sucursales']} sucursales.", "",
          f"**Estado: {rep['estado'].upper()}** · WAPE semanal {rep['resumen']['wape_semanal_pct']} % · "
          f"sesgo {rep['resumen']['sesgo_semanal_pct']} % · cobertura P90 (4 sem.) {rep['resumen']['cobertura_p90_ultimas4_pct']} %", "",
          f"Acción recomendada: {rep['accion_recomendada']}", "", "| Semana | WAPE | Sesgo | Cobertura P90 | Fill rate |", "|---|---|---|---|---|"]
    md += [f"| {w['semana']} | {w['wape_semanal_pct']} % | {w['sesgo_semanal_pct']} % | {w['cobertura_p90_pct']} % | {w['fill_rate_pct']} % |"
           for w in rep["por_semana"]]
    md += ["", "| Variable | PSI |", "|---|---|"] + [f"| {k} | {v} |" for k, v in rep["psi"].items()]
    if rep["alertas"]:
        md += ["", "### Alertas"] + [f"- [{a['tipo']}] {a['semana']}: {a['detalle']}" for a in rep["alertas"]]
    (salida / "resumen.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write("\n".join(md) + "\n")
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"estado={rep['estado']}\nreentrenar={'true' if rep['accion_recomendada'].startswith('reentrenar') else 'false'}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
