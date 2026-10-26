import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from demanda_ia.api import app  # noqa: E402


@pytest.fixture(scope="session")
def cliente():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def base():
    return {"sucursal_id": "SUC-001", "sku": "SKU-0001", "fecha": "2026-11-04",
            "lag_7": 14, "media_7": 13.5, "media_28": 13.0}


@pytest.fixture
def historial(cliente):
    r = cliente.get("/api/v1/historial", params={"sucursal_id": "SUC-001", "sku": "SKU-0009", "hasta": "2026-11-01"})
    return r.json()["ventas"]
