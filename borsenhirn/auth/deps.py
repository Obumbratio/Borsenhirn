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


def _resolved_tenant(
    authorization: Optional[str] = Header(default=None),
    verifier: TokenVerifier = Depends(get_verifier),
    tm: TenantManager = Depends(get_tenant_manager),
):
    """Verifica el JWT y provisiona/resuelve el Tenant (objeto). 401 si inválido."""
    token = _extract_bearer(authorization)
    try:
        claims = verifier.verify(token)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"token inválido: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Actor para el audit log (B5): quién hace la request.
    try:
        from borsenhirn.audit import set_actor
        set_actor(claims.sub)
    except Exception:   # pragma: no cover
        pass
    return tm.provision_for_clerk_user(
        claims.sub,
        claims.email_for_provisioning(),
        claims.name_for_provisioning(),
    )


def get_current_tenant(tenant=Depends(_resolved_tenant)) -> str:
    """`tenant_id` de cualquier usuario autenticado (SIN gating de status).

    Para endpoints accesibles aun con suscripción inactiva (p.ej. billing,
    para que un tenant suspendido pueda volver a pagar)."""
    return tenant.tenant_id


def get_active_tenant(tenant=Depends(_resolved_tenant)) -> str:
    """`tenant_id` SOLO si el tenant está `active` (gating de billing, B4.5).

    Si la suscripción está suspendida/cancelada → 402, para que el frontend
    mande al usuario a pagar."""
    if getattr(tenant, "status", None) != "active":
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"suscripción inactiva (status={getattr(tenant, 'status', None)})",
        )
    return tenant.tenant_id


__all__ = [
    "get_verifier",
    "reset_verifier",
    "get_admin_conn",
    "get_tenant_manager",
    "get_current_tenant",
    "get_active_tenant",
]
