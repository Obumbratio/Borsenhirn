"""
B3.4 — Tests de la dependency de FastAPI get_current_tenant (sin DB).

Monta get_current_tenant en una app MÍNIMA (no importa borsenhirn.api.main,
que acopla redis/sqlalchemy — subsistemas ajenos a auth). Con
dependency_overrides: verifier = StaticTokenVerifier, tenant_manager = fake.
Prueba 401s y el happy path sin tocar Postgres.

Los endpoints reales de api/main.py (/me, /me/trades/count) son wrappers finos
de esta misma dependency; su lógica queda cubierta acá + en el e2e gated.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from borsenhirn.auth import deps
from borsenhirn.auth.verifier import StaticTokenVerifier

SECRET = "dev-secret-para-deps"
FAKE_TID = "00000000-0000-0000-0000-0000000000fa"

# App mínima que monta la dependency real (sin api.main / redis / sqlalchemy).
mini_app = FastAPI()


@mini_app.get("/me")
def _me(tenant_id: str = Depends(deps.get_current_tenant)):
    return {"tenant_id": tenant_id}


@mini_app.get("/health")
def _health():
    return {"status": "ok"}


class _FakeTenant:
    def __init__(self, tid):
        self.tenant_id = tid


class _FakeManager:
    def provision_for_clerk_user(self, sub, email, name):
        return _FakeTenant(FAKE_TID)


def _token(sub="user_deps_1", exp_delta=60, **extra):
    payload = {"sub": sub,
               "exp": datetime.now(timezone.utc) + timedelta(seconds=exp_delta),
               **extra}
    return jwt.encode(payload, SECRET, algorithm="HS256")


@pytest.fixture
def client():
    mini_app.dependency_overrides[deps.get_verifier] = lambda: StaticTokenVerifier(SECRET)
    mini_app.dependency_overrides[deps.get_tenant_manager] = lambda: _FakeManager()
    try:
        yield TestClient(mini_app)
    finally:
        mini_app.dependency_overrides.clear()


def test_me_without_auth_is_401(client):
    assert client.get("/me").status_code == 401


def test_me_with_garbage_token_is_401(client):
    assert client.get("/me", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401


def test_me_with_non_bearer_scheme_is_401(client):
    assert client.get("/me", headers={"Authorization": "Basic abc"}).status_code == 401


def test_me_with_expired_token_is_401(client):
    r = client.get("/me", headers={"Authorization": f"Bearer {_token(exp_delta=-60)}"})
    assert r.status_code == 401


def test_me_with_valid_token_returns_tenant(client):
    r = client.get("/me", headers={"Authorization": f"Bearer {_token(email='u@x.com')}"})
    assert r.status_code == 200
    assert r.json()["tenant_id"] == FAKE_TID


def test_health_stays_public(client):
    assert client.get("/health").status_code == 200
