# ADR-004 · El modelo de media no cambia la política de pedido

**Estado:** aceptada

## Contexto
La Fase II encontró que el P50 subestima la suma semanal entre 11 y 14 %. Se entrenó un modelo
de media con pérdida Poisson (v1.1). Bajó el WAPE semanal de 19.7 % a 17.8 % y el sesgo de
-11.3 % a -2.9 % en la prueba temporal.

## Pregunta
¿Conviene calcular el pedido con la media en vez del P50?

## Evidencia (backtest de reabasto, `reports/frontera_reabasto.json`)
- Con el mismo factor de seguridad, la media pide más: excedente 31.8 % vs 24.4 % de la venta.
- Moviendo el factor k para igualar inventario, en la prueba temporal las dos curvas coinciden;
  en sucursales no vistas la media da **menos** servicio con el mismo excedente.
- Calibrar k por clase (esenciales 97.5 %, resto 96.5 %) con la prueba temporal bajaba el
  excedente, pero con la media el servicio en sucursales no vistas caía a 94.9 %, debajo de la meta
  de 96 % (con el P50 quedaba justo en 96.0 %, sin margen).

## Decisión
- El pedido sigue siendo P50 + 1.0 × √Σ(P90−P50)²: 97.8 % y 96.8 % de servicio, con
  esenciales en 98.0 % y 97.2 %.
- La media se publica aparte (`pronostico_media`, `demanda_media`) para planear compras y
  negociar con proveedores, que es donde el sesgo sí importa.
- El factor queda en `config/umbrales.toml` para ajustarlo con datos reales sin tocar código.
