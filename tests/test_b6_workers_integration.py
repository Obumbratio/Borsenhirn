"""
B6.4 — e2e del runner contra borsenhirn_dev (gated).

run_all_tenants lista los tenants ACTIVE reales y corre un ciclo no-op aislado
por cada uno. Verifica que el default tenant aparece y corre OK.
"""

from __future__ import annotations

import pytest

import config
import borsenhirn.db as bdb
from borsenhirn.workers import run_all_tenants
from borsenhirn.tenancy.constants import DEFAULT_TENANT_UUID

if config.DB_NAME != "borsenhirn_dev":
    pytest.skip(
        f"B6 workers requiere DB_NAME=borsenhirn_dev (actual: {config.DB_NAME!r}).",
        allow_module_level=True,
    )

pytestmark = pytest.mark.integration


def test_run_all_active_tenants_isolated():
    seen = []

    def cycle(tenant_id, credentials):
        seen.append(tenant_id)
        return "noop"

    try:
        results = run_all_tenants(cycle)
    finally:
        bdb.close_all_pools()

    ok = {r["tenant_id"] for r in results if r["status"] == "ok"}
    # el default tenant está activo y su ciclo corrió
    assert DEFAULT_TENANT_UUID in ok
    assert DEFAULT_TENANT_UUID in seen
    # ningún tenant quedó en 'error' por el ciclo no-op
    assert all(r["status"] in ("ok", "skipped_halt") for r in results)
