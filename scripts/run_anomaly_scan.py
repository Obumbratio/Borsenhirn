"""
Entrypoint: un pase de detección de anomalías por tenant (B10).

Pensado para correr periódicamente desde un systemd timer / cron (cada hora) —
ver docs/DEPLOY_ALWAYS_ON.md. NO es un loop: hace un pase y sale (el scheduler
lo vuelve a invocar). La cadencia vive afuera, así que no se re-alerta la misma
anomalía constantemente (y el AlertManager además deduplica por ventana).

Uso manual (desde la raíz del repo, con el .env apuntando a la DB deseada):
    venv/bin/python -m scripts.run_anomaly_scan
"""

import logging
import sys

from logger import setup_logging
from borsenhirn.workers import scan_anomalies_all_tenants

setup_logging()
logger = logging.getLogger("anomaly_scan")


def main() -> int:
    results = scan_anomalies_all_tenants()
    ok = sum(1 for r in results if r.get("status") == "ok")
    err = sum(1 for r in results if r.get("status") == "error")
    total_findings = sum(len(r.get("findings", [])) for r in results)
    logger.info(
        "[ANOMALY] pase completo | tenants=%d ok=%d error=%d findings=%d",
        len(results), ok, err, total_findings,
    )
    for r in results:
        if r.get("findings"):
            logger.warning("[ANOMALY] tenant=%s findings=%s",
                           r["tenant_id"], r["findings"])
        if r.get("status") == "error":
            logger.error("[ANOMALY] tenant=%s error=%s",
                         r["tenant_id"], r.get("error"))
    # Exit 0 aunque algún tenant haya fallado (errores ya aislados/logueados);
    # solo una excepción no capturada propaga código != 0.
    return 0


if __name__ == "__main__":
    sys.exit(main())
