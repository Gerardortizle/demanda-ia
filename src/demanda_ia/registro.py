"""Registro de modelos versionado en Git (models/registro.json).

Cada versión guarda: artefacto, hash SHA-256, huella de los datos, hiperparámetros,
commit de origen, métricas y etapa (campeon, retador, archivado o rechazado).
El campo "campeon" decide qué modelo sirve la API. Como el archivo vive en Git,
promover o regresar un modelo es un commit revisable y reversible (GitOps).

MLflow registra los mismos datos para comparar experimentos, pero el despliegue
solo confía en este archivo (ver docs/adr/ADR-001).
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from .config import MODELS_DIR, REGISTRO_PATH

ETAPAS = {"campeon", "retador", "archivado", "rechazado"}


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def leer(ruta: Path = REGISTRO_PATH) -> dict:
    if not ruta.exists():
        return {"campeon": None, "modelos": {}, "historial": []}
    return json.loads(ruta.read_text(encoding="utf-8"))


def guardar(reg: dict, ruta: Path = REGISTRO_PATH) -> None:
    ruta.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _evento(reg: dict, accion: str, version: str, detalle: str) -> None:
    reg["historial"].append({
        "fecha": datetime.now(UTC).isoformat(timespec="seconds"),
        "accion": accion, "version": version, "detalle": detalle,
    })


def registrar(version: str, artefacto: Path, resumen: dict, etapa: str = "retador",
              ruta: Path = REGISTRO_PATH, detalle: str = "") -> dict:
    """Agrega o actualiza una versión. `resumen` trae métricas, huella de datos, parámetros, etc."""
    if etapa not in ETAPAS:
        raise ValueError(f"Etapa invalida: {etapa}")
    reg = leer(ruta)
    reg["modelos"][version] = {
        "artefacto": artefacto.name,
        "sha256": sha256(artefacto),
        "etapa": etapa,
        "registrado_en": datetime.now(UTC).isoformat(timespec="seconds"),
        **resumen,
    }
    _evento(reg, "registro", version, detalle or f"etapa={etapa}")
    guardar(reg, ruta)
    return reg


def promover(version: str, motivo: str, ruta: Path = REGISTRO_PATH) -> dict:
    """Convierte `version` en campeón y archiva al anterior."""
    reg = leer(ruta)
    if version not in reg["modelos"]:
        raise KeyError(f"Version no registrada: {version}")
    anterior = reg.get("campeon")
    if anterior and anterior != version:
        reg["modelos"][anterior]["etapa"] = "archivado"
    reg["modelos"][version]["etapa"] = "campeon"
    reg["campeon"] = version
    _evento(reg, "promocion", version, f"{motivo} (anterior: {anterior})")
    guardar(reg, ruta)
    return reg


def rechazar(version: str, motivo: str, ruta: Path = REGISTRO_PATH) -> dict:
    reg = leer(ruta)
    reg["modelos"][version]["etapa"] = "rechazado"
    _evento(reg, "rechazo", version, motivo)
    guardar(reg, ruta)
    return reg


def verificar_integridad(ruta: Path = REGISTRO_PATH, models_dir: Path = MODELS_DIR) -> list[str]:
    """Devuelve la lista de problemas (vacía si todo cuadra): artefacto faltante o hash distinto."""
    reg = leer(ruta)
    problemas = []
    if not reg.get("campeon"):
        problemas.append("El registro no tiene campeon")
    for v, m in reg["modelos"].items():
        if m["etapa"] in {"campeon", "archivado"}:
            art = models_dir / m["artefacto"]
            if not art.exists():
                problemas.append(f"{v}: falta {art.name}")
            elif sha256(art) != m["sha256"]:
                problemas.append(f"{v}: el hash de {art.name} no coincide con el registro")
    return problemas


def main(argv: list[str] | None = None) -> int:
    """CLI:  python -m demanda_ia.registro listar | verificar | promover <version> --motivo "..." """
    import argparse
    ap = argparse.ArgumentParser(prog="python -m demanda_ia.registro")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("listar")
    sub.add_parser("verificar")
    p = sub.add_parser("promover", help="Promueve (o regresa) una versión registrada a campeón")
    p.add_argument("version")
    p.add_argument("--motivo", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "listar":
        reg = leer()
        print(f"Campeon: {reg['campeon']}")
        for v, m in reg["modelos"].items():
            mt = m.get("metricas", {}).get("prueba_temporal", {})
            print(f"  {v:8s} {m['etapa']:10s} {m['artefacto']:28s} sha256={m['sha256'][:12]} "
                  f"WAPE_sem={mt.get('wape_semanal_pct', '-')} sesgo={mt.get('sesgo_semanal_pct', '-')}")
        return 0
    if args.cmd == "verificar":
        problemas = verificar_integridad()
        print("\n".join(problemas) if problemas else "Registro integro: artefactos presentes y hashes correctos")
        return 1 if problemas else 0
    promover(args.version, args.motivo)
    print(f"{args.version} es el nuevo campeon")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
