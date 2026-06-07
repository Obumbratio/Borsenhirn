"""
B7 — e2e del flujo legal contra borsenhirn_dev (gated).

Provisiona un tenant, confirma que /me/trades/count da 451 (no acepto), acepta
terms+privacy, y entonces accede (200). Limpia child rows + tenant en teardown.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest

import config
import borsenhirn.db as bdb
from borsenhirn.auth import deps as auth_deps
from borsenhirn.auth.verifier import StaticTokenVerifier

if config.DB_NAME != "borsenhirn_dev":
    pytest.skip(
        f"B7 legal requiere DB_NAME=borsenhirn_dev (actual: {config.DB_NAME!r}).",
        allow_module_level=True,
    )

pytestmark = pytest.mark.integration

SECRET = "secret-b7-legal"
CLERK_SUB = "user_b7_legal_e2e"


def _token():
    return jwt.encode(
        {"sub": CLERK_SUB, "exp": datetime.now(timezone.utc) + timedelta(seconds=60)},
        SECRET, algorithm="HS256")


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from borsenhirn.api.main import app
    app.dependency_overrides[auth_deps.get_verifier] = lambda: StaticTokenVerifier(SECRET)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        with bdb.get_conn(role="admin") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM legal_acceptance WHERE tenant_id IN "
                    "(SELECT tenant_id FROM tenants WHERE clerk_user_id=%s)", (CLERK_SUB,))
                cur.execute(
                    "DELETE FROM audit_log WHERE tenant_id IN "
                    "(SELECT tenant_id FROM tenants WHERE clerk_user_id=%s)", (CLERK_SUB,))
                cur.execute("DELETE FROM tenants WHERE clerk_user_id=%s", (CLERK_SUB,))
            conn.commit()
        bdb.close_all_pools()


def test_legal_gating_flow(client):
    hdr = {"Authorization": f"Bearer {_token()}"}

    # /legal/current es público
    versions = client.get("/legal/current").json()["versions"]
    assert "terms" in versions and "privacy" in versions

    # provisiona (via /me) y NO acepta -> producto gated con 451
    assert client.get("/me", headers=hdr).status_code == 200
    assert client.get("/me/legal", headers=hdr).json()["compliant"] is False
    assert client.get("/me/trades/count", headers=hdr).status_code == 451

    # acepta ambos docs
    for doc, ver in versions.items():
        r = client.post("/me/legal/accept", headers=hdr,
                        json={"document": doc, "version": ver})
        assert r.status_code == 200

    # ahora compliant -> producto accesible
    assert client.get("/me/legal", headers=hdr).json()["compliant"] is True
    assert client.get("/me/trades/count", headers=hdr).status_code == 200


def test_accept_stale_version_409(client):
    hdr = {"Authorization": f"Bearer {_token()}"}
    client.get("/me", headers=hdr)
    r = client.post("/me/legal/accept", headers=hdr,
                    json={"document": "terms", "version": "1999-01-01"})
    assert r.status_code == 409
