"""
B3.2 — Tests del TokenVerifier (StaticTokenVerifier HS256).

Puro: sin DB ni red. Mintea JWTs propios con pyjwt y verifica el contrato
(firma + exp + claims). Corren en la baseline.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from borsenhirn.auth import StaticTokenVerifier, AuthError, Claims

SECRET = "dev-secret-para-tests"


def make_token(
    secret: str = SECRET,
    *,
    sub: str = "user_abc123",
    exp_delta: int = 60,
    include_exp: bool = True,
    include_sub: bool = True,
    **extra,
) -> str:
    payload = dict(extra)
    if include_sub:
        payload["sub"] = sub
    if include_exp:
        payload["exp"] = datetime.now(timezone.utc) + timedelta(seconds=exp_delta)
    return jwt.encode(payload, secret, algorithm="HS256")


def test_valid_token_returns_claims():
    v = StaticTokenVerifier(SECRET)
    tok = make_token(sub="user_x", email="u@x.com", name="Uri")
    claims = v.verify(tok)
    assert isinstance(claims, Claims)
    assert claims.sub == "user_x"
    assert claims.email == "u@x.com"
    assert claims.name == "Uri"


def test_expired_token_raises():
    v = StaticTokenVerifier(SECRET)
    tok = make_token(exp_delta=-60)   # ya expirado
    with pytest.raises(AuthError):
        v.verify(tok)


def test_bad_signature_raises():
    v = StaticTokenVerifier(SECRET)
    tok = make_token(secret="otro-secret")
    with pytest.raises(AuthError):
        v.verify(tok)


def test_missing_sub_raises():
    v = StaticTokenVerifier(SECRET)
    tok = make_token(include_sub=False)
    with pytest.raises(AuthError):
        v.verify(tok)


def test_missing_exp_raises():
    v = StaticTokenVerifier(SECRET)
    tok = make_token(include_exp=False)
    with pytest.raises(AuthError):
        v.verify(tok)


def test_issuer_enforced():
    v = StaticTokenVerifier(SECRET, issuer="https://clerk.miapp.com")
    ok = make_token(iss="https://clerk.miapp.com")
    assert v.verify(ok).sub == "user_abc123"
    bad = make_token(iss="https://evil.com")
    with pytest.raises(AuthError):
        v.verify(bad)


def test_audience_enforced():
    v = StaticTokenVerifier(SECRET, audience="borsenhirn-api")
    ok = make_token(aud="borsenhirn-api")
    assert v.verify(ok).sub == "user_abc123"
    bad = make_token()   # sin aud
    with pytest.raises(AuthError):
        v.verify(bad)


def test_empty_secret_rejected():
    with pytest.raises(ValueError):
        StaticTokenVerifier("")


# ── Claims helpers (fallbacks de provisión, D3) ────────────────

def test_email_for_provisioning_uses_email_when_present():
    c = Claims(sub="user_1", email="real@x.com")
    assert c.email_for_provisioning() == "real@x.com"


def test_email_for_provisioning_falls_back_to_sub():
    c = Claims(sub="user_1")
    assert c.email_for_provisioning() == "user_1@clerk.local"


def test_name_for_provisioning_fallback_chain():
    assert Claims(sub="s", email="e@x.com", name="N").name_for_provisioning() == "N"
    assert Claims(sub="s", email="e@x.com").name_for_provisioning() == "e@x.com"
    assert Claims(sub="s").name_for_provisioning() == "s"
