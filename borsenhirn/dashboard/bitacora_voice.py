"""
bitacora_voice.py — Generador de la "Heutige Beobachtung" del bot.

Cada render del dashboard incluye una observación corta firmada por M2.ANALYST.
Este módulo produce ese texto. Reglas heredadas del brief del sprint:

    1. Empezar con el estado del mercado en alemán
       ("Bullenmarkt sostenido.", "Bärenmarkt débil.", etc.)
    2. Datos clave en inglés
       ("VIX dócil en 19.", "CPI cooling at 3.3%.")
    3. Estado del portafolio mezclando alemán + español natural
       ("Doce posiciones — vier ganando, sieben cediendo terreno.")
    4. Conclusión en castellano elevado, voz reflexiva
    5. Cierre opcional con frase corta en alemán
    6. 2–4 oraciones máximo. Concisión > verbosidad.
    7. Tono naturalista paciente. Nunca exclamativo.

Estrategia de implementación
────────────────────────────
La regla 'M2 in-process + caché 6h' aprobada en el plan implica que la
generación viva en el proceso del dashboard, sin subprocess. Como el paquete
borsenhirn.m2_analyst hoy expone solo __init__.py vacío (la lógica de M2 vive
en otro lado del repo y produce el regime_data ya consumido vía /status), este
generador es PROCEDURAL · usa las plantillas trilingües que el brief especifica
y las hidrata con el state real del bot. La voz queda fiel al brief.

Punto de extensión
──────────────────
Si en un sprint futuro M2 expone una función LLM (e.g.
m2_analyst.generate_daily_observation(state) -> str), basta con cambiar la
función `_generate_text` para preferirla y caer al procedural como fallback.
La firma pública (`get_observation(state)`) no cambia.

Caché
─────
TTL 6 horas. Persiste en ~/.borsenhirn/bitacora_observation.json para sobrevivir
restarts de Streamlit. Se invalida si:
    - Pasaron más de 6h desde la última generación
    - El régimen cambió (BULL→BEAR etc.)
    - El usuario fuerza ciclo del bot (llamando `invalidate_cache()`)
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .bitacora_state import STATE_DIR

__all__ = [
    "get_observation",
    "invalidate_cache",
    "ObservationContext",
]

CACHE_PATH = STATE_DIR / "bitacora_observation.json"
CACHE_TTL = timedelta(hours=6)


# ─── Datos de entrada ─────────────────────────────────────────────────────────

@dataclass
class ObservationContext:
    """Snapshot del state que necesita el generador."""
    regime: str = "—"            # BULL · BEAR · SIDEWAYS · PANIC
    confidence: float = 0.0      # 0.0–1.0
    vix: float = 0.0
    cpi_pct: Optional[float] = None
    fed_rate_pct: Optional[float] = None
    positions_open: int = 0
    positions_winning: int = 0
    positions_losing: int = 0
    net_pnl: float = 0.0
    cumulative_pnl: float = 0.0
    days_since_first: int = 0
    win_rate_pct: Optional[float] = None
    new_positions_today: int = 0

    def fingerprint(self) -> str:
        """Hash corto que cambia cuando algo material del state cambia."""
        return (
            f"{self.regime}|{round(self.confidence, 2)}|"
            f"{round(self.vix, 1)}|{self.positions_open}|"
            f"{self.positions_winning}|{self.positions_losing}|"
            f"{round(self.cumulative_pnl, 0)}"
        )


# ─── Diccionarios trilingües ─────────────────────────────────────────────────

# Números pequeños en alemán · suenan natural cuando se mezclan con prosa
DE_NUMBERS = {
    0: "null", 1: "ein", 2: "zwei", 3: "drei", 4: "vier", 5: "fünf",
    6: "sechs", 7: "sieben", 8: "acht", 9: "neun", 10: "zehn",
    11: "elf", 12: "zwölf", 13: "dreizehn", 14: "vierzehn", 15: "fünfzehn",
    16: "sechzehn", 17: "siebzehn", 18: "achtzehn", 19: "neunzehn", 20: "zwanzig",
}

# Números pequeños en español castellano para abrir frases
ES_NUMBERS = {
    0: "ninguna", 1: "una", 2: "dos", 3: "tres", 4: "cuatro", 5: "cinco",
    6: "seis", 7: "siete", 8: "ocho", 9: "nueve", 10: "diez",
    11: "once", 12: "doce", 13: "trece", 14: "catorce", 15: "quince",
    16: "dieciséis", 17: "diecisiete", 18: "dieciocho", 19: "diecinueve",
    20: "veinte",
}

REGIME_OPENERS_BULL = [
    "Bullenmarkt sostenido.",
    "Bullenmarkt firme.",
    "Bullenmarkt — el mercado respira hondo.",
    "Bullenmarkt continúa.",
]
REGIME_OPENERS_BEAR = [
    "Bärenmarkt débil.",
    "Bärenmarkt — el mercado cede.",
    "Bärenmarkt persistente.",
]
REGIME_OPENERS_SIDEWAYS = [
    "Seitwärts.",
    "Seitwärts — sin convicción direccional.",
    "Seitwärts, mercado dubitativo.",
]
REGIME_OPENERS_PANIC = [
    "Panik im Markt.",
    "Panik — el VIX dispara.",
    "Panik · todos corren al mismo tiempo.",
]

REGIME_CLOSERS_BULL = [
    "Der Markt will höher — ich folge.",
    "Der Markt zieht hoch — ich beobachte.",
    "Bull continúa, ich bleibe wach.",
]
REGIME_CLOSERS_BEAR = [
    "Der Markt sinkt — ich warte.",
    "Bär weiter — ich schütze Kapital.",
]
REGIME_CLOSERS_SIDEWAYS = [
    "Der Markt zögert — ich auch.",
    "Sin urgencia, ich bleibe ruhig.",
]
REGIME_CLOSERS_PANIC = [
    "Im Sturm bleibt der Hirn still.",
    "Panik passiert — ich nicht.",
]

DECISION_PATIENT = [
    "No abro nuevas hoy: la convicción sin urgencia es señal de paciencia.",
    "Mantengo la cartera intacta — la paciencia rinde más que el reflejo.",
    "Dejo correr lo que corre — cerrar por cerrar no es estrategia.",
]
DECISION_ACTIVE = [
    "Abro {n_es} ({n_de}) posición nueva — la convergencia me lo permite.",
    "Sumo {n_es} ({n_de}) entrada — la señal converge en tres dimensiones.",
]
DECISION_DEFENSIVE = [
    "Cierro lo más débil: el capital escaso pide selección, no concurrencia.",
    "Reduzco exposición — el regime no premia osadía hoy.",
]


# ─── Helpers de redacción ────────────────────────────────────────────────────

def _opener(regime: str) -> str:
    rmap = {
        "BULL": REGIME_OPENERS_BULL,
        "BEAR": REGIME_OPENERS_BEAR,
        "SIDEWAYS": REGIME_OPENERS_SIDEWAYS,
        "PANIC": REGIME_OPENERS_PANIC,
    }
    pool = rmap.get(regime.upper(), ["Mercado en lectura."])
    return random.choice(pool)


def _closer(regime: str) -> Optional[str]:
    rmap = {
        "BULL": REGIME_CLOSERS_BULL,
        "BEAR": REGIME_CLOSERS_BEAR,
        "SIDEWAYS": REGIME_CLOSERS_SIDEWAYS,
        "PANIC": REGIME_CLOSERS_PANIC,
    }
    pool = rmap.get(regime.upper())
    if not pool:
        return None
    # 70% de las veces incluimos el cierre alemán · queda sobrio
    return random.choice(pool) if random.random() < 0.7 else None


def _vix_phrase(vix: float) -> str:
    if vix <= 0:
        return ""
    if vix < 15:
        return f"VIX dócil en {vix:.0f}."
    if vix < 22:
        return f"VIX en {vix:.0f} — calma con tensión."
    if vix < 30:
        return f"VIX subiendo a {vix:.0f}."
    return f"VIX disparado en {vix:.0f}."


def _portfolio_phrase(ctx: ObservationContext) -> str:
    n = ctx.positions_open
    if n == 0:
        return "Cero posiciones abiertas — la cartera respira."
    n_es = ES_NUMBERS.get(n, str(n)).capitalize()
    win = ctx.positions_winning
    los = ctx.positions_losing
    if win > 0 or los > 0:
        win_de = DE_NUMBERS.get(win, str(win))
        los_de = DE_NUMBERS.get(los, str(los))
        return (
            f"{n_es} posiciones — {win_de} ganando, {los_de} cediendo terreno."
        )
    return f"{n_es} posiciones abiertas, distribución neutra."


def _pnl_phrase(ctx: ObservationContext) -> str:
    if abs(ctx.cumulative_pnl) < 1:
        return ""
    label = "Net positiv" if ctx.cumulative_pnl >= 0 else "Net negativ"
    amount = f"${abs(ctx.cumulative_pnl):,.0f}"
    if ctx.days_since_first > 0:
        return f"{label} {amount} acumulado · seit {ctx.days_since_first} Tage."
    return f"{label} {amount} acumulado."


def _decision_phrase(ctx: ObservationContext) -> str:
    # Heurística simple para elegir la voz de la decisión:
    if ctx.new_positions_today > 0:
        n_es = ES_NUMBERS.get(ctx.new_positions_today, str(ctx.new_positions_today))
        n_de = DE_NUMBERS.get(ctx.new_positions_today, str(ctx.new_positions_today))
        return random.choice(DECISION_ACTIVE).format(n_es=n_es, n_de=n_de)
    if ctx.regime.upper() in ("BEAR", "PANIC") and ctx.positions_losing > ctx.positions_winning:
        return random.choice(DECISION_DEFENSIVE)
    return random.choice(DECISION_PATIENT)


# ─── Generación principal ────────────────────────────────────────────────────

def _generate_text(ctx: ObservationContext) -> str:
    """
    Voz procedural · 2–4 oraciones según brief.
    Punto de extensión: si M2 expone una función generativa LLM en el futuro,
    chequearla acá ANTES del flujo procedural. Caer al procedural si falla.
    """
    # ── try LLM-based M2 generation (placeholder — no instalado aún) ──
    try:
        from borsenhirn.m2_analyst import generate_daily_observation  # type: ignore
        text = generate_daily_observation(ctx.__dict__)
        if isinstance(text, str) and 30 <= len(text) <= 600:
            return text.strip()
    except Exception:
        pass  # cae al generador procedural

    # ── flujo procedural ──
    parts = [_opener(ctx.regime)]

    vix = _vix_phrase(ctx.vix)
    if vix:
        parts.append(vix)

    portfolio = _portfolio_phrase(ctx)
    pnl = _pnl_phrase(ctx)
    if pnl:
        parts.append(f"{portfolio} {pnl}")
    else:
        parts.append(portfolio)

    parts.append(_decision_phrase(ctx))

    closer = _closer(ctx.regime)
    if closer:
        parts.append(closer)

    return " ".join(p for p in parts if p)


# ─── Caché ────────────────────────────────────────────────────────────────────

def _read_cache() -> Optional[dict]:
    if not CACHE_PATH.exists():
        return None
    try:
        with CACHE_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _write_cache(text: str, ctx: ObservationContext) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "text": text,
        "fingerprint": ctx.fingerprint(),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "regime": ctx.regime,
        "confidence": ctx.confidence,
    }
    tmp = CACHE_PATH.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    tmp.replace(CACHE_PATH)


def _cache_is_valid(cache: dict, ctx: ObservationContext) -> bool:
    try:
        gen = datetime.fromisoformat(cache["generated_at"])
        if datetime.now() - gen > CACHE_TTL:
            return False
        if cache.get("regime") != ctx.regime:
            return False
        if cache.get("fingerprint") != ctx.fingerprint():
            # Permitimos que el fingerprint cambie SOLO si el TTL aún es joven (< 1h),
            # para no regenerar texto en cada tic mínimo. Si pasaron más de 1h y
            # algo cambió, sí regeneramos.
            if datetime.now() - gen > timedelta(hours=1):
                return False
        return True
    except Exception:
        return False


def get_observation(ctx: ObservationContext, *, force: bool = False) -> dict:
    """
    Devuelve un dict con: text, generated_at, source, components_active.
    Usa caché de 6h salvo `force=True`.
    """
    if not force:
        cached = _read_cache()
        if cached and _cache_is_valid(cached, ctx):
            return {
                "text": cached["text"],
                "generated_at": cached["generated_at"],
                "source": "cache",
                "components_active": "9/9",
            }

    text = _generate_text(ctx)
    _write_cache(text, ctx)
    return {
        "text": text,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "fresh",
        "components_active": "9/9",
    }


def invalidate_cache() -> None:
    """Llamada desde el botón 'Forzar ciclo del bot'."""
    if CACHE_PATH.exists():
        try:
            CACHE_PATH.unlink()
        except OSError:
            pass
