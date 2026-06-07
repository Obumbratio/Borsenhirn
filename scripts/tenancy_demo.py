"""
Demo end-to-end del módulo borsenhirn.tenancy contra Postgres real.

ATENCIÓN — sobre superusers y RLS:
    Postgres bypassea RLS para roles SUPERUSER o con BYPASSRLS, incluso
    con FORCE ROW LEVEL SECURITY. Este demo crea TEMPORALMENTE un rol
    `borsenhirn_demo_rls` SIN esos privilegios y se conecta como ese
    rol para los pasos de aislamiento. Después lo borra.

    Esto refleja la arquitectura recomendada para producción:
        - rol `postgres`: solo migraciones / admin / backups.
        - rol `borsenhirn_app`: usado por bot/api, SIN bypassrls.
        - rol `borsenhirn_admin`: dashboards internos, CON bypassrls.

Cubre:
    1. Crear 2 tenants A y B (como superuser).
    2. Crear tabla de prueba con RLS aplicado.
    3. Crear rol no-superuser temporal con grants mínimos.
    4. Insertar trades en A y en B (como superuser, los inserts pasan).
    5. Re-conectarse como rol no-superuser y verificar aislamiento real.
    6. Sin tenant context: SELECT trae 0 filas (FORCE RLS aplica).
    7. Cleanup completo (rol + tabla + tenants).

Uso:
    python scripts/tenancy_demo.py
"""

from __future__ import annotations

import logging
import os
import secrets
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import config  # noqa: E402
from logger import setup_logging  # noqa: E402
from borsenhirn.tenancy import (  # noqa: E402
    TenantContext,
    TenantManager,
    clear_current_tenant,
)

setup_logging()
logger = logging.getLogger(__name__)

SEP = "=" * 72

DEMO_ROLE = "borsenhirn_demo_rls"
DEMO_TABLE = "demo_rls_trades"


def get_conn(user: str | None = None, password: str | None = None):
    """Conexión psycopg2. Si no se pasan user/password, usa los de config."""
    import psycopg2
    return psycopg2.connect(
        host=config.DB_HOST, port=config.DB_PORT,
        dbname=config.DB_NAME,
        user=user or config.DB_USER,
        password=password or config.DB_PASSWORD,
    )


