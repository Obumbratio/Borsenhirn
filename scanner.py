"""
scanner.py — Escaner multi-simbolo.

Evalua todos los activos del watchlist cada ciclo y retorna
señales rankeadas por confianza. El bot compra los mejores
y vende los que esten en posicion con señal negativa.

Usa ThreadPoolExecutor para evaluar simbolos en paralelo.
"""
import logging
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

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
MAX_WORKERS = 6  # hilos paralelos para API calls


class MarketScanner:
    def __init__(self, model: TradingModel, fetcher: DataFetcher):
        self.model    = model
        self.fetcher  = fetcher
        self.strategy = TradingStrategy(model=model)

    def _evaluate_symbol(self, symbol: str, start_dt, end_dt, timeframe: str,
                         held_symbols: set, market_ctx: dict, memory) -> dict:
        """Evalua un simbolo individual. Diseñado para correr en un thread."""
        df_raw = self.fetcher.get_historical(symbol, start_dt, end_dt, timeframe)

        if df_raw.empty or len(df_raw) < MIN_BARS:
            logger.debug(f"[SCANNER] {symbol}: datos insuficientes ({len(df_raw)} velas), skip")
            return {"symbol": symbol, "result": "skip"}

        df     = add_all_indicators(df_raw.copy())
        signal = self.strategy.generate_signal(df, market_ctx=market_ctx)
        price  = self.fetcher.get_current_price(symbol)
        if price <= 0:
            price = float(df.iloc[-1]["close"])

        entry = {"symbol": symbol, "signal": signal, "price": price}

        if signal["action"] == "buy" and symbol not in held_symbols:
            sym_score = memory.get_symbol_score(symbol) if memory else 0.5
            entry["_rank"] = signal["confidence"] * 0.7 + sym_score * 0.3
            return {"symbol": symbol, "result": "buy", "entry": entry}
        elif signal["action"] == "sell" and symbol in held_symbols:
            return {"symbol": symbol, "result": "sell", "entry": entry}
        else:
            return {"symbol": symbol, "result": "hold", "reason": signal["reason"][:60]}

    def scan(self, symbols: list, timeframe: str,
             held_symbols: set = None, market_ctx: dict = None,
             memory=None) -> dict:
        """
        Evalua todos los simbolos del watchlist en paralelo.

        Retorna:
            {
              "buys":  [{"symbol", "signal", "price"}, ...],  # rankeados por confidence
              "sells": [{"symbol", "signal", "price"}, ...],  # solo simbolos en posicion abierta
            }
        """
        held_symbols = held_symbols or set()
        buys  = []
        sells = []

        end_dt   = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=LOOKBACK_DAYS.get(timeframe, 60))

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(
                    self._evaluate_symbol, symbol, start_dt, end_dt,
                    timeframe, held_symbols, market_ctx, memory
                ): symbol
                for symbol in symbols
            }

            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    res = future.result()
                    if res["result"] == "buy":
                        buys.append(res["entry"])
                        sig = res["entry"]["signal"]
                        logger.info(
                            f"[SCANNER] {symbol}: BUY | "
                            f"conf={sig['confidence']:.2f} | {sig['reason'][:70]}"
                        )
                    elif res["result"] == "sell":
                        sells.append(res["entry"])
                        logger.info(f"[SCANNER] {symbol}: SELL | {res['entry']['signal']['reason'][:70]}")
                    elif res["result"] == "hold":
                        logger.info(f"[SCANNER] {symbol}: HOLD | {res['reason']}")
                except Exception as e:
                    logger.error(f"[SCANNER] Error evaluando {symbol}: {e}")

        buys.sort(key=lambda x: x.get("_rank", x["signal"]["confidence"]), reverse=True)

        logger.info(
            f"[SCANNER] Resumen: {len(buys)} BUY | {len(sells)} SELL "
            f"| Watchlist: {len(symbols)} simbolos"
        )
        return {"buys": buys, "sells": sells}
