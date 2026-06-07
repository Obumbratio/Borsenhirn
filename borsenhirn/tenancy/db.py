"""
TenantContext: helpers para setear y limpiar `app.current_tenant_id` en
una sesión de Postgres.

Postgres Row-Level Security filtra por una variable de sesión. Cada
conexión que reciba queries del usuario debe configurarse con el
tenant_id correcto al inicio. Si no se setea, FORCE ROW LEVEL SECURITY
hace que todas las queries devuelvan 0 filas — defensa en profundidad
contra fugas accidentales.

Patrón típico:

    conn = open_db_connection()
    with TenantContext(conn, "user-uuid-123"):
        # queries dentro de este bloque ven SOLO los datos de ese tenant
        cur.execute("SELECT * FROM trades")  # implícitamente filtrado
    # al salir del bloque, current_tenant_id se resetea a NULL
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Iterator, Optional

from borsenhirn.tenancy.tenant import is_valid_tenant_id

logger = logging.getLogger(__name__)

# Thread-local para tracking del tenant activo en cada thread.
# Útil para logs/debug y para evitar set redundantes.
_local = threading.local()


def get_current_tenant() -> Optional[str]:
    """Devuelve el tenant_id activo en este thread, o None si no hay."""
    return getattr(_local, "tenant_id", None)


def set_current_tenant(conn, tenant_id: str) -> None:
    """
    Setea `app.current_tenant_id` en la conexión Postgres.

    Args:
        conn: psycopg2 connection.
        tenant_id: UUID string. Validado.

    Raises:
        ValueError si tenant_id no es UUID válido.
    """
    if not is_valid_tenant_id(tenant_id):
        raise ValueError(f"tenant_id inválido: {tenant_id!r}")
    with conn.cursor() as cur:
        # SET LOCAL solo dura la transacción actual; usamos SET para
        # toda la sesión hasta clear_current_tenant().
        cur.execute("SELECT set_config('app.current_tenant_id', %s, false)",
                    (tenant_id,))
    _local.tenant_id = tenant_id
    logger.debug("tenant context set: %s", tenant_id)


def clear_current_tenant(conn) -> None:
    """
    Limpia `app.current_tenant_id`. Después de esto, las queries con RLS
    no devuelven nada (defensa en profundidad).
    """
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('app.current_tenant_id', '', false)")
    _local.tenant_id = None
    logger.debug("tenant context cleared")


class TenantContext:
    """
    Context manager para usar dentro de `with`:

        with TenantContext(conn, tenant_id):
            ...

    Al entrar: SET app.current_tenant_id = <uuid>.
    Al salir: clear (incluso si hay excepción).
    """

    def __init__(self, conn, tenant_id: str):
        if not is_valid_tenant_id(tenant_id):
            raise ValueError(f"tenant_id inválido: {tenant_id!r}")
        self.conn = conn
        self.tenant_id = tenant_id
        self._previous: Optional[str] = None

    def __enter__(self) -> "TenantContext":
        self._previous = get_current_tenant()
        set_current_tenant(self.conn, self.tenant_id)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        # Restaurar tenant previo (puede ser None) — útil cuando se anidan
        try:
            if self._previous is None:
                clear_current_tenant(self.conn)
            else:
                set_current_tenant(self.conn, self._previous)
        except Exception as exc2:   # pragma: no cover
            logger.error("clear_current_tenant fallo en __exit__: %s", exc2)


# ── Helper de conveniencia ──────────────────────────────────


@contextmanager
def open_for_tenant(get_conn_fn, tenant_id: str) -> Iterator:
    """
    Abre una conexión Y la configura para un tenant en una sola línea.

    Uso:
        from bot_memory_pg import _get_conn
        with open_for_tenant(_get_conn, "user-uuid") as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM trades")
                rows = cur.fetchall()   # solo trades del tenant

    NO cierra la conexión al salir — eso lo controla el caller (la
    conexión puede ser de un pool).
    """
    conn = get_conn_fn()
    with TenantContext(conn, tenant_id):
        yield conn
