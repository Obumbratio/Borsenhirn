"""
Constantes de tenancy — single source of truth para los UUIDs especiales
del sistema multi-tenant Börsenhirn.

Este módulo NO debe importar nada de `borsenhirn.tenancy.*` para evitar
ciclos: es leaf del paquete. `tenant.py` importa de acá, no al revés.
"""

from __future__ import annotations


# UUID reservado para data cross-cutting / sentinel.
# NO debe existir como fila en la tabla 'tenants'.
# No usar para queries — RLS rechazará todas las filas.
SYSTEM_TENANT_ID = "00000000-0000-0000-0000-000000000000"

# Tenant real creado en B1 Bloque 2. Owner de las 128 filas legacy
# de paper trading. Usar como tenant_id por defecto hasta que la
# capa de auth (Bloque B3 del roadmap SaaS) provea per-user UUIDs.
DEFAULT_TENANT_UUID = "00000000-0000-0000-0000-000000000001"


__all__ = [
    "SYSTEM_TENANT_ID",
    "DEFAULT_TENANT_UUID",
]
