"""
borsenhirn.audit — registro de auditoría append-only (B5).

`AuditLogger.record(...)` inserta una fila en `audit_log` (tenant-scoped, RLS).
El actor (quién) sale de un contextvar que setea la capa de auth por request;
default 'system'. El fallo al auditar NUNCA rompe la operación principal.
"""

from borsenhirn.audit.logger import (
    AuditLogger,
    get_audit_logger,
    set_audit_logger,
    reset_audit_logger,
    set_actor,
    get_actor,
    actor_scope,
)
from borsenhirn.audit.actions import AuditAction

__all__ = [
    "AuditLogger",
    "get_audit_logger",
    "set_audit_logger",
    "reset_audit_logger",
    "set_actor",
    "get_actor",
    "actor_scope",
    "AuditAction",
]
