"""
Secret providers — carga de secretos (p.ej. la master key del Vault) desde
distintos backends, sin acoplar el código a uno solo.

Motivación (B2)
---------------
La master key NO debe vivir en `.env` en producción. Pero tampoco queremos
acoplar el código a un secrets manager específico (AWS SM, Doppler, HashiCorp
Vault, GCP SM, 1Password...). Esta capa abstrae *de dónde* sale un secreto:

    EnvSecretProvider      -> os.environ[name]                 (dev + PaaS)
    FileSecretProvider     -> contenido del archivo {name}_FILE (Docker/K8s mounts)
    CommandSecretProvider  -> stdout de {name}_CMD              (CLIs de managers)

`resolve_secret(name)` los prueba en orden de prioridad y devuelve el primero
que tenga valor. Por diseño, las fuentes explícitas de producción
(archivo / comando) ganan sobre la env var de dev.

Para un secrets manager con SDK (boto3, hvac), basta agregar un provider nuevo
que implemente `.get(name)`; no cambia nada del resto.

Seguridad
---------
- NUNCA se loguea el valor del secreto; solo qué provider lo entregó.
- `CommandSecretProvider` ejecuta un comando definido por el OPERADOR vía env
  (`{name}_CMD`), nunca input de usuario. Cubre `doppler secrets get --plain`,
  `aws secretsmanager get-secret-value ...`, `vault kv get ...`, `op read ...`.
"""

from __future__ import annotations

import logging
import os
import subprocess
from typing import List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


class SecretError(Exception):
    """Fallo al resolver un secreto (no encontrado, comando falló, etc.)."""


@runtime_checkable
class SecretProvider(Protocol):
    name: str

    def get(self, key: str) -> Optional[str]:
        """Devuelve el valor del secreto `key`, o None si este provider no lo tiene."""
        ...


class EnvSecretProvider:
    """Lee el secreto directo de una variable de entorno (`key`)."""
    name = "env"

    def get(self, key: str) -> Optional[str]:
        val = os.environ.get(key)
        return val if val else None


class FileSecretProvider:
    """
    Lee el secreto del archivo cuya ruta está en `{key}_FILE`.
    Patrón de Docker/Kubernetes secrets montados (p.ej. /run/secrets/...).
    """
    name = "file"

    def get(self, key: str) -> Optional[str]:
        path = os.environ.get(f"{key}_FILE")
        if not path:
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                val = fh.read().strip()
        except OSError as exc:
            raise SecretError(f"no se pudo leer {key}_FILE={path!r}: {exc}") from exc
        return val or None


class CommandSecretProvider:
    """
    Ejecuta el comando en `{key}_CMD` y usa su stdout como valor.
    Cubre los CLIs de los secrets managers sin agregar dependencias.
    """
    name = "command"
    timeout_sec = 15

    def get(self, key: str) -> Optional[str]:
        cmd = os.environ.get(f"{key}_CMD")
        if not cmd:
            return None
        try:
            res = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                timeout=self.timeout_sec,
            )
        except subprocess.TimeoutExpired as exc:
            raise SecretError(f"{key}_CMD excedió {self.timeout_sec}s") from exc
        if res.returncode != 0:
            # stderr puede traer pistas; NO incluimos stdout (podría ser el secreto).
            raise SecretError(
                f"{key}_CMD falló (rc={res.returncode}): {res.stderr.strip()[:200]}"
            )
        val = res.stdout.strip()
        return val or None


# Orden de prioridad: fuentes explícitas de prod primero, env (dev) al final.
def default_chain() -> List[SecretProvider]:
    return [FileSecretProvider(), CommandSecretProvider(), EnvSecretProvider()]


def resolve_secret(
    key: str,
    providers: Optional[List[SecretProvider]] = None,
    *,
    required: bool = False,
    default: Optional[str] = None,
) -> Optional[str]:
    """
    Resuelve `key` probando los providers en orden; devuelve el primer valor.

    Args:
        key: nombre lógico del secreto (p.ej. "BORSENHIRN_MASTER_KEY").
        providers: cadena a usar; default = file -> command -> env.
        required: si True y no se encuentra, lanza SecretError.
        default: valor a devolver si no se encuentra (y required=False).

    NUNCA loguea el valor, solo el provider que lo entregó.
    """
    chain = providers if providers is not None else default_chain()
    for p in chain:
        val = p.get(key)
        if val:
            logger.info("secreto %s resuelto via provider '%s'", key, p.name)
            return val
    if required:
        raise SecretError(
            f"secreto {key!r} no encontrado en ningún provider "
            f"({', '.join(p.name for p in chain)}). "
            f"Seteá {key}, {key}_FILE o {key}_CMD."
        )
    return default


def load_master_key(env_var: str = "BORSENHIRN_MASTER_KEY") -> str:
    """Resuelve la master key del Vault (required). Atajo de resolve_secret."""
    return resolve_secret(env_var, required=True)  # type: ignore[return-value]


__all__ = [
    "SecretError",
    "SecretProvider",
    "EnvSecretProvider",
    "FileSecretProvider",
    "CommandSecretProvider",
    "default_chain",
    "resolve_secret",
    "load_master_key",
]
