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


class ClerkJWKSVerifier:
    """
    Verifica JWTs de Clerk (RS256) usando el JWKS público de Clerk.

    Las claves se obtienen vía `PyJWKClient` por `kid` (cacheadas; refresca
    ante un kid desconocido). Valida firma + exp + issuer (+ audience opcional).

    Config (B3.3, producción):
        jwks_url : https://<tu-frontend-api>/.well-known/jwks.json
        issuer   : el issuer de tu app Clerk (claim `iss`)
        audience : opcional (claim `aud`/`azp`)

    `jwk_client` es inyectable para tests (sin red).
    """
    name = "clerk"

    def __init__(
        self,
        jwks_url: str,
        issuer: str,
        *,
        audience: Optional[str] = None,
        leeway: int = 10,
        jwk_client: object = None,
    ) -> None:
        if not jwks_url:
            raise ValueError("ClerkJWKSVerifier requiere jwks_url")
        if not issuer:
            raise ValueError("ClerkJWKSVerifier requiere issuer")
        self.jwks_url = jwks_url
        self.issuer = issuer
        self.audience = audience
        self.leeway = leeway
        # PyJWKClient no toca la red al construirse (lazy hasta el primer verify).
        self._jwk_client = jwk_client or jwt.PyJWKClient(jwks_url, cache_keys=True)

    def verify(self, token: str) -> Claims:
        options = {"require": ["exp", "sub"]}
        if self.audience is None:
            options["verify_aud"] = False
        try:
            signing_key = self._jwk_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self.issuer,
                audience=self.audience,
                leeway=self.leeway,
                options=options,
            )
        except jwt.PyJWTError as exc:
            raise AuthError(f"token inválido: {exc}") from exc
        except Exception as exc:   # red/JWKS/kid desconocido
            raise AuthError(f"no se pudo verificar el token (JWKS): {exc}") from exc
        return _claims_from_payload(payload)


def build_verifier_from_env() -> TokenVerifier:
    """
    Construye el TokenVerifier según env (tee-up de B3.4):

        AUTH_VERIFIER=clerk  -> ClerkJWKSVerifier (CLERK_JWKS_URL, CLERK_ISSUER,
                                                    CLERK_AUDIENCE opcional)
        AUTH_VERIFIER=static -> StaticTokenVerifier (AUTH_DEV_SECRET, + issuer/aud opc)
                                (default; para dev/tests)
    """
    import os
    kind = (os.getenv("AUTH_VERIFIER") or "static").lower()
    if kind in ("clerk", "jwks"):
        return ClerkJWKSVerifier(
            jwks_url=os.environ.get("CLERK_JWKS_URL", ""),
            issuer=os.environ.get("CLERK_ISSUER", ""),
            audience=os.getenv("CLERK_AUDIENCE") or None,
        )
    if kind in ("static", "dev"):
        secret = os.getenv("AUTH_DEV_SECRET")
        if not secret:
            raise ValueError(
                "AUTH_DEV_SECRET requerido para AUTH_VERIFIER=static/dev"
            )
        return StaticTokenVerifier(
            secret,
            issuer=os.getenv("AUTH_DEV_ISSUER") or None,
            audience=os.getenv("AUTH_DEV_AUDIENCE") or None,
        )
    raise ValueError(f"AUTH_VERIFIER desconocido: {kind!r}")


__all__ = [
    "Claims",
    "AuthError",
    "TokenVerifier",
    "StaticTokenVerifier",
    "ClerkJWKSVerifier",
    "build_verifier_from_env",
    "_claims_from_payload",
]
