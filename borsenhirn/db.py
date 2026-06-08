"""
borsenhirn.db — Connection layer central para multi-tenancy con RLS.

Esta capa centraliza la obtención de conexiones Postgres y la gestión
del contexto de tenant. Después de B1 toda la persistencia debe pasar
por acá. El módulo es independiente — al cargarse no abre ninguna
conexión, los pools son lazy.

Conceptos:

    APP role  vs  ADMIN role
    -------------------------
    - APP role (`borsenhirn_app`, NOSUPERUSER + NOBYPASSRLS):
        para todo el código de runtime. Las RLS policies filtran filas
        por `app.current_tenant_id`. Si no se setea el tenant context,
        las queries devuelven 0 filas (defensa en profundidad).
    - ADMIN role (`postgres`, SUPERUSER + BYPASSRLS):
        SOLO para tareas administrativas: migrations, TenantManager
        lifecycle, batch jobs cross-tenant. NUNCA desde código de runtime.

    Tenant context
    --------------
    Toda query desde el APP pool DEBE estar dentro de un `set_tenant`
    block:

        with get_conn() as conn, set_tenant(conn, DEFAULT_TENANT_UUID):
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM bot_trade_outcomes")
                rows = cur.fetchall()  # filtradas por RLS

    Bypass (peligroso)
    ------------------
    Para reportes admin que necesitan ver across tenants:

        with get_conn(role='admin') as conn, bypass_rls(conn):
            cur.execute("SELECT tenant_id, count(*) FROM bot_trade_outcomes GROUP BY 1")

Configuración
-------------
Lee de `config.py` (top-level):
    DB_HOST, DB_PORT, DB_NAME            — endpoint común
    DB_USER, DB_PASSWORD                 — admin (postgres)
    APP_DB_USER, APP_DB_PASSWORD         — app (borsenhirn_app)

Si `APP_DB_USER` no está seteado, hace fallback a `DB_USER` (vía
config.py default). En ese modo el bot funciona como antes (single-user
con BYPASSRLS), pero NO obtenés enforcement de aislamiento. Activá las
APP creds en `.env.dev`/`.env` para tener seguridad real.

Tests
-----
Para tests, monkeypatch el factory:

    from unittest.mock import MagicMock
    from borsenhirn import db
    fake_conn = MagicMock()
    db.set_connection_factory(lambda role: fake_conn)
    try:
        ...  # tu código bajo test
    finally:
        db.clear_connection_factory()
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Optional

import psycopg2
import psycopg2.extensions
import psycopg2.pool

import config

from borsenhirn.tenancy.constants import DEFAULT_TENANT_UUID, SYSTEM_TENANT_ID
from borsenhirn.tenancy.db import (
    TenantContext,
    clear_current_tenant,
    get_current_tenant,
    set_current_tenant,
)


logger = logging.getLogger(__name__)


# =====================================================================
# Adaptadores numpy -> psycopg2
# =====================================================================
# numpy 2.0 cambió el repr de los escalares (`repr(np.float64(0.75))` pasó a
# ser "np.float64(0.75)"); psycopg2 los renderiza con ese repr y produce SQL
# inválido ("schema np does not exist"). Registramos adaptadores que castean a
# tipos Python nativos, así CUALQUIER INSERT con valores numpy funciona.
try:
    import numpy as _np
    from psycopg2.extensions import register_adapter as _reg, AsIs as _AsIs

    _reg(_np.float64, lambda v: _AsIs(repr(float(v))))
    _reg(_np.float32, lambda v: _AsIs(repr(float(v))))
    _reg(_np.int64,   lambda v: _AsIs(int(v)))
    _reg(_np.int32,   lambda v: _AsIs(int(v)))
    _reg(_np.bool_,   lambda v: _AsIs("true" if v else "false"))
except Exception:   # numpy ausente o API distinta: no es fatal
    pass


# =====================================================================
# Pools (lazy singletons)
# =====================================================================

_pool_lock = threading.Lock()
_app_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None
_admin_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None

# Defaults razonables. Si más adelante necesitás tunearlos, exponé como
# env vars en config.py. Para single-user dev sobra con 1-10.
_POOL_MIN = 1
_POOL_MAX = 10


def _make_pool(user: str, password: str) -> psycopg2.pool.ThreadedConnectionPool:
    """Construye un ThreadedConnectionPool con la config global de DB."""
    return psycopg2.pool.ThreadedConnectionPool(
        minconn=_POOL_MIN,
        maxconn=_POOL_MAX,
        host=config.DB_HOST,
        port=config.DB_PORT,
        dbname=config.DB_NAME,
        user=user,
        password=password,
    )


def get_app_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """
    Devuelve el pool de runtime (rol APP, sujeto a RLS).

    El pool se crea una única vez por proceso (singleton lazy). Las
    queries por defecto van por acá.
    """
    global _app_pool
    if _app_pool is None:
        with _pool_lock:
            if _app_pool is None:
                _app_pool = _make_pool(config.APP_DB_USER, config.APP_DB_PASSWORD)
                logger.info(
                    "App pool initialized: user=%s db=%s host=%s",
                    config.APP_DB_USER, config.DB_NAME, config.DB_HOST,
                )
    return _app_pool


def get_admin_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """
    Devuelve el pool admin (rol superuser, BYPASSRLS).

    Usar SOLO para migrations, TenantManager, y batch jobs admin.
    Nunca desde código de runtime.
    """
    global _admin_pool
    if _admin_pool is None:
        with _pool_lock:
            if _admin_pool is None:
                _admin_pool = _make_pool(config.DB_USER, config.DB_PASSWORD)
                logger.info(
                    "Admin pool initialized: user=%s db=%s host=%s",
                    config.DB_USER, config.DB_NAME, config.DB_HOST,
                )
    return _admin_pool


def close_all_pools() -> None:
    """
    Cierra ambos pools y resetea su estado lazy. Útil en shutdowns
    limpios o tests que necesitan recrear todo.
    """
    global _app_pool, _admin_pool
    with _pool_lock:
        if _app_pool is not None:
            try:
                _app_pool.closeall()
            except Exception as exc:   # pragma: no cover
                logger.warning("Error closing app pool: %s", exc)
            _app_pool = None
        if _admin_pool is not None:
            try:
                _admin_pool.closeall()
            except Exception as exc:   # pragma: no cover
                logger.warning("Error closing admin pool: %s", exc)
            _admin_pool = None


# =====================================================================
# Test injection hook
# =====================================================================
#
# Si los tests no quieren tocar Postgres real, pueden inyectar un
# factory que reemplaza la obtención de conexiones del pool.
# El factory recibe (role: str) y debe devolver un objeto compatible
# con psycopg2.connection (en la práctica, FakeConn / MagicMock).

_connection_factory: Optional[Callable[[str], Any]] = None


def set_connection_factory(factory: Optional[Callable[[str], Any]]) -> None:
    """
    Inyecta un factory que reemplaza la obtención de conexiones del pool.

    Si `factory` es None, se restaura el comportamiento normal (pools).

    Ejemplo en test:

        from borsenhirn import db
        fake = MagicMock()
        db.set_connection_factory(lambda role: fake)
        try:
            ... # código bajo test
        finally:
            db.clear_connection_factory()
    """
    global _connection_factory
    _connection_factory = factory


def clear_connection_factory() -> None:
    """Atajo para `set_connection_factory(None)`."""
    set_connection_factory(None)


# =====================================================================
# Connection context manager
# =====================================================================

@contextmanager
def get_conn(role: str = "app") -> Iterator[Any]:
    """
    Context manager que entrega una conexión del pool indicado y la
    devuelve al salir (no la cierra).

    Args:
        role: "app" (default — sujeto a RLS, uso normal de runtime)
              o "admin" (BYPASSRLS — solo para tareas administrativas).

    Yields:
        psycopg2.connection. Si hay un factory de tests inyectado,
        devuelve lo que el factory retorne.

    Comportamiento al salir:
        - Si la conexión sigue en transacción abierta (no commit/rollback
          explícito por el caller), se hace rollback para no propagar
          estado al siguiente consumidor del pool.
        - Si la conexión fue cerrada (`conn.closed`), se descarta del
          pool con `putconn(close=True)`.

    Ejemplos:

        # Lectura normal de runtime
        with get_conn() as conn, set_tenant(conn, tenant_id):
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM bot_trade_outcomes")

        # Operación admin
        with get_conn(role="admin") as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM tenants")
            conn.commit()
    """
    if role not in ("app", "admin"):
        raise ValueError(f"role must be 'app' or 'admin', got {role!r}")

    # Test path: bypass del pool real.
    if _connection_factory is not None:
        conn = _connection_factory(role)
        try:
            yield conn
        finally:
            # No cleanup automático en tests; el factory/test decide.
            pass
        return

    pool = get_app_pool() if role == "app" else get_admin_pool()
    conn = pool.getconn()
    try:
        yield conn
    finally:
        _safely_return(pool, conn)


def _safely_return(
    pool: psycopg2.pool.ThreadedConnectionPool,
    conn: Any,
) -> None:
    """
    Devuelve `conn` al pool. Si quedó una transacción abierta, hace
    rollback antes para que el próximo consumidor reciba una conexión
    en estado IDLE.
    """
    try:
        if getattr(conn, "closed", 0):
            pool.putconn(conn, close=True)
            return

        # Si quedó una transacción abierta sin commit/rollback explícito,
        # rollback para no contaminar el pool.
        try:
            tx_status = conn.info.transaction_status
        except Exception:
            tx_status = None

        if tx_status not in (
            None,
            psycopg2.extensions.TRANSACTION_STATUS_IDLE,
        ):
            try:
                conn.rollback()
            except Exception as exc:   # pragma: no cover
                logger.warning("rollback fallo en cleanup: %s", exc)

        pool.putconn(conn)
    except Exception as exc:   # pragma: no cover
        logger.warning("putconn fallo: %s", exc)


# =====================================================================
# Tenant context (re-export user-friendly)
# =====================================================================
#
# `set_tenant` es alias literal de `TenantContext` (de tenancy/db.py).
# Sintaxis idéntica:
#
#     with set_tenant(conn, tenant_id):
#         ...
#
# Lo re-exportamos acá para que los callers necesiten un único import:
# `from borsenhirn.db import get_conn, set_tenant`.

set_tenant = TenantContext


# =====================================================================
# Bypass RLS (admin only)
# =====================================================================

@contextmanager
def bypass_rls(conn: Any) -> Iterator[None]:
    """
    Activa la policy `admin_bypass` de las 17 tablas A durante la
    transacción actual. Esto vuelve TODAS las filas visibles, ignorando
    el filtro de tenant.

    PELIGRO: usar SOLO para tareas administrativas explícitas (reportes
    cross-tenant, batch jobs). Loggea WARNING al activarse para que
    quede traza en logs.

    Implementación: `SET LOCAL app.bypass_rls = 'on'`. El `LOCAL` hace
    que el efecto dure SOLO la transacción actual; al hacer COMMIT /
    ROLLBACK se descarta automáticamente. Igualmente, al salir del
    context lo limpiamos explícitamente por defensa.

    Pre-requisito: la conexión debe estar en una transacción (cualquier
    cursor.execute la abre implícitamente). Si no hay txn, el SET LOCAL
    se descarta inmediatamente y la policy no aplica.

    Ejemplo:

        with get_conn(role="admin") as conn, bypass_rls(conn):
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT tenant_id, count(*) FROM bot_trade_outcomes "
                    "GROUP BY 1"
                )
                rows = cur.fetchall()
    """
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('app.bypass_rls', 'on', true)")
    logger.warning(
        "bypass_rls ACTIVATED — RLS filter disabled for this transaction"
    )
    try:
        yield
    finally:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.bypass_rls', '', true)")
        except Exception as exc:   # pragma: no cover
            logger.error("bypass_rls cleanup fallo: %s", exc)


# =====================================================================
# Public API
# =====================================================================

__all__ = [
    # Constants
    "DEFAULT_TENANT_UUID",
    "SYSTEM_TENANT_ID",
    # Pool management
    "get_app_pool",
    "get_admin_pool",
    "close_all_pools",
    # Connection context
    "get_conn",
    # Test injection
    "set_connection_factory",
    "clear_connection_factory",
    # Tenant context (re-exports + alias)
    "TenantContext",
    "set_tenant",
    "set_current_tenant",
    "clear_current_tenant",
    "get_current_tenant",
    # Bypass for admin tasks
    "bypass_rls",
]
