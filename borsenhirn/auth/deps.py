"""
Dependencies de FastAPI para auth (B3.4).

Atan: extraer Bearer token -> verificar (TokenVerifier) -> resolver/provisionar
el tenant (TenantManager) -> devolver tenant_id para que el handler corra sus
queries bajo el RLS context correcto.

Todo es inyectable vía `app.dependency_overrides` para testear sin Clerk vivo
ni DB (override de get_verifier / get_tenant_manager).
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException, status

import borsenhirn.db as bdb
from borsenhirn.auth.verifier import (
    AuthError,
    TokenVerifier,
    build_verifier_from_env,
)
from borsenhirn.tenancy.management import TenantManager


# ── Verifier (singleton lazy desde env) ─────────────────────────

_verifier: Optional[TokenVerifier] = None


def get_verifier() -> TokenVerifier:
    """TokenVerifier construido desde env (AUTH_VERIFIER). Cacheado por proceso."""
    global _verifier
    if _verifier is None:
        _verifier = build_verifier_from_env()
    return _verifier


def reset_verifier() -> None:
    """Resetea el singleton (tests / cambio de config)."""
    global _verifier
    _verifier = None


# ── TenantManager sobre el pool admin (provisión escribe en tenants) ──

def get_admin_conn():
    """Conn admin para la request; vuelve al pool al terminar (sin leak, B7)."""
    with bdb.get_conn(role="admin") as conn:
        yield conn


def get_tenant_manager(conn=Depends(get_admin_conn)) -> TenantManager:
    return TenantManager(get_conn=lambda: conn)


# ── Dependency principal ────────────────────────────────────────

def _extract_bearer(authorization: Optional[str]) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="falta header Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token vacío",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


def get_current_tenant(
    authorization: Optional[str] = Header(default=None),
    verifier: TokenVerifier = Depends(get_verifier),
    tm: TenantManager = Depends(get_tenant_manager),
) -> str:
    """
    Verifica el JWT y devuelve el `tenant_id` del usuario (provisionado lazy).
    Lanza 401 si el token falta o es inválido.
    """
    token = _extract_bearer(authorization)
    try:
        claims = verifier.verify(token)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"token inválido: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    tenant = tm.provision_for_clerk_user(
        claims.sub,
        claims.email_for_provisioning(),
        claims.name_for_provisioning(),
    )
    return tenant.tenant_id


__all__ = [
    "get_verifier",
    "reset_verifier",
    "get_admin_conn",
    "get_tenant_manager",
    "get_current_tenant",
]
