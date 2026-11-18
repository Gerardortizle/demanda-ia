"""Alta inicial del registro de modelos (se corrió una sola vez al iniciar la Fase III).

Registra el artefacto de la Fase II (models/demanda_ia_v1.joblib, versión 1.0.0) como campeón,
re-evaluado con las métricas de negocio y equidad que se agregaron en la Fase III,
para que el primer retador se compare contra él en igualdad de condiciones.

    PYTHONPATH=src python scripts/registrar_v1.py
"""
import json

import joblib

from demanda_ia import registro
from demanda_ia.config import MODELS_DIR, cargar_umbrales
from demanda_ia.pipeline import _resumen_registro, compuertas
from demanda_ia.train import datos_entrenamiento, evaluar_modelos
from demanda_ia.validacion_datos import huella

ruta = MODELS_DIR / "demanda_ia_v1.joblib"
art = joblib.load(ruta)
datos = datos_entrenamiento()
res = evaluar_modelos({"p50": art["p50"], "p90": art["p90"], "media": None}, datos)
meta = {**art["meta"], "hiperparametros": {"cuantiles": "ver train.PARAMS_CUANTIL", "media": None}}
resumen = _resumen_registro(res, huella(datos["entrenamiento"]), meta, "fase-ii")
gates = compuertas(res, cargar_umbrales())
resumen["compuertas_fallidas"] = [g["regla"] + "@" + g["conjunto"] for g in gates if not g["paso"]]
registro.registrar("1.0.0", ruta, resumen, etapa="retador", detalle="alta inicial: modelo de la Fase II")
registro.promover("1.0.0", "campeon inicial (Fase II, desplegado en Cloud Run)")
print(json.dumps(resumen["metricas"], indent=2))
print("Compuertas fallidas:", resumen["compuertas_fallidas"] or "ninguna")
