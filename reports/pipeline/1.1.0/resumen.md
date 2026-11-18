## Pipeline de entrenamiento DEMANDA-IA 1.1.0

Commit `e3cc079` · huella de datos `8e5e72b7995f362c` · APROBADO

| Regla | Conjunto | Valor | Límite | Resultado |
|---|---|---|---|---|
| wape_semanal_max_pct | prueba_temporal | 17.79 | 22.0 | ✅ |
| sesgo_semanal_abs_max_pct | prueba_temporal | -2.859 | 15.0 | ✅ |
| mejora_min_vs_lag7_pct | prueba_temporal | 36.456 | 10.0 | ✅ |
| cobertura_p90_rango_pct | prueba_temporal | 88.79 | [85.0, 93.0] | ✅ |
| fill_rate_min_pct | prueba_temporal | 97.784 | 96.0 | ✅ |
| fill_rate_esenciales_min_pct | prueba_temporal | 97.967 | 97.0 | ✅ |
| razon_equidad_max | prueba_temporal | 1.223 | 1.25 | ✅ |
| wape_semanal_max_pct | sucursales_no_vistas | 19.298 | 22.0 | ✅ |
| sesgo_semanal_abs_max_pct | sucursales_no_vistas | -7.767 | 15.0 | ✅ |
| mejora_min_vs_lag7_pct | sucursales_no_vistas | 28.149 | 10.0 | ✅ |
| cobertura_p90_rango_pct | sucursales_no_vistas | 88.388 | [85.0, 93.0] | ✅ |
| fill_rate_min_pct | sucursales_no_vistas | 96.833 | 96.0 | ✅ |
| fill_rate_esenciales_min_pct | sucursales_no_vistas | 97.169 | 97.0 | ✅ |
| razon_equidad_max | sucursales_no_vistas | 1.238 | 1.25 | ✅ |
| diferencia_holdout_max_pts | ambos | 1.508 | 3.0 | ✅ |

### Campeón 1.0.0 vs retador 1.1.0

| Conjunto | WAPE sem. campeón | WAPE sem. retador | Sesgo campeón | Sesgo retador | Fill rate campeón | Fill rate retador |
|---|---|---|---|---|---|---|
| prueba_temporal | 19.7 % | 17.8 % | -11.3 % | -2.9 % | 97.8 % | 97.8 % |
| sucursales_no_vistas | 20.9 % | 19.3 % | -14.0 % | -7.8 % | 96.8 % | 96.8 % |
