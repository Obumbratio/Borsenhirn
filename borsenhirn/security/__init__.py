"""
borsenhirn.security — encryption at rest para secretos de usuarios SaaS.

Componentes:
    vault:       wrapper sobre cryptography.fernet para encrypt/decrypt.
    credentials: CRUD de user_credentials (claves Alpaca encriptadas).
"""

from borsenhirn.security.vault import (
    Vault,
    VaultError,
    generate_master_key,
    derive_key_from_passphrase,
)
from borsenhirn.security.credentials import (
    CredentialStore,
    UserCredentials,
)
from borsenhirn.security.secret_provider import (
    SecretError,
    resolve_secret,
    load_master_key,
    EnvSecretProvider,
    FileSecretProvider,
    CommandSecretProvider,
)

__all__ = [
    "Vault",
    "VaultError",
    "generate_master_key",
    "derive_key_from_passphrase",
    "CredentialStore",
    "UserCredentials",
    # B2 — secret providers
    "SecretError",
    "resolve_secret",
    "load_master_key",
    "EnvSecretProvider",
    "FileSecretProvider",
    "CommandSecretProvider",
]
