## Monitoreo DEMANDA-IA · modelo 1.1.0 · escenario `alza_precios`

Alza general de precios de 15 % desde la semana 5 (fuera del rango de entrenamiento). Ventana 2026-08-03 a 2026-10-25, 30 sucursales.

**Estado: ALERTA** · WAPE semanal 19.73 % · sesgo 3.06 % · cobertura P90 (4 sem.) 91.65 %

Acción recomendada: investigar: hay deriva o inequidad sin degradacion confirmada del error

| Semana | WAPE | Sesgo | Cobertura P90 | Fill rate |
|---|---|---|---|---|
| 2026-08-03 | 19.23 % | -4.5 % | 89.03 % | 97.85 % |
| 2026-08-10 | 19.36 % | -3.96 % | 88.63 % | 97.43 % |
| 2026-08-17 | 19.03 % | -6.35 % | 88.49 % | 97.03 % |
| 2026-08-24 | 19.26 % | -6.2 % | 88.56 % | 96.95 % |
| 2026-08-31 | 21.11 % | 12.67 % | 94.08 % | 99.61 % |
| 2026-09-07 | 21.21 % | 11.31 % | 93.87 % | 99.43 % |
| 2026-09-14 | 21.97 % | 10.17 % | 93.4 % | 99.02 % |
| 2026-09-21 | 18.51 % | 5.95 % | 92.86 % | 99.02 % |
| 2026-09-28 | 18.96 % | 5.34 % | 91.68 % | 98.62 % |
| 2026-10-05 | 19.92 % | 7.88 % | 92.56 % | 98.87 % |
| 2026-10-12 | 19.66 % | 5.8 % | 91.27 % | 98.71 % |
| 2026-10-19 | 19.06 % | 4.82 % | 91.08 % | 98.52 % |

| Variable | PSI |
|---|---|
| precio_relativo | 6.041 |
| en_promocion | 0.0001 |
| dia_semana | 0.0 |
| es_quincena | 0.0031 |
| lag_7 | 0.0358 |
| media_7 | 0.0175 |
| media_28 | 0.0188 |
| pronostico | 0.0122 |
| venta_real | 0.0454 |

### Alertas
- [deriva_datos] ventana: PSI de precio_relativo = 6.041 > 0.25
- [equidad] ventana: Razon de WAPE peor/mejor quintil 1.253 > 1.25
