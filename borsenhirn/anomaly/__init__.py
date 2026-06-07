"""
borsenhirn.anomaly — detección de anomalías por tenant (B10).

Reglas pluggables sobre un snapshot (audit_log + trading) que emiten findings;
`scan_and_alert` los manda al AlertManager. Solo alerta (no auto-bloquea).
"""

from borsenhirn.anomaly.detector import (
    AnomalyFinding,
    AnomalyDetector,
    build_snapshot,
    scan_and_alert,
    DEFAULT_RULES,
)

__all__ = [
    "AnomalyFinding",
    "AnomalyDetector",
    "build_snapshot",
    "scan_and_alert",
    "DEFAULT_RULES",
]
