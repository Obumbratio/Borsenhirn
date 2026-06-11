"""
Orquestación de workers por tenant (B6) — secuencial con aislamiento de errores.

    load_broker_credentials(tenant_id) -> (api_key, api_secret) | None
        del vault (B2); fallback al config global para el default tenant.

    TenantWorker(tenant_id, credentials)
        contexto aislado de un tenant; run_cycle(cycle_fn) ejecuta un ciclo.

    WorkerOrchestrator(tenant_manager)
        .run_once(cycle_fn): recorre los tenants ACTIVE, saltea los que están en
        kill-switch HALT, y corre el ciclo de cada uno con try/except AISLADO.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_PROVIDER = "alpaca"


def load_broker_credentials(
    tenant_id: str,
    *,
    provider: str = DEFAULT_PROVIDER,
    store: Any = None,
) -> Optional[Tuple[str, str]]:
    """
    Devuelve (api_key, api_secret) del tenant desde el vault, o None.

    - `store` inyectable (tests). Si es None, se construye un CredentialStore
      real (Vault.from_provider + app pool, scoped al tenant).
    - Fallback: para el DEFAULT tenant, usa `config.ALPACA_API_KEY/SECRET`
      (preserva el bot single-user actual).
    """
    creds = None
    try:
        if store is None:
            import borsenhirn.db as bdb
            from borsenhirn.security import CredentialStore, Vault
            vault = Vault.from_provider()
            with bdb.get_conn(role="app") as conn:
                s = CredentialStore(lambda: conn, vault, tenant_id=tenant_id)
                # Modelo 1:1 (B3): user_id == tenant_id.
                creds = s.get(tenant_id, provider)
        else:
            creds = store.get(tenant_id, provider)
    except Exception as exc:
        logger.warning("load_broker_credentials(%s) falló: %s", tenant_id, exc)

    if creds is not None:
        return (creds.api_key, creds.api_secret)

    # Fallback para el default tenant (single-user dev).
    try:
        import config
        from borsenhirn.tenancy.constants import DEFAULT_TENANT_UUID
        if tenant_id == DEFAULT_TENANT_UUID and config.ALPACA_API_KEY:
            return (config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY)
    except Exception:   # pragma: no cover
        pass
    return None


class TenantWorker:
    """Contexto aislado de un tenant para correr un ciclo del bot."""

    def __init__(self, tenant_id: str, credentials: Optional[Tuple[str, str]] = None):
        self.tenant_id = tenant_id
        self.credentials = credentials

    def run_cycle(self, cycle_fn: Callable[[str, Optional[Tuple[str, str]]], Any]) -> Any:
        """
        Ejecuta `cycle_fn(tenant_id, credentials)` bajo el contexto del tenant.
        El actor de audit queda marcado como el worker del tenant.
        """
        try:
            from borsenhirn.audit import actor_scope
            with actor_scope(f"worker:{self.tenant_id}"):
                return cycle_fn(self.tenant_id, self.credentials)
        except Exception:
            # si el módulo de audit no está, corremos igual
            return cycle_fn(self.tenant_id, self.credentials)


class WorkerOrchestrator:
    """Recorre los tenants activos y corre el ciclo de cada uno, aislado."""

    def __init__(
        self,
        tenant_manager: Any,
        *,
        cred_loader: Callable[[str], Optional[Tuple[str, str]]] = load_broker_credentials,
        halted_check: Optional[Callable[[str], bool]] = None,
        global_halt_check: Optional[Callable[[], bool]] = None,
    ):
        self.tm = tenant_manager
        self.cred_loader = cred_loader
        self.halted_check = halted_check
        self.global_halt_check = global_halt_check

    def _is_global_halt(self) -> bool:
        check = self.global_halt_check
        if check is None:
            try:
                from borsenhirn.safety.global_killswitch import is_global_halt
                check = is_global_halt
            except Exception:   # pragma: no cover
                return False
        try:
            return bool(check())
        except Exception as exc:   # fail-open: un error de chequeo no frena todo
            logger.warning("global_halt_check falló (se continúa): %s", exc)
            return False

    def run_once(self, cycle_fn: Callable[[str, Optional[Tuple[str, str]]], Any]) -> list:
        """
        Un pase sobre todos los tenants ACTIVE. Devuelve una lista de resúmenes
        por tenant: {tenant_id, status: ok|skipped_halt|error, ...}.
        Un error en un tenant NO frena a los demás.

        Si el kill-switch GLOBAL (B8) está activo, no corre ningún tenant.
        """
        from borsenhirn.tenancy.tenant import TenantStatus
        from borsenhirn.tenancy.constants import SYSTEM_TENANT_ID
        if self._is_global_halt():
            logger.warning("GLOBAL kill-switch activo: no se corre ningún tenant.")
            return [{"status": "global_halt"}]
        results = []
        for tenant in self.tm.list_tenants(status=TenantStatus.ACTIVE):
            tid = tenant.tenant_id
            # El tenant SYSTEM es del control-plane (kill-switch global, etc.),
            # NO tradea: nunca se corre como worker (aunque figure ACTIVE).
            if tid == SYSTEM_TENANT_ID:
                continue
            if self.halted_check is not None:
                try:
                    if self.halted_check(tid):
                        results.append({"tenant_id": tid, "status": "skipped_halt"})
                        continue
                except Exception as exc:   # pragma: no cover
                    logger.warning("halted_check(%s) falló: %s", tid, exc)
            try:
                creds = self.cred_loader(tid)
                out = TenantWorker(tid, creds).run_cycle(cycle_fn)
                results.append({"tenant_id": tid, "status": "ok", "result": out})
            except Exception as exc:
                logger.error("worker del tenant %s falló (aislado): %s", tid, exc)
                results.append({"tenant_id": tid, "status": "error", "error": str(exc)})
        return results


__all__ = ["load_broker_credentials", "TenantWorker", "WorkerOrchestrator"]
