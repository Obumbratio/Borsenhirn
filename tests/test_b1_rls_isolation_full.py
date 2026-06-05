"""
B1 Bloque 6 — Tests amplios de aislamiento RLS (escritura + 2 tenants).

Cubre la checklist "Tests obligatorios antes de mergear fase B" de
MULTI_TENANCY.md, que 5.6 dejó a medias (5.6 cubrió el caso read-only
"sin contexto / default / ajeno / bypass"). Acá:

    1. INSERT con el tenant correcto funciona.
    2. INSERT cross-tenant es rechazado (WITH CHECK).
    3. UPDATE cross-tenant es rechazado (WITH CHECK).
    4. Aggregations (COUNT/SUM) respetan RLS.
    5. FK ON DELETE RESTRICT impide borrar un tenant con filas.
    6. Dos tenants reales: cada uno ve solo lo suyo.
    7. Las 17 tablas A tienen RLS enabled + forced + >=2 policies.

TODOS los tests de escritura son transaccionales: hacen rollback al final,
así `borsenhirn_dev` queda intacto (y el `== 31` de 5.6 sigue válido).

Gating idéntico a 5.6: `@pytest.mark.integration` (salta sin
RUN_DB_INTEGRATION) + auto-skip si DB_NAME != borsenhirn_dev.

Correr:
    set -a && source .env.dev && set +a
    RUN_DB_INTEGRATION=1 venv/bin/pytest tests/test_b1_rls_isolation_full.py -v
"""

from __future__ import annotations

import psycopg2
import pytest

import config
from borsenhirn import db
from borsenhirn.tenancy.constants import DEFAULT_TENANT_UUID

if config.DB_NAME != "borsenhirn_dev":
    pytest.skip(
        f"RLS integration requiere DB_NAME=borsenhirn_dev (actual: {config.DB_NAME!r}).",
        allow_module_level=True,
    )

pytestmark = pytest.mark.integration

TABLE = "bot_trade_outcomes"
FOREIGN_TENANT = "0000ffff-0000-0000-0000-0000000000ff"   # UUID válido, sin filas
TENANT_B = "00000000-0000-0000-0000-0000000000b0"          # tenant temporal del test #6


def _insert_row_sql() -> str:
    """INSERT con todas las columnas NOT NULL de bot_trade_outcomes."""
    return (
        f"INSERT INTO {TABLE} "
        "(trade_date, symbol, buy_price, sell_price, qty, pnl, win, tenant_id) "
        "VALUES (CURRENT_DATE, 'TEST', 100, 110, 1, 10, true, %s)"
    )


def _count(conn) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {TABLE}")
        return cur.fetchone()[0]


@pytest.fixture
def app_conn():
    """Conexión app con rollback garantizado: ningún test persiste nada."""
    with db.get_conn(role="app") as conn:
        try:
            yield conn
        finally:
            try:
                conn.rollback()
            except Exception:
                pass


# ────────────────────────────────────────────────────────────────
# 1-3. Escrituras: WITH CHECK
# ────────────────────────────────────────────────────────────────

def test_insert_correct_tenant_works(app_conn):
    """Con el tenant correcto, el INSERT entra y es visible (luego rollback)."""
    with db.set_tenant(app_conn, DEFAULT_TENANT_UUID):
        before = _count(app_conn)
        with app_conn.cursor() as cur:
            cur.execute(_insert_row_sql(), (DEFAULT_TENANT_UUID,))
        assert _count(app_conn) == before + 1
    app_conn.rollback()  # no persistir


def test_insert_cross_tenant_rejected(app_conn):
    """Insertar una fila con tenant_id ajeno es rechazado por WITH CHECK."""
    with db.set_tenant(app_conn, DEFAULT_TENANT_UUID):
        with pytest.raises(psycopg2.Error) as exc:
            with app_conn.cursor() as cur:
                cur.execute(_insert_row_sql(), (FOREIGN_TENANT,))
        # 42501 = insufficient_privilege (violación de RLS policy)
        assert exc.value.pgcode == "42501"
    app_conn.rollback()


def test_update_cross_tenant_rejected(app_conn):
    """Reasignar una fila propia a otro tenant es rechazado por WITH CHECK."""
    with db.set_tenant(app_conn, DEFAULT_TENANT_UUID):
        with pytest.raises(psycopg2.Error) as exc:
            with app_conn.cursor() as cur:
                cur.execute(
                    f"UPDATE {TABLE} SET tenant_id = %s "
                    f"WHERE id = (SELECT id FROM {TABLE} LIMIT 1)",
                    (FOREIGN_TENANT,),
                )
        assert exc.value.pgcode == "42501"
    app_conn.rollback()


