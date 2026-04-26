"""
bitacora_state.py — Eintrag counter para el dashboard "Bitácora Nocturna".

Cada render del dashboard es una entrada (Eintrag) numerada del diario que el
bot lleva sobre su propia operación. El contador persiste entre sesiones en un
archivo JSON local porque la regla dura del sprint prohíbe tocar el schema de
Postgres.

Reglas de incremento
────────────────────
1. El contador incrementa UNA vez por día calendario (zona horaria local del
   user) en el primer render de ese día.
2. El primer día de uso se registra como `first_session_date` y el Eintrag
   arranca en 1. Si el archivo no existe, se crea.
3. Llamar `force_increment()` (atado al botón "Forzar ciclo") agrega 1 al
   contador independientemente de la fecha — útil para diferenciar ciclos
   manuales del bot dentro del mismo día.
4. La función `current_eintrag()` es idempotente: en el mismo día, repetidas
   llamadas devuelven el mismo número.

Estructura del JSON
───────────────────
    {
      "entry_number": 412,
      "last_increment_date": "2026-04-26",
      "first_session_date": "2026-03-28",
      "manual_cycles_today": 0
    }

Localización
────────────
    ~/.borsenhirn/bitacora_state.json    (Linux/macOS)
    %USERPROFILE%\\.borsenhirn\\bitacora_state.json  (Windows)
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Tuple

__all__ = [
    "current_eintrag",
    "force_increment",
    "session_metadata",
    "STATE_PATH",
]

STATE_DIR = Path.home() / ".borsenhirn"
STATE_PATH = STATE_DIR / "bitacora_state.json"


def _today_iso() -> str:
    return date.today().isoformat()


def _load() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        with STATE_PATH.open("r", encoding="utf-8") as f:
            return json.load(f) or {}
    except (json.JSONDecodeError, OSError):
        # Si el archivo está corrupto, empezamos de cero · no fallamos el dashboard.
        return {}


def _save(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp, STATE_PATH)


def _seed(state: dict) -> dict:
    """Asegura que todas las claves existan."""
    today = _today_iso()
    state.setdefault("entry_number", 0)
    state.setdefault("first_session_date", today)
    state.setdefault("last_increment_date", "")
    state.setdefault("manual_cycles_today", 0)
    return state


def current_eintrag() -> int:
    """
    Devuelve el número de Eintrag de hoy. Incrementa una vez por día.
    Idempotente dentro del mismo día.
    """
    state = _seed(_load())
    today = _today_iso()

    if state["last_increment_date"] != today:
        state["entry_number"] = int(state["entry_number"]) + 1
        state["last_increment_date"] = today
        state["manual_cycles_today"] = 0
        _save(state)

    return int(state["entry_number"])


def force_increment() -> int:
    """
    Forza un nuevo Eintrag aunque sea el mismo día. Atado al botón
    "Forzar ciclo del bot". Devuelve el nuevo número.
    """
    state = _seed(_load())
    today = _today_iso()
    state["entry_number"] = int(state["entry_number"]) + 1
    state["last_increment_date"] = today
    state["manual_cycles_today"] = int(state.get("manual_cycles_today", 0)) + 1
    _save(state)
    return int(state["entry_number"])


def session_metadata() -> dict:
    """
    Devuelve un diccionario completo con:
        entry_number, first_session_date, days_since_first,
        manual_cycles_today, last_increment_date.
    Útil para alimentar la cabecera del dashboard.
    """
    state = _seed(_load())
    today = _today_iso()

    if state["last_increment_date"] != today:
        # Garantizamos que entry_number esté incrementado para hoy.
        current_eintrag()
        state = _seed(_load())

    try:
        first = datetime.fromisoformat(state["first_session_date"]).date()
        days_since = (date.today() - first).days
    except Exception:
        days_since = 0

    return {
        "entry_number": int(state["entry_number"]),
        "first_session_date": state["first_session_date"],
        "last_increment_date": state["last_increment_date"],
        "manual_cycles_today": int(state.get("manual_cycles_today", 0)),
        "days_since_first": days_since,
    }


def reset_for_test(starting_entry: int = 0) -> None:
    """
    Helper SOLO para tests. Borra el archivo y reinicia el contador.
    No usar en runtime de producción.
    """
    if STATE_PATH.exists():
        STATE_PATH.unlink()
    if starting_entry > 0:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        _save({
            "entry_number": starting_entry,
            "first_session_date": _today_iso(),
            "last_increment_date": "",  # forzar increment al primer current_eintrag
            "manual_cycles_today": 0,
        })


def get_state_path() -> Tuple[Path, bool]:
    """Devuelve (path, exists) — útil para diagnósticos en el dashboard."""
    return STATE_PATH, STATE_PATH.exists()
