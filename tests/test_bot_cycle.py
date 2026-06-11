"""
Wire-up del ciclo real del bot al orquestador multi-tenant.

Verifica `make_bot_cycle_fn` con un `BotEngine` mockeado (sin DB, sin red, sin
órdenes): cache por tenant, paso de credenciales/flags, gating del alerter
global, y la integración con `WorkerOrchestrator` (aislamiento + reuso del
engine entre pasadas).
"""

from __future__ import annotations

import pytest

from borsenhirn.workers.bot_cycle import make_bot_cycle_fn
from borsenhirn.workers import WorkerOrchestrator
from borsenhirn.tenancy.constants import DEFAULT_TENANT_UUID

OTHER_TENANT = "00000000-0000-0000-0000-000000000099"


def _install_fake_engine(monkeypatch):
    """Reemplaza borsenhirn.engine.BotEngine por un doble que registra calls."""
    built = []

    class _FakeEngine:
        def __init__(self, tenant_id, credentials=None, *,
                     train=False, live=False, register_alerter=True):
            self.tenant_id = tenant_id
            self.credentials = credentials
            self.train = train
            self.live = live
            self.register_alerter = register_alerter
            self.cycles = 0
            built.append(self)

        def run_cycle(self):
            self.cycles += 1
            return {"status": "ok", "tenant": self.tenant_id, "n": self.cycles}

    monkeypatch.setattr("borsenhirn.engine.BotEngine", _FakeEngine)
    return built


def test_cycle_fn_caches_engine_per_tenant(monkeypatch):
    built = _install_fake_engine(monkeypatch)
    fn = make_bot_cycle_fn()

    fn(OTHER_TENANT, None)
    fn(OTHER_TENANT, None)          # mismo tenant -> reusa el engine
    assert len(built) == 1
    assert built[0].cycles == 2

    fn(DEFAULT_TENANT_UUID, None)   # tenant distinto -> engine nuevo
    assert len(built) == 2


def test_cycle_fn_returns_run_cycle_result(monkeypatch):
    _install_fake_engine(monkeypatch)
    fn = make_bot_cycle_fn()
    out = fn(OTHER_TENANT, None)
    assert out["status"] == "ok"
    assert out["tenant"] == OTHER_TENANT
    assert out["n"] == 1


def test_cycle_fn_passes_credentials_and_flags(monkeypatch):
    built = _install_fake_engine(monkeypatch)
    fn = make_bot_cycle_fn(live=True, train=True)
    fn(OTHER_TENANT, ("k", "s"))
    eng = built[0]
    assert eng.credentials == ("k", "s")
    assert eng.live is True
    assert eng.train is True


def test_alerter_registered_only_for_default_tenant(monkeypatch):
    built = _install_fake_engine(monkeypatch)
    fn = make_bot_cycle_fn()
    fn(DEFAULT_TENANT_UUID, None)
    fn(OTHER_TENANT, None)
    by_tenant = {e.tenant_id: e.register_alerter for e in built}
    assert by_tenant[DEFAULT_TENANT_UUID] is True
    assert by_tenant[OTHER_TENANT] is False


# ── Integración con el orquestador (sin DB; fake tenant_manager) ────

class _T:
    def __init__(self, tid):
        self.tenant_id = tid


class _FakeTM:
    def __init__(self, tids):
        self._tenants = [_T(t) for t in tids]

    def list_tenants(self, status=None, **kw):
        return self._tenants


def test_orchestrator_runs_real_cycle_fn_isolated(monkeypatch):
    built = _install_fake_engine(monkeypatch)
    tm = _FakeTM([DEFAULT_TENANT_UUID, OTHER_TENANT])
    cycle_fn = make_bot_cycle_fn()
    orch = WorkerOrchestrator(tm, cred_loader=lambda tid: ("k", "s"))

    res = orch.run_once(cycle_fn)
    by = {r["tenant_id"]: r["status"] for r in res}
    assert by == {DEFAULT_TENANT_UUID: "ok", OTHER_TENANT: "ok"}
    assert len(built) == 2   # un engine por tenant

    # Segunda pasada: reusa los mismos engines (cache vive en el closure)
    orch.run_once(cycle_fn)
    assert len(built) == 2
    assert all(e.cycles == 2 for e in built)
