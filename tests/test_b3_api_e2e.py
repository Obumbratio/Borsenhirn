"""
B3.4 — e2e del backend de auth contra borsenhirn_dev (gated).

Flujo real: token (StaticTokenVerifier) -> get_current_tenant provisiona el
tenant (pool admin real) -> endpoint tenant-scoped cuenta bajo RLS context.

App mínima (api.main acopla redis/sqlalchemy, ajenos a auth). Limpia el tenant
provisionado en teardown. Gated por RUN_DB_INTEGRATION + DB_NAME=borsenhirn_dev.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import config
import borsenhirn.db as bdb
from borsenhirn.auth import deps
from borsenhirn.auth.verifier import StaticTokenVerifier

if config.DB_NAME != "borsenhirn_dev":
    pytest.skip(
        f"B3 e2e requiere DB_NAME=borsenhirn_dev (actual: {config.DB_NAME!r}).",
        allow_module_level=True,
    )

pytestmark = pytest.mark.integration

SECRET = "e2e-secret-b3"
CLERK_SUB = "user_b3_apie2e_xyz"

mini = FastAPI()


@mini.get("/me")
def _me(tenant_id: str = Depends(deps.get_current_tenant)):
    return {"tenant_id": tenant_id}


@mini.get("/me/trades/count")
def _count(tenant_id: str = Depends(deps.get_current_tenant)):
    with bdb.get_conn(role="app") as conn, bdb.set_tenant(conn, tenant_id):
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM bot_trade_outcomes")
            n = cur.fetchone()[0]
    return {"tenant_id": tenant_id, "trades": n}


def _token(sub=CLERK_SUB, exp_delta=60, **extra):
    payload = {"sub": sub,
               "exp": datetime.now(timezone.utc) + timedelta(seconds=exp_delta),
               **extra}
    return jwt.encode(payload, SECRET, algorithm="HS256")


@pytest.fixture
def client():
    # Solo override del verifier; el tenant_manager usa el pool admin REAL.
    mini.dependency_overrides[deps.get_verifier] = lambda: StaticTokenVerifier(SECRET)
    try:
        yield TestClient(mini)
    finally:
        mini.dependency_overrides.clear()
        # cleanup: borrar child rows (audit_log del provision) + el tenant
        with bdb.get_conn(role="admin") as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM audit_log WHERE tenant_id IN "
                            "(SELECT tenant_id FROM tenants WHERE clerk_user_id=%s)", (CLERK_SUB,))
                cur.execute("DELETE FROM tenants WHERE clerk_user_id = %s", (CLERK_SUB,))
            conn.commit()
        bdb.close_all_pools()


def test_me_provisions_tenant(client):
    hdr = {"Authorization": f"Bearer {_token(email='e2e@test.local')}"}
    r = client.get("/me", headers=hdr)
    assert r.status_code == 200
    tid = r.json()["tenant_id"]
    assert tid
    # idempotente: segundo request -> mismo tenant
    r2 = client.get("/me", headers=hdr)
    assert r2.json()["tenant_id"] == tid


def test_tenant_scoped_count_under_rls(client):
    hdr = {"Authorization": f"Bearer {_token(email='e2e@test.local')}"}
    r = client.get("/me/trades/count", headers=hdr)
    assert r.status_code == 200
    # tenant nuevo => 0 trades (RLS lo aísla del default que tiene 31)
    assert r.json()["trades"] == 0


def test_no_token_401(client):
    assert client.get("/me").status_code == 401
