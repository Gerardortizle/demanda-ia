## Monitoreo DEMANDA-IA · modelo 1.1.0 · escenario `brote_respiratorio`

Brote respiratorio: antigripales y analgésicos +80 % desde la semana 5. Ventana 2026-08-03 a 2026-10-25, 30 sucursales.

**Estado: ALERTA** · WAPE semanal 27.73 % · sesgo -19.85 % · cobertura P90 (4 sem.) 82.65 %

Acción recomendada: reentrenar: lanzar el workflow 'entrenamiento' y evaluar al retador contra el campeon

| Semana | WAPE | Sesgo | Cobertura P90 | Fill rate |
|---|---|---|---|---|
| 2026-08-03 | 19.23 % | -4.5 % | 89.03 % | 97.85 % |
| 2026-08-10 | 19.36 % | -3.96 % | 88.63 % | 97.43 % |
| 2026-08-17 | 19.03 % | -6.35 % | 88.49 % | 97.03 % |
| 2026-08-24 | 19.26 % | -6.2 % | 88.56 % | 96.95 % |
| 2026-08-31 | 35.14 % | -29.08 % | 77.54 % | 80.11 % |
| 2026-09-07 | 32.35 % | -26.5 % | 79.19 % | 84.92 % |
| 2026-09-14 | 31.02 % | -24.18 % | 82.4 % | 87.55 % |
| 2026-09-21 | 29.13 % | -23.97 % | 83.43 % | 90.7 % |
| 2026-09-28 | 29.69 % | -24.01 % | 82.65 % | 89.46 % |
| 2026-10-05 | 29.08 % | -22.89 % | 83.32 % | 89.78 % |
| 2026-10-12 | 29.29 % | -23.98 % | 82.32 % | 90.23 % |
| 2026-10-19 | 30.49 % | -25.56 % | 82.32 % | 89.64 % |

| Variable | PSI |
|---|---|
| precio_relativo | 0.0 |
| en_promocion | 0.0001 |
| dia_semana | 0.0 |
| es_quincena | 0.0031 |
| lag_7 | 0.0273 |
| media_7 | 0.0474 |
| media_28 | 0.032 |
| pronostico | 0.0049 |
| venta_real | 0.0357 |

### Alertas
- [desempeno] 2026-08-31: WAPE semanal 35.14 % > 26.0 %
- [sesgo] 2026-08-31: Sesgo semanal -29.08 % (limite +/-15.0 %)
- [desempeno] 2026-09-07: WAPE semanal 32.35 % > 26.0 %
- [sesgo] 2026-09-07: Sesgo semanal -26.5 % (limite +/-15.0 %)
- [desempeno] 2026-09-14: WAPE semanal 31.02 % > 26.0 %
- [sesgo] 2026-09-14: Sesgo semanal -24.18 % (limite +/-15.0 %)
- [desempeno] 2026-09-21: WAPE semanal 29.13 % > 26.0 %
- [sesgo] 2026-09-21: Sesgo semanal -23.97 % (limite +/-15.0 %)
- [desempeno] 2026-09-28: WAPE semanal 29.69 % > 26.0 %
- [sesgo] 2026-09-28: Sesgo semanal -24.01 % (limite +/-15.0 %)
- [desempeno] 2026-10-05: WAPE semanal 29.08 % > 26.0 %
- [sesgo] 2026-10-05: Sesgo semanal -22.89 % (limite +/-15.0 %)
- [desempeno] 2026-10-12: WAPE semanal 29.29 % > 26.0 %
- [sesgo] 2026-10-12: Sesgo semanal -23.98 % (limite +/-15.0 %)
- [desempeno] 2026-10-19: WAPE semanal 30.49 % > 26.0 %
- [sesgo] 2026-10-19: Sesgo semanal -25.56 % (limite +/-15.0 %)
- [calibracion] ultimas 4: Cobertura P90 promedio 82.7 % < 85.0 %
