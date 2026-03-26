"""
regime_detector.py — Detector de régimen de mercado.

Detecta uno de 4 estados: BULL / BEAR / SIDEWAYS / PANIC

Corre UNA vez por ciclo. Recibe el market_ctx ya calculado en main.py
para reutilizar el VIX sin hacer llamadas duplicadas a APIs externas.

Jerarquía de clasificación (prioridad descendente):
  PANIC    > BEAR > SIDEWAYS > BULL

Histéresis: requiere REGIME_HYSTERESIS_CYCLES ciclos consecutivos
con el mismo régimen antes de confirmar el cambio. Evita flapping
cuando el mercado oscila en el borde de dos regímenes.

Breadth: cacheado REGIME_BREADTH_CACHE_MIN minutos para no hacer
44 llamadas a la API en cada ciclo.
"""

import logging
from datetime import datetime, timezone, timedelta

import pandas as pd
import config

logger = logging.getLogger(__name__)

# ── Estado interno del módulo ─────────────────────────────────────────────────

_breadth_cache = {"value": None, "timestamp": None}
_regime_history = []   # últimos N regímenes sin filtrar (para histéresis)
_confirmed_regime = None  # último régimen confirmado por histéresis


def _calc_adx(df: pd.DataFrame, period: int = 14) -> float:
    """ADX usando la librería ta (ya en requirements.txt)."""
    try:
        from ta.trend import ADXIndicator
        adx_ind = ADXIndicator(
            high=df["high"], low=df["low"], close=df["close"], window=period
        )
        val = adx_ind.adx().iloc[-1]
        return float(val) if pd.notna(val) else 0.0
    except Exception as e:
        logger.warning(f"[REGIME] ADX error: {e}")
        return 0.0


def _calc_breadth(fetcher) -> float:
    """
    Porcentaje de símbolos del watchlist que cierran sobre su SMA50 (diario).
    Resultado cacheado REGIME_BREADTH_CACHE_MIN minutos.
    """
    global _breadth_cache

    now       = datetime.now(timezone.utc)
    cached_ts = _breadth_cache.get("timestamp")
    cache_secs = config.REGIME_BREADTH_CACHE_MIN * 60

    if cached_ts is not None and (now - cached_ts).total_seconds() < cache_secs:
        logger.debug("[REGIME] Breadth desde caché.")
        return _breadth_cache["value"]

    above   = 0
    total   = 0
    end_dt   = now
    start_dt = end_dt - timedelta(days=120)   # ~80 barras diarias, suficiente para SMA50

    for sym in config.WATCHLIST:
        try:
            df = fetcher.get_historical(sym, start_dt, end_dt, "1Day")
            if df.empty or len(df) < 52:
                continue
            sma50 = df["close"].rolling(50).mean().iloc[-1]
            price = df["close"].iloc[-1]
            if pd.notna(sma50) and price > sma50:
                above += 1
            total += 1
        except Exception:
            pass   # si un símbolo falla, lo ignoramos y continuamos

    breadth = (above / total) if total > 0 else 0.5
    _breadth_cache["value"]     = breadth
    _breadth_cache["timestamp"] = now
    logger.info(f"[REGIME] Breadth: {above}/{total} = {breadth:.1%} sobre SMA50")
    return breadth


def _classify(spy_above_sma50: bool, spy_above_sma20: bool,
              spy_day_change_pct: float, vix: float,
              breadth: float, adx: float) -> tuple:
    """
    Clasifica el régimen con jerarquía PANIC > BEAR > SIDEWAYS > BULL.
    Retorna (régimen: str, confianza: float).
    """
    # ── PANIC (verificar primero — prioridad máxima) ──────────────
    panic_signals = [
        vix > 35,
        spy_day_change_pct < -3.0,
        breadth < 0.20,
    ]
    if any(panic_signals):
        conf = sum(panic_signals) / len(panic_signals)
        return "PANIC", round(min(conf + 0.4, 1.0), 2)

    # ── BEAR ──────────────────────────────────────────────────────
    bear_signals = [
        not spy_above_sma50,
        breadth < 0.40,
        vix > 20,
    ]
    bear_score = sum(bear_signals)

    # ── SIDEWAYS ──────────────────────────────────────────────────
    sideways_signals = [
        adx < 20,
        0.40 <= breadth <= 0.60,
        not spy_above_sma50 and not spy_above_sma20,
    ]
    sideways_score = sum(sideways_signals)

    # ── BULL ──────────────────────────────────────────────────────
    bull_signals = [
        spy_above_sma50,
        breadth > 0.60,
        vix < 20,
        adx > 20,
    ]
    bull_score = sum(bull_signals)

    # Seleccionar el régimen con más señales confirmadas.
    # En empate, jerarquía: BEAR > SIDEWAYS > BULL (conservador).
    candidates = {}
    if bear_score     >= 2: candidates["BEAR"]     = bear_score / 3
    if sideways_score >= 2: candidates["SIDEWAYS"] = sideways_score / 3
    if bull_score     >= 3: candidates["BULL"]     = bull_score / 4

    if not candidates:
        return "SIDEWAYS", 0.40   # sin consenso → neutro con baja confianza

    # Prioridad en empate: BEAR > SIDEWAYS > BULL
    priority = {"BEAR": 3, "SIDEWAYS": 2, "BULL": 1}
    best = max(candidates, key=lambda r: (candidates[r], priority.get(r, 0)))
    return best, round(candidates[best], 2)


