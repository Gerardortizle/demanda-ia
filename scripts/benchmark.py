"""Mide latencia de la API desplegada.  Uso: python scripts/benchmark.py [URL_BASE] [N]"""
import json
import statistics
import sys
import time
import urllib.request

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 200


def post(ruta, cuerpo):
    req = urllib.request.Request(URL + ruta, data=json.dumps(cuerpo).encode(), headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=60) as r:
        r.read()
    return (time.perf_counter() - t0) * 1000


def resumen(nombre, ms):
    ms = sorted(ms)
    p95 = ms[int(0.95 * (len(ms) - 1))]
    print(f"{nombre:<34} n={len(ms):<4} p50={statistics.median(ms):7.1f} ms  p95={p95:7.1f} ms  max={ms[-1]:7.1f} ms")


base = {"sucursal_id": "SUC-001", "sku": "SKU-0001", "fecha": "2026-11-04", "lag_7": 14, "media_7": 13.5, "media_28": 13.0}
post("/api/v1/pronostico", base)  # calentamiento
resumen("POST /pronostico (1 registro)", [post("/api/v1/pronostico", base) for _ in range(N)])
lote = {"registros": [dict(base, sucursal_id=f"SUC-{1 + i % 140:03d}", sku=f"SKU-{1 + i % 30:04d}") for i in range(1000)]}
resumen("POST /pronostico/lote (1000)", [post("/api/v1/pronostico/lote", lote) for _ in range(20)])
with urllib.request.urlopen(f"{URL}/api/v1/historial?sucursal_id=SUC-001&sku=SKU-0009&hasta=2026-11-01") as r:
    hist = json.loads(r.read())["ventas"]
reab = {"sucursal_id": "SUC-001", "sku": "SKU-0009", "fecha_inicio": "2026-11-02", "horizonte_dias": 14,
        "existencia_actual": 10, "historial_ventas": hist}
resumen("POST /reabasto (14 dias)", [post("/api/v1/reabasto", reab) for _ in range(50)])
# Proyección de la corrida nocturna: 140 sucursales x 30 SKU = 4 200 pronósticos
t0 = time.perf_counter()
regs = [dict(base, sucursal_id=f"SUC-{s:03d}", sku=f"SKU-{k:04d}") for s in range(1, 141) for k in range(1, 31)]
for i in range(0, len(regs), 1000):
    post("/api/v1/pronostico/lote", {"registros": regs[i:i + 1000]})
print(f"Corrida nocturna completa (4 200 pronosticos en lotes de 1000): {time.perf_counter() - t0:.2f} s")
