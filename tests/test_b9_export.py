"""
B9.2 — e2e del export por tenant contra borsenhirn_dev (gated).

Provisiona (audita tenant.provisioned), exporta, y confirma que el export trae
las tablas del tenant (incluido audit_log) y EXCLUYE user_credentials.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest

import config
import borsenhirn.db as bdb
from borsenhirn.backups import export_tenant, EXCLUDED_TABLES
from borsenhirn.auth import deps as auth_deps
from borsenhirn.auth.verifier import StaticTokenVerifier

if config.DB_NAME != "borsenhirn_dev":
    pytest.skip(
        f"B9 export requiere DB_NAME=borsenhirn_dev (actual: {config.DB_NAME!r}).",
        allow_module_level=True,
    )

pytestmark = pytest.mark.integration

SECRET = "secret-b9-export"
CLERK_SUB = "user_b9_export_e2e"


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
                cur.execute("DELETE FROM audit_log WHERE tenant_id IN "
                            "(SELECT tenant_id FROM tenants WHERE clerk_user_id=%s)", (CLERK_SUB,))
                cur.execute("DELETE FROM tenants WHERE clerk_user_id=%s", (CLERK_SUB,))
            conn.commit()
        bdb.close_all_pools()


def test_export_contains_tenant_data_excludes_secrets(client):
    hdr = {"Authorization": f"Bearer {_token()}"}
    tid = client.get("/me", headers=hdr).json()["tenant_id"]   # provisiona (audita)

    exp = export_tenant(tid)
    assert exp["tenant_id"] == tid
    # trae tablas tenant-scoped, incluido el audit del provision
    assert "audit_log" in exp["tables"]
    assert any(e.get("action") == "tenant.provisioned" for e in exp["tables"]["audit_log"])
    # NO exporta secretos
    for excl in EXCLUDED_TABLES:
        assert excl not in exp["tables"]


def test_me_export_endpoint(client):
    hdr = {"Authorization": f"Bearer {_token()}"}
    client.get("/me", headers=hdr)
    r = client.get("/me/export", headers=hdr)
    assert r.status_code == 200
    body = r.json()
    assert "tables" in body and "user_credentials" not in body["tables"]


def test_me_export_requires_auth(client):
    assert client.get("/me/export").status_code == 401
