"""
Detector de anomalías por tenant (B10) — reglas por umbral sobre un snapshot.

`build_snapshot` cuenta acciones recientes del audit_log + stats de trading (bajo
RLS). Las reglas son PURAS sobre el snapshot (testeables sin DB). `scan_and_alert`
emite una alerta por finding. Solo alerta (no auto-bloquea — D1).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import borsenhirn.db as bdb

logger = logging.getLogger(__name__)


def _thr(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# Umbrales (override por env).
CRED_READ_SPIKE = _thr("ANOMALY_CRED_READ_SPIKE", 20)
KS_HALT_BURST = _thr("ANOMALY_KS_HALT_BURST", 3)
LOSING_STREAK = _thr("ANOMALY_LOSING_STREAK", 5)
TRADE_VOLUME_SPIKE = _thr("ANOMALY_TRADE_VOLUME_SPIKE", 50)


@dataclass(frozen=True)
class AnomalyFinding:
    rule: str
    severity: str            # 'warn' | 'critical'
    message: str
    metadata: Dict[str, Any] = field(default_factory=dict)


def build_snapshot(tenant_id: str, *, window_hours: int = 24) -> Dict[str, Any]:
    """Snapshot del tenant (bajo RLS): counts del audit_log + stats de trading."""
    snap: Dict[str, Any] = {
        "tenant_id": tenant_id, "audit_counts": {},
        "recent_wins": [], "trades_today": 0,
    }
    with bdb.get_conn(role="app") as conn, bdb.set_tenant(conn, tenant_id):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT action, count(*) FROM audit_log "
                "WHERE at > now() - %s::interval GROUP BY action",
                (f"{window_hours} hours",))
            snap["audit_counts"] = {r[0]: r[1] for r in cur.fetchall()}
            cur.execute(
                "SELECT win FROM bot_trade_outcomes ORDER BY created_at DESC LIMIT 20")
            snap["recent_wins"] = [r[0] for r in cur.fetchall()]
            cur.execute(
                "SELECT count(*) FROM bot_trade_outcomes WHERE trade_date = CURRENT_DATE")
            snap["trades_today"] = cur.fetchone()[0]
    return snap


# ── Reglas (puras sobre el snapshot) ────────────────────────────

def rule_credential_access_spike(snap) -> List[AnomalyFinding]:
    n = snap.get("audit_counts", {}).get("credentials.read", 0)
    if n >= CRED_READ_SPIKE:
        return [AnomalyFinding("credential_access_spike", "warn",
                f"{n} accesos a credenciales en la ventana", {"count": n})]
    return []


def rule_killswitch_burst(snap) -> List[AnomalyFinding]:
    n = snap.get("audit_counts", {}).get("killswitch.halt", 0)
    if n >= KS_HALT_BURST:
        return [AnomalyFinding("killswitch_burst", "warn",
                f"{n} activaciones de kill-switch en la ventana", {"count": n})]
    return []


def rule_losing_streak(snap) -> List[AnomalyFinding]:
    streak = 0
    for win in snap.get("recent_wins", []):   # más reciente primero
        if win:
            break
        streak += 1
    if streak >= LOSING_STREAK:
        return [AnomalyFinding("losing_streak", "warn",
                f"racha de {streak} pérdidas seguidas", {"streak": streak})]
    return []


def rule_trade_volume_spike(snap) -> List[AnomalyFinding]:
    n = snap.get("trades_today", 0)
    if n >= TRADE_VOLUME_SPIKE:
        return [AnomalyFinding("trade_volume_spike", "warn",
                f"{n} trades hoy (volumen anómalo)", {"trades_today": n})]
    return []


DEFAULT_RULES: List[Callable[[Dict[str, Any]], List[AnomalyFinding]]] = [
    rule_credential_access_spike,
    rule_killswitch_burst,
    rule_losing_streak,
    rule_trade_volume_spike,
]


class AnomalyDetector:
    def __init__(self, rules=None, *, snapshot_fn: Callable = build_snapshot):
        self.rules = rules if rules is not None else DEFAULT_RULES
        self.snapshot_fn = snapshot_fn

    def scan(self, tenant_id: str) -> List[AnomalyFinding]:
        snap = self.snapshot_fn(tenant_id)
        findings: List[AnomalyFinding] = []
        for rule in self.rules:
            try:
                findings.extend(rule(snap))
            except Exception as exc:   # una regla que falla no rompe el scan
                logger.warning("regla de anomalía %s falló: %s", rule, exc)
        return findings


def scan_and_alert(
    tenant_id: str,
    alert_mgr: Any,
    *,
    detector: Optional[AnomalyDetector] = None,
) -> List[AnomalyFinding]:
    """Escanea y emite una alerta por finding (solo alerta — no auto-bloquea)."""
    findings = (detector or AnomalyDetector()).scan(tenant_id)
    if not findings:
        return findings
    from borsenhirn.safety.alerts import AlertLevel
    for f in findings:
        level = AlertLevel.CRITICAL if f.severity == "critical" else AlertLevel.WARN
        alert_mgr.send(level, f"Anomalía: {f.rule}", f.message,
                       meta={"tenant_id": tenant_id, **f.metadata})
    return findings


__all__ = [
    "AnomalyFinding", "AnomalyDetector", "build_snapshot",
    "scan_and_alert", "DEFAULT_RULES",
]
