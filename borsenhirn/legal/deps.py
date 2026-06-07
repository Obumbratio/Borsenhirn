"""
Gating de compliance legal (B7) — dependency de FastAPI.

`get_compliant_tenant` exige que el tenant esté activo (billing) Y haya aceptado
la versión vigente de los docs requeridos; sino 451 (Unavailable For Legal
Reasons). Se usa en endpoints de producto. Los endpoints /legal/* no lo usan.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException

from borsenhirn.auth.deps import get_active_tenant
from borsenhirn.legal.service import is_compliant

HTTP_451 = 451  # Unavailable For Legal Reasons


def get_compliant_tenant(tenant_id: str = Depends(get_active_tenant)) -> str:
    if not is_compliant(tenant_id):
        raise HTTPException(
            status_code=HTTP_451,
            detail="aceptación de términos y privacidad vigentes requerida")
    return tenant_id


__all__ = ["get_compliant_tenant"]
