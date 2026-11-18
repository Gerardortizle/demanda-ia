"""Compuerta de CI para el modelo que se va a desplegar (corre en cada push y pull request).

Falla (código 1) si:
  - el registro no tiene campeón, falta un artefacto o su SHA-256 no coincide (artefacto alterado);
  - las métricas guardadas del campeón no cumplen config/umbrales.toml (alguien cambió un umbral
    o subió un modelo sin pasar por el pipeline);
  - la versión de scikit-learn del artefacto no es la fijada en requirements.txt.

    PYTHONPATH=src python scripts/verificar_modelo.py
"""
import json
import os
import re
import sys

from demanda_ia import registro
from demanda_ia.config import METADATA_PATH, RAIZ, cargar_umbrales
from demanda_ia.pipeline import compuertas

problemas = registro.verificar_integridad()
reg = registro.leer()
meta = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
if meta["version"] != reg["campeon"]:
    problemas.append(f"El artefacto servido ({meta['version']}) no es el campeon del registro ({reg['campeon']})")

gates = compuertas(meta["evaluacion"], cargar_umbrales())
problemas += [f"Compuerta {g['regla']}@{g['conjunto']}: {g['valor']} vs {g['limite']}" for g in gates if not g["paso"]]

req = (RAIZ / "requirements.txt").read_text(encoding="utf-8")
fijada = re.search(r"scikit-learn==([\d.]+)", req).group(1)
if meta["sklearn_version"] != fijada:
    problemas.append(f"Artefacto entrenado con scikit-learn {meta['sklearn_version']} pero requirements fija {fijada}")

lineas = [f"### Verificación del modelo campeón {reg['campeon']}", "",
          f"- Artefacto: `{reg['modelos'][reg['campeon']]['artefacto']}` · sha256 `{reg['modelos'][reg['campeon']]['sha256'][:12]}`",
          f"- Compuertas: {sum(g['paso'] for g in gates)}/{len(gates)} cumplidas",
          f"- Resultado: {'❌ ' + '; '.join(problemas) if problemas else '✅ listo para desplegar'}"]
print("\n".join(lineas))
if os.getenv("GITHUB_STEP_SUMMARY"):
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")
sys.exit(1 if problemas else 0)
