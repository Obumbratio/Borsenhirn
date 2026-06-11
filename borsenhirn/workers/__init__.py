"""
borsenhirn.workers — orquestación de workers por tenant (B6).

Corre el bot por tenant, aislado: cada uno con su tenant_id (RLS), sus
credenciales de broker (vault), y aislamiento de errores (el fallo de un tenant
no frena a los demás).
"""

from borsenhirn.workers.orchestrator import (
    load_broker_credentials,
    TenantWorker,
    WorkerOrchestrator,
)
from borsenhirn.workers.runner import make_halted_check, run_all_tenants
from borsenhirn.workers.anomaly_scan import scan_anomalies_all_tenants

__all__ = [
    "load_broker_credentials",
    "TenantWorker",
    "WorkerOrchestrator",
    "make_halted_check",
    "run_all_tenants",
    "scan_anomalies_all_tenants",
]
