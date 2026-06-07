"""
Runner — wire-up del orquestador con la DB real (B6.4).

`make_halted_check()` arma un check de kill-switch por tenant (saltea los que
están en HALT). `run_all_tenants(cycle_fn)` lista los tenants activos y corre
el ciclo de cada uno, aislado.

El `cycle_fn(tenant_id, credentials)` es la lógica del bot por ciclo — se inyecta
desde el entry point real (reusa `main`); acá queda inyectable.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, Tuple

import borsenhirn.db as bdb
from borsenhirn.workers.orchestrator import WorkerOrchestrator

logger = logging.getLogger(__name__)


def make_halted_check() -> Callable[[str], bool]:
    """Devuelve halted(tenant_id) -> True si el tenant tiene kill-switch activo."""
    from borsenhirn.safety.state_store_pg import PostgresStateStore

    def halted(tenant_id: str) -> bool:
        store = PostgresStateStore(
            lambda: bdb.get_conn(role="app"), tenant_id=tenant_id)
        return len(store.list_active()) > 0

    return halted


def run_all_tenants(
    cycle_fn: Callable[[str, Optional[Tuple[str, str]]], Any],
    *,
    tenant_manager: Any = None,
    halted_check: Optional[Callable[[str], bool]] = None,
) -> list:
    """
    Un pase sobre todos los tenants ACTIVE corriendo `cycle_fn` aislado por tenant.
    Usa el pool admin para listar tenants y app por tenant (RLS). Inyectable en tests.
    """
    if tenant_manager is not None:
        orch = WorkerOrchestrator(
            tenant_manager, halted_check=halted_check or make_halted_check())
        return orch.run_once(cycle_fn)

    from borsenhirn.tenancy.management import TenantManager
    with bdb.get_conn(role="admin") as conn:
        tm = TenantManager(get_conn=lambda: conn)
        orch = WorkerOrchestrator(
            tm, halted_check=halted_check or make_halted_check())
        return orch.run_once(cycle_fn)


__all__ = ["make_halted_check", "run_all_tenants"]
