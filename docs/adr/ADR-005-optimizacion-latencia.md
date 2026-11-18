# ADR-005 · Optimización de la latencia de /reabasto

**Estado:** aceptada

Al agregar el tercer modelo, el p50 de `/reabasto` (14 días) subió de 96 ms (Fase II) a 145 ms,
porque el pronóstico recursivo llamaba a los tres modelos en cada día. Solo el P50 alimenta las
ventanas de los días siguientes, así que el bucle ahora predice únicamente el P50 y el P90 y la
media se calculan al final en un solo lote. Resultado medido con `scripts/benchmark.py`:
**55 ms** (−62 %), con salida idéntica en 8 casos de comparación.
