"""
borsenhirn.tenancy — multi-tenancy con Postgres Row-Level Security.

Componentes:
    constants:  UUIDs especiales (SYSTEM_TENANT_ID, DEFAULT_TENANT_UUID).
    tenant:     dataclass Tenant + helpers (uuid, slug, validation).
    db:         TenantContext (context manager) que setea app.current_tenant_id.
    management: TenantManager (CRUD: create, get, list, disable).

Filosofía:
    - Un único Postgres con RLS. Cada query lleva tenant_id implícito.
    - Cada conexión hace `SET app.current_tenant_id = '<uuid>'` al inicio.
    - Las policies en cada tabla filtran por current_setting('app.current_tenant_id').
    - SYSTEM_TENANT_ID = '00...0' es sentinel cross-cutting (NO existe como fila).
    - DEFAULT_TENANT_UUID = '00...1' es el tenant real para data legacy single-user.
"""

from borsenhirn.tenancy.constants import (
    DEFAULT_TENANT_UUID,
    SYSTEM_TENANT_ID,
)
from borsenhirn.tenancy.tenant import (
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
    "DEFAULT_TENANT_UUID",
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
