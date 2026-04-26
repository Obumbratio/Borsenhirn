"""
borsenhirn.safety — kill switches, alertas y sanity checks para el bot.

Módulos:
    alerts:     DiscordChannel + EmailChannel + DashboardChannel + AlertManager.
    killswitch: reglas de halt automático con estado persistente en Postgres.
    sanity:     validaciones pre-orden (precio, qty, símbolo, duplicados, wash).
    health:     snapshot del estado operacional + endpoint /health.
"""

from borsenhirn.safety.alerts import (
    AlertLevel,
    AlertManager,
    DashboardChannel,
    DiscordChannel,
    EmailChannel,
)
from borsenhirn.safety.killswitch import KillSwitch, KillReason
from borsenhirn.safety.sanity import SanityChecker, SanityResult
from borsenhirn.safety.health import get_health_snapshot

__all__ = [
    "AlertLevel",
    "AlertManager",
    "DashboardChannel",
    "DiscordChannel",
    "EmailChannel",
    "KillSwitch",
    "KillReason",
    "SanityChecker",
    "SanityResult",
    "get_health_snapshot",
]
