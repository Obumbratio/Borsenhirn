"""
Kill switches: halt automático del bot ante condiciones peligrosas.

Reglas incluidas:
    - max_daily_loss:       PnL diario < -MAX_DAILY_LOSS_PCT * equity_day_start.
    - max_drawdown_7d:      drawdown rolling 7 días < -MAX_DRAWDOWN_7D_PCT.
    - consecutive_failures: N órdenes rechazadas seguidas por Alpaca.
    - manual_halt:          flag en Postgres activado por admin/CLI.

Estado persistente en tabla killswitch_state (ver safety/migrations.sql).
Si el proceso se reinicia, el bot recuerda que está HALTED y NO hace trades
hasta que un humano (tú) llame a clear().

Diseño:
    KillSwitch.check_all(snapshot) -> lista de KillTriggered
    KillSwitch.is_halted() -> bool (cualquier trigger activo)
    KillSwitch.manual_halt(reason)
    KillSwitch.clear(key, note)

El módulo NO toca Postgres directo — recibe una interfaz `StateStore` para
desacoplar. Una implementación con psycopg2 vive en state_store_pg.py o
en el módulo que ya manejes DB. Si no hay store, se usa InMemoryStateStore
(solo para tests/desarrollo).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────
# Tipos de trigger
# ────────────────────────────────────────────────────────────────

class KillReason(str, Enum):
    MAX_DAILY_LOSS = "max_daily_loss"
    MAX_DRAWDOWN_7D = "max_drawdown_7d"
    CONSECUTIVE_FAILURES = "consecutive_failures"
    MANUAL = "manual_halt"


@dataclass
class KillTriggered:
    key: KillReason
    reason: str
    data: Dict[str, Any] = field(default_factory=dict)
    triggered_at: float = field(default_factory=time.time)


# ────────────────────────────────────────────────────────────────
# State store (desacoplado)
# ────────────────────────────────────────────────────────────────

class StateStore(Protocol):
    """
    Interfaz que debe cumplir la implementación de persistencia.
    En producción se usa Postgres; en tests se usa InMemoryStateStore.
    """

    def get(self, key: str) -> Optional[Dict[str, Any]]: ...
    def set(self, key: str, triggered: bool, reason: str,
            data: Optional[Dict[str, Any]] = None) -> None: ...
    def list_active(self) -> List[Dict[str, Any]]: ...
    def clear(self, key: str, note: str = "") -> None: ...


class InMemoryStateStore:
    """Implementación in-memory solo para tests y fallback."""

    def __init__(self):
        self._rows: Dict[str, Dict[str, Any]] = {}

    def get(self, key: str):
        return self._rows.get(key)

    def set(self, key: str, triggered: bool, reason: str,
            data: Optional[Dict[str, Any]] = None):
        self._rows[key] = {
            "key": key,
            "triggered": triggered,
            "reason": reason,
            "data": data or {},
            "triggered_at": time.time() if triggered else None,
            "cleared_at": None if triggered else time.time(),
        }

    def list_active(self):
        return [r for r in self._rows.values() if r["triggered"]]

    def clear(self, key: str, note: str = ""):
        if key in self._rows:
            self._rows[key]["triggered"] = False
            self._rows[key]["cleared_at"] = time.time()
            self._rows[key]["data"] = {
                **(self._rows[key].get("data") or {}),
                "clear_note": note,
            }


# ────────────────────────────────────────────────────────────────
# Snapshot de entrada
# ────────────────────────────────────────────────────────────────

@dataclass
class KillSnapshot:
    """
    Estado del bot en un instante, input para check_all().
    Todos los campos son tolerantes a None si no se puede calcular.
    """
    equity_now: float
    equity_day_start: Optional[float] = None
    daily_pnl: Optional[float] = None
    equity_history_7d: Optional[List[float]] = None  # lista de equity diaria
    consecutive_order_failures: int = 0


# ────────────────────────────────────────────────────────────────
# KillSwitch
# ────────────────────────────────────────────────────────────────

@dataclass
class KillSwitchConfig:
    max_daily_loss_pct: float = 0.05          # -5% sobre equity inicio día
    max_drawdown_7d_pct: float = 0.15          # -15% vs pico últimos 7d
    max_consecutive_failures: int = 5          # N rejects seguidos


class KillSwitch:
    """
    Motor de kill switches.

    Uso típico en el loop principal del bot:

        ks = KillSwitch(store, alert_manager, KillSwitchConfig())

        # Antes de cada orden:
        if ks.is_halted():
            logger.info("Bot en HALT, skip orden.")
            continue

        # Después de cada tick / cada orden:
        triggered = ks.check_all(snapshot)
        if triggered:
            # check_all ya persistió estado y disparó alertas.
            continue

    `alert_send` es un callable (p.ej. AlertManager.critical).
    """

    def __init__(
        self,
        store: StateStore,
        alert_send: Callable[..., Any],
        config: Optional[KillSwitchConfig] = None,
    ):
        self.store = store
        self.alert_send = alert_send
        self.config = config or KillSwitchConfig()

    # ── Queries ───────────────────────────────────────────
    def is_halted(self) -> bool:
        return len(self.store.list_active()) > 0

    def active_reasons(self) -> List[Dict[str, Any]]:
        return self.store.list_active()

    # ── Comandos ──────────────────────────────────────────
    def _audit_ks(self, action: str, detail: str) -> None:
        """Audit best-effort (B5). Solo si el store tiene tenant_id."""
        tid = getattr(self.store, "tenant_id", None)
        if not tid:
            return
        try:
            from borsenhirn.audit import get_audit_logger
            get_audit_logger().record(tid, action, resource=(detail or None))
        except Exception:   # pragma: no cover
            pass

    def manual_halt(self, reason: str = "manual halt via admin") -> None:
        self._trigger(KillReason.MANUAL, reason, {})
        self._audit_ks("killswitch.halt", reason)

    def clear(self, key: KillReason, note: str = "") -> None:
        self.store.clear(key.value, note)
        logger.info("KillSwitch: cleared %s (%s)", key.value, note or "-")
        self._audit_ks("killswitch.clear", note)

    def clear_all(self, note: str = "") -> None:
        for row in self.store.list_active():
            self.store.clear(row["key"], note)
        logger.info("KillSwitch: cleared ALL (%s)", note or "-")

    # ── Checks ────────────────────────────────────────────
    def check_all(self, snapshot: KillSnapshot) -> List[KillTriggered]:
        """Corre todos los checks. Devuelve los que dispararon."""
        triggered: List[KillTriggered] = []

        t = self._check_daily_loss(snapshot)
        if t:
            triggered.append(t)

        t = self._check_drawdown_7d(snapshot)
        if t:
            triggered.append(t)

        t = self._check_consecutive_failures(snapshot)
        if t:
            triggered.append(t)

        for tr in triggered:
            self._trigger(tr.key, tr.reason, tr.data)

        return triggered

    def _check_daily_loss(self, s: KillSnapshot) -> Optional[KillTriggered]:
        if s.equity_day_start is None or s.daily_pnl is None:
            return None
        limit = -abs(s.equity_day_start * self.config.max_daily_loss_pct)
        if s.daily_pnl < limit:
            return KillTriggered(
                key=KillReason.MAX_DAILY_LOSS,
                reason=f"PnL diario {s.daily_pnl:.2f} < límite {limit:.2f}",
                data={
                    "daily_pnl": s.daily_pnl,
                    "equity_day_start": s.equity_day_start,
                    "equity_now": s.equity_now,
                    "limit_pct": self.config.max_daily_loss_pct,
                },
            )
        return None

    def _check_drawdown_7d(self, s: KillSnapshot) -> Optional[KillTriggered]:
        hist = s.equity_history_7d or []
        if len(hist) < 2:
            return None
        peak = max(hist)
        if peak <= 0:
            return None
        dd = (s.equity_now - peak) / peak
        if dd < -abs(self.config.max_drawdown_7d_pct):
            return KillTriggered(
                key=KillReason.MAX_DRAWDOWN_7D,
                reason=f"Drawdown 7d {dd:.2%} > límite {self.config.max_drawdown_7d_pct:.2%}",
                data={"drawdown": dd, "peak_7d": peak, "equity_now": s.equity_now},
            )
        return None

    def _check_consecutive_failures(self, s: KillSnapshot) -> Optional[KillTriggered]:
        if s.consecutive_order_failures >= self.config.max_consecutive_failures:
            return KillTriggered(
                key=KillReason.CONSECUTIVE_FAILURES,
                reason=f"{s.consecutive_order_failures} rechazos/errores consecutivos",
                data={"count": s.consecutive_order_failures,
                      "limit": self.config.max_consecutive_failures},
            )
        return None

    # ── Internos ──────────────────────────────────────────
    def _trigger(self, key: KillReason, reason: str,
                 data: Dict[str, Any]) -> None:
        """Persiste el halt y dispara alerta CRITICAL. Idempotente."""
        existing = self.store.get(key.value)
        if existing and existing.get("triggered"):
            # Ya estaba activo; actualizamos data pero no re-alertamos.
            self.store.set(key.value, True, reason, data)
            return
        self.store.set(key.value, True, reason, data)
        try:
            self.alert_send(
                subject=f"KILL SWITCH: {key.value}",
                body=reason,
                **data,
            )
        except Exception as exc:
            logger.error("KillSwitch: alert_send falló: %s", exc)
        logger.warning("KILL SWITCH ACTIVADO: %s - %s", key.value, reason)
