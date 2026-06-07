"""
export_tenant — dump JSON de todos los datos de un tenant (B9).

Corre bajo el rol app + tenant context: RLS garantiza que solo se exporta lo del
tenant. Excluye `user_credentials` (secretos cifrados — no se exportan).
"""

from __future__ import annotations

from typing import Any, Dict

import borsenhirn.db as bdb

# Tablas tenant-scoped que NO se exportan (secretos).
EXCLUDED_TABLES = {"user_credentials"}


def export_tenant(tenant_id: str) -> Dict[str, Any]:
    """
    Devuelve {tenant_id, tables: {tabla: [filas...]}} con todas las filas del
    tenant en cada tabla tenant-scoped (excepto las excluidas). JSON-serializable.
    """
    result: Dict[str, Any] = {"tenant_id": tenant_id, "tables": {}}
    with bdb.get_conn(role="app") as conn, bdb.set_tenant(conn, tenant_id):
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.relname
                FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname='public' AND c.relkind='r' AND c.relname <> 'tenants'
                  AND EXISTS (SELECT 1 FROM information_schema.columns col
                              WHERE col.table_name=c.relname AND col.column_name='tenant_id')
                ORDER BY c.relname
                """)
            tables = [r[0] for r in cur.fetchall() if r[0] not in EXCLUDED_TABLES]
            for t in tables:
                cur.execute(
                    f"SELECT COALESCE(jsonb_agg(to_jsonb(x)), '[]'::jsonb) FROM {t} x")
                result["tables"][t] = cur.fetchone()[0]
    return result


__all__ = ["export_tenant", "EXCLUDED_TABLES"]