def _apply_hysteresis(raw_regime: str) -> str:
    """
    Requiere config.REGIME_HYSTERESIS_CYCLES ciclos consecutivos
    del mismo régimen antes de confirmar el cambio de estado.
    """
    global _regime_history, _confirmed_regime

    _regime_history.append(raw_regime)
    # Mantener solo la ventana necesaria
    window = config.REGIME_HYSTERESIS_CYCLES + 1
    if len(_regime_history) > window:
        _regime_history = _regime_history[-window:]

    # ¿Los últimos N ciclos coinciden?
    n = config.REGIME_HYSTERESIS_CYCLES
    if len(_regime_history) >= n and len(set(_regime_history[-n:])) == 1:
        _confirmed_regime = raw_regime

    # Si aún no hay régimen confirmado, usar el primero de la historia
    if _confirmed_regime is None:
        _confirmed_regime = raw_regime

    return _confirmed_regime


def detect_regime(fetcher, market_ctx: dict = None) -> dict:
    """
    Detecta el régimen actual del mercado.

    Debe llamarse UNA sola vez por ciclo, después de get_full_context().

    Args:
        fetcher:    instancia de DataFetcher ya inicializada.
        market_ctx: dict retornado por market_context.get_full_context().
                    Se reutiliza el VIX de ahí para evitar llamadas duplicadas.

    Returns:
        {
          "regime":          "BULL" | "BEAR" | "SIDEWAYS" | "PANIC",
          "confidence":      float 0.0–1.0,
          "vix":             float,
          "spy_trend":       "UP" | "DOWN" | "FLAT",
          "breadth_pct":     float | None,
          "adx":             float,
          "spy_change_pct":  float,
        }
    """
    result = {
        "regime":         "SIDEWAYS",
        "confidence":     0.5,
        "vix":            0.0,
        "spy_trend":      "FLAT",
        "breadth_pct":    None,
        "adx":            0.0,
        "spy_change_pct": 0.0,
    }

    try:
        # ── VIX: reutilizar el de market_ctx (ya descargado) ─────
        vix = 0.0
        if market_ctx:
            vix = float(market_ctx.get("vix", {}).get("value") or 0.0)
        result["vix"] = vix

        # ── Datos diarios de SPY: SMA20, SMA50, ADX, cambio % ────
        end_dt   = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=120)
        df_spy   = fetcher.get_historical("SPY", start_dt, end_dt, "1Day")

        if df_spy.empty or len(df_spy) < 52:
            logger.warning("[REGIME] Datos SPY insuficientes — usando SIDEWAYS por defecto.")
            return result

        spy_close = float(df_spy["close"].iloc[-1])
        sma20     = float(df_spy["close"].rolling(20).mean().iloc[-1])
        sma50     = float(df_spy["close"].rolling(50).mean().iloc[-1])

        spy_above_sma50 = spy_close > sma50
        spy_above_sma20 = spy_close > sma20

        # Cambio % del día (vela anterior vs última)
        spy_prev          = float(df_spy["close"].iloc[-2]) if len(df_spy) >= 2 else spy_close
        spy_day_change_pct = (spy_close - spy_prev) / spy_prev * 100
        result["spy_change_pct"] = round(spy_day_change_pct, 2)

        # Tendencia SMA20: comparar hoy vs 5 días atrás
        if len(df_spy) >= 26:
            sma20_5d = float(df_spy["close"].rolling(20).mean().iloc[-6])
            if sma20 > sma20_5d * 1.002:
                result["spy_trend"] = "UP"
            elif sma20 < sma20_5d * 0.998:
                result["spy_trend"] = "DOWN"
            else:
                result["spy_trend"] = "FLAT"

        # ── ADX ──────────────────────────────────────────────────
        adx = _calc_adx(df_spy)
        result["adx"] = round(adx, 1)

        # ── Breadth (cacheado) ────────────────────────────────────
        breadth = _calc_breadth(fetcher)
        result["breadth_pct"] = round(breadth, 3)

        # ── Clasificar con jerarquía ──────────────────────────────
        raw_regime, confidence = _classify(
            spy_above_sma50, spy_above_sma20,
            spy_day_change_pct, vix, breadth, adx
        )

        # ── Aplicar histéresis ────────────────────────────────────
        stable_regime        = _apply_hysteresis(raw_regime)
        result["regime"]     = stable_regime
        result["confidence"] = confidence

        logger.info(
            f"[REGIME] {stable_regime} (raw={raw_regime}) | "
            f"conf={confidence:.0%} | "
            f"SPY {'>' if spy_above_sma50 else '<'} SMA50 "
            f"({'>' if spy_above_sma20 else '<'} SMA20) | "
            f"VIX={vix:.1f} | ADX={adx:.1f} | "
            f"breadth={breadth:.1%} | SPY Δ={spy_day_change_pct:+.2f}%"
        )

    except Exception as e:
        logger.error(f"[REGIME] Error en detect_regime: {e}", exc_info=True)

    return result
