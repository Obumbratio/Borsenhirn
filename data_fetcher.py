import logging, time
import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestBarRequest, StockLatestTradeRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
import config
from circuit_breaker import alpaca_cb

logger = logging.getLogger(__name__)

TIMEFRAME_MAP = {
    "1Min":  TimeFrame(1,  TimeFrameUnit.Minute),
    "5Min":  TimeFrame(5,  TimeFrameUnit.Minute),
    "15Min": TimeFrame(15, TimeFrameUnit.Minute),
    "1Hour": TimeFrame(1,  TimeFrameUnit.Hour),
    "4Hour": TimeFrame(4,  TimeFrameUnit.Hour),
    "1Day":  TimeFrame(1,  TimeFrameUnit.Day),
}

class DataFetcher:
    def __init__(self, api_key=None, secret_key=None):
        self.api_key    = api_key    or config.ALPACA_API_KEY
        self.secret_key = secret_key or config.ALPACA_SECRET_KEY
        self.client     = StockHistoricalDataClient(self.api_key, self.secret_key)
        logger.info("DataFetcher listo.")

    def get_historical(self, symbol, start, end, timeframe="1Hour", retries=3):
        tf = TIMEFRAME_MAP.get(timeframe)
        if not tf:
            raise ValueError(f"Timeframe '{timeframe}' no válido.")
        if not alpaca_cb.can_call():
            logger.warning(f"Circuit breaker Alpaca abierto — omitiendo get_historical({symbol})")
            return pd.DataFrame()
        for attempt in range(1, retries + 1):
            try:
                req  = StockBarsRequest(symbol_or_symbols=symbol, timeframe=tf,
                                        start=start, end=end, feed="iex")
                bars = self.client.get_stock_bars(req)
                df   = bars.df
                if df.empty:
                    logger.warning("Sin datos.")
                    return pd.DataFrame()
                if isinstance(df.index, pd.MultiIndex):
                    df = df.xs(symbol, level="symbol")
                df.index = pd.to_datetime(df.index)
                df.index.name = "timestamp"
                df = df[["open","high","low","close","volume"]].copy()
                df.sort_index(inplace=True)
                logger.info(f"{len(df)} velas descargadas ({symbol} {timeframe})")
                alpaca_cb.record_success()
                return df
            except Exception as e:
                logger.error(f"Intento {attempt}: {e}")
                if attempt < retries:
                    time.sleep(2 ** attempt)
        alpaca_cb.record_failure()
        return pd.DataFrame()

    def get_latest_bar(self, symbol):
        if not alpaca_cb.can_call():
            logger.warning(f"Circuit breaker Alpaca abierto — omitiendo get_latest_bar({symbol})")
            return pd.Series()
        try:
            req  = StockLatestBarRequest(symbol_or_symbols=symbol, feed="iex")
            bar  = self.client.get_stock_latest_bar(req)[symbol]
            alpaca_cb.record_success()
            return pd.Series({"open":bar.open,"high":bar.high,"low":bar.low,
                               "close":bar.close,"volume":bar.volume}, name=bar.timestamp)
        except Exception as e:
            logger.error(f"get_latest_bar: {e}")
            alpaca_cb.record_failure()
            return pd.Series()

    def get_current_price(self, symbol):
        if not alpaca_cb.can_call():
            logger.warning(f"Circuit breaker Alpaca abierto — omitiendo get_current_price({symbol})")
            return 0.0
        try:
            req = StockLatestTradeRequest(symbol_or_symbols=symbol, feed="iex")
            price = float(self.client.get_stock_latest_trade(req)[symbol].price)
            alpaca_cb.record_success()
            return price
        except Exception as e:
            logger.error(f"get_current_price: {e}")
            alpaca_cb.record_failure()
            return 0.0

    def subscribe_prices(self, symbols: list, callback):
        """Subscribe to real-time price updates via WebSocket (optional).
        Falls back to polling if WebSocket unavailable.

        Args:
            symbols: List of ticker symbols to subscribe to.
            callback: Function(symbol: str, price: float) called on each bar update.

        Returns:
            True if WebSocket stream started, False if unavailable.
        """
        try:
            from alpaca.data.live import StockDataStream
            stream = StockDataStream(config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY)

            async def on_bar(bar):
                callback(bar.symbol, float(bar.close))

            for sym in symbols:
                stream.subscribe_bars(on_bar, sym)

            # Run in background thread
            import threading
            t = threading.Thread(target=stream.run, daemon=True)
            t.start()
            logger.info(f"[WS] Subscrito a {len(symbols)} simbolos via WebSocket")
            return True
        except Exception as e:
            logger.warning(f"[WS] WebSocket no disponible: {e} — usando polling")
            return False
