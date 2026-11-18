# ADR-001 · Registro de modelos en Git + MLflow para experimentos

**Estado:** aceptada (Fase III, nov 2026)

## Contexto
La rúbrica pide versionado de modelos y artefactos. En la Fase II el modelo era un archivo
(`models/demanda_ia_v1.joblib`) sin registro de qué datos, código y métricas lo produjeron, y
cambiarlo requería editar el Dockerfile.

## Decisión
1. `models/registro.json`, versionado en Git, es la **fuente de verdad del despliegue**: lista cada
   versión con su artefacto, SHA-256, huella de datos, commit, hiperparámetros, métricas y etapa
   (`campeon`, `retador`, `archivado`, `rechazado`). La API carga el campeón al arrancar.
2. **MLflow** (backend SQLite) registra cada corrida del pipeline y de la búsqueda de
   hiperparámetros para comparar experimentos. La base se publica como artefacto del workflow.

## Alternativas descartadas
- *Solo MLflow Model Registry:* necesita un servidor de tracking permanente (costo y otra pieza
  que operar) y separa el estado del modelo del estado del código. Con GitOps, el modelo que
  corre debe poder leerse en un commit.
- *DVC para datos:* los datos son sintéticos y se regeneran de forma determinista desde el código
  y la semilla. Se registra la huella SHA-256 del dataset en cada versión, que da la trazabilidad
  sin un remoto de almacenamiento. Con datos reales del ERP, DVC o snapshots en el data lake
  serían necesarios (ver documento técnico, sección de limitaciones).

## Consecuencias
- Promover o regresar un modelo es un commit revisable (`python -m demanda_ia.registro promover`).
- El CI verifica el hash de cada artefacto: un `.joblib` alterado o subido a mano rompe el build.
