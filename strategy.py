import logging
import config
from ml_model import TradingModel

logger = logging.getLogger(__name__)


class TradingStrategy:
    def __init__(self, model=None):
        self.model = model

    def _col(self, df, name):
        if name in df.columns:
            return df[name]
        m = [c for c in df.columns if c.startswith(name)]
        return df[m[0]] if m else None

    def generate_signal(self, df, market_ctx: dict = None):
        """
        Genera señal de trading. Acepta opcionalmente market_ctx
        (dict de market_context.get_full_context) para modular
        el comportamiento segun VIX, Fear&Greed y earnings.
        """
        result = {"action": "hold", "confidence": 0.0,
                  "stop_loss": 0.0, "reason": "Sin senal.",
                  "rsi": 50.0, "ma_trend": "neutral", "ml_prob": 0.5}
        if len(df) < config.MA_LONG_WINDOW + 5:
            result["reason"] = "Datos insuficientes."
            return result
        try:
            price = float(df.iloc[-1]["close"])
            atr   = float(df.iloc[-1].get("atr", 0))

            # ── Contexto de mercado externo ───────────────────
            vix_val    = None
            fg_val     = None
            mkt_signal = "neutral"
            earnings_risk = False

            if market_ctx:
                vix_val    = market_ctx.get("vix", {}).get("value")
                fg_val     = market_ctx.get("fear_greed", {}).get("value")
                mkt_signal = market_ctx.get("market_signal", "neutral")
                earn       = market_ctx.get("earnings", {})
                earnings_risk = (earn.get("has_earnings") and
                                 (earn.get("days_away") or 99) <= 2)
                if earnings_risk:
                    logger.warning(f"EARNINGS en {earn.get('days_away')} dias — operacion con precaucion")

            # ── Umbral de buy_score dinamico segun VIX ────────
            # VIX alto = mercado nervioso = necesito mas señales para comprar
            # VIX bajo = mercado calmo   = con menos señales me animo
            if vix_val is not None:
                if vix_val >= 35:
                    min_score = 5    # panico: necesito 5 señales tecnicas
                elif vix_val >= 30:
                    min_score = 4    # muy alto: 4 señales
                elif vix_val >= 25:
                    min_score = 3    # elevado: 3 señales
                elif vix_val >= 20:
                    min_score = 2    # normal: 2 señales
                else:
                    min_score = 1    # bajo/calmo: con 1 señal basta
            else:
                min_score = 2        # sin VIX: comportamiento moderado

            # Fear&Greed extremo ajusta el score minimo
            if fg_val is not None:
                if fg_val <= 20:    min_score = max(1, min_score - 1)  # miedo extremo = oportunidad
                elif fg_val >= 80:  min_score = min_score + 1           # codicia extrema = cuidado

            # ── Tendencia ─────────────────────────────────────
            sma_l = self._col(df, f"sma_{config.MA_LONG_WINDOW}")
            sma_s = self._col(df, f"sma_{config.MA_SHORT_WINDOW}")

            uptrend   = sma_l is not None and price > float(sma_l.iloc[-1])
            downtrend = sma_l is not None and price < float(sma_l.iloc[-1])
            result["ma_trend"] = "up" if uptrend else "down"

            ma_cross_up = (sma_s is not None and sma_l is not None and
                           float(sma_s.iloc[-2]) <= float(sma_l.iloc[-2]) and
                           float(sma_s.iloc[-1]) >  float(sma_l.iloc[-1]))
            ma_cross_dn = (sma_s is not None and sma_l is not None and
                           float(sma_s.iloc[-2]) >= float(sma_l.iloc[-2]) and
                           float(sma_s.iloc[-1]) <  float(sma_l.iloc[-1]))

            # ── RSI ───────────────────────────────────────────
            rsi        = float(df.iloc[-1].get("rsi", 50))
            oversold   = rsi < config.RSI_OVERSOLD
            overbought = rsi > config.RSI_OVERBOUGHT
            rsi_rising = rsi > float(df.iloc[-2].get("rsi", 50))
            result["rsi"] = round(rsi, 2)

            # ── Bollinger Bands ───────────────────────────────
            bbl = self._col(df, f"BBL_{config.BB_WINDOW}")
            bbu = self._col(df, f"BBU_{config.BB_WINDOW}")
            bbm = self._col(df, f"BBM_{config.BB_WINDOW}")
            near_low  = bbl is not None and price <= float(bbl.iloc[-1]) * (1 + config.BB_TOUCH_PCT)
            near_hi   = bbu is not None and price >= float(bbu.iloc[-1]) * (1 - config.BB_TOUCH_PCT)
            above_mid = bbm is not None and price >  float(bbm.iloc[-1])

            # ── MACD ──────────────────────────────────────────
            macd_col = self._col(df, "MACD_12_26_9")
            macd_s   = self._col(df, "MACDs_12_26_9")
            macd_bull = (macd_col is not None and macd_s is not None and
                         float(macd_col.iloc[-1]) > float(macd_s.iloc[-1]) and
                         float(macd_col.iloc[-2]) <= float(macd_s.iloc[-2]))
            macd_bear = (macd_col is not None and macd_s is not None and
                         float(macd_col.iloc[-1]) < float(macd_s.iloc[-1]) and
                         float(macd_col.iloc[-2]) >= float(macd_s.iloc[-2]))

            # ── Volumen ───────────────────────────────────────
            # No comprar si el volumen actual es menor al 80% del promedio 20 dias
            # Volumen bajo = señal debil, el mercado no esta convencido
            vol_now = float(df.iloc[-1].get("volume", 0))
            vol_avg = float(df["volume"].iloc[-20:].mean()) if "volume" in df.columns and len(df) >= 20 else vol_now
            vol_ok  = vol_now >= vol_avg * 0.8 if vol_avg > 0 else True

            # ── Stop-loss dinamico ────────────────────────────
            # Basado en el minimo reciente como soporte + buffer ATR.
            # Vende solo si el precio rompe por debajo del soporte real,
            # evitando vendas falsas cuando se compra durante una recuperacion.
            recent_low = float(df["low"].iloc[-config.STOP_LOSS_LOOKBACK:].min())
            stop_loss  = recent_low - atr * 0.5
            result["stop_loss"] = round(stop_loss, 4)

            # ── Modelo ML ─────────────────────────────────────
            p_up   = self.model.predict_prob(df) if self.model else 0.5
            p_down = 1.0 - p_up
            ml_buy  = p_up   > config.ML_BUY_PROB_THRESHOLD
            ml_sell = p_down > config.ML_SELL_PROB_THRESHOLD
            result["ml_prob"] = round(p_up, 4)

            # ════════════════════════════════════════
            # CONDICIONES DE COMPRA — MODO AGRESIVO
            # ════════════════════════════════════════
            buy_signals = [
                oversold,                                    # RSI bajo
                ma_cross_up,                                 # cruce dorado
                near_low and rsi_rising,                     # rebote en BB inferior
                macd_bull,                                   # cruce MACD alcista
                ml_buy,                                      # ML confirma (umbral 52%)
                uptrend and above_mid,                       # tendencia + sobre media BB
                downtrend and oversold and rsi_rising,       # caida fuerte + rebote RSI
                mkt_signal == "comprar_agresivo" and oversold,  # contexto externo muy positivo
            ]
            buy_score = sum(buy_signals)

            # Override: si score tecnico >= min_score, compra aunque ML no confirme
            ml_override = buy_score >= min_score

            # Bloquear compra si hay earnings en 2 dias o volumen muy bajo
            buy_blocked = earnings_risk or not vol_ok

            ctx_tag = ""
            if vix_val:
                ctx_tag = f" | VIX={vix_val}"
            if fg_val:
                ctx_tag += f" | F&G={fg_val}"

            if buy_score >= 1 and (ml_buy or ml_override) and not buy_blocked:
                reasons = []
                if oversold:                              reasons.append(f"RSI={rsi:.0f} bajo")
                if ma_cross_up:                           reasons.append("Cruce dorado SMA")
                if near_low and rsi_rising:               reasons.append("Rebote BB inferior")
                if macd_bull:                             reasons.append("Cruce MACD alcista")
                if downtrend and oversold and rsi_rising: reasons.append("Caida+rebote RSI")
                if mkt_signal == "comprar_agresivo":      reasons.append("Mercado: COMPRAR")
                if ml_override and not ml_buy:            reasons.append(f"Score={buy_score}>={min_score}")
                reasons.append(f"ML={p_up:.2f}{ctx_tag}")
                result.update(action="buy", confidence=round(p_up, 3),
                              reason=" | ".join(reasons))
                logger.info(f"SEÑAL BUY (score={buy_score}/{min_score}, ml={ml_buy}) | {result['reason']}")
                return result

            if earnings_risk:
                logger.info(f"Compra BLOQUEADA por earnings proximos")
            if not vol_ok:
                logger.info(f"Compra BLOQUEADA por volumen bajo ({vol_now:,.0f} < {vol_avg*0.8:,.0f})")

            # ════════════════════════════════════════
            # CONDICIONES DE VENTA
            # Si VIX es panico, vender ante cualquier señal debil
            # ════════════════════════════════════════
            panic_mode = vix_val is not None and vix_val >= 35

            sell_signals = {
                "Stop-loss":         price < stop_loss,
                "ML venta fuerte":   ml_sell,
                "RSI+BB superior":   overbought and near_hi,
                "Cruce bajista SMA": ma_cross_dn,
                "MACD bajista":      macd_bear and downtrend,
                "Panico VIX>35":     panic_mode and downtrend,
            }
            triggered = [k for k, v in sell_signals.items() if v]

            if triggered:
                result.update(action="sell", confidence=round(p_down, 3),
                              reason=" | ".join(triggered))
                logger.info(f"SEÑAL SELL | {result['reason']}")
                return result

            result["confidence"] = round(p_up, 3)
            result["reason"] = (
                f"HOLD | RSI={rsi:.1f} | "
                f"{'Tendencia alcista' if uptrend else 'Tendencia bajista'} | "
                f"ML={p_up:.2f} | Score={buy_score}/{min_score}{ctx_tag}"
            )
        except Exception as e:
            logger.error(f"Error en senal: {e}", exc_info=True)
        return result
