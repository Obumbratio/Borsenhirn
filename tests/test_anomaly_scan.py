"""
Pase de anomalías por tenant (B10 multi-tenant) — sin DB ni red.

Inyecta un `tenant_manager` fake y un `detector` fake, y mockea la factory del
AlertManager para capturar el ruteo por tenant. Verifica: exclusión de SYSTEM,
aislamiento de errores, y que cada finding se alerta en la alert_mgr del tenant.
"""

from __future__ import annotations

import pytest

from borsenhirn.workers.anomaly_scan import scan_anomalies_all_tenants
from borsenhirn.anomaly import AnomalyFinding
from borsenhirn.tenancy.constants import SYSTEM_TENANT_ID

T1 = "00000000-0000-0000-0000-000000000001"
T2 = "00000000-0000-0000-0000-000000000099"


class _T:
    def __init__(self, tid):
        self.tenant_id = tid


class _FakeTM:
    def __init__(self, tids):
        self._tenants = [_T(t) for t in tids]

    def list_tenants(self, status=None, **kw):
        return self._tenants


class _FakeMgr:
    """AlertManager fake: registra los sends."""
    def __init__(self):
        self.sent = []

    def send(self, level, subject, body, meta=None):
        self.sent.append({"level": level, "subject": subject, "meta": meta})


class _FakeDetector:
    def __init__(self, mapping):
        self.mapping = mapping            # tid -> [AnomalyFinding] | Exception

    def scan(self, tenant_id):
        out = self.mapping.get(tenant_id, [])
        if isinstance(out, Exception):
            raise out
        return out


@pytest.fixture
def patched_mgrs(monkeypatch):
    """Mockea la factory: una _FakeMgr por tenant, accesible por tid."""
    mgrs = {}

    def _fake_factory(get_conn_fn, tenant_id=None):
        m = _FakeMgr()
        mgrs[tenant_id] = m
        return m

    monkeypatch.setattr(
        "borsenhirn.safety.bootstrap.build_alert_manager_from_config",
        _fake_factory,
    )
    return mgrs


def test_excludes_system_tenant(patched_mgrs):
    tm = _FakeTM([SYSTEM_TENANT_ID, T1])
    detector = _FakeDetector({T1: []})
    res = scan_anomalies_all_tenants(tenant_manager=tm, detector=detector)
    assert [r["tenant_id"] for r in res] == [T1]      # SYSTEM no aparece
    assert SYSTEM_TENANT_ID not in patched_mgrs        # ni se le construyó alert_mgr


def test_routes_findings_to_each_tenant_manager(patched_mgrs):
    tm = _FakeTM([T1, T2])
    f1 = AnomalyFinding("losing_streak", "warn", "racha de 5", {"streak": 5})
    f2 = AnomalyFinding("trade_volume_spike", "warn", "60 trades", {"trades_today": 60})
    detector = _FakeDetector({T1: [f1], T2: [f2]})

    res = scan_anomalies_all_tenants(tenant_manager=tm, detector=detector)
    by = {r["tenant_id"]: r for r in res}
    assert by[T1]["findings"] == ["losing_streak"]
    assert by[T2]["findings"] == ["trade_volume_spike"]
    # Cada finding fue a la alert_mgr de SU tenant (sin cruce)
    assert [s["subject"] for s in patched_mgrs[T1].sent] == ["Anomalía: losing_streak"]
    assert [s["subject"] for s in patched_mgrs[T2].sent] == ["Anomalía: trade_volume_spike"]
    assert patched_mgrs[T1].sent[0]["meta"]["tenant_id"] == T1


def test_isolates_errors_per_tenant(patched_mgrs):
    tm = _FakeTM([T1, T2])
    detector = _FakeDetector({T1: [], T2: RuntimeError("boom")})
    res = scan_anomalies_all_tenants(tenant_manager=tm, detector=detector)
    by = {r["tenant_id"]: r["status"] for r in res}
    assert by[T1] == "ok"        # T1 corrió pese al error de T2
    assert by[T2] == "error"


def test_no_findings_no_alerts(patched_mgrs):
    tm = _FakeTM([T1])
    res = scan_anomalies_all_tenants(tenant_manager=tm, detector=_FakeDetector({T1: []}))
    assert res == [{"tenant_id": T1, "status": "ok", "findings": []}]
    assert patched_mgrs[T1].sent == []
