"""
Kill-switch GLOBAL / de plataforma (B8) — freno de emergencia para TODOS los tenants.

Se guarda como una fila de `killswitch_state` bajo el tenant SYSTEM (…000), que
es independiente de cualquier tenant real. Cuando está activo, el orquestador de
workers (B6) saltea a todos los tenants.

    is_global_halt()           -> bool
    trip_global(reason, actor) -> activa el freno global
    clear_global(note, actor)  -> lo limpia

Audita cada acción (B5) bajo el tenant SYSTEM.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

GLOBAL_KEY = "global_halt"


def _store():
    import borsenhirn.db as bdb
    from borsenhirn.safety.state_store_pg import PostgresStateStore
    from borsenhirn.tenancy.constants import SYSTEM_TENANT_ID
    return PostgresStateStore(lambda: bdb.get_conn(role="app"), tenant_id=SYSTEM_TENANT_ID)


def _audit(action: str, detail: str, actor: str) -> None:
    try:
        from borsenhirn.audit import get_audit_logger
        from borsenhirn.tenancy.constants import SYSTEM_TENANT_ID
        get_audit_logger().record(
            SYSTEM_TENANT_ID, action, actor=actor, resource=(detail or None))
    except Exception:   # pragma: no cover
        pass


def is_global_halt() -> bool:
    """True si el freno global está activo."""
    row = _store().get(GLOBAL_KEY)
    return bool(row and row.get("triggered"))


def trip_global(reason: str, *, actor: str = "admin") -> None:
    """Activa el freno de plataforma (para a TODOS los tenants)."""
    _store().set(GLOBAL_KEY, True, reason or "global halt", {"actor": actor})
    logger.warning("GLOBAL KILL-SWITCH activado por %s: %s", actor, reason)
    from borsenhirn.audit import AuditAction
    _audit(AuditAction.KS_GLOBAL_HALT, reason, actor)


def clear_global(note: str = "", *, actor: str = "admin") -> None:
    """Limpia el freno de plataforma."""
    _store().clear(GLOBAL_KEY, note)
    logger.warning("GLOBAL KILL-SWITCH limpiado por %s (%s)", actor, note or "-")
    from borsenhirn.audit import AuditAction
    _audit(AuditAction.KS_GLOBAL_CLEAR, note, actor)


__all__ = ["is_global_halt", "trip_global", "clear_global", "GLOBAL_KEY"]
