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
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PostgresStateStore:
    """
    StateStore para killswitch.

    Recibe una función `get_conn()` que devuelve una conexión psycopg2 ya
    abierta. Cada método abre/cierra cursor pero no la conexión.
    """

    def __init__(self, get_conn):
        self.get_conn = get_conn

    def _row_to_dict(self, row, cols) -> Dict[str, Any]:
        return dict(zip(cols, row))

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        sql = """
            SELECT key, triggered, reason, data, triggered_at, cleared_at
              FROM killswitch_state
             WHERE key = %s
        """
        conn = self.get_conn()
        try:
            with conn.cursor() as cur:
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
        conn = self.get_conn()
        try:
            with conn.cursor() as cur:
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
        conn = self.get_conn()
        try:
            with conn.cursor() as cur:
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
        conn = self.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (note, key))
            conn.commit()
        except Exception as exc:
            logger.error("PostgresStateStore.clear(%s) falló: %s", key, exc)
            conn.rollback()


def make_dashboard_db_write(get_conn):
    """
    Helper que devuelve una función apta para DashboardChannel.
    Escribe una fila en alerts_log por cada alerta.
    """
    def _write(row: Dict[str, Any]) -> None:
        sql = """
            INSERT INTO alerts_log (level, subject, body, meta)
            VALUES (%s, %s, %s, %s::jsonb)
        """
        conn = get_conn()
        try:
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
