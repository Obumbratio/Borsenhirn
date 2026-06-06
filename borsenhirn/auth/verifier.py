"""
TokenVerifier — verifica un JWT y devuelve Claims. Pluggable (B3).

    StaticTokenVerifier  -> HS256 con secret compartido (dev / tests).
    ClerkJWKSVerifier    -> RS256 + JWKS de Clerk (B3.3).

Toda verificación valida firma + exp + (opcional) issuer/audience ANTES de
confiar en cualquier claim. `sub` (Clerk user id) es obligatorio.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable

import jwt


class AuthError(Exception):
    """Token inválido/expirado/mal firmado. La capa HTTP lo mapea a 401."""


@dataclass(frozen=True)
class Claims:
    """Claims verificados de un token. `raw` es el payload completo."""
    sub: str                      # Clerk user id (identidad externa)
    email: Optional[str] = None
    name: Optional[str] = None
    raw: dict = field(default_factory=dict)

    def email_for_provisioning(self) -> str:
        """Email para provisionar el tenant. Fallback si el token no lo trae (D3)."""
        return self.email or f"{self.sub}@clerk.local"

    def name_for_provisioning(self) -> str:
        return self.name or self.email or self.sub


@runtime_checkable
class TokenVerifier(Protocol):
    name: str

    def verify(self, token: str) -> Claims:
        """Valida el token y devuelve Claims, o lanza AuthError."""
        ...


def _claims_from_payload(payload: dict) -> Claims:
    sub = payload.get("sub")
    if not sub:
        raise AuthError("token sin claim 'sub'")
    return Claims(
        sub=str(sub),
        email=payload.get("email"),
        name=payload.get("name") or payload.get("full_name"),
        raw=payload,
    )


class StaticTokenVerifier:
    """
    Verifica JWTs HS256 firmados con un secret compartido. Para desarrollo y
    tests: permite emitir tokens propios sin un Clerk vivo, manteniendo el
    mismo contrato (firma + exp + claims) que el verifier real.
    """
    name = "static"

    def __init__(
        self,
        secret: str,
        *,
        issuer: Optional[str] = None,
        audience: Optional[str] = None,
        algorithm: str = "HS256",
        leeway: int = 10,
    ) -> None:
        if not secret:
            raise ValueError("StaticTokenVerifier requiere un secret")
        self.secret = secret
        self.issuer = issuer
        self.audience = audience
        self.algorithm = algorithm
        self.leeway = leeway

    def verify(self, token: str) -> Claims:
        options = {"require": ["exp", "sub"]}
        if self.audience is None:
            options["verify_aud"] = False
        try:
            payload = jwt.decode(
                token,
                self.secret,
                algorithms=[self.algorithm],
                issuer=self.issuer,
                audience=self.audience,
                leeway=self.leeway,
                options=options,
            )
        except jwt.PyJWTError as exc:
            raise AuthError(f"token inválido: {exc}") from exc
        return _claims_from_payload(payload)


__all__ = [
    "Claims",
    "AuthError",
    "TokenVerifier",
    "StaticTokenVerifier",
    "_claims_from_payload",
]
