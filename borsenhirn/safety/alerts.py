"""
Canales de alertas para eventos críticos del bot.

Canales implementados:
    - DiscordChannel:   webhook POST a Discord.
    - EmailChannel:     SMTP (Gmail, Outlook, etc.) con app password.
    - DashboardChannel: escribe a tabla alerts_log en Postgres para que
                        Streamlit muestre banner rojo.

AlertManager orquesta múltiples canales, aplica rate-limiting (dedupe por
fingerprint + ventana) y nunca hace crashear al bot si un canal falla.
"""

from __future__ import annotations

import hashlib
import json
import logging
import smtplib
import threading
import time
from dataclasses import dataclass, field
from email.mime.text import MIMEText
from enum import Enum
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class AlertLevel(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    CRITICAL = "CRITICAL"


# ────────────────────────────────────────────────────────────────
# Channel interface
# ────────────────────────────────────────────────────────────────

class Channel:
    name: str = "base"

    def send(self, level: AlertLevel, subject: str, body: str,
             meta: Optional[Dict[str, Any]] = None) -> bool:
        raise NotImplementedError


# ────────────────────────────────────────────────────────────────
# Discord
# ────────────────────────────────────────────────────────────────

class DiscordChannel(Channel):
    """
    Envía mensajes a un webhook de Discord.

    El URL completo es una credencial — NO lo hardcodees ni commitees.
    Carga desde env var (config.DISCORD_WEBHOOK_URL).
    """

    name = "discord"

    COLORS = {
        AlertLevel.INFO: 0x3498DB,      # azul
        AlertLevel.WARN: 0xF39C12,      # naranja
        AlertLevel.CRITICAL: 0xE74C3C,  # rojo
    }

    EMOJI = {
        AlertLevel.INFO: "ℹ️",
        AlertLevel.WARN: "⚠️",
        AlertLevel.CRITICAL: "🚨",
    }

    def __init__(self, webhook_url: str, timeout: float = 5.0):
        if not webhook_url:
            logger.warning("DiscordChannel: webhook_url vacío, canal deshabilitado.")
        self.webhook_url = webhook_url
        self.timeout = timeout

    def send(self, level: AlertLevel, subject: str, body: str,
             meta: Optional[Dict[str, Any]] = None) -> bool:
        if not self.webhook_url:
            return False
        embed = {
            "title": f"{self.EMOJI[level]} {subject}",
            "description": body[:2000],  # Discord limit
            "color": self.COLORS[level],
        }
        if meta:
            # Hasta 25 fields, truncar valores largos
            fields = []
            for k, v in list(meta.items())[:10]:
                fields.append({"name": str(k)[:256],
                               "value": str(v)[:1024] or "-",
                               "inline": True})
            embed["fields"] = fields
        payload = {"embeds": [embed]}
        try:
            r = requests.post(self.webhook_url, json=payload, timeout=self.timeout)
            if r.status_code // 100 != 2:
                logger.warning("Discord webhook devolvió %s: %s",
                               r.status_code, r.text[:200])
                return False
            return True
        except Exception as exc:
            logger.warning("DiscordChannel fallo: %s", exc)
            return False


# ────────────────────────────────────────────────────────────────
# Email (SMTP)
# ────────────────────────────────────────────────────────────────

@dataclass
class SmtpConfig:
    host: str
    port: int
    user: str
    password: str
    use_tls: bool = True


class EmailChannel(Channel):
    """
    Envía email vía SMTP.

    Para Gmail:
      - Activar 2FA en la cuenta.
      - Generar "App Password" en https://myaccount.google.com/apppasswords
      - host=smtp.gmail.com, port=587, use_tls=True, user=tu_email, password=app_pass
    """

    name = "email"

    def __init__(self, smtp: SmtpConfig, to_addrs: List[str],
                 from_name: str = "Borsenhirn Bot"):
        self.smtp = smtp
        self.to_addrs = to_addrs
        self.from_name = from_name

    def send(self, level: AlertLevel, subject: str, body: str,
             meta: Optional[Dict[str, Any]] = None) -> bool:
        if not self.smtp.host or not self.to_addrs:
            return False
        # Armar cuerpo
        body_full = body
        if meta:
            body_full += "\n\n--- Contexto ---\n"
            body_full += "\n".join(f"{k}: {v}" for k, v in meta.items())
        msg = MIMEText(body_full)
        msg["Subject"] = f"[{level.value}] {subject}"
        msg["From"] = f"{self.from_name} <{self.smtp.user}>"
        msg["To"] = ", ".join(self.to_addrs)
        try:
            with smtplib.SMTP(self.smtp.host, self.smtp.port, timeout=10) as s:
                if self.smtp.use_tls:
                    s.starttls()
                s.login(self.smtp.user, self.smtp.password)
                s.send_message(msg)
            return True
        except Exception as exc:
            logger.warning("EmailChannel fallo: %s", exc)
            return False


# ────────────────────────────────────────────────────────────────
# Dashboard (Postgres)
# ────────────────────────────────────────────────────────────────

class DashboardChannel(Channel):
    """
    Persiste la alerta en tabla alerts_log para que el dashboard Streamlit
    muestre banner rojo en tiempo real. Requiere que la tabla exista.

    Inyecta una función `db_write_fn(row_dict)` — así este módulo no acopla
    a ningún driver Postgres específico. El llamador usa su propio helper.
    """

    name = "dashboard"

    def __init__(self, db_write_fn):
        self.db_write_fn = db_write_fn

    def send(self, level: AlertLevel, subject: str, body: str,
             meta: Optional[Dict[str, Any]] = None) -> bool:
        row = {
            "level": level.value,
            "subject": subject,
            "body": body,
            "meta": json.dumps(meta or {}, default=str),
        }
        try:
            self.db_write_fn(row)
            return True
        except Exception as exc:
            logger.warning("DashboardChannel fallo: %s", exc)
            return False


# ────────────────────────────────────────────────────────────────
# AlertManager
# ────────────────────────────────────────────────────────────────

@dataclass
class _DedupeEntry:
    last_sent: float
    count: int = 1


class AlertManager:
    """
    Orquesta múltiples Channels con rate limiting / dedupe.

    Rate limiting: si una alerta con el mismo fingerprint se envió hace
    menos de `dedupe_window_sec` segundos, no se reenvía — solo se cuenta.
    El fingerprint por default es sha1(level + subject).

    Thread-safe.
    """

    def __init__(self, channels: List[Channel],
                 dedupe_window_sec: int = 300,
                 min_level: AlertLevel = AlertLevel.INFO):
        self.channels = channels
        self.dedupe_window_sec = dedupe_window_sec
        self.min_level = min_level
        self._dedupe: Dict[str, _DedupeEntry] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _fingerprint(level: AlertLevel, subject: str) -> str:
        h = hashlib.sha1(f"{level.value}|{subject}".encode("utf-8")).hexdigest()
        return h[:16]

    def _level_ok(self, level: AlertLevel) -> bool:
        order = [AlertLevel.INFO, AlertLevel.WARN, AlertLevel.CRITICAL]
        return order.index(level) >= order.index(self.min_level)

    def send(self, level: AlertLevel, subject: str, body: str,
             meta: Optional[Dict[str, Any]] = None,
             force: bool = False) -> Dict[str, bool]:
        """
        Envía una alerta a todos los canales. Devuelve dict {channel_name: ok}.
        Si `force=False`, aplica dedupe. CRITICAL siempre pasa.
        """
        if not self._level_ok(level):
            return {}

        fp = self._fingerprint(level, subject)
        should_send = True
        with self._lock:
            if not force and level != AlertLevel.CRITICAL and fp in self._dedupe:
                elapsed = time.time() - self._dedupe[fp].last_sent
                if elapsed < self.dedupe_window_sec:
                    self._dedupe[fp].count += 1
                    should_send = False
            if should_send:
                self._dedupe[fp] = _DedupeEntry(time.time())

        if not should_send:
            logger.debug("AlertManager: dedupe descartó '%s'", subject)
            return {}

        results: Dict[str, bool] = {}
        for ch in self.channels:
            try:
                ok = ch.send(level, subject, body, meta)
                results[ch.name] = bool(ok)
            except Exception as exc:
                logger.warning("AlertManager: canal %s crasheó: %s",
                               getattr(ch, "name", "?"), exc)
                results[getattr(ch, "name", "?")] = False

        logger.info("Alert [%s] '%s' → %s", level.value, subject, results)
        return results

    # Helpers rápidos
    def info(self, subject: str, body: str = "", **meta):
        return self.send(AlertLevel.INFO, subject, body, meta or None)

    def warn(self, subject: str, body: str = "", **meta):
        return self.send(AlertLevel.WARN, subject, body, meta or None)

    def critical(self, subject: str, body: str = "", **meta):
        return self.send(AlertLevel.CRITICAL, subject, body, meta or None)


# ────────────────────────────────────────────────────────────────
# Factory de conveniencia
# ────────────────────────────────────────────────────────────────

def build_default_manager(
    discord_webhook_url: Optional[str] = None,
    smtp: Optional[SmtpConfig] = None,
    email_to: Optional[List[str]] = None,
    db_write_fn=None,
    dedupe_window_sec: int = 300,
    min_level: AlertLevel = AlertLevel.INFO,
) -> AlertManager:
    """
    Construye un AlertManager con los canales que estén configurados.
    Los canales sin credenciales se omiten silenciosamente.
    """
    channels: List[Channel] = []
    if discord_webhook_url:
        channels.append(DiscordChannel(discord_webhook_url))
    if smtp and email_to:
        channels.append(EmailChannel(smtp, email_to))
    if db_write_fn is not None:
        channels.append(DashboardChannel(db_write_fn))
    if not channels:
        logger.warning("build_default_manager: ningún canal configurado.")
    return AlertManager(channels, dedupe_window_sec=dedupe_window_sec,
                        min_level=min_level)
