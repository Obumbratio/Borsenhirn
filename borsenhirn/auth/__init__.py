"""
borsenhirn.auth — verificación de identidad (Clerk JWT) y resolución de tenant.

B3. Capa pluggable: un `TokenVerifier` que valida un JWT y devuelve `Claims`.
    - StaticTokenVerifier: HS256 con secret compartido (dev / tests).
    - ClerkJWKSVerifier:    RS256 + JWKS de Clerk (B3.3, producción).
"""

from borsenhirn.auth.verifier import (
    Claims,
    AuthError,
    TokenVerifier,
    StaticTokenVerifier,
    ClerkJWKSVerifier,
    build_verifier_from_env,
)

__all__ = [
    "Claims",
    "AuthError",
    "TokenVerifier",
    "StaticTokenVerifier",
    "ClerkJWKSVerifier",
    "build_verifier_from_env",
]
