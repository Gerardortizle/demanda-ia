# Cambios

## 1.1.0 · Fase III (noviembre 2026) · MLOps y GitOps
- Pipeline de entrenamiento con contrato de datos (14 reglas), 15 compuertas de calidad y comparación campeón vs retador (`demanda_ia.pipeline`).
- Registro de modelos versionado en Git (`models/registro.json`) con SHA-256, huella de datos y commit; seguimiento de experimentos en MLflow.
- Nuevo modelo de media (Poisson): WAPE semanal 19.7 % → 17.8 %, sesgo −11.3 % → −2.9 %. Campos nuevos `pronostico_media` y `demanda_media` (compatibles hacia atrás).
- Backtest de la política de pedido y métrica de equidad por quintil de sucursal.
- API: auditoría por inferencia con `X-Request-ID`, `/api/v1/monitoreo`, `/api/v1/auditoria` y `/metrics` (Prometheus).
- Monitoreo por lotes semanal con PSI, desempeño, calibración y equidad, y escenarios de prueba.
- Workflows: `ci.yml` (lint, pruebas, compuerta del modelo, contenedor, Trivy, GHCR), `entrenamiento.yml`, `monitoreo.yml`, `cd.yml` (Cloud Run GitOps con staging y producción).
- `/reabasto` 62 % más rápido (145 → 55 ms p50).
- 45 → 69 pruebas automatizadas.

## 1.0.0 · Fase II (noviembre 2026)
- API FastAPI, frontend, contenedor multi-etapa, CI con prueba de humo y despliegue en Cloud Run.
