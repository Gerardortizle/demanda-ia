# Model card · DEMANDA-IA v1.1.0

Ficha del modelo campeón (respuesta al riesgo R14 de la Fase I: documentación obligatoria en cada liberación).

| Campo | Valor |
|---|---|
| Propósito | Pronóstico diario por SKU y sucursal y pedido sugerido para el resurtido nocturno de Farmacias Occidente Salud |
| Usuarios | ERP (corrida nocturna por lote), compradores y gerentes (interfaz web) |
| Fuera de alcance | Medicamentos controlados (aprobación humana), decisiones clínicas, datos de pacientes |
| Algoritmo | 3 × `HistGradientBoostingRegressor`: cuantil 0.5, cuantil 0.9 y media con pérdida Poisson |
| Variables | 15: categoría, tipo y estado de sucursal, tamaño, demanda base, precio relativo, promoción, calendario (día, mes, quincena, festivo), lag 7, media 7 y media 28 |
| Datos | Simulador determinista (2024-2025), 40 sucursales × 30 SKU para entrenar; huella SHA-256 `8e5e72b7995f362c…` |
| Validación | Prueba temporal oct-dic 2025 y 10 sucursales nunca vistas |
| Artefacto | `models/demanda_ia_1.1.0.joblib`, SHA-256 en `models/registro.json` |

## Desempeño (semanas completas)

| Métrica | Prueba temporal | Sucursales no vistas | Umbral |
|---|---|---|---|
| WAPE semanal (media) | 17.8 % | 19.3 % | ≤ 22 % |
| Sesgo semanal (media) | −2.9 % | −7.8 % | ±15 % |
| Mejora vs repetir la semana anterior | 36.5 % | 28.1 % | ≥ 10 % |
| Cobertura P90 | 88.8 % | 88.4 % | 85-93 % |
| Nivel de servicio simulado | 97.8 % | 96.8 % | ≥ 96 % |
| Servicio en esenciales | 98.0 % | 97.2 % | ≥ 97 % |
| Razón de equidad (WAPE peor/mejor quintil) | 1.22 | 1.24 | ≤ 1.25 |

## Limitaciones conocidas
- Datos sintéticos: las métricas validan el método, no el desempeño con ventas reales.
- No extrapola precios por encima de lista (la API avisa y acota) ni choques de demanda grandes:
  en el escenario de brote respiratorio el WAPE semanal llegó a 35 % y el monitoreo lo alertó.
- La razón de equidad en sucursales no vistas se calcula con 2 sucursales por quintil.
- El P50 sigue subestimando la suma semanal; por eso el pedido suma stock de seguridad (ADR-004).

## Monitoreo y responsables
Semanal (`monitoreo.yml`), reentrenamiento mensual o por alerta (`entrenamiento.yml`),
promoción solo por pull request aprobado. Responsable técnico: José Gerardo Ortiz Leñero.
