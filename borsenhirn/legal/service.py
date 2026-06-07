"""
Servicio de aceptación legal (B7) — escribe/lee `legal_acceptance` (append-only).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import config
import borsenhirn.db as bdb

logger = logging.getLogger(__name__)

REQUIRED_DOCS = ("terms", "privacy")


def current_versions() -> Dict[str, str]:
    """Versiones vigentes de los docs requeridos (de config)."""
    return {
        "terms": config.LEGAL_TERMS_VERSION,
        "privacy": config.LEGAL_PRIVACY_VERSION,
    }


def record_acceptance(
    tenant_id: str,
    document: str,
    version: str,
    *,
    actor: str = "system",
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Registra una aceptación (INSERT append-only, bajo RLS del tenant)."""
    if document not in REQUIRED_DOCS:
        raise ValueError(f"documento inválido: {document!r} (esperado {REQUIRED_DOCS})")
    if not version:
        raise ValueError("version requerida")
    with bdb.get_conn(role="app") as conn, bdb.set_tenant(conn, tenant_id):
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO legal_acceptance (tenant_id, document, version, actor, metadata) "
                "VALUES (%s, %s, %s, %s, %s::jsonb)",
                (tenant_id, document, version, actor or "system",
                 json.dumps(metadata or {}, default=str)),
            )
        conn.commit()
    logger.info("legal acceptance: tenant=%s %s v%s", tenant_id, document, version)


def get_acceptances(tenant_id: str) -> List[Dict[str, Any]]:
    """Aceptaciones del tenant (más recientes primero)."""
    with bdb.get_conn(role="app") as conn, bdb.set_tenant(conn, tenant_id):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT document, version, accepted_at, actor "
                "FROM legal_acceptance ORDER BY accepted_at DESC")
            rows = cur.fetchall()
    return [{"document": r[0], "version": r[1],
             "accepted_at": r[2].isoformat() if r[2] else None, "actor": r[3]}
            for r in rows]


def is_compliant(tenant_id: str) -> bool:
    """True si el tenant aceptó la versión vigente de TODOS los docs requeridos."""
    cur_v = current_versions()
    with bdb.get_conn(role="app") as conn, bdb.set_tenant(conn, tenant_id):
        with conn.cursor() as cur:
            for doc in REQUIRED_DOCS:
                cur.execute(
                    "SELECT 1 FROM legal_acceptance WHERE document=%s AND version=%s LIMIT 1",
                    (doc, cur_v[doc]))
                if cur.fetchone() is None:
                    return False
    return True


__all__ = [
    "REQUIRED_DOCS", "current_versions", "record_acceptance",
    "get_acceptances", "is_compliant",
]
