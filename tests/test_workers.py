"""
B6 — Tests de la capa de workers (orquestación secuencial aislada).
Sin DB: fakes para tenant_manager, store y cycle_fn.
"""

from __future__ import annotations

import pytest

from borsenhirn.workers import (
    load_broker_credentials, TenantWorker, WorkerOrchestrator,
)
from borsenhirn.tenancy.constants import DEFAULT_TENANT_UUID

OTHER_TENANT = "00000000-0000-0000-0000-000000000099"


# ── load_broker_credentials ─────────────────────────────────────

class _Creds:
    api_key = "k"
    api_secret = "s"


class _StoreOK:
    def get(self, uid, provider):
        return _Creds()


class _StoreNone:
    def get(self, uid, provider):
        return None


def test_load_creds_from_vault_store():
    assert load_broker_credentials(OTHER_TENANT, store=_StoreOK()) == ("k", "s")


def test_load_creds_none_for_non_default_without_creds():
    assert load_broker_credentials(OTHER_TENANT, store=_StoreNone()) is None


def test_load_creds_fallback_to_config_for_default(monkeypatch):
    import config
    monkeypatch.setattr(config, "ALPACA_API_KEY", "gk", raising=False)
    monkeypatch.setattr(config, "ALPACA_SECRET_KEY", "gs", raising=False)
    assert load_broker_credentials(DEFAULT_TENANT_UUID, store=_StoreNone()) == ("gk", "gs")


# ── TenantWorker ────────────────────────────────────────────────

def test_worker_runs_cycle_with_context():
    seen = {}
    def cycle(tid, creds):
        seen["tid"] = tid
        seen["creds"] = creds
        return "done"
    out = TenantWorker("t1", ("k", "s")).run_cycle(cycle)
    assert out == "done" and seen["tid"] == "t1" and seen["creds"] == ("k", "s")


# ── WorkerOrchestrator ──────────────────────────────────────────

class _T:
    def __init__(self, tid):
        self.tenant_id = tid


class _FakeTM:
    def __init__(self, tids):
        self._tenants = [_T(t) for t in tids]
    def list_tenants(self, status=None, **kw):
        return self._tenants


def test_orchestrator_isolates_errors_and_skips_halt():
    tm = _FakeTM(["t1", "t2", "t3"])

    def cycle(tid, creds):
        if tid == "t2":
            raise RuntimeError("boom")
        return f"ran {tid}"

    orch = WorkerOrchestrator(
        tm,
        cred_loader=lambda tid: None,
        halted_check=lambda tid: tid == "t3",
    )
    res = orch.run_once(cycle)
    by = {r["tenant_id"]: r["status"] for r in res}
    assert by == {"t1": "ok", "t2": "error", "t3": "skipped_halt"}
    # t1 corrió a pesar del error de t2 (aislamiento)
    assert any(r["tenant_id"] == "t1" and r.get("result") == "ran t1" for r in res)


def test_orchestrator_passes_credentials():
    tm = _FakeTM(["tA"])
    captured = {}
    def cycle(tid, creds):
        captured["creds"] = creds
    orch = WorkerOrchestrator(tm, cred_loader=lambda tid: ("ka", "sa"))
    orch.run_once(cycle)
    assert captured["creds"] == ("ka", "sa")


def test_orchestrator_empty_when_no_active():
    orch = WorkerOrchestrator(_FakeTM([]), cred_loader=lambda tid: None)
    assert orch.run_once(lambda tid, creds: None) == []


def test_orchestrator_skips_system_tenant():
    from borsenhirn.tenancy.constants import SYSTEM_TENANT_ID
    tm = _FakeTM([SYSTEM_TENANT_ID, "t1"])
    ran = []
    orch = WorkerOrchestrator(tm, cred_loader=lambda tid: None)
    res = orch.run_once(lambda tid, creds: ran.append(tid) or "ok")
    # SYSTEM (control-plane) no corre; t1 sí
    assert ran == ["t1"]
    assert [r["tenant_id"] for r in res] == ["t1"]


def test_orchestrator_global_halt_skips_all():
    tm = _FakeTM(["t1", "t2"])
    ran = []
    orch = WorkerOrchestrator(
        tm, cred_loader=lambda tid: None, global_halt_check=lambda: True)
    res = orch.run_once(lambda tid, creds: ran.append(tid))
    assert res == [{"status": "global_halt"}]
    assert ran == []   # ningún tenant corrió
