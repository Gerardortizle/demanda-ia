#!/usr/bin/env sh
# Prueba de humo contra un despliegue de DEMANDA-IA (local, contenedor o nube).
# Uso: ./scripts/smoke_test.sh [URL_BASE]     (por defecto http://localhost:8000)
set -eu
URL="${1:-http://localhost:8000}"
FALLAS=0

revisar() {  # nombre, código esperado, comando curl (args)
  nombre="$1"; esperado="$2"; shift 2
  codigo=$(curl -s -o /tmp/smoke_cuerpo.json -w "%{http_code}" "$@")
  if [ "$codigo" = "$esperado" ]; then
    echo "OK    [$codigo] $nombre"
  else
    echo "FALLA [$codigo != $esperado] $nombre"; cat /tmp/smoke_cuerpo.json; echo
    FALLAS=$((FALLAS + 1))
  fi
}

J="Content-Type: application/json"
revisar "GET  /api/v1/salud"              200 "$URL/api/v1/salud"
revisar "GET  /api/v1/modelo"             200 "$URL/api/v1/modelo"
revisar "GET  /api/v1/catalogo"           200 "$URL/api/v1/catalogo"
revisar "GET  / (frontend)"               200 "$URL/"
revisar "GET  /docs (Swagger)"            200 "$URL/docs"
revisar "POST /api/v1/pronostico"         200 -X POST -H "$J" "$URL/api/v1/pronostico" \
  -d '{"sucursal_id":"SUC-001","sku":"SKU-0005","fecha":"2026-12-15","lag_7":12,"media_7":11,"media_28":10}'
revisar "POST /api/v1/pronostico/lote"    200 -X POST -H "$J" "$URL/api/v1/pronostico/lote" \
  -d '{"registros":[{"sucursal_id":"SUC-001","sku":"SKU-0001","fecha":"2026-11-04","lag_7":14,"media_7":13,"media_28":13},{"sucursal_id":"SUC-002","sku":"SKU-0012","fecha":"2026-11-15","lag_7":8,"media_7":7,"media_28":7}]}'
HIST=$(curl -s "$URL/api/v1/historial?sucursal_id=SUC-001&sku=SKU-0009&hasta=2026-11-01" | sed -n 's/.*"ventas":\(\[[^]]*\]\).*/\1/p')
revisar "POST /api/v1/reabasto"           200 -X POST -H "$J" "$URL/api/v1/reabasto" \
  -d "{\"sucursal_id\":\"SUC-001\",\"sku\":\"SKU-0009\",\"fecha_inicio\":\"2026-11-02\",\"horizonte_dias\":7,\"existencia_actual\":15,\"historial_ventas\":$HIST}"
cat /tmp/smoke_cuerpo.json; echo
revisar "POST pronostico SKU invalido"    422 -X POST -H "$J" "$URL/api/v1/pronostico" \
  -d '{"sucursal_id":"SUC-001","sku":"SKU-9999","fecha":"2026-12-15","lag_7":1,"media_7":1,"media_28":1}'

echo "-----"
[ "$FALLAS" -eq 0 ] && echo "Prueba de humo superada" || { echo "$FALLAS prueba(s) fallaron"; exit 1; }
