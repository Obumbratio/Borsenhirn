"""
Wire-up del ciclo REAL del bot al orquestador multi-tenant (B6).

`make_bot_cycle_fn()` devuelve un `cycle_fn(tenant_id, credentials)` apto para
`WorkerOrchestrator.run_once` / `run_all_tenants`. Cachea un `BotEngine` por
tenant (el setup —modelo, scanner, safety— se hace una sola vez por tenant y se
reusa entre pasadas), y en cada llamada corre UN ciclo de ese tenant.

Uso (un pase sobre todos los tenants ACTIVE, paper):

    from borsenhirn.workers.runner import run_all_tenants
    from borsenhirn.workers.bot_cycle import make_bot_cycle_fn
    results = run_all_tenants(make_bot_cycle_fn())

El orquestador ya: lista los ACTIVE, saltea los que están en HALT (per-tenant),
frena todo si el kill-switch GLOBAL está activo, aísla errores por tenant y
marca el actor de audit como `worker:<tenant_id>`. El `BotEngine` corre bajo
RLS scoped al tenant (memoria/safety toman `tenant_id`) y usa las credenciales
de broker del tenant (vault; fallback a config para el DEFAULT tenant).
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, Tuple

logger = logging.getLogger(__name__)


def make_bot_cycle_fn(
    *,
    live: bool = False,
    train: bool = False,
) -> Callable[[str, Optional[Tuple[str, str]]], Any]:
    """
    Construye el `cycle_fn` con un cache de `BotEngine` por tenant.

    `live`/`train` se pasan a cada `BotEngine` nuevo. Por defecto PAPER y sin
    reentrenar (el modelo se reentrena solo cada 7 días vía la memoria).
    """
    from borsenhirn.engine import BotEngine
    from borsenhirn.tenancy.constants import DEFAULT_TENANT_UUID

    engines: dict = {}

    def cycle_fn(tenant_id: str, credentials: Optional[Tuple[str, str]] = None) -> dict:
        eng = engines.get(tenant_id)
        if eng is None:
            # Solo el DEFAULT tenant engancha el alerter global (un único webhook
            # de Discord); los demás tenants no lo registran para no duplicar.
            eng = BotEngine(
                tenant_id,
                credentials=credentials,
                train=train,
                live=live,
                register_alerter=(tenant_id == DEFAULT_TENANT_UUID),
            )
            engines[tenant_id] = eng
        return eng.run_cycle()

    return cycle_fn


__all__ = ["make_bot_cycle_fn"]
