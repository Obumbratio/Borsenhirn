"""
B10 — Tests del detector de anomalías (reglas puras + scan + alertas). Sin DB.
"""

from __future__ import annotations

from borsenhirn.anomaly.detector import (
    rule_credential_access_spike, rule_killswitch_burst,
    rule_losing_streak, rule_trade_volume_spike,
    AnomalyDetector, scan_and_alert,
    CRED_READ_SPIKE, KS_HALT_BURST, LOSING_STREAK, TRADE_VOLUME_SPIKE,
)


def _snap(**kw):
    base = {"audit_counts": {}, "recent_wins": [], "trades_today": 0}
    base.update(kw)
    return base


# ── reglas individuales ─────────────────────────────────────────

def test_cred_spike_triggers_at_threshold():
    f = rule_credential_access_spike(_snap(audit_counts={"credentials.read": CRED_READ_SPIKE}))
    assert f and f[0].rule == "credential_access_spike" and f[0].severity == "warn"


def test_cred_spike_below_threshold_silent():
    assert rule_credential_access_spike(_snap(audit_counts={"credentials.read": 1})) == []


def test_killswitch_burst():
    assert rule_killswitch_burst(_snap(audit_counts={"killswitch.halt": KS_HALT_BURST}))
    assert rule_killswitch_burst(_snap(audit_counts={"killswitch.halt": 0})) == []


def test_losing_streak_triggers():
    f = rule_losing_streak(_snap(recent_wins=[False] * LOSING_STREAK))
    assert f and f[0].metadata["streak"] == LOSING_STREAK


def test_losing_streak_broken_by_recent_win():
    # más reciente primero: 1 pérdida, luego ganancia -> streak=1
    assert rule_losing_streak(_snap(recent_wins=[False, True, False, False, False, False])) == []


def test_volume_spike():
    assert rule_trade_volume_spike(_snap(trades_today=TRADE_VOLUME_SPIKE))
    assert rule_trade_volume_spike(_snap(trades_today=1)) == []


# ── detector ────────────────────────────────────────────────────

def test_detector_scan_runs_all_rules():
    det = AnomalyDetector(snapshot_fn=lambda tid: _snap(
        audit_counts={"credentials.read": 99}, trades_today=99))
    rules = {f.rule for f in det.scan("t")}
    assert {"credential_access_spike", "trade_volume_spike"} <= rules


def test_detector_no_anomalies_empty():
    det = AnomalyDetector(snapshot_fn=lambda tid: _snap())
    assert det.scan("t") == []


def test_failing_rule_does_not_break_scan():
    def boom(snap):
        raise RuntimeError("x")
    det = AnomalyDetector(rules=[boom, rule_trade_volume_spike],
                          snapshot_fn=lambda tid: _snap(trades_today=99))
    assert any(f.rule == "trade_volume_spike" for f in det.scan("t"))


# ── scan_and_alert ──────────────────────────────────────────────

class _FakeAlertMgr:
    def __init__(self):
        self.sent = []
    def send(self, level, subject, body, meta=None):
        self.sent.append((level, subject, body, meta))


def test_scan_and_alert_emits_per_finding():
    det = AnomalyDetector(snapshot_fn=lambda tid: _snap(audit_counts={"credentials.read": 99}))
    am = _FakeAlertMgr()
    findings = scan_and_alert("t1", am, detector=det)
    assert findings and len(am.sent) == len(findings)
    # el tenant_id va en el meta
    assert am.sent[0][3]["tenant_id"] == "t1"


def test_scan_and_alert_no_findings_no_alert():
    det = AnomalyDetector(snapshot_fn=lambda tid: _snap())
    am = _FakeAlertMgr()
    assert scan_and_alert("t1", am, detector=det) == []
    assert am.sent == []
