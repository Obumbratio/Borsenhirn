"""
borsenhirn.tenancy — multi-tenancy con Postgres Row-Level Security.

Componentes:
    tenant:     dataclass Tenant + helpers (uuid, slug, validation).
    db:         TenantContext (context manager) que setea app.current_tenant_id.
    management: TenantManager (CRUD: create, get, list, disable).

Filosofía:
    - Un único Postgres con RLS. Cada query lleva tenant_id implícito.
    - Cada conexión hace `SET app.current_tenant_id = '<uuid>'` al inicio.
    - Las policies en cada tabla filtran por current_setting('app.current_tenant_id').
    - SYSTEM_TENANT_ID = '00...0' para datos pre-multi-tenant (el bot single-user actual).
"""

from borsenhirn.tenancy.tenant import (
    SYSTEM_TENANT_ID,
    Tenant,
    TenantStatus,
    is_valid_tenant_id,
    new_tenant_id,
)
from borsenhirn.tenancy.db import (
    TenantContext,
    set_current_tenant,
    clear_current_tenant,
    get_current_tenant,
)
from borsenhirn.tenancy.management import TenantManager

__all__ = [
    "SYSTEM_TENANT_ID",
    "Tenant",
    "TenantStatus",
    "TenantContext",
    "TenantManager",
    "is_valid_tenant_id",
    "new_tenant_id",
    "set_current_tenant",
    "clear_current_tenant",
    "get_current_tenant",
]