# ────────────────────────────────────────────────────────────────
# 4. Aggregations respetan RLS
# ────────────────────────────────────────────────────────────────

def test_aggregations_respect_rls(app_conn):
    """COUNT y SUM se calculan después del filtro RLS, no antes."""
    with db.set_tenant(app_conn, DEFAULT_TENANT_UUID):
        with app_conn.cursor() as cur:
            cur.execute(f"SELECT count(*), sum(pnl) FROM {TABLE}")
            n_def, sum_def = cur.fetchone()
    with db.set_tenant(app_conn, FOREIGN_TENANT):
        with app_conn.cursor() as cur:
            cur.execute(f"SELECT count(*), sum(pnl) FROM {TABLE}")
            n_for, sum_for = cur.fetchone()
    assert n_def == 31 and sum_def is not None
    assert n_for == 0 and sum_for is None


# ────────────────────────────────────────────────────────────────
# 5. FK ON DELETE RESTRICT
# ────────────────────────────────────────────────────────────────

def test_fk_on_delete_restrict():
    """Borrar un tenant que tiene filas debe fallar (ON DELETE RESTRICT)."""
    with db.get_conn(role="admin") as conn:
        try:
            with pytest.raises(psycopg2.Error) as exc:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM tenants WHERE tenant_id = %s",
                        (DEFAULT_TENANT_UUID,),
                    )
            # 23001 = restrict_violation (confirma ON DELETE RESTRICT,
            # distinto de 23503 foreign_key_violation que daría NO ACTION).
            assert exc.value.pgcode == "23001"
        finally:
            conn.rollback()


# ────────────────────────────────────────────────────────────────
# 6. Dos tenants reales: cada uno ve solo lo suyo
# ────────────────────────────────────────────────────────────────

@pytest.fixture
def temp_tenant_b():
    """Crea un tenant B temporal (admin) y lo borra en teardown."""
    with db.get_conn(role="admin") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO tenants (tenant_id, slug, email, display_name) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT (tenant_id) DO NOTHING",
                (TENANT_B, "test-b6-tenant", "b6@test.local", "Test Tenant B6"),
            )
        conn.commit()
    try:
        yield TENANT_B
    finally:
        with db.get_conn(role="admin") as conn:
            with conn.cursor() as cur:
                # por si algún test dejó filas (no debería: todo va con rollback)
                cur.execute(f"DELETE FROM {TABLE} WHERE tenant_id = %s", (TENANT_B,))
                cur.execute("DELETE FROM tenants WHERE tenant_id = %s", (TENANT_B,))
            conn.commit()


def test_two_tenants_isolated(app_conn, temp_tenant_b):
    """Tenant B inserta una fila; B ve 1, el default sigue viendo 31."""
    with db.set_tenant(app_conn, temp_tenant_b):
        with app_conn.cursor() as cur:
            cur.execute(_insert_row_sql(), (temp_tenant_b,))
        assert _count(app_conn) == 1                      # B ve solo lo suyo

    with db.set_tenant(app_conn, DEFAULT_TENANT_UUID):
        assert _count(app_conn) == 31                     # default no ve la fila de B
    app_conn.rollback()


# ────────────────────────────────────────────────────────────────
# 7. Cobertura: las 17 tablas A con RLS completo
# ────────────────────────────────────────────────────────────────

def test_all_tenant_tables_have_rls():
    """Toda tabla con columna tenant_id (excepto tenants) tiene RLS + 2 policies."""
    sql = """
        SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
               (SELECT count(*) FROM pg_policies p WHERE p.tablename = c.relname)
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'r'
          AND c.relname <> 'tenants'
          AND EXISTS (
              SELECT 1 FROM information_schema.columns col
              WHERE col.table_name = c.relname AND col.column_name = 'tenant_id'
          )
    """
    with db.get_conn(role="admin") as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()

    assert len(rows) >= 17, f"esperaba >=17 tablas A, vi {len(rows)}"
    offenders = [
        name for name, en, force, npol in rows
        if not en or not force or npol < 2
    ]
    assert not offenders, f"tablas sin RLS completo: {offenders}"
