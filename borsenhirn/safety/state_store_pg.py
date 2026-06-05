"""
Implementación Postgres de StateStore para killswitch.

Usa psycopg2 directamente (lo mismo que borsenhirn/core/database.py, para
mantener consistencia con el resto del proyecto). Si tu proyecto usa otra
librería (asyncpg, SQLAlchemy), adapta solo los métodos que tocan la DB.
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

from borsenhirn.tenancy import is_valid_tenant_id
from borsenhirn.tenancy.db import TenantContext

logger = logging.getLogger(__name__)


@contextmanager
def _acquire(get_conn):
    """
    Normaliza el factory `get_conn` para no filtrar conexiones del pool.

    - Si `get_conn()` devuelve un context manager (p.ej. `bdb.get_conn()`),
      se entra y se sale de él: la conexión vuelve al pool al terminar la
      operación. Este es el path de runtime correcto (sin leak).
    - Si devuelve una conexión plana (legacy: ks_admin.py, test_alerts.py,
      tests con conn fijo), se cede tal cual; su ciclo de vida lo maneja el
      caller, igual que antes.

    Motivo: antes el store hacía `conn = get_conn()` y nunca la devolvía.
    Con `_safety_get_conn` sacando del pool por cada `is_halted()`, el bot
    agotaba el pool tras ~10 iteraciones del loop (B1 Bloque 7).
    """
    obj = get_conn()
    if hasattr(obj, "__enter__") and hasattr(obj, "__exit__"):
        with obj as conn:
            yield conn
    else:
        yield obj


class PostgresStateStore:
    """
    StateStore para killswitch.

    Recibe una función `get_conn()` que devuelve una conexión psycopg2 ya
    abierta. Cada método abre/cierra cursor pero no la conexión.
    """

    def __init__(self, get_conn, tenant_id: Optional[str] = None):
        """
        Args:
            get_conn: callable que devuelve una conexion psycopg2.
            tenant_id: si se pasa, todas las queries se ejecutan dentro
                de un TenantContext que setea `app.current_tenant_id`.
                Si es None (default), no se aplica scoping — modo
                backwards-compat para callers admin (ks_admin.py) o
                tests que usan BYPASSRLS.
        """
        self.get_conn = get_conn
        if tenant_id is not None and not is_valid_tenant_id(tenant_id):
            raise ValueError(f"tenant_id invalido: {tenant_id!r}")
        self.tenant_id = tenant_id

    @contextmanager
    def _scoped_cursor(self, conn) -> Iterator[Any]:
        """
        Yields un cursor sobre `conn`, opcionalmente envuelto en un
        TenantContext si self.tenant_id != None.
        """
        if self.tenant_id is None:
            with conn.cursor() as cur:
                yield cur
        else:
            with TenantContext(conn, self.tenant_id):
                with conn.cursor() as cur:
                    yield cur

    def _row_to_dict(self, row, cols) -> Dict[str, Any]:
        return dict(zip(cols, row))

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        sql = """
            SELECT key, triggered, reason, data, triggered_at, cleared_at
              FROM killswitch_state
             WHERE key = %s
        """
        with _acquire(self.get_conn) as conn:
            try:
                with self._scoped_cursor(conn) as cur:
                    cur.execute(sql, (key,))
                    row = cur.fetchone()
                    if not row:
                        return None
                    return self._row_to_dict(
                        row, ["key", "triggered", "reason", "data",
                              "triggered_at", "cleared_at"]
                    )
            except Exception as exc:
                logger.error("PostgresStateStore.get(%s) falló: %s", key, exc)
                return None

    def set(self, key: str, triggered: bool, reason: str,
            data: Optional[Dict[str, Any]] = None) -> None:
        sql = """
            INSERT INTO killswitch_state
                (key, triggered, reason, data, triggered_at, cleared_at, updated_at)
            VALUES (%s, %s, %s, %s::jsonb,
                    CASE WHEN %s THEN now() ELSE NULL END,
                    CASE WHEN %s THEN NULL ELSE now() END,
                    now())
            ON CONFLICT (key) DO UPDATE SET
                triggered = EXCLUDED.triggered,
                reason = EXCLUDED.reason,
                data = EXCLUDED.data,
                triggered_at = CASE
                    WHEN EXCLUDED.triggered AND NOT killswitch_state.triggered
                        THEN now()
                    WHEN EXCLUDED.triggered
                        THEN killswitch_state.triggered_at
                    ELSE NULL
                END,
                cleared_at = CASE
                    WHEN NOT EXCLUDED.triggered THEN now()
                    ELSE NULL
                END,
                updated_at = now()
        """
        payload = json.dumps(data or {}, default=str)
        with _acquire(self.get_conn) as conn:
            try:
                with self._scoped_cursor(conn) as cur:
                    cur.execute(sql, (key, triggered, reason, payload,
                                      triggered, triggered))
                conn.commit()
            except Exception as exc:
                logger.error("PostgresStateStore.set(%s) falló: %s", key, exc)
                conn.rollback()

    def list_active(self) -> List[Dict[str, Any]]:
        sql = """
            SELECT key, triggered, reason, data, triggered_at, cleared_at
              FROM killswitch_state
             WHERE triggered = true
             ORDER BY triggered_at DESC NULLS LAST
        """
        with _acquire(self.get_conn) as conn:
            try:
                with self._scoped_cursor(conn) as cur:
                    cur.execute(sql)
                    rows = cur.fetchall()
                    return [
                        self._row_to_dict(
                            r,
                            ["key", "triggered", "reason", "data",
                             "triggered_at", "cleared_at"],
                        )
                        for r in rows
                    ]
            except Exception as exc:
                logger.error("PostgresStateStore.list_active falló: %s", exc)
                return []

    def clear(self, key: str, note: str = "") -> None:
        sql = """
            UPDATE killswitch_state
               SET triggered = false,
                   cleared_at = now(),
                   data = COALESCE(data, '{}'::jsonb)
                          || jsonb_build_object('clear_note', %s),
                   updated_at = now()
             WHERE key = %s
        """
        with _acquire(self.get_conn) as conn:
            try:
                with self._scoped_cursor(conn) as cur:
                    cur.execute(sql, (note, key))
                conn.commit()
            except Exception as exc:
                logger.error("PostgresStateStore.clear(%s) falló: %s", key, exc)
                conn.rollback()


def make_dashboard_db_write(get_conn, tenant_id: Optional[str] = None):
    """
    Helper que devuelve una funcion apta para DashboardChannel.
    Escribe una fila en alerts_log por cada alerta.

    Args:
        get_conn: callable que devuelve una conexion psycopg2.
        tenant_id: si se pasa, cada INSERT se ejecuta dentro de un
            TenantContext (RLS aplica). Si es None (default), no
            se aplica scoping — backwards compat.
    """
    if tenant_id is not None and not is_valid_tenant_id(tenant_id):
        raise ValueError(f"tenant_id invalido: {tenant_id!r}")

    def _write(row: Dict[str, Any]) -> None:
        sql = """
            INSERT INTO alerts_log (level, subject, body, meta)
            VALUES (%s, %s, %s, %s::jsonb)
        """
        with _acquire(get_conn) as conn:
            try:
                if tenant_id is None:
                    with conn.cursor() as cur:
                        cur.execute(sql, (
                            row.get("level"),
                            row.get("subject"),
                            row.get("body"),
                            row.get("meta"),
                        ))
                else:
                    with TenantContext(conn, tenant_id):
                        with conn.cursor() as cur:
                            cur.execute(sql, (
                                row.get("level"),
                                row.get("subject"),
                                row.get("body"),
                                row.get("meta"),
                            ))
                conn.commit()
            except Exception as exc:
                logger.error("alerts_log write falló: %s", exc)
                conn.rollback()
    return _write
