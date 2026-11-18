"""Pipeline de entrenamiento con compuertas de calidad (MLOps).

    python -m demanda_ia.pipeline --version 1.1.0 [--promover] [--mlflow]

Etapas:
  1. Datos: genera/extrae el histórico y valida el contrato de datos (validacion_datos).
  2. Entrenamiento del retador (P50, P90 y media).
  3. Evaluación técnica, de negocio (backtest de reabasto) y de equidad.
  4. Compuertas: umbrales de config/umbrales.toml (Fase I y Fase II).
  5. Comparación campeón vs retador en los mismos datos.
  6. Registro en models/registro.json (y en MLflow si --mlflow) y, con --promover,
     promoción si pasa compuertas y no empeora al campeón.
Deja todo en reports/pipeline/<version>/ como evidencia auditable.
Código de salida 1 si el retador no pasa compuertas (el CI lo marca en rojo).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import joblib

from . import registro
from .config import MODELS_DIR, REGISTRO_PATH, REPORTS_DIR, cargar_umbrales
from .evaluacion import pronostico_semanal
from .train import construir_meta, datos_entrenamiento, entrenar, evaluar_modelos, guardar
from .validacion_datos import huella, resumen, validar


def _commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return os.getenv("GITHUB_SHA", "desconocido")[:7]


def compuertas(resultados: list[dict], u: dict) -> list[dict]:
    """Evalúa cada regla en cada conjunto. Devuelve lista de {regla, conjunto, valor, limite, paso}."""
    c = u["compuertas_entrenamiento"]
    out = []

    def regla(nombre, conjunto, valor, limite, paso):
        out.append({"regla": nombre, "conjunto": conjunto, "valor": round(valor, 3), "limite": limite, "paso": bool(paso)})

    por = {r["conjunto"]: r for r in resultados}
    for nom, e in por.items():
        sem = pronostico_semanal(e)
        lag = e["semanal"]["baseline_lag7"]["wape_pct"]
        regla("wape_semanal_max_pct", nom, sem["wape_pct"], c["wape_semanal_max_pct"], sem["wape_pct"] <= c["wape_semanal_max_pct"])
        regla("sesgo_semanal_abs_max_pct", nom, sem["sesgo_pct"], c["sesgo_semanal_abs_max_pct"], abs(sem["sesgo_pct"]) <= c["sesgo_semanal_abs_max_pct"])
        mejora = 100 * (lag - sem["wape_pct"]) / lag
        regla("mejora_min_vs_lag7_pct", nom, mejora, c["mejora_min_vs_lag7_pct"], mejora >= c["mejora_min_vs_lag7_pct"])
        cob = e["cobertura_p90_pct"]
        regla("cobertura_p90_rango_pct", nom, cob, [c["cobertura_p90_min_pct"], c["cobertura_p90_max_pct"]],
              c["cobertura_p90_min_pct"] <= cob <= c["cobertura_p90_max_pct"])
        rb = e["reabasto"]["modelo"]
        regla("fill_rate_min_pct", nom, rb["total"]["fill_rate_pct"], c["fill_rate_min_pct"], rb["total"]["fill_rate_pct"] >= c["fill_rate_min_pct"])
        regla("fill_rate_esenciales_min_pct", nom, rb["esenciales"]["fill_rate_pct"], c["fill_rate_esenciales_min_pct"],
              rb["esenciales"]["fill_rate_pct"] >= c["fill_rate_esenciales_min_pct"])
        razon = e["equidad"]["razon_peor_mejor"]
        regla("razon_equidad_max", nom, razon, c["razon_equidad_max"], razon <= c["razon_equidad_max"])
    if {"prueba_temporal", "sucursales_no_vistas"} <= por.keys():
        dif = abs(pronostico_semanal(por["sucursales_no_vistas"])["wape_pct"] - pronostico_semanal(por["prueba_temporal"])["wape_pct"])
        regla("diferencia_holdout_max_pts", "ambos", dif, c["diferencia_holdout_max_pts"], dif <= c["diferencia_holdout_max_pts"])
    return out


def comparar_con_campeon(datos: dict, resultados_retador: list[dict]) -> dict | None:
    """Evalúa al campeón actual en los mismos datos para una comparación justa."""
    reg = registro.leer()
    if not reg.get("campeon"):
        return None
    v = reg["campeon"]
    art = joblib.load(MODELS_DIR / reg["modelos"][v]["artefacto"])
    res_c = evaluar_modelos({"p50": art["p50"], "p90": art["p90"], "media": art.get("media")}, datos)
    filas = []
    for rc, rr in zip(res_c, resultados_retador):
        sc, sr = pronostico_semanal(rc), pronostico_semanal(rr)
        filas.append({
            "conjunto": rc["conjunto"],
            "campeon": {"wape_semanal_pct": sc["wape_pct"], "sesgo_semanal_pct": sc["sesgo_pct"],
                        "cobertura_p90_pct": rc["cobertura_p90_pct"],
                        "fill_rate_pct": rc["reabasto"]["modelo"]["total"]["fill_rate_pct"],
                        "excedente_pct": rc["reabasto"]["modelo"]["total"]["excedente_pct"]},
            "retador": {"wape_semanal_pct": sr["wape_pct"], "sesgo_semanal_pct": sr["sesgo_pct"],
                        "cobertura_p90_pct": rr["cobertura_p90_pct"],
                        "fill_rate_pct": rr["reabasto"]["modelo"]["total"]["fill_rate_pct"],
                        "excedente_pct": rr["reabasto"]["modelo"]["total"]["excedente_pct"]},
        })
    return {"version_campeon": v, "comparacion": filas}


def _resumen_registro(resultados: list[dict], dhuella: str, meta: dict, commit: str) -> dict:
    m = {}
    for e in resultados:
        s = pronostico_semanal(e)
        m[e["conjunto"]] = {
            "wape_semanal_pct": round(s["wape_pct"], 3),
            "sesgo_semanal_pct": round(s["sesgo_pct"], 3),
            "wape_diario_p50_pct": round(e["modelo_p50"]["wape_pct"], 3),
            "cobertura_p90_pct": round(e["cobertura_p90_pct"], 3),
            "fill_rate_pct": round(e["reabasto"]["modelo"]["total"]["fill_rate_pct"], 3),
            "razon_equidad": round(e["equidad"]["razon_peor_mejor"], 3),
        }
    return {"algoritmo": meta["algoritmo"], "sklearn_version": meta["sklearn_version"],
            "huella_datos": dhuella, "commit": commit, "hiperparametros": meta["hiperparametros"], "metricas": m}


def _mlflow(version: str, meta: dict, resultados: list[dict], gates: list[dict], ruta: Path, aprobado: bool) -> str | None:
    try:
        import mlflow
    except ImportError:
        print("  MLflow no instalado; se omite (pip install -r requirements-mlops.txt)")
        return None
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", f"sqlite:///{(REPORTS_DIR.parent / 'mlflow.db').as_posix()}"))
    mlflow.set_experiment("demanda-ia")
    with mlflow.start_run(run_name=f"pipeline-{version}") as run:
        mlflow.set_tags({"version": version, "commit": meta.get("commit", ""), "aprobado": str(aprobado)})
        hp = meta["hiperparametros"]
        mlflow.log_params({f"cuantil_{k}": v for k, v in hp["cuantiles"].items()})
        if hp["media"]:
            mlflow.log_params({f"media_{k}": v for k, v in hp["media"].items()})
        mlflow.log_param("huella_datos", meta.get("huella_datos", "")[:16])
        for e in resultados:
            p = "test" if e["conjunto"] == "prueba_temporal" else "holdout"
            s = pronostico_semanal(e)
            mlflow.log_metrics({
                f"{p}_wape_semanal": s["wape_pct"], f"{p}_sesgo_semanal": s["sesgo_pct"],
                f"{p}_wape_diario_p50": e["modelo_p50"]["wape_pct"], f"{p}_cobertura_p90": e["cobertura_p90_pct"],
                f"{p}_fill_rate": e["reabasto"]["modelo"]["total"]["fill_rate_pct"],
                f"{p}_excedente": e["reabasto"]["modelo"]["total"]["excedente_pct"],
                f"{p}_razon_equidad": e["equidad"]["razon_peor_mejor"],
            })
        mlflow.log_metric("compuertas_fallidas", sum(not g["paso"] for g in gates))
        mlflow.log_artifact(str(ruta))
        mlflow.log_artifact(str(ruta.with_suffix(".json")))
        return run.info.run_id


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", required=True)
    ap.add_argument("--promover", action="store_true", help="Promueve a campeón si pasa compuertas y no empeora")
    ap.add_argument("--mlflow", action="store_true", help="Registra la corrida en MLflow")
    ap.add_argument("--sin-media", action="store_true")
    args = ap.parse_args(argv)

    u = cargar_umbrales()
    salida = REPORTS_DIR / "pipeline" / args.version
    salida.mkdir(parents=True, exist_ok=True)
    bitacora: dict = {"version": args.version, "commit": _commit(), "etapas": []}
    t0 = time.time()

    def etapa(nombre, **info):
        bitacora["etapas"].append({"etapa": nombre, "segundos": round(time.time() - t0, 1), **info})
        print(f"[{time.time() - t0:6.1f}s] {nombre}: {json.dumps(info, ensure_ascii=False)[:160]}")

    # 1. Datos
    datos = datos_entrenamiento()
    rep_datos = {k: resumen(validar(datos[k])) for k in ("entrenamiento", "prueba_temporal", "sucursales_no_vistas")}
    (salida / "validacion_datos.json").write_text(json.dumps(rep_datos, indent=2, ensure_ascii=False), encoding="utf-8")
    dhuella = huella(datos["entrenamiento"])
    etapa("validacion_datos", aprobado=all(r["aprobado"] for r in rep_datos.values()),
          filas_entrenamiento=len(datos["entrenamiento"]), huella=dhuella[:16])
    if not all(r["aprobado"] for r in rep_datos.values()):
        print("Datos rechazados: se detiene el pipeline")
        return 1

    # 2. Entrenamiento
    modelos = entrenar(datos, con_media=not args.sin_media)
    etapa("entrenamiento", modelos=[k for k, v in modelos.items() if v is not None])

    # 3. Evaluación
    resultados = evaluar_modelos(modelos, datos)
    meta = construir_meta(args.version, datos, resultados, not args.sin_media, time.time() - t0)
    meta["huella_datos"], meta["commit"] = dhuella, bitacora["commit"]
    etapa("evaluacion", **{e["conjunto"]: round(pronostico_semanal(e)["wape_pct"], 2) for e in resultados})

    # 4. Compuertas
    gates = compuertas(resultados, u)
    aprobado = all(g["paso"] for g in gates)
    (salida / "compuertas.json").write_text(json.dumps(gates, indent=2, ensure_ascii=False), encoding="utf-8")
    etapa("compuertas", aprobado=aprobado, fallidas=[g["regla"] + "@" + g["conjunto"] for g in gates if not g["paso"]])

    # 5. Campeón vs retador
    comp = comparar_con_campeon(datos, resultados)
    if comp:
        (salida / "campeon_vs_retador.json").write_text(json.dumps(comp, indent=2, ensure_ascii=False), encoding="utf-8")
        etapa("comparacion", campeon=comp["version_campeon"])

    # 6. Registro y promoción
    ruta = guardar(modelos, meta, args.version)
    (salida / "metricas.json").write_text(json.dumps(resultados, indent=2, ensure_ascii=False), encoding="utf-8")
    resumen_reg = _resumen_registro(resultados, dhuella, meta, bitacora["commit"])
    resumen_reg["mlflow_run_id"] = _mlflow(args.version, meta, resultados, gates, ruta, aprobado)
    if not aprobado:
        registro.registrar(args.version, ruta, resumen_reg, etapa="rechazado", detalle="no paso compuertas")
        etapa("registro", etapa_modelo="rechazado")
    else:
        registro.registrar(args.version, ruta, resumen_reg, etapa="retador")
        decision = "registrado como retador"
        if args.promover:
            tol = u["promocion"]["tolerancia_wape_semanal_pts"]
            empeora = comp and any(f["retador"]["wape_semanal_pct"] > f["campeon"]["wape_semanal_pct"] + tol
                                   for f in comp["comparacion"])
            if empeora:
                decision = "no promovido: empeora el WAPE semanal del campeon"
            else:
                registro.promover(args.version, "paso compuertas y no empeora al campeon")
                decision = "promovido a campeon"
        etapa("registro", etapa_modelo=decision)
    bitacora["aprobado"] = aprobado
    bitacora["registro"] = str(REGISTRO_PATH.relative_to(REPORTS_DIR.parent))
    (salida / "bitacora.json").write_text(json.dumps(bitacora, indent=2, ensure_ascii=False), encoding="utf-8")
    # Resumen legible para el job summary de GitHub Actions
    lineas = [f"## Pipeline de entrenamiento DEMANDA-IA {args.version}", "",
              f"Commit `{bitacora['commit']}` · huella de datos `{dhuella[:16]}` · {'APROBADO' if aprobado else 'RECHAZADO'}", "",
              "| Regla | Conjunto | Valor | Límite | Resultado |", "|---|---|---|---|---|"]
    lineas += [f"| {g['regla']} | {g['conjunto']} | {g['valor']} | {g['limite']} | {'✅' if g['paso'] else '❌'} |" for g in gates]
    if comp:
        lineas += ["", f"### Campeón {comp['version_campeon']} vs retador {args.version}", "",
                   "| Conjunto | WAPE sem. campeón | WAPE sem. retador | Sesgo campeón | Sesgo retador | Fill rate campeón | Fill rate retador |",
                   "|---|---|---|---|---|---|---|"]
        lineas += [f"| {f['conjunto']} | {f['campeon']['wape_semanal_pct']:.1f} % | {f['retador']['wape_semanal_pct']:.1f} % | "
                   f"{f['campeon']['sesgo_semanal_pct']:.1f} % | {f['retador']['sesgo_semanal_pct']:.1f} % | "
                   f"{f['campeon']['fill_rate_pct']:.1f} % | {f['retador']['fill_rate_pct']:.1f} % |" for f in comp["comparacion"]]
    (salida / "resumen.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write("\n".join(lineas) + "\n")
    return 0 if aprobado else 1


if __name__ == "__main__":
    sys.exit(main())
