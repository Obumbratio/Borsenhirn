"""
B1 Bloque 5.6 — Tests de integración RLS end-to-end (rol borsenhirn_app real).

Prueba final del sprint: confirma que las RLS policies del Bloque 4 funcionan
de verdad cuando la app se conecta con el rol `borsenhirn_app`
(NOSUPERUSER + NOBYPASSRLS), usando la capa central `borsenhirn.db`.

NO corren por default (no tocan Postgres en la suite normal). Para correrlos:

    set -a && source .env.dev && set +a
    RUN_DB_INTEGRATION=1 python -m pytest tests/test_b1_rls_integration.py -v

El gate `RUN_DB_INTEGRATION` lo aplica `tests/conftest.py` sobre todos los
tests marcados `@pytest.mark.integration`. Además, este módulo se auto-salta
si `DB_NAME` no es `borsenhirn_dev` — defensa para no tocar producción jamás.

Tabla de verdad sobre `bot_trade_outcomes` (31 filas del default tenant en dev):

    | contexto                         | filas esperadas |
    |----------------------------------|-----------------|
    | sin tenant context              | 0               |
    | tenant DEFAULT (...001)         | 31 (todas)      |
    | tenant ajeno (UUID válido raro) | 0               |
    | bypass_rls (policy admin_bypass)| 31 (todas)      |
"""

from __future__ import annotations

import pytest

import config
from borsenhirn import db
from borsenhirn.tenancy.constants import DEFAULT_TENANT_UUID

# Defensa anti-producción: este módulo SOLO corre contra la DB de desarrollo.
if config.DB_NAME != "borsenhirn_dev":
    pytest.skip(
        f"RLS integration requiere DB_NAME=borsenhirn_dev "
        f"(actual: {config.DB_NAME!r}). Hacé `source .env.dev` antes de correr.",
        allow_module_level=True,
    )

pytestmark = pytest.mark.integration

# UUID válido pero que NO es dueño de ninguna fila legacy.
FOREIGN_TENANT = "0000ffff-0000-0000-0000-0000000000ff"

TABLE = "bot_trade_outcomes"


def _count(conn) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {TABLE}")
        return cur.fetchone()[0]


# ────────────────────────────────────────────────────────────────
# Guard: el rol con el que corremos NO debe bypassear RLS
# ────────────────────────────────────────────────────────────────

def test_app_role_is_not_superuser():
    """Si esto falla, el resto de los tests son ficción (un superuser ve todo)."""
    with db.get_conn(role="app") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT current_user, "
                "(SELECT rolsuper  FROM pg_roles WHERE rolname = current_user), "
                "(SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user)"
            )
            user, is_super, is_bypass = cur.fetchone()
    assert not is_super, f"el rol app {user!r} es SUPERUSER — RLS no se está probando"
    assert not is_bypass, f"el rol app {user!r} tiene BYPASSRLS — RLS no se está probando"


# ────────────────────────────────────────────────────────────────
# Tabla de verdad
# ────────────────────────────────────────────────────────────────

def test_no_context_sees_zero():
    """Sin tenant context, FORCE RLS devuelve 0 filas (fail-closed)."""
    with db.get_conn(role="app") as conn:
        db.clear_current_tenant(conn)
        assert _count(conn) == 0


def test_default_tenant_sees_all():
    """Con el tenant default, se ven todas las filas legacy."""
    with db.get_conn(role="app") as conn:
        with db.set_tenant(conn, DEFAULT_TENANT_UUID):
            n = _count(conn)
    assert n > 0, "el default tenant no ve filas — ¿backfill perdido?"
    assert n == 31, f"esperaba 31 filas legacy en {TABLE}, vi {n}"


def test_foreign_tenant_sees_zero():
    """Un tenant ajeno (UUID válido pero sin datos) ve 0 filas."""
    with db.get_conn(role="app") as conn:
        with db.set_tenant(conn, FOREIGN_TENANT):
            assert _count(conn) == 0


def test_bypass_sees_all():
    """La policy admin_bypass deja ver todo SIN ser superuser."""
    with db.get_conn(role="app") as conn:
        db.clear_current_tenant(conn)
        with db.bypass_rls(conn):
            n = _count(conn)
    assert n == 31, f"con bypass_rls esperaba 31, vi {n}"


# ────────────────────────────────────────────────────────────────
# Cierre defensivo: no dejar estado de sesión colgado en el pool
# ────────────────────────────────────────────────────────────────

def test_zzz_teardown_clears_pool_state():
    """Limpia el GUC de tenant en la conexión reusada del pool."""
    with db.get_conn(role="app") as conn:
        db.clear_current_tenant(conn)
        assert _count(conn) == 0
