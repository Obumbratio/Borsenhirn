"""
Audita el estado de Row-Level Security en Postgres.

Lista todas las tablas del schema public y reporta:
    - Cuáles tienen RLS habilitado (ENABLE) y forzado (FORCE).
    - Cuáles tienen policies activas y cuántas.
    - Cuáles NO tienen RLS (candidatas a `borsenhirn_enable_rls()` en
      fase B de multi-tenancy).

Uso:
    python scripts/check_rls_coverage.py
    python scripts/check_rls_coverage.py --strict   # exit 1 si hay tablas sin RLS

Útil para CI: en el pipeline corré con --strict tras agregar tablas
nuevas, así te avisa si te olvidaste de habilitar RLS.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import config  # noqa: E402

SEP = "=" * 72

# Tablas que NO necesitan RLS por diseño (admin / shared / system).
RLS_EXEMPT = {
    "tenants",                       # admin shared
    "alembic_version",               # migration tracking
    "schema_migrations",             # idem
}


def get_conn():
    import psycopg2
    return psycopg2.connect(
        host=config.DB_HOST, port=config.DB_PORT,
        dbname=config.DB_NAME, user=config.DB_USER,
        password=config.DB_PASSWORD,
    )


def list_tables_with_rls_status(cur) -> List[Tuple[str, bool, bool, int]]:
    """
    Returns [(table, rls_enabled, rls_forced, n_policies), ...]
    """
    cur.execute("""
        SELECT
            c.relname                                   AS table_name,
            c.relrowsecurity                            AS rls_enabled,
            c.relforcerowsecurity                       AS rls_forced,
            COALESCE((
                SELECT count(*) FROM pg_policies p
                 WHERE p.tablename = c.relname
                   AND p.schemaname = n.nspname
            ), 0)                                       AS n_policies
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE c.relkind = 'r'
           AND n.nspname = 'public'
         ORDER BY c.relname
    """)
    return [(r[0], bool(r[1]), bool(r[2]), int(r[3])) for r in cur.fetchall()]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--strict", action="store_true",
                   help="exit 1 si hay tablas sin RLS y no exentas")
    args = p.parse_args()

    print(f"\n{SEP}\n  RLS COVERAGE — schema public\n{SEP}")
    try:
        conn = get_conn()
    except Exception as exc:
        print(f"FAIL: no pude conectar a Postgres: {exc}")
        sys.exit(2)

    with conn.cursor() as cur:
        rows = list_tables_with_rls_status(cur)

    if not rows:
        print("(sin tablas en schema public)")
        conn.close()
        sys.exit(0)

    enabled = [r for r in rows if r[1]]
    disabled = [r for r in rows if not r[1] and r[0] not in RLS_EXEMPT]
    exempt = [r for r in rows if not r[1] and r[0] in RLS_EXEMPT]

    print(f"\n[OK] Con RLS ({len(enabled)}):")
    for t, ena, force, npol in enabled:
        flags = "ENABLE" + (" + FORCE" if force else "")
        warn = "" if force else "  ⚠ sin FORCE"
        print(f"  ✓ {t:35s}  {flags}  policies={npol}{warn}")

    if exempt:
        print(f"\n[SKIP] Sin RLS pero exentas por diseño ({len(exempt)}):")
        for t, *_ in exempt:
            print(f"  - {t}")

    if disabled:
        print(f"\n[FAIL] Sin RLS — candidatas a habilitar ({len(disabled)}):")
        for t, *_ in disabled:
            print(f"  ✗ {t}")
        print(f"\nFix por tabla:")
        print(f"  psql -c \"SELECT borsenhirn_enable_rls('<tabla>')\"")
    else:
        print("\n[OK] Todas las tablas no exentas tienen RLS.")

    conn.close()

    print(f"\n{SEP}")
    print(f"  Total: {len(rows)} tablas | con RLS: {len(enabled)} | "
          f"sin RLS: {len(disabled)} | exentas: {len(exempt)}")
    print(SEP)

    if args.strict and disabled:
        print(f"\n--strict: hay {len(disabled)} tablas sin RLS → exit 1")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
