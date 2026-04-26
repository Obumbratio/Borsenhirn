"""
Modelo Tenant + helpers de identidad.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


# UUID reservado para datos pre-multi-tenant (single-user histórico).
# Cuando migrés bot_memory_pg.py al modelo multi-tenant, las filas
# existentes se backfillean con este tenant_id.
SYSTEM_TENANT_ID = "00000000-0000-0000-0000-000000000000"


class TenantStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"      # paga pero pausado (impagos, abuso)
    DISABLED = "disabled"        # cancelado, conservar data 30d
    DELETED = "deleted"          # marcado para eliminación


@dataclass
class Tenant:
    tenant_id: str               # UUID v4 string
    slug: str                    # short slug user-readable, único, p.ej. "uriel-x9k2"
    email: str
    display_name: str
    status: TenantStatus = TenantStatus.ACTIVE
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    suspended_at: Optional[datetime] = None
    metadata: dict = field(default_factory=dict)

    def is_active(self) -> bool:
        return self.status == TenantStatus.ACTIVE

    def can_trade(self) -> bool:
        return self.status == TenantStatus.ACTIVE


# ── Helpers de identidad ─────────────────────────────────────


_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def new_tenant_id() -> str:
    """Genera un UUID v4 string."""
    return str(uuid.uuid4())


def is_valid_tenant_id(value: str) -> bool:
    """True si `value` es un UUID v4 válido (string lowercase)."""
    if not isinstance(value, str):
        return False
    return bool(_UUID_RE.match(value))


_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,38}[a-z0-9]$")


def is_valid_slug(value: str) -> bool:
    """
    True si `value` es un slug válido:
      - 3-40 chars
      - lowercase letras/dígitos/guiones/underscores
      - empieza y termina con letra o dígito
    """
    if not isinstance(value, str):
        return False
    return bool(_SLUG_RE.match(value))


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(value: str) -> bool:
    """Validación email mínima — no es RFC 5322 compliant, suficiente para signup."""
    return isinstance(value, str) and bool(_EMAIL_RE.match(value))
