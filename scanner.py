"""
scanner.py — Escaner multi-simbolo.

Evalua todos los activos del watchlist cada ciclo y retorna
señales rankeadas por confianza. El bot compra los mejores
y vende los que esten en posicion con señal negativa.
"""
import logging
from datetime import datetime, timezone, timedelta

import config
from data_fetcher import DataFetcher
from indicators import add_all_indicators
from strategy import TradingStrategy
from ml_model import TradingModel

logger = logging.getLogger(__name__)

LOOKBACK_DAYS = {
    "1Min": 3, "5Min": 7, "15Min": 14,
    "1Hour": 60, "4Hour": 160, "1Day": 400,
}
MIN_BARS = config.MA_LONG_WINDOW + 10  # minimo de velas para calcular indicadores


class MarketScanner:
    def __init__(self, model: TradingModel, fetcher: DataFetcher):
        self.model    = model
        self.fetcher  = fetcher
        self.strategy = TradingStrategy(model=model)

    def scan(self, symbols: list, timeframe: str,
             held_symbols: set = None, market_ctx: dict = None,
             memory=None) -> dict:
        """
        Evalua todos los simbolos del watchlist.

        Retorna:
            {
              "buys":  [{"symbol", "signal", "price"}, ...],  # rankeados por confidence
              "sells": [{"symbol", "signal", "price"}, ...],  # solo simbolos en posicion abierta
            }

        held_symbols: set de simbolos con posicion abierta actualmente.
        Solo genera SELL para simbolos en held_symbols.
        Solo genera BUY para simbolos que NO esten en held_symbols.
        """
        held_symbols = held_symbols or set()
        buys  = []
        sells = []

        end_dt   = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=LOOKBACK_DAYS.get(timeframe, 60))

        for symbol in symbols:
            try:
                df_raw = self.fetcher.get_historical(symbol, start_dt, end_dt, timeframe)

                if df_raw.empty or len(df_raw) < MIN_BARS:
                    logger.debug(f"[SCANNER] {symbol}: datos insuficientes ({len(df_raw)} velas), skip")
                    continue

                df     = add_all_indicators(df_raw.copy())
                signal = self.strategy.generate_signal(df, market_ctx=market_ctx)
                price  = self.fetcher.get_current_price(symbol)
                if price <= 0:
                    price = float(df.iloc[-1]["close"])

                entry = {"symbol": symbol, "signal": signal, "price": price}

                if signal["action"] == "buy" and symbol not in held_symbols:
                    # Symbol score: penaliza simbolos con historial negativo
                    sym_score = memory.get_symbol_score(symbol) if memory else 0.5
                    entry["_rank"] = signal["confidence"] * 0.7 + sym_score * 0.3
                    buys.append(entry)
                    logger.info(
                        f"[SCANNER] {symbol}: BUY | "
                        f"conf={signal['confidence']:.2f} | {signal['reason'][:70]}"
                    )
                elif signal["action"] == "sell" and symbol in held_symbols:
                    sells.append(entry)
                    logger.info(f"[SCANNER] {symbol}: SELL | {signal['reason'][:70]}")
                else:
                    logger.info(
                        f"[SCANNER] {symbol}: HOLD | {signal['reason'][:60]}"
                    )

            except Exception as e:
                logger.error(f"[SCANNER] Error evaluando {symbol}: {e}")

        # Rankear buys por confianza ML (70%) + symbol score historico (30%)
        buys.sort(key=lambda x: x.get("_rank", x["signal"]["confidence"]), reverse=True)

        logger.info(
            f"[SCANNER] Resumen: {len(buys)} BUY | {len(sells)} SELL "
            f"| Watchlist: {symbols}"
        )
        return {"buys": buys, "sells": sells}
