"""
B5.4 — e2e del endpoint /me/audit contra borsenhirn_dev (gated).

Provisiona un tenant vía /me (que audita 'tenant.provisioned') y confirma que
GET /me/audit lo lista bajo RLS. Limpia en teardown.
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
        f"B5 audit endpoint requiere DB_NAME=borsenhirn_dev (actual: {config.DB_NAME!r}).",
        allow_module_level=True,
    )

pytestmark = pytest.mark.integration

SECRET = "secret-b5-audit"
CLERK_SUB = "user_b5_audit_e2e"


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
                    "DELETE FROM audit_log WHERE tenant_id IN "
                    "(SELECT tenant_id FROM tenants WHERE clerk_user_id=%s)", (CLERK_SUB,))
                cur.execute("DELETE FROM tenants WHERE clerk_user_id=%s", (CLERK_SUB,))
            conn.commit()
        bdb.close_all_pools()


def test_me_audit_lists_provision_event(client):
    hdr = {"Authorization": f"Bearer {_token()}"}
    # provisiona (audita tenant.provisioned)
    assert client.get("/me", headers=hdr).status_code == 200
    r = client.get("/me/audit", headers=hdr)
    assert r.status_code == 200
    actions = [e["action"] for e in r.json()["events"]]
    assert "tenant.provisioned" in actions


def test_me_audit_requires_auth(client):
    assert client.get("/me/audit").status_code == 401
