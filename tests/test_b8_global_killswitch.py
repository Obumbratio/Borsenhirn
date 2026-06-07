"""
B8 — e2e del kill-switch global contra borsenhirn_dev (gated).

Activa el freno global, confirma que el orquestador no corre ningún tenant, y
lo limpia. También prueba el endpoint admin con API key.
"""

from __future__ import annotations

import pytest

import config
import borsenhirn.db as bdb

if config.DB_NAME != "borsenhirn_dev":
    pytest.skip(
        f"B8 global killswitch requiere DB_NAME=borsenhirn_dev (actual: {config.DB_NAME!r}).",
        allow_module_level=True,
    )

pytestmark = pytest.mark.integration


def test_global_killswitch_flow():
    from borsenhirn.safety.global_killswitch import (
        trip_global, is_global_halt, clear_global)
    from borsenhirn.workers import run_all_tenants

    clear_global("pre-test", actor="test")   # estado limpio
    try:
        assert is_global_halt() is False
        trip_global("test halt", actor="test")
        assert is_global_halt() is True

        # el orquestador NO corre ningún tenant con el freno global activo
        ran = []
        res = run_all_tenants(lambda tid, creds: ran.append(tid))
        assert res == [{"status": "global_halt"}]
        assert ran == []
    finally:
        clear_global("test cleanup", actor="test")
        bdb.close_all_pools()
    assert is_global_halt() is False


def test_admin_endpoint_global_flow(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_API_KEY", "test-admin-key", raising=False)
    from fastapi.testclient import TestClient
    from borsenhirn.api.main import app
    from borsenhirn.safety.global_killswitch import clear_global

    c = TestClient(app)
    h = {"X-Admin-Key": "test-admin-key"}
    try:
        assert c.post("/admin/killswitch/global", params={"reason": "e2e"},
                      headers=h).json()["global_halt"] is True
        assert c.get("/admin/killswitch/global", headers=h).json()["global_halt"] is True
        assert c.post("/admin/killswitch/global/clear",
                      headers=h).json()["global_halt"] is False
    finally:
        clear_global("cleanup", actor="test")
        bdb.close_all_pools()
