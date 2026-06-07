"""
Smoke test de la API real: importa borsenhirn.api.main y sus endpoints
públicos funcionan SIN redis ni sqlalchemy instalados (imports lazy).

Antes, importar api.main fallaba por `import redis` / `import sqlalchemy` a
nivel módulo (vía core.cache / core.database), aunque los endpoints de auth
(/me) no los usan. Ahora esos imports son lazy.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_api_main_imports_without_redis_or_sqlalchemy():
    # No debe lanzar ModuleNotFoundError al importar.
    from borsenhirn.api.main import app
    assert app.title == "Börsenhirn API"


def test_public_endpoints_ok():
    from borsenhirn.api.main import app
    client = TestClient(app)
    assert client.get("/").status_code == 200
    assert client.get("/health").status_code == 200


def test_me_route_is_registered():
    from borsenhirn.api.main import app
    paths = {r.path for r in app.routes if hasattr(r, "path")}
    assert "/me" in paths and "/me/trades/count" in paths
