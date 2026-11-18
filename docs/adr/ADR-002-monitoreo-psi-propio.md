# ADR-002 · Monitoreo con PSI y métricas propias en lugar de Evidently

**Estado:** aceptada

## Contexto
Se necesita detectar degradación del pronóstico y deriva de los datos cada semana.

## Decisión
Implementar en `src/demanda_ia/monitoreo.py` (≈250 líneas) el PSI por variable, el WAPE/sesgo
semanal, la cobertura del P90, el nivel de servicio simulado y la equidad por quintil, con
umbrales en `config/umbrales.toml`. Se ejecuta en GitHub Actions (`monitoreo.yml`).

## Razones
- Las métricas que importan al negocio (WAPE semanal ≤ 22 %, alerta > 26 %, nivel de servicio,
  razón de equidad ≤ 1.25) salen de la Fase I y no vienen en las librerías genéricas.
- Evidently agrega cientos de dependencias y su API cambió varias veces entre versiones; para
  siete variables numéricas el PSI es una fórmula de una línea, probada en `tests/`.
- Los atributos fijos de sucursal se excluyen del PSI porque reflejan qué sucursales están en la
  muestra, no un cambio de comportamiento (hallazgo de la primera corrida: PSI 0.43 falso).

## Consecuencias
Si el monitoreo crece (datos de texto, imágenes o cientos de variables) conviene migrar a
Evidently o a Vertex AI Model Monitoring.
