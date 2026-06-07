"""
Diagnóstico de RLS en Postgres.

Imprime el estado de RLS de las tablas multi-tenant + información sobre
el usuario actual + qué policies están activas. Útil para entender por
qué el aislamiento no funciona.

Uso:
    python scripts/diagnose_rls.py
    python scripts/diagnose_rls.py --table trades
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import config  # noqa: E402

SEP = "=" * 72


def get_conn():
    import psycopg2
    return psycopg2.connect(
        host=config.DB_HOST, port=config.DB_PORT,
        dbname=config.DB_NAME, user=config.DB_USER,
        password=config.DB_PASSWORD,
    )


def print_section(title: str) -> None:
    print(f"\n{SEP}\n  {title}\n{SEP}")


def diagnose(table: str | None = None):
    conn = get_conn()
    cur = conn.cursor()

    # ── 1. Quién soy? ─────────────────────────────────────
    print_section("[1] Identidad y privilegios del rol actual")
    cur.execute("""
        SELECT rolname, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole
          FROM pg_roles
         WHERE rolname = current_user
    """)
    rolname, sup, bypass, _, _ = cur.fetchone()
    print(f"  current_user:    {rolname}")
    print(f"  rolsuper:        {sup}    {'⚠ SUPERUSER (bypassea RLS SIEMPRE)' if sup else 'ok'}")
    print(f"  rolbypassrls:    {bypass} {'⚠ BYPASSRLS (bypassea RLS)' if bypass else 'ok'}")

    if sup or bypass:
        print()
        print("  >>> Tu rol bypassea RLS — el aislamiento NO se va a aplicar")
        print("  >>> mientras te conectes con este rol. Necesitás un rol")
        print("  >>> separado SIN superuser/bypassrls para validar el flujo.")

    # ── 2. Variable de sesión ─────────────────────────────
    print_section("[2] Variable de sesión app.current_tenant_id")
    cur.execute("SELECT current_setting('app.current_tenant_id', true)")
    val = cur.fetchone()[0]
    print(f"  valor actual: {val!r}")
    print(f"  → si es vacío, las queries con RLS devuelven 0 filas")

    # ── 3. Tablas con RLS ─────────────────────────────────
    print_section("[3] Tablas con RLS habilitado")
    cur.execute("""
        SELECT n.nspname || '.' || c.relname AS table_name,
               c.relrowsecurity, c.relforcerowsecurity
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE c.relkind = 'r'
           AND n.nspname NOT IN ('pg_catalog', 'information_schema')
           AND (c.relrowsecurity OR c.relforcerowsecurity)
         ORDER BY 1
    """)
    rows = cur.fetchall()
    if not rows:
        print("  (ninguna tabla tiene RLS activado)")
    for tname, ena, force in rows:
        flags = []
        if ena: flags.append("ENABLE")
        if force: flags.append("FORCE")
        print(f"  {tname:50s}  {' '.join(flags)}")

    # ── 4. Policies activas ───────────────────────────────
    print_section("[4] Policies activas")
    if table:
        cur.execute("""
            SELECT schemaname, tablename, policyname, cmd,
                   permissive, qual, with_check
              FROM pg_policies
             WHERE tablename = %s
             ORDER BY tablename, policyname
        """, (table,))
    else:
        cur.execute("""
            SELECT schemaname, tablename, policyname, cmd,
                   permissive, qual, with_check
              FROM pg_policies
             ORDER BY tablename, policyname
        """)
    rows = cur.fetchall()
    if not rows:
        print(f"  (ninguna policy activa{' en ' + table if table else ''})")
    for schema, tbl, pol, cmd, perm, qual, check in rows:
        print(f"  ▸ {schema}.{tbl} — {pol} ({cmd}, "
              f"{'PERMISSIVE' if perm else 'RESTRICTIVE'})")
        print(f"      USING:      {qual}")
        if check:
            print(f"      WITH CHECK: {check}")

    # ── 5. Roles con BYPASSRLS ────────────────────────────
    print_section("[5] Roles que bypassean RLS")
    cur.execute("""
        SELECT rolname, rolsuper, rolbypassrls
          FROM pg_roles
         WHERE rolsuper OR rolbypassrls
         ORDER BY rolname
    """)
    rows = cur.fetchall()
    for rolname, sup, bypass in rows:
        flags = []
        if sup: flags.append("SUPERUSER")
        if bypass: flags.append("BYPASSRLS")
        print(f"  {rolname:30s}  {' + '.join(flags)}")

    # ── 6. Sugerencia ─────────────────────────────────────
    print_section("[6] Recomendación")
    if sup or bypass:
        print("  Para que el aislamiento RLS se aplique en tu app:")
        print()
        print("  1. Crear un rol sin BYPASSRLS:")
        print("     CREATE ROLE borsenhirn_app LOGIN PASSWORD 'xxxxx';")
        print("     GRANT CONNECT ON DATABASE borsenhirn TO borsenhirn_app;")
        print("     GRANT USAGE ON SCHEMA public TO borsenhirn_app;")
        print("     GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN")
        print("       SCHEMA public TO borsenhirn_app;")
        print("     GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public")
        print("       TO borsenhirn_app;")
        print()
        print("  2. Hacer que la app/bot/api se conecte con ese rol")
        print("     (NO con postgres). En .env:")
        print("       DB_USER=borsenhirn_app")
        print("       DB_PASSWORD=xxxxx")
        print()
        print("  3. Mantener postgres SOLO para administración / migraciones")
        print("     / backups. NUNCA usar postgres en código de producción.")
    else:
        print("  ✓ Tu rol no bypassea RLS. Configuración OK.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--table", help="filtrar policies a una tabla específica")
    args = p.parse_args()
    diagnose(table=args.table)
