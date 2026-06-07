"""
B8 — Tests de auth del endpoint admin del kill-switch global (sin DB).
Solo los caminos 403 (la auth falla antes de tocar la DB).
"""

from __future__ import annotations

import config
from fastapi.testclient import TestClient


def _client():
    from borsenhirn.api.main import app
    return TestClient(app)


def test_admin_disabled_when_no_key(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_API_KEY", "", raising=False)
    assert _client().get("/admin/killswitch/global").status_code == 403


def test_admin_403_without_key(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_API_KEY", "s3cret", raising=False)
    assert _client().get("/admin/killswitch/global").status_code == 403


def test_admin_403_wrong_key(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_API_KEY", "s3cret", raising=False)
    r = _client().get("/admin/killswitch/global", headers={"X-Admin-Key": "wrong"})
    assert r.status_code == 403
