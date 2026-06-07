"""
B3.3 — Tests del ClerkJWKSVerifier (RS256 + JWKS) y del factory.

Sin Clerk vivo ni red: se genera una RSA keypair en el test, se firma un JWT
RS256, y se inyecta un jwk_client fake que devuelve la clave pública. Cubre el
mismo contrato que el verifier real contra el JWKS de Clerk.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from borsenhirn.auth import (
    ClerkJWKSVerifier,
    StaticTokenVerifier,
    AuthError,
    build_verifier_from_env,
)

ISSUER = "https://clerk.miapp.com"
JWKS_URL = "https://clerk.miapp.com/.well-known/jwks.json"


@pytest.fixture(scope="module")
def rsa_keys():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return priv, priv.public_key()


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKClient:
    """Devuelve siempre la clave pública dada (simula el JWKS de Clerk)."""
    def __init__(self, public_key):
        self._pub = public_key
    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey(self._pub)


def _make_rs256(priv, *, sub="user_clerk_1", iss=ISSUER, exp_delta=60, **extra):
    payload = {"sub": sub, "iss": iss,
               "exp": datetime.now(timezone.utc) + timedelta(seconds=exp_delta),
               **extra}
    return jwt.encode(payload, priv, algorithm="RS256", headers={"kid": "test-kid"})


def _verifier(pub, **kw):
    return ClerkJWKSVerifier(JWKS_URL, ISSUER, jwk_client=_FakeJWKClient(pub), **kw)


# ── ClerkJWKSVerifier ───────────────────────────────────────────

def test_valid_rs256_token(rsa_keys):
    priv, pub = rsa_keys
    tok = _make_rs256(priv, email="u@x.com", name="Uri")
    claims = _verifier(pub).verify(tok)
    assert claims.sub == "user_clerk_1"
    assert claims.email == "u@x.com"


def test_wrong_issuer_rejected(rsa_keys):
    priv, pub = rsa_keys
    tok = _make_rs256(priv, iss="https://evil.com")
    with pytest.raises(AuthError):
        _verifier(pub).verify(tok)


def test_expired_rejected(rsa_keys):
    priv, pub = rsa_keys
    tok = _make_rs256(priv, exp_delta=-60)
    with pytest.raises(AuthError):
        _verifier(pub).verify(tok)


def test_bad_signature_rejected(rsa_keys):
    priv, pub = rsa_keys
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    tok = _make_rs256(other)              # firmado con otra clave
    with pytest.raises(AuthError):        # se verifica contra `pub`
        _verifier(pub).verify(tok)


def test_audience_enforced(rsa_keys):
    priv, pub = rsa_keys
    ok = _make_rs256(priv, aud="borsenhirn-api")
    assert _verifier(pub, audience="borsenhirn-api").verify(ok).sub == "user_clerk_1"
    with pytest.raises(AuthError):
        _verifier(pub, audience="borsenhirn-api").verify(_make_rs256(priv))


def test_constructor_validates_config():
    with pytest.raises(ValueError):
        ClerkJWKSVerifier("", ISSUER)
    with pytest.raises(ValueError):
        ClerkJWKSVerifier(JWKS_URL, "")


# ── build_verifier_from_env (factory) ───────────────────────────

@pytest.fixture(autouse=True)
def _clean_auth_env(monkeypatch):
    for v in ("AUTH_VERIFIER", "AUTH_DEV_SECRET", "AUTH_DEV_ISSUER",
              "AUTH_DEV_AUDIENCE", "CLERK_JWKS_URL", "CLERK_ISSUER", "CLERK_AUDIENCE"):
        monkeypatch.delenv(v, raising=False)
    yield


def test_factory_static_default(monkeypatch):
    monkeypatch.setenv("AUTH_DEV_SECRET", "x" * 16)
    v = build_verifier_from_env()
    assert isinstance(v, StaticTokenVerifier)


def test_factory_static_requires_secret(monkeypatch):
    monkeypatch.setenv("AUTH_VERIFIER", "static")
    with pytest.raises(ValueError):
        build_verifier_from_env()


def test_factory_clerk(monkeypatch):
    monkeypatch.setenv("AUTH_VERIFIER", "clerk")
    monkeypatch.setenv("CLERK_JWKS_URL", JWKS_URL)
    monkeypatch.setenv("CLERK_ISSUER", ISSUER)
    v = build_verifier_from_env()
    assert isinstance(v, ClerkJWKSVerifier)
    assert v.name == "clerk"


def test_factory_unknown_kind(monkeypatch):
    monkeypatch.setenv("AUTH_VERIFIER", "magic")
    with pytest.raises(ValueError):
        build_verifier_from_env()
