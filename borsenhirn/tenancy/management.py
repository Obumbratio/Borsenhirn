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

    def get_tenant_by_clerk_id(self, clerk_user_id: str) -> Optional[Tenant]:
        """Devuelve el Tenant mapeado a ese clerk_user_id, o None (B3)."""
        if not clerk_user_id:
            raise ValueError("clerk_user_id vacío")
        sql = """
            SELECT tenant_id, slug, email, display_name, status,
                   created_at, updated_at, suspended_at, metadata
              FROM tenants
             WHERE clerk_user_id = %s
        """
        conn = self.get_conn()
        with conn.cursor() as cur:
            cur.execute(sql, (clerk_user_id,))
            row = cur.fetchone()
        return self._row_to_tenant(row) if row else None

    def provision_for_clerk_user(
        self, clerk_user_id: str, email: str, display_name: str,
    ) -> Tenant:
        """
        Resuelve (o crea) el tenant de un usuario Clerk. Modelo 1:1 (B3).

        Lazy + race-safe: si no existe, INSERT con
        `ON CONFLICT (clerk_user_id) DO NOTHING`; si otro request ganó la
        carrera, re-lookup. Sin tenants huérfanos.

        Corre con credenciales admin (escribe en `tenants`).
        """
        if not clerk_user_id:
            raise ValueError("clerk_user_id vacío")
        existing = self.get_tenant_by_clerk_id(clerk_user_id)
        if existing:
            return existing
        if not is_valid_email(email):
            raise ValueError(f"email inválido: {email!r}")
        if not display_name or len(display_name) > 200:
            raise ValueError("display_name debe tener entre 1 y 200 chars")

        tid = new_tenant_id()
        slug = self._derive_slug(email, tid)
        meta = {"clerk_user_id": clerk_user_id, "source": "clerk"}
        sql = """
            INSERT INTO tenants
                (tenant_id, slug, email, display_name, status, metadata, clerk_user_id)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT (clerk_user_id) DO NOTHING
            RETURNING tenant_id, slug, email, display_name, status,
                      created_at, updated_at, suspended_at, metadata
        """
        conn = self.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    tid, slug, email, display_name,
                    TenantStatus.ACTIVE.value, json.dumps(meta), clerk_user_id,
                ))
                row = cur.fetchone()
            conn.commit()
        except Exception as exc:
            conn.rollback()
            logger.error("provision_for_clerk_user fallo: %s", exc)
            raise
        if row:
            logger.info("Tenant provisionado para clerk_user=%s -> %s",
                        clerk_user_id, tid)
            return self._row_to_tenant(row)
        # Conflicto: otro request lo creó primero → re-lookup.
        existing = self.get_tenant_by_clerk_id(clerk_user_id)
        if existing:
            return existing
        raise RuntimeError(
            f"no se pudo provisionar ni resolver clerk_user={clerk_user_id!r}"
        )

    # ── billing (B4) ─────────────────────────────────────

    def get_tenant_by_stripe_customer_id(self, customer_id: str) -> Optional[Tenant]:
        """Devuelve el Tenant con ese stripe_customer_id, o None (lookup de webhook)."""
        if not customer_id:
            raise ValueError("customer_id vacío")
        sql = """
            SELECT tenant_id, slug, email, display_name, status,
                   created_at, updated_at, suspended_at, metadata
              FROM tenants
             WHERE stripe_customer_id = %s
        """
        conn = self.get_conn()
        with conn.cursor() as cur:
            cur.execute(sql, (customer_id,))
            row = cur.fetchone()
        return self._row_to_tenant(row) if row else None

    def get_stripe_customer_id(self, tenant_id: str) -> Optional[str]:
        """Devuelve el stripe_customer_id del tenant, o None."""
        if not is_valid_tenant_id(tenant_id):
            raise ValueError(f"tenant_id inválido: {tenant_id!r}")
        conn = self.get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT stripe_customer_id FROM tenants WHERE tenant_id = %s",
                (tenant_id,),
            )
            row = cur.fetchone()
        return row[0] if row and row[0] else None

    def set_billing(
        self,
        tenant_id: str,
        *,
        customer_id: Optional[str] = None,
        subscription_id: Optional[str] = None,
        plan: Optional[str] = None,
        status: Optional[str] = None,
        current_period_end=None,
    ) -> None:
        """
        Actualiza los campos de billing del tenant (los que se pasen).
        `status` se valida contra el CHECK de tenants; el mapeo
        stripe_status -> status lo hace la capa de billing (B4.3).
        """
        if not is_valid_tenant_id(tenant_id):
            raise ValueError(f"tenant_id inválido: {tenant_id!r}")
        fields, params = [], []
        if customer_id is not None:
            fields.append("stripe_customer_id = %s"); params.append(customer_id)
        if subscription_id is not None:
            fields.append("stripe_subscription_id = %s"); params.append(subscription_id)
        if plan is not None:
            fields.append("plan = %s"); params.append(plan)
        if current_period_end is not None:
            fields.append("current_period_end = %s"); params.append(current_period_end)
        if status is not None:
            if status not in ("active", "suspended", "disabled", "deleted"):
                raise ValueError(f"status inválido: {status!r}")
            fields.append("status = %s"); params.append(status)
        if not fields:
            return
        fields.append("updated_at = now()")
        sql = f"UPDATE tenants SET {', '.join(fields)} WHERE tenant_id = %s"
        params.append(tenant_id)
        conn = self.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            logger.error("set_billing(%s) falló: %s", tenant_id, exc)
            raise

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
