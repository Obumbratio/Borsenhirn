"""
TenantManager: CRUD de la tabla `tenants`.

NO requiere RLS — la tabla `tenants` es shared (un admin debe poder ver
todos los tenants). El control de acceso a esta tabla se hace a nivel
de aplicación (solo admins pueden invocar TenantManager).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, List, Optional

from borsenhirn.tenancy.tenant import (
    Tenant,
    TenantStatus,
    is_valid_email,
    is_valid_slug,
    is_valid_tenant_id,
    new_tenant_id,
)

logger = logging.getLogger(__name__)


class TenantManager:
    """
    CRUD de tenants. Recibe `get_conn` callable para no acoplarse al driver.
    """

    def __init__(self, get_conn: Callable[[], Any]):
        self.get_conn = get_conn

    # ── create ───────────────────────────────────────────

    def create_tenant(
        self,
        email: str,
        display_name: str,
        slug: Optional[str] = None,
        tenant_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Tenant:
        """
        Crea un tenant nuevo.

        Args:
            email: email del usuario.
            display_name: nombre amigable.
            slug: opcional. Si no se da, se genera derivado del email.
            tenant_id: opcional. Si no se da, se genera UUID v4.
            metadata: dict opcional.

        Raises:
            ValueError si los inputs son inválidos.
        """
        if not is_valid_email(email):
            raise ValueError(f"email inválido: {email!r}")
        if not display_name or len(display_name) > 200:
            raise ValueError("display_name debe tener entre 1 y 200 chars")

        tid = tenant_id or new_tenant_id()
        if not is_valid_tenant_id(tid):
            raise ValueError(f"tenant_id inválido: {tid!r}")

        slug_final = slug or self._derive_slug(email, tid)
        if not is_valid_slug(slug_final):
            raise ValueError(f"slug inválido: {slug_final!r}")

        meta = metadata or {}

        sql = """
            INSERT INTO tenants
                (tenant_id, slug, email, display_name, status, metadata)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            RETURNING tenant_id, slug, email, display_name, status,
                      created_at, updated_at, suspended_at, metadata
        """
        conn = self.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    tid, slug_final, email, display_name,
                    TenantStatus.ACTIVE.value, json.dumps(meta),
                ))
                row = cur.fetchone()
            conn.commit()
            logger.info("Tenant creado: %s (%s)", tid, slug_final)
            return self._row_to_tenant(row)
        except Exception as exc:
            conn.rollback()
            logger.error("create_tenant fallo: %s", exc)
            raise

    # ── get ──────────────────────────────────────────────

    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """Devuelve el Tenant o None si no existe."""
        if not is_valid_tenant_id(tenant_id):
            raise ValueError(f"tenant_id inválido: {tenant_id!r}")
        sql = """
            SELECT tenant_id, slug, email, display_name, status,
                   created_at, updated_at, suspended_at, metadata
              FROM tenants
             WHERE tenant_id = %s
        """
        conn = self.get_conn()
        with conn.cursor() as cur:
            cur.execute(sql, (tenant_id,))
            row = cur.fetchone()
        return self._row_to_tenant(row) if row else None

    def get_tenant_by_slug(self, slug: str) -> Optional[Tenant]:
        if not is_valid_slug(slug):
            raise ValueError(f"slug inválido: {slug!r}")
        sql = """
            SELECT tenant_id, slug, email, display_name, status,
                   created_at, updated_at, suspended_at, metadata
              FROM tenants
             WHERE slug = %s
        """
        conn = self.get_conn()
        with conn.cursor() as cur:
            cur.execute(sql, (slug,))
            row = cur.fetchone()
        return self._row_to_tenant(row) if row else None

    def get_tenant_by_email(self, email: str) -> Optional[Tenant]:
        if not is_valid_email(email):
            raise ValueError(f"email inválido: {email!r}")
        sql = """
            SELECT tenant_id, slug, email, display_name, status,
                   created_at, updated_at, suspended_at, metadata
              FROM tenants
             WHERE lower(email) = lower(%s)
        """
        conn = self.get_conn()
        with conn.cursor() as cur:
            cur.execute(sql, (email,))
            row = cur.fetchone()
        return self._row_to_tenant(row) if row else None

    # ── list ─────────────────────────────────────────────

    def list_tenants(
        self,
        status: Optional[TenantStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Tenant]:
        if status:
            sql = """
                SELECT tenant_id, slug, email, display_name, status,
                       created_at, updated_at, suspended_at, metadata
                  FROM tenants
                 WHERE status = %s
                 ORDER BY created_at DESC
                 LIMIT %s OFFSET %s
            """
            params: tuple = (status.value, limit, offset)
        else:
            sql = """
                SELECT tenant_id, slug, email, display_name, status,
                       created_at, updated_at, suspended_at, metadata
                  FROM tenants
                 ORDER BY created_at DESC
                 LIMIT %s OFFSET %s
            """
            params = (limit, offset)
        conn = self.get_conn()
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [self._row_to_tenant(r) for r in rows]

    def count_tenants(self, status: Optional[TenantStatus] = None) -> int:
        if status:
            sql = "SELECT COUNT(*) FROM tenants WHERE status = %s"
            params: tuple = (status.value,)
        else:
            sql = "SELECT COUNT(*) FROM tenants"
            params = ()
        conn = self.get_conn()
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return int(cur.fetchone()[0])

    # ── update / suspend / disable ───────────────────────

    def update_status(self, tenant_id: str, new_status: TenantStatus,
                       reason: Optional[str] = None) -> bool:
        if not is_valid_tenant_id(tenant_id):
            raise ValueError(f"tenant_id inválido: {tenant_id!r}")
        suspended_at_clause = (
            "now()" if new_status == TenantStatus.SUSPENDED else "NULL"
        )
        sql = f"""
            UPDATE tenants
               SET status = %s,
                   suspended_at = {suspended_at_clause},
                   metadata = COALESCE(metadata, '{{}}'::jsonb)
                              || jsonb_build_object('last_status_change_reason', %s,
                                                    'last_status_change_at', now()::text)
             WHERE tenant_id = %s
        """
        conn = self.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (new_status.value, reason or "", tenant_id))
                changed = cur.rowcount
            conn.commit()
            return changed > 0
        except Exception as exc:
            conn.rollback()
            logger.error("update_status fallo: %s", exc)
            raise

    def suspend(self, tenant_id: str, reason: str = "") -> bool:
        return self.update_status(tenant_id, TenantStatus.SUSPENDED, reason)

    def disable(self, tenant_id: str, reason: str = "") -> bool:
        return self.update_status(tenant_id, TenantStatus.DISABLED, reason)

    def reactivate(self, tenant_id: str, reason: str = "") -> bool:
        return self.update_status(tenant_id, TenantStatus.ACTIVE, reason)

    # ── delete (soft) ────────────────────────────────────

    def soft_delete(self, tenant_id: str, reason: str = "") -> bool:
        """
        Marca como 'deleted' (NO borra realmente). Para hard delete,
        ejecutar DELETE manualmente después de un período de gracia.
        """
        return self.update_status(tenant_id, TenantStatus.DELETED, reason)

    # ── helpers privados ─────────────────────────────────

    def _row_to_tenant(self, row) -> Tenant:
        if row is None:
            return None  # type: ignore
        (tid, slug, email, name, status, created, updated,
         suspended, metadata) = row
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (ValueError, TypeError):
                metadata = {}
        return Tenant(
            tenant_id=str(tid),
            slug=slug,
            email=email,
            display_name=name,
            status=TenantStatus(status),
            created_at=created,
            updated_at=updated,
            suspended_at=suspended,
            metadata=metadata or {},
        )

    @staticmethod
    def _derive_slug(email: str, tenant_id: str) -> str:
        """
        Genera un slug a partir de email + sufijo random del tenant_id.
        Ej: 'uriel.castano@gmail.com' + 'a1b2...' → 'uriel-castano-a1b2'
        """
        local = email.split("@", 1)[0].lower()
        # solo letras, dígitos, guiones
        clean = "".join(c if c.isalnum() else "-" for c in local)
        clean = "-".join(filter(None, clean.split("-")))[:30]
        suffix = tenant_id.replace("-", "")[:4]
        slug = f"{clean}-{suffix}" if clean else f"user-{suffix}"
        # Asegurar que cumple regex (3-40 chars, empieza/termina con alphanum)
        if len(slug) < 3:
            slug = f"user-{suffix}"
        return slug
