import logging, time
import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestBarRequest, StockLatestTradeRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
import config

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
                return df
            except Exception as e:
                logger.error(f"Intento {attempt}: {e}")
                if attempt < retries:
                    time.sleep(2 ** attempt)
        return pd.DataFrame()

    def get_latest_bar(self, symbol):
        try:
            req  = StockLatestBarRequest(symbol_or_symbols=symbol, feed="iex")
            bar  = self.client.get_stock_latest_bar(req)[symbol]
            return pd.Series({"open":bar.open,"high":bar.high,"low":bar.low,
                               "close":bar.close,"volume":bar.volume}, name=bar.timestamp)
        except Exception as e:
            logger.error(f"get_latest_bar: {e}")
            return pd.Series()

    def get_current_price(self, symbol):
        try:
            req = StockLatestTradeRequest(symbol_or_symbols=symbol, feed="iex")
            return float(self.client.get_stock_latest_trade(req)[symbol].price)
        except Exception as e:
            logger.error(f"get_current_price: {e}")
            return 0.0
