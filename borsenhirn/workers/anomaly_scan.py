"""
Pase de detección de anomalías por tenant (B10) — wire-up multi-tenant.

`scan_anomalies_all_tenants()` recorre los tenants ACTIVE y, para cada uno,
construye un AlertManager scoped al tenant y corre `scan_and_alert` (que escanea
el audit_log + trading bajo RLS y alerta por finding — solo alerta, no bloquea).

A diferencia del pase de trading (`run_all_tenants`):
- NO saltea tenants en HALT: queremos detectar anomalías (cred-spike, burst de
  kill-switch, racha de pérdidas) incluso —sobre todo— cuando el tenant frenó.
- NO se gatea por el kill-switch global: la monitorización debe seguir viva.
- Excluye el tenant SYSTEM (control-plane), igual que el pase de trading.

La cadencia la decide quien lo agenda (cron / loop): correrlo cada hora o cada
día evita el spam de re-alertar la misma anomalía (el AlertManager además
deduplica por ventana). Pensado para no vivir dentro del ciclo de trading.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

import borsenhirn.db as bdb

logger = logging.getLogger(__name__)


def _app_conn():
    return bdb.get_conn(role="app")


def scan_anomalies_all_tenants(
    *,
    tenant_manager: Any = None,
    detector: Any = None,
) -> List[dict]:
    """
    Un pase de anomalías sobre todos los tenants ACTIVE (excl. SYSTEM).

    Devuelve una lista de resúmenes por tenant:
    {tenant_id, status: ok|error, findings: [rule, ...]} | {..., error}.
    Un error en un tenant NO frena a los demás. `tenant_manager`/`detector`
    son inyectables (tests).
    """
    from borsenhirn.tenancy.tenant import TenantStatus
    from borsenhirn.tenancy.constants import SYSTEM_TENANT_ID
    from borsenhirn.anomaly import scan_and_alert
    from borsenhirn.safety.bootstrap import build_alert_manager_from_config

    # Materializar la lista de tenants (no mantener la conn admin abierta
    # durante todo el barrido; cada scan abre sus propias conns app).
    if tenant_manager is not None:
        tenants = list(tenant_manager.list_tenants(status=TenantStatus.ACTIVE))
    else:
        from borsenhirn.tenancy.management import TenantManager
        with bdb.get_conn(role="admin") as conn:
            tm = TenantManager(get_conn=lambda: conn)
            tenants = list(tm.list_tenants(status=TenantStatus.ACTIVE))

    results: List[dict] = []
    for tenant in tenants:
        tid = tenant.tenant_id
        if tid == SYSTEM_TENANT_ID:
            continue
        try:
            alert_mgr = build_alert_manager_from_config(_app_conn, tid)
            findings = scan_and_alert(tid, alert_mgr, detector=detector)
            results.append({
                "tenant_id": tid,
                "status": "ok",
                "findings": [f.rule for f in findings],
            })
        except Exception as exc:
            logger.error("scan de anomalías del tenant %s falló (aislado): %s", tid, exc)
            results.append({"tenant_id": tid, "status": "error", "error": str(exc)})
    return results


__all__ = ["scan_anomalies_all_tenants"]
