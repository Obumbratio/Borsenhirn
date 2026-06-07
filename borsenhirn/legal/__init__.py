"""
borsenhirn.legal — aceptación de términos/privacidad versionados (B7).

Registra (append-only) qué versión aceptó cada tenant y expone is_compliant
para gatear el acceso al producto hasta que acepte la versión vigente.
"""

from borsenhirn.legal.service import (
    REQUIRED_DOCS,
    current_versions,
    record_acceptance,
    get_acceptances,
    is_compliant,
)
from borsenhirn.legal.deps import get_compliant_tenant

__all__ = [
    "REQUIRED_DOCS",
    "current_versions",
    "record_acceptance",
    "get_acceptances",
    "is_compliant",
    "get_compliant_tenant",
]
