# Prueba de humo para Windows PowerShell.  Uso: .\scripts\smoke_test.ps1 [-Url http://localhost:8000]
param([string]$Url = "http://localhost:8000")
$ErrorActionPreference = "Stop"
$fallas = 0
function Revisar($nombre, $bloque) {
  try { $r = & $bloque; Write-Host "OK    $nombre" -ForegroundColor Green; return $r }
  catch { Write-Host "FALLA $nombre -> $($_.Exception.Message)" -ForegroundColor Red; $script:fallas++ }
}
Revisar "GET /api/v1/salud" { Invoke-RestMethod "$Url/api/v1/salud" } | Format-List
Revisar "GET /api/v1/catalogo" { (Invoke-RestMethod "$Url/api/v1/catalogo").limites } | Format-List
$p = @{ sucursal_id="SUC-001"; sku="SKU-0005"; fecha="2026-12-15"; lag_7=12; media_7=11; media_28=10 } | ConvertTo-Json
Revisar "POST /api/v1/pronostico" { Invoke-RestMethod "$Url/api/v1/pronostico" -Method Post -ContentType "application/json" -Body $p } | Format-List
$h = Invoke-RestMethod "$Url/api/v1/historial?sucursal_id=SUC-001&sku=SKU-0009&hasta=2026-11-01"
$r = @{ sucursal_id="SUC-001"; sku="SKU-0009"; fecha_inicio="2026-11-02"; horizonte_dias=7; existencia_actual=15; historial_ventas=$h.ventas } | ConvertTo-Json
Revisar "POST /api/v1/reabasto" { Invoke-RestMethod "$Url/api/v1/reabasto" -Method Post -ContentType "application/json" -Body $r } |
  Select-Object sucursal_id, sku, demanda_esperada, stock_seguridad, pedido_sugerido | Format-List
try {
  $malo = @{ sucursal_id="SUC-001"; sku="SKU-9999"; fecha="2026-12-15"; lag_7=1; media_7=1; media_28=1 } | ConvertTo-Json
  Invoke-RestMethod "$Url/api/v1/pronostico" -Method Post -ContentType "application/json" -Body $malo | Out-Null
  Write-Host "FALLA SKU invalido deberia dar 422" -ForegroundColor Red; $fallas++
} catch { Write-Host "OK    SKU invalido rechazado (422)" -ForegroundColor Green }
if ($fallas -eq 0) { Write-Host "Prueba de humo superada" } else { Write-Host "$fallas prueba(s) fallaron"; exit 1 }