def is_superuser(conn) -> tuple[bool, str]:
    """Devuelve (is_super_or_bypass, role_name)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT current_user, rolsuper, rolbypassrls "
            "FROM pg_roles WHERE rolname = current_user"
        )
        rolname, sup, bypass = cur.fetchone()
    return bool(sup or bypass), rolname


def main():
    print(f"\n{SEP}\n  TENANCY DEMO — multi-tenant aislamiento via RLS\n{SEP}")

    admin = get_conn()  # como configurado en .env (probable: postgres)
    is_priv, role_name = is_superuser(admin)
    print(f"[admin] conectado como '{role_name}' "
          f"({'superuser/bypassrls — necesitamos rol separado' if is_priv else 'no-priv'})")

    # ── 1. Verificar tabla `tenants` ───────────────────────
    with admin.cursor() as cur:
        cur.execute("SELECT to_regclass('public.tenants')")
        if cur.fetchone()[0] is None:
            print("FAIL: tabla `tenants` no existe.")
            print("  → aplicá: psql -f borsenhirn/tenancy/migrations.sql")
            sys.exit(1)
    print("[1] OK tabla `tenants` existe")

    mgr = TenantManager(get_conn=lambda: admin)

    # ── 2. Crear 2 tenants ─────────────────────────────────
    t_a = mgr.create_tenant(email="demo-a@borsenhirn.test",
                              display_name="Demo Tenant A")
    t_b = mgr.create_tenant(email="demo-b@borsenhirn.test",
                              display_name="Demo Tenant B")
    print(f"[2] OK tenants creados: A={t_a.tenant_id[:8]}... "
          f"B={t_b.tenant_id[:8]}...")

    # ── 3. Crear tabla con RLS ─────────────────────────────
    with admin.cursor() as cur:
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {DEMO_TABLE} (
                id        bigserial PRIMARY KEY,
                tenant_id uuid      NOT NULL,
                symbol    text      NOT NULL,
                price     numeric   NOT NULL,
                created_at timestamptz DEFAULT now()
            )
        """)
        cur.execute("TRUNCATE " + DEMO_TABLE)  # limpia residuos de runs previos
        cur.execute(f"SELECT borsenhirn_enable_rls('{DEMO_TABLE}')")
    admin.commit()
    print(f"[3] OK tabla {DEMO_TABLE} creada con RLS habilitado")

    # ── 4. Crear rol no-superuser para los tests reales ────
    demo_password = "demo_" + secrets.token_hex(8)
    with admin.cursor() as cur:
        # Limpia rol previo si quedó
        cur.execute(
            f"REVOKE ALL ON {DEMO_TABLE} FROM {DEMO_ROLE}"
        ) if False else None  # not always present
        try:
            cur.execute(f"DROP OWNED BY {DEMO_ROLE} CASCADE")
            cur.execute(f"DROP ROLE IF EXISTS {DEMO_ROLE}")
        except Exception:
            admin.rollback()
        admin.commit()

        # Crear rol limpio
        cur.execute(
            f"CREATE ROLE {DEMO_ROLE} LOGIN PASSWORD '{demo_password}'"
        )
        cur.execute(f"GRANT CONNECT ON DATABASE {config.DB_NAME} TO {DEMO_ROLE}")
        cur.execute(f"GRANT USAGE ON SCHEMA public TO {DEMO_ROLE}")
        cur.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {DEMO_TABLE} "
                    f"TO {DEMO_ROLE}")
        cur.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public "
                    f"TO {DEMO_ROLE}")
    admin.commit()
    print(f"[4] OK rol no-superuser '{DEMO_ROLE}' creado con grants mínimos")

    # ── 5. Insertar trades como rol no-superuser ───────────
    # Cada tenant inserta los suyos. RLS verifica WITH CHECK.
    app = get_conn(user=DEMO_ROLE, password=demo_password)
    try:
        with TenantContext(app, t_a.tenant_id):
            with app.cursor() as cur:
                for sym, price in [("AAPL", 150), ("TSLA", 200), ("SPY", 450)]:
                    cur.execute(
                        f"INSERT INTO {DEMO_TABLE} (tenant_id, symbol, price) "
                        f"VALUES (%s, %s, %s)",
                        (t_a.tenant_id, sym, price),
                    )
            app.commit()
        print(f"[5a] OK 3 trades insertados como tenant A (vía {DEMO_ROLE})")

        with TenantContext(app, t_b.tenant_id):
            with app.cursor() as cur:
                cur.execute(
                    f"INSERT INTO {DEMO_TABLE} (tenant_id, symbol, price) "
                    f"VALUES (%s, %s, %s)",
                    (t_b.tenant_id, "QQQ", 380),
                )
            app.commit()
        print(f"[5b] OK 1 trade insertado como tenant B (vía {DEMO_ROLE})")

        # ── 6. Verificar aislamiento ───────────────────────
        with TenantContext(app, t_a.tenant_id):
            with app.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM {DEMO_TABLE}")
                n_a = cur.fetchone()[0]
        ok_a = n_a == 3
        print(f"[6a] Tenant A ve {n_a} trades (esperado 3): "
              f"{'OK' if ok_a else 'FAIL'}")

        with TenantContext(app, t_b.tenant_id):
            with app.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM {DEMO_TABLE}")
                n_b = cur.fetchone()[0]
        ok_b = n_b == 1
        print(f"[6b] Tenant B ve {n_b} trades (esperado 1): "
              f"{'OK' if ok_b else 'FAIL'}")

        # ── 7. Sin context: 0 filas ─────────────────────────
        clear_current_tenant(app)
        with app.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {DEMO_TABLE}")
            n_none = cur.fetchone()[0]
        ok_none = n_none == 0
        print(f"[7]  Sin tenant context ve {n_none} trades (esperado 0): "
              f"{'OK' if ok_none else 'FAIL'}")

        # ── 8. Insert con tenant_id de OTRO tenant: WITH CHECK debe fallar
        with TenantContext(app, t_a.tenant_id):
            try:
                with app.cursor() as cur:
                    cur.execute(
                        f"INSERT INTO {DEMO_TABLE} (tenant_id, symbol, price) "
                        f"VALUES (%s, %s, %s)",
                        (t_b.tenant_id, "INTRUDER", 0),
                    )
                app.commit()
                print("[8]  FAIL: insert cross-tenant pasó (no debería)")
                ok_cross = False
            except Exception:
                app.rollback()
                print("[8]  OK insert cross-tenant rechazado por WITH CHECK")
                ok_cross = True

        all_ok = ok_a and ok_b and ok_none and ok_cross
    finally:
        app.close()

    # ── 9. Cleanup ─────────────────────────────────────────
    with admin.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {DEMO_TABLE} CASCADE")
        try:
            cur.execute(f"DROP OWNED BY {DEMO_ROLE} CASCADE")
            cur.execute(f"DROP ROLE IF EXISTS {DEMO_ROLE}")
        except Exception as exc:
            logger.warning("cleanup rol %s: %s", DEMO_ROLE, exc)
            admin.rollback()
        else:
            admin.commit()
        cur.execute(
            "DELETE FROM tenants WHERE email LIKE 'demo-%@borsenhirn.test'"
        )
    admin.commit()
    admin.close()
    print(f"[9]  OK cleanup (tabla, rol y tenants borrados)")

    print(f"\n{SEP}")
    if all_ok:
        print("  DEMO COMPLETO — RLS aislamiento verificado ✓")
    else:
        print("  DEMO FALLÓ — revisá scripts/diagnose_rls.py")
    print(SEP)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logger.error("Demo falló: %s", exc, exc_info=True)
        sys.exit(2)
