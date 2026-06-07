"""
AuditLogger — inserta filas en `audit_log` (append-only, RLS) (B5).

- `actor` (quién): contextvar que setea la capa de auth por request; default
  'system'. Para eventos del sistema (webhooks, jobs) queda 'system'.
- Soft-fail: si el INSERT falla, se loggea WARNING y NO se propaga — auditar
  nunca debe romper la operación principal.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import logging
from typing import Any, Dict, Optional

import borsenhirn.db as bdb

logger = logging.getLogger(__name__)

_current_actor: contextvars.ContextVar[str] = contextvars.ContextVar(
    "audit_actor", default="system")


def set_actor(actor: str) -> contextvars.Token:
    """Setea el actor actual (p.ej. clerk_user_id). Devuelve un token para reset."""
    return _current_actor.set(actor or "system")


def get_actor() -> str:
    return _current_actor.get()


@contextlib.contextmanager
def actor_scope(actor: str):
    """Setea el actor dentro del bloque y lo restaura al salir."""
    token = _current_actor.set(actor or "system")
    try:
        yield
    finally:
        _current_actor.reset(token)


class AuditLogger:
    """Escribe en `audit_log`. Inyectable/desactivable en tests."""

    def record(
        self,
        tenant_id: str,
        action: str,
        *,
        actor: Optional[str] = None,
        resource: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        actor = actor or get_actor()
        try:
            with bdb.get_conn(role="app") as conn, bdb.set_tenant(conn, tenant_id):
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO audit_log (tenant_id, actor, action, resource, metadata) "
                        "VALUES (%s, %s, %s, %s, %s::jsonb)",
                        (tenant_id, actor, action, resource,
                         json.dumps(metadata or {}, default=str)),
                    )
                conn.commit()
        except Exception as exc:   # soft-fail: nunca rompe la operación principal
            logger.warning("audit record falló (%s tenant=%s): %s",
                           action, tenant_id, exc)


# Singleton inyectable.
_audit: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    global _audit
    if _audit is None:
        _audit = AuditLogger()
    return _audit


def set_audit_logger(impl: AuditLogger) -> None:
    """Inyecta un logger (tests)."""
    global _audit
    _audit = impl


def reset_audit_logger() -> None:
    global _audit
    _audit = None


__all__ = [
    "AuditLogger",
    "get_audit_logger",
    "set_audit_logger",
    "reset_audit_logger",
    "set_actor",
    "get_actor",
    "actor_scope",
]
