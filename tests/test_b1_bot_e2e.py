"""
B1 Bloque 7 — Bot end-to-end contra borsenhirn_dev (capa DB).

Ejercita exactamente lo que B1 cambió: la capa de persistencia del bot
(`BotMemory` y `SafetyStack`) operando contra la DB real con el rol app
bajo RLS, tal como `main.run()` la construye. SIN red ni Alpaca ni órdenes.

Estrategia de aislamiento: todo corre bajo un TENANT DE TEST temporal
(`…00e7`). Las escrituras commitean de verdad (BotMemory commitea solo),
pero van a ese tenant y se borran en teardown. Las 128 filas del default
tenant nunca se tocan — se verifica al final.

Gating idéntico a 5.6/B6: `@pytest.mark.integration` + auto-skip si
DB_NAME != borsenhirn_dev.

Correr:
    set -a && source .env.dev && set +a
    RUN_DB_INTEGRATION=1 venv/bin/pytest tests/test_b1_bot_e2e.py -v
"""

from __future__ import annotations

import pytest

import config
from borsenhirn import db
from borsenhirn.tenancy.constants import DEFAULT_TENANT_UUID

if config.DB_NAME != "borsenhirn_dev":
    pytest.skip(
        f"e2e requiere DB_NAME=borsenhirn_dev (actual: {config.DB_NAME!r}).",
        allow_module_level=True,
    )

pytestmark = pytest.mark.integration

E2E_TENANT = "00000000-0000-0000-0000-0000000000e7"


def _count_under(tenant_id: str, table: str = "bot_trade_outcomes") -> int:
    with db.get_conn(role="app") as conn, db.set_tenant(conn, tenant_id):
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM {table}")
            return cur.fetchone()[0]


def _tenant_tables(conn) -> list:
    """Las tablas con columna tenant_id (excepto tenants)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.relname
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname='public' AND c.relkind='r' AND c.relname <> 'tenants'
              AND EXISTS (SELECT 1 FROM information_schema.columns col
                          WHERE col.table_name=c.relname AND col.column_name='tenant_id')
            """
        )
        return [r[0] for r in cur.fetchall()]


@pytest.fixture
def e2e_tenant():
    """Crea un tenant de test y borra TODAS sus filas en teardown."""
    with db.get_conn(role="admin") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO tenants (tenant_id, slug, email, display_name) "
                "VALUES (%s,%s,%s,%s) ON CONFLICT (tenant_id) DO NOTHING",
                (E2E_TENANT, "e2e-b7", "e2e@test.local", "E2E Tenant B7"),
            )
        conn.commit()
    try:
        yield E2E_TENANT
    finally:
        with db.get_conn(role="admin") as conn:
            with conn.cursor() as cur:
                for t in _tenant_tables(conn):
                    cur.execute(f"DELETE FROM {t} WHERE tenant_id = %s", (E2E_TENANT,))
                cur.execute("DELETE FROM tenants WHERE tenant_id = %s", (E2E_TENANT,))
            conn.commit()
        db.close_all_pools()  # descarta conns filtradas por la safety stack


# ────────────────────────────────────────────────────────────────
# BotMemory: round-trips de escritura/lectura bajo el tenant de test
# ────────────────────────────────────────────────────────────────

def test_botmemory_roundtrips(e2e_tenant):
    from bot_memory_pg import BotMemory

    mem = BotMemory(tenant_id=e2e_tenant)   # constructor corre bootstrap DDL vía admin pool

    # trade outcome
    pnl = mem.record_trade_outcome("SPY", 100.0, 110.0, 10, "e2e-test")
    assert pnl == 100.0
    stats = mem.get_win_stats(last_n=20)
    assert stats and stats.get("wins", 0) >= 1

    # symbol score
    mem.update_symbol_score("SPY", won=True, pnl=100.0)
    assert isinstance(mem.get_symbol_score("SPY"), float)
    assert any(s.get("symbol") == "SPY" for s in mem.get_top_symbols(10))

    # daily state
    mem.update_daily_state(trades_today=1, wins_today=1, losses_today=0,
                           day_start_equity=100_000.0)
    ds = mem.get_daily_state()
    assert ds and ds.get("trades_today") == 1

    # ml metrics
    mem.record_ml_metrics(accuracy=0.80, precision=0.70, recall=0.60,
                          f1=0.65, n_samples=1000)
    assert len(mem.get_ml_metrics_history(n=5)) >= 1

    # entry price set/get/clear
    mem.set_entry_price("SPY", 123.45)
    assert mem.get_entry_price("SPY") == 123.45
    mem.clear_entry_price("SPY")
    assert mem.get_entry_price("SPY") is None

    # log_summary lee varias tablas — no debe crashear
    mem.log_summary()


# ────────────────────────────────────────────────────────────────
# Aislamiento: lo escrito por el tenant de test NO contamina el default
# ────────────────────────────────────────────────────────────────

def test_e2e_writes_isolated_from_default(e2e_tenant):
    from bot_memory_pg import BotMemory

    BotMemory(tenant_id=e2e_tenant).record_trade_outcome("SPY", 100.0, 110.0, 10, "e2e")

    assert _count_under(e2e_tenant) == 1        # el tenant de test ve su fila
    assert _count_under(DEFAULT_TENANT_UUID) == 31   # el default sigue intacto


# ────────────────────────────────────────────────────────────────
# SafetyStack: kill switch read/write bajo el tenant de test
# ────────────────────────────────────────────────────────────────

def test_safety_stack_killswitch(e2e_tenant):
    from borsenhirn.safety.bootstrap import SafetyStack

    # get_conn_fn idéntico al _safety_get_conn de main.py (conn del app pool)
    def get_conn_fn():
        return db.get_app_pool().getconn()

    stack = SafetyStack.init_from_config(get_conn_fn, tenant_id=e2e_tenant)

    assert not stack.is_halted()
    stack.killswitch.manual_halt("e2e bloque 7")
    assert stack.is_halted()
    assert len(stack.killswitch.active_reasons()) >= 1
    stack.killswitch.clear_all("e2e cleanup")
    assert not stack.is_halted()
