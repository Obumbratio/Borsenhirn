"""
setup_proyecto.py
Ejecuta este archivo UNA SOLA VEZ desde el terminal de PyCharm:
    python setup_proyecto.py

Creará toda la estructura del proyecto automáticamente.
"""

import os

BASE = os.path.dirname(os.path.abspath(__file__))

def write(path, content):
    full = os.path.join(BASE, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  ✅  {path}")

print("\n🚀 Creando estructura del proyecto...\n")

# Crear carpetas vacías
for folder in ["models", "logs", "results"]:
    os.makedirs(os.path.join(BASE, folder), exist_ok=True)
    print(f"  📁  {folder}/")

# ─────────────────────────────────────────────────────────────
# .env
# ─────────────────────────────────────────────────────────────
write(".env", """\
ALPACA_API_KEY=YOUR_ALPACA_API_KEY_HERE
ALPACA_SECRET_KEY=YOUR_ALPACA_SECRET_KEY_HERE
ALPACA_BASE_URL=https://paper-api.alpaca.markets
ANTHROPIC_API_KEY=YOUR_ANTHROPIC_API_KEY_HERE
# TELEGRAM_BOT_TOKEN=
# TELEGRAM_CHAT_ID=
""")

# ─────────────────────────────────────────────────────────────
# requirements.txt
# ─────────────────────────────────────────────────────────────
write("requirements.txt", """\
alpaca-py>=0.13.0
pandas>=2.0.0
numpy>=1.24.0
ta>=0.11.0
scikit-learn>=1.3.0
joblib>=1.3.0
python-dotenv>=1.0.0
requests>=2.31.0
matplotlib>=3.7.0
fpdf2>=2.7.0
""")

# ─────────────────────────────────────────────────────────────
# config.py
# ─────────────────────────────────────────────────────────────
write("config.py", '''\
import os
from dotenv import load_dotenv
load_dotenv()

ALPACA_API_KEY    = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL   = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

SYMBOL     = "SPY"
TIMEFRAME  = "1Day"
CAPITAL    = 100_000

MA_SHORT_WINDOW        = 20
MA_LONG_WINDOW         = 100
ATR_PERIOD             = 14
STOP_LOSS_ATR_MULT     = 1.5
STOP_LOSS_LOOKBACK     = 20
RSI_PERIOD             = 14
RSI_OVERSOLD           = 35
RSI_OVERBOUGHT         = 65
BB_WINDOW              = 20
BB_STD                 = 2
BB_TOUCH_PCT           = 0.01

ML_HORIZON             = 5
ML_THRESHOLD           = 0.01
ML_SELL_PROB_THRESHOLD = 0.80
ML_BUY_PROB_THRESHOLD  = 0.55
RF_N_ESTIMATORS        = 200
RF_MAX_DEPTH           = 8
RF_RANDOM_STATE        = 42

MAX_DAILY_LOSS_PCT     = 0.03
MAX_TRADES_PER_DAY     = 3
MAX_POSITION_PCT       = 0.30

MODEL_PATH  = "models/random_forest.pkl"
SCALER_PATH = "models/scaler.pkl"
LOG_DIR     = "logs/"
TRADES_LOG  = "logs/trades.csv"

LOG_LEVEL  = "INFO"
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
''')

# ─────────────────────────────────────────────────────────────
# data_fetcher.py
# ─────────────────────────────────────────────────────────────
write("data_fetcher.py", '''\
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
            raise ValueError(f"Timeframe \'{timeframe}\' no válido.")
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
''')

# ─────────────────────────────────────────────────────────────
# indicators.py
# ─────────────────────────────────────────────────────────────
write("indicators.py", '''\
import logging
import pandas as pd
import ta
import config

logger = logging.getLogger(__name__)


def add_moving_averages(df, short=config.MA_SHORT_WINDOW, long=config.MA_LONG_WINDOW):
    df[f"sma_{short}"] = df["close"].rolling(window=short).mean()
    df[f"sma_{long}"]  = df["close"].rolling(window=long).mean()
    return df


def add_rsi(df, period=config.RSI_PERIOD):
    df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=period).rsi()
    return df


def add_macd(df):
    macd_ind = ta.trend.MACD(df["close"])
    df["MACD_12_26_9"]  = macd_ind.macd()
    df["MACDs_12_26_9"] = macd_ind.macd_signal()
    df["MACDh_12_26_9"] = macd_ind.macd_diff()
    return df


def add_bollinger_bands(df, window=config.BB_WINDOW, std=config.BB_STD):
    bb = ta.volatility.BollingerBands(df["close"], window=window, window_dev=std)
    df[f"BBL_{window}_{float(std)}"] = bb.bollinger_lband()
    df[f"BBM_{window}_{float(std)}"] = bb.bollinger_mavg()
    df[f"BBU_{window}_{float(std)}"] = bb.bollinger_hband()
    return df


def add_atr(df, period=config.ATR_PERIOD):
    df["atr"] = ta.volatility.AverageTrueRange(
        df["high"], df["low"], df["close"], window=period
    ).average_true_range()
    return df


def add_all_indicators(df):
    df = add_moving_averages(df)
    df = add_rsi(df)
    df = add_macd(df)
    df = add_bollinger_bands(df)
    df = add_atr(df)
    before = len(df)
    df.dropna(inplace=True)
    logger.info(f"Indicadores OK. Filas: {len(df)} (dropped {before - len(df)})")
    return df
''')

# ─────────────────────────────────────────────────────────────
# ml_model.py
# ─────────────────────────────────────────────────────────────
write("ml_model.py", '''\
import os, logging, joblib
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, confusion_matrix
import config

logger = logging.getLogger(__name__)

FEATURE_COLS = [
    "open","high","low","close","volume",
    f"sma_{config.MA_SHORT_WINDOW}", f"sma_{config.MA_LONG_WINDOW}",
    "rsi","atr",
    "MACD_12_26_9","MACDs_12_26_9","MACDh_12_26_9",
    f"BBL_{config.BB_WINDOW}_{float(config.BB_STD)}",
    f"BBM_{config.BB_WINDOW}_{float(config.BB_STD)}",
    f"BBU_{config.BB_WINDOW}_{float(config.BB_STD)}",
]

class TradingModel:
    def __init__(self, model_path=config.MODEL_PATH, scaler_path=config.SCALER_PATH):
        self.model_path  = model_path
        self.scaler_path = scaler_path
        self.model       = None
        self.scaler      = None

    def _avail(self, df):
        return [c for c in FEATURE_COLS if c in df.columns]

    def prepare_features(self, df):
        fc = self._avail(df)
        X  = df[fc].values
        sc = StandardScaler()
        return sc.fit_transform(X), sc, fc

    def create_labels(self, df, horizon=config.ML_HORIZON, threshold=config.ML_THRESHOLD):
        fut = df["close"].shift(-horizon)
        return ((fut - df["close"]) / df["close"] >= threshold).astype(int)

    def train(self, df):
        labels   = self.create_labels(df)
        fc       = self._avail(df)
        valid    = labels.dropna().index
        X_raw    = df.loc[valid, fc].values
        y        = labels.loc[valid].values
        self.scaler = StandardScaler()
        X        = self.scaler.fit_transform(X_raw)
        split    = int(len(X) * 0.8)
        Xtr,Xte  = X[:split], X[split:]
        ytr,yte  = y[:split], y[split:]
        logger.info(f"Entrenando RF con {len(Xtr)} muestras...")
        self.model = RandomForestClassifier(
            n_estimators=config.RF_N_ESTIMATORS,
            max_depth=config.RF_MAX_DEPTH,
            random_state=config.RF_RANDOM_STATE, n_jobs=-1)
        self.model.fit(Xtr, ytr)
        yp  = self.model.predict(Xte)
        acc = (yp == yte).mean()
        logger.info(f"Accuracy test: {acc:.4f}")
        logger.info("\\n" + classification_report(yte, yp))
        self.save_model()
        return {"accuracy": acc, "confusion_matrix": confusion_matrix(yte, yp).tolist()}

    def save_model(self):
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        joblib.dump(self.model,  self.model_path)
        joblib.dump(self.scaler, self.scaler_path)
        logger.info(f"Modelo guardado en {self.model_path}")

    def load_model(self):
        try:
            self.model  = joblib.load(self.model_path)
            self.scaler = joblib.load(self.scaler_path)
            logger.info("Modelo cargado.")
            return True
        except FileNotFoundError:
            logger.warning("Modelo no encontrado. Entrena primero.")
            return False

    def predict_prob(self, df):
        if self.model is None or self.scaler is None:
            return 0.5
        fc  = self._avail(df)
        X   = self.scaler.transform(df[fc].iloc[[-1]].values)
        prb = self.model.predict_proba(X)[0]
        cls = list(self.model.classes_)
        return float(prb[cls.index(1)]) if 1 in cls else 0.5
''')

# ─────────────────────────────────────────────────────────────
# strategy.py
# ─────────────────────────────────────────────────────────────
write("strategy.py", '''\
import logging
import config
from ml_model import TradingModel

logger = logging.getLogger(__name__)

class TradingStrategy:
    def __init__(self, model=None):
        self.model = model

    def _col(self, df, name):
        if name in df.columns: return df[name]
        m = [c for c in df.columns if c.startswith(name)]
        return df[m[0]] if m else None

    def generate_signal(self, df):
        result = {"action":"hold","confidence":0.0,"stop_loss":0.0,"reason":"Sin señal."}
        if len(df) < config.MA_LONG_WINDOW + 5:
            result["reason"] = "Datos insuficientes."
            return result
        try:
            last  = df.iloc[-1]
            price = float(last["close"])
            atr   = float(last.get("atr", 0))

            sma_l = self._col(df, f"sma_{config.MA_LONG_WINDOW}")
            sma_s = self._col(df, f"sma_{config.MA_SHORT_WINDOW}")
            uptrend  = sma_l is not None and price > float(sma_l.iloc[-1])
            ma_cross = (sma_s is not None and sma_l is not None and
                        float(sma_s.iloc[-2]) <= float(sma_l.iloc[-2]) and
                        float(sma_s.iloc[-1]) >  float(sma_l.iloc[-1]))

            rsi        = float(last.get("rsi", 50))
            oversold   = rsi < config.RSI_OVERSOLD
            overbought = rsi > config.RSI_OVERBOUGHT

            bbl = self._col(df, f"BBL_{config.BB_WINDOW}")
            bbu = self._col(df, f"BBU_{config.BB_WINDOW}")
            near_low = bbl is not None and price <= float(bbl.iloc[-1]) * 1.005
            near_hi  = bbu is not None and price >= float(bbu.iloc[-1]) * 0.995

            stop_loss = float(df["high"].iloc[-10:].max()) - atr * config.STOP_LOSS_ATR_MULT
            result["stop_loss"] = round(stop_loss, 4)

            p_up    = self.model.predict_prob(df) if self.model else 0.5
            ml_sell = (1 - p_up) > config.ML_SELL_PROB_THRESHOLD
            ml_buy  = p_up       > config.ML_SELL_PROB_THRESHOLD

            buy1 = uptrend and oversold and near_low
            buy2 = ma_cross and (ml_buy or self.model is None)
            if buy1 or buy2:
                reasons = []
                if buy1: reasons.append(f"Tendencia↑ + RSI={rsi:.1f} + BB inferior")
                if buy2: reasons.append(f"Cruce dorado + ML P(↑)={p_up:.2f}")
                result.update(action="buy", confidence=round(p_up,4), reason=" | ".join(reasons))
                logger.info(f"SEÑAL BUY | {result[\'reason\']}")
                return result

            sel1 = overbought and near_hi
            sel2 = ml_sell
            sel3 = price < stop_loss
            if sel1 or sel2 or sel3:
                reasons = []
                if sel1: reasons.append(f"RSI={rsi:.1f} sobrecomprado + BB superior")
                if sel2: reasons.append(f"ML P(↓)={1-p_up:.2f}")
                if sel3: reasons.append(f"Precio {price:.2f} < stop {stop_loss:.2f}")
                result.update(action="sell", confidence=round(1-p_up,4), reason=" | ".join(reasons))
                logger.info(f"SEÑAL SELL | {result[\'reason\']}")
                return result

            result["confidence"] = round(p_up, 4)
            result["reason"] = f"HOLD | RSI={rsi:.1f} | ML P(↑)={p_up:.2f}"
        except Exception as e:
            logger.error(f"Error en señal: {e}", exc_info=True)
        return result
''')

# ─────────────────────────────────────────────────────────────
# risk_manager.py
# ─────────────────────────────────────────────────────────────
write("risk_manager.py", '''\
import logging
import config

logger = logging.getLogger(__name__)

class RiskManager:
    def __init__(self):
        self.capital         = config.CAPITAL
        self.daily_pnl       = 0.0
        self.trades_today    = 0
        self.portfolio_value = config.CAPITAL

    def update(self, portfolio_value, daily_pnl, trades_today):
        self.portfolio_value = portfolio_value
        self.daily_pnl       = daily_pnl
        self.trades_today    = trades_today

    def reset_daily(self):
        self.daily_pnl    = 0.0
        self.trades_today = 0
        logger.info("Contadores diarios reiniciados.")

    def check_daily_loss(self):
        limit = self.portfolio_value * config.MAX_DAILY_LOSS_PCT
        if self.daily_pnl < -limit:
            logger.warning(f"⛔ Límite pérdida diaria: PnL={self.daily_pnl:.2f}")
            return True
        return False

    def check_max_trades(self):
        if self.trades_today >= config.MAX_TRADES_PER_DAY:
            logger.warning(f"⛔ Máx operaciones: {self.trades_today}")
            return True
        return False

    def validate_order(self, signal, current_price, position_qty=0.0):
        action = signal.get("action","hold")
        if action == "hold":       return False, "Hold, sin orden."
        if self.check_daily_loss():return False, "Límite pérdida diaria."
        if self.check_max_trades():return False, "Máx operaciones diarias."
        if action == "buy":
            qty = int(self.portfolio_value * config.MAX_POSITION_PCT / current_price) if current_price else 0
            if qty < 1: return False, "Capital insuficiente."
            return True, f"BUY aprobado: hasta {qty} acciones @ {current_price:.2f}"
        if action == "sell":
            if position_qty <= 0: return False, "Sin posición abierta."
            return True, f"SELL aprobado: {position_qty} acciones"
        return False, f"Acción desconocida: {action}"

    def calc_order_qty(self, current_price):
        if current_price <= 0: return 0
        return max(1, int(self.portfolio_value * config.MAX_POSITION_PCT / current_price))
''')

# ─────────────────────────────────────────────────────────────
# execution.py
# ─────────────────────────────────────────────────────────────
write("execution.py", '''\
import logging
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
import config

logger = logging.getLogger(__name__)

class Executor:
    def __init__(self, api_key=None, secret_key=None, paper=True):
        self.client = TradingClient(api_key or config.ALPACA_API_KEY,
                                    secret_key or config.ALPACA_SECRET_KEY, paper=paper)
        logger.info(f"Executor listo ({'PAPER' if paper else 'LIVE'}).")

    def get_account(self):
        try:
            a = self.client.get_account()
            return {"equity":float(a.equity),"buying_power":float(a.buying_power),
                    "cash":float(a.cash),"portfolio_value":float(a.portfolio_value)}
        except Exception as e:
            logger.error(f"get_account: {e}"); return {}

    def get_position(self, symbol):
        try:
            p = self.client.get_open_position(symbol)
            return {"qty":float(p.qty),"avg_entry_price":float(p.avg_entry_price),
                    "market_value":float(p.market_value),"unrealized_pl":float(p.unrealized_pl)}
        except Exception:
            return {}

    def get_positions(self):
        try:
            return [{"symbol":p.symbol,"qty":float(p.qty),"avg_entry_price":float(p.avg_entry_price),
                     "market_value":float(p.market_value)} for p in self.client.get_all_positions()]
        except Exception as e:
            logger.error(f"get_positions: {e}"); return []

    def submit_order(self, symbol, qty, side, order_type="market"):
        if qty <= 0: return None
        try:
            req   = MarketOrderRequest(symbol=symbol, qty=qty,
                        side=OrderSide.BUY if side.lower()=="buy" else OrderSide.SELL,
                        time_in_force=TimeInForce.DAY)
            order = self.client.submit_order(req)
            logger.info(f"Orden: {side.upper()} {qty} {symbol} | ID={order.id}")
            return str(order.id)
        except Exception as e:
            logger.error(f"submit_order: {e}"); return None

    def close_position(self, symbol):
        try:
            self.client.close_position(symbol)
            logger.info(f"Posición {symbol} cerrada."); return True
        except Exception as e:
            logger.error(f"close_position: {e}"); return False

    def cancel_all_orders(self):
        try:
            self.client.cancel_orders(); return True
        except Exception as e:
            logger.error(f"cancel_orders: {e}"); return False
''')

# ─────────────────────────────────────────────────────────────
# logger.py
# ─────────────────────────────────────────────────────────────
write("logger.py", '''\
import os, csv, logging, logging.handlers, requests
from datetime import datetime
import config

def setup_logging():
    os.makedirs(config.LOG_DIR, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))
    fmt  = logging.Formatter(config.LOG_FORMAT)
    ch   = logging.StreamHandler()
    ch.setFormatter(fmt)
    root.addHandler(ch)
    fh = logging.handlers.TimedRotatingFileHandler(
        os.path.join(config.LOG_DIR,"trading_bot.log"),
        when="midnight", backupCount=30, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    return root

def log_trade(action, symbol, price, qty, reason):
    os.makedirs(os.path.dirname(config.TRADES_LOG), exist_ok=True)
    exists = os.path.isfile(config.TRADES_LOG)
    row = {"timestamp":datetime.now(timezone.utc).isoformat(),"action":action,
           "symbol":symbol,"price":price,"qty":qty,
           "value":round(price*qty,2),"reason":reason}
    with open(config.TRADES_LOG,"a",newline="",encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=row.keys())
        if not exists: w.writeheader()
        w.writerow(row)
    logging.getLogger(__name__).info(f"TRADE | {action.upper()} {qty}x{symbol} @ {price:.2f}")

def send_alert(message):
    logging.getLogger(__name__).info(f"ALERTA: {message}")
    if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        try:
            requests.post(f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
                          json={"chat_id":config.TELEGRAM_CHAT_ID,"text":f"🤖 Bot\\n{message}"},
                          timeout=5)
        except Exception as e:
            logging.getLogger(__name__).error(f"Telegram: {e}")
''')

# ─────────────────────────────────────────────────────────────
# backtest.py
# ─────────────────────────────────────────────────────────────
write("backtest.py", '''\
import os, argparse, logging
from datetime import datetime, timezone, timedelta
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import config
from logger import setup_logging
from data_fetcher import DataFetcher
from indicators import add_all_indicators
from ml_model import TradingModel
from strategy import TradingStrategy

setup_logging()
logger = logging.getLogger(__name__)
COMMISSION = 0.001

def run_backtest(symbol, start, end, timeframe, capital, train_model):
    logger.info(f"Descargando datos {symbol}...")
    df_raw = DataFetcher().get_historical(symbol, start, end, timeframe)
    if df_raw.empty:
        logger.error("Sin datos. Abortando."); return {}
    df = add_all_indicators(df_raw.copy())

    model = TradingModel()
    if train_model or not os.path.exists(config.MODEL_PATH):
        logger.info("Entrenando modelo...")
        m = model.train(df)
        logger.info(f"Accuracy: {m.get(\'accuracy\',0):.4f}")
    else:
        model.load_model()

    strategy   = TradingStrategy(model=model)
    cash, shares, entry_px = capital, 0, 0.0
    equity_curve, trades_log = [], []
    min_w = config.MA_LONG_WINDOW + 10

    for i in range(min_w, len(df)):
        win   = df.iloc[:i]
        price = float(win["close"].iloc[-1])
        sig   = strategy.generate_signal(win)
        pv    = cash + shares * price
        equity_curve.append({"timestamp": win.index[-1], "equity": pv})

        if sig["action"] == "buy" and shares == 0:
            qty = int(pv * config.MAX_POSITION_PCT / price)
            if qty > 0:
                cash -= qty * price * (1 + COMMISSION)
                shares += qty; entry_px = price
                trades_log.append({"timestamp":win.index[-1],"action":"buy",
                    "price":price,"qty":qty,"equity":cash+shares*price,"reason":sig["reason"]})

        elif sig["action"] == "sell" and shares > 0:
            proceeds = shares * price * (1 - COMMISSION)
            pnl      = proceeds - shares * entry_px
            cash    += proceeds
            trades_log.append({"timestamp":win.index[-1],"action":"sell",
                "price":price,"qty":shares,"pnl":round(pnl,2),"equity":cash,"reason":sig["reason"]})
            shares = 0; entry_px = 0.0

    if shares > 0:
        price = float(df["close"].iloc[-1])
        cash += shares * price * (1 - COMMISSION)

    eq_df  = pd.DataFrame(equity_curve).set_index("timestamp")
    ret    = (cash - capital) / capital * 100
    roll   = eq_df["equity"].cummax()
    dd     = (eq_df["equity"] - roll) / roll * 100
    eq_df["r"] = eq_df["equity"].pct_change()
    py  = 252 if timeframe == "1Day" else 252*6
    sh  = (eq_df["r"].mean()/eq_df["r"].std())*(py**0.5) if eq_df["r"].std()>0 else 0
    sel = [t for t in trades_log if "sell" in t.get("action","")]
    win_r = len([t for t in sel if t.get("pnl",0)>0]) / len(sel) * 100 if sel else 0
    gp  = sum(t.get("pnl",0) for t in sel if t.get("pnl",0)>0)
    gl  = abs(sum(t.get("pnl",0) for t in sel if t.get("pnl",0)<0))
    pf  = gp/gl if gl>0 else float("inf")

    metrics = {"symbol":symbol,"return_%":round(ret,2),"max_dd_%":round(float(dd.min()),2),
               "sharpe":round(sh,3),"trades":len(sel),"win_rate_%":round(win_r,2),"profit_factor":round(pf,3)}
    for k,v in metrics.items(): logger.info(f"  {k}: {v}")

    os.makedirs("results", exist_ok=True)
    pd.DataFrame(trades_log).to_csv("results/backtest_trades.csv", index=False)
    eq_df.to_csv("results/backtest_equity.csv")

    fig,(ax1,ax2) = plt.subplots(2,1,figsize=(14,8),sharex=True)
    ax1.plot(eq_df.index, eq_df["equity"], color="royalblue", linewidth=1.5)
    ax1.axhline(capital, color="gray", linestyle="--", linewidth=0.8)
    ax1.set_title(f"Backtest {symbol} | Return: {ret:.2f}% | Sharpe: {sh:.2f}")
    ax1.set_ylabel("Equity ($)"); ax1.grid(alpha=0.3)
    ax2.fill_between(dd.index, dd, 0, color="tomato", alpha=0.5)
    ax2.set_ylabel("Drawdown (%)"); ax2.set_xlabel("Fecha"); ax2.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig("results/backtest_equity.png", dpi=150); plt.close()
    logger.info("Gráfico guardado en results/backtest_equity.png")
    return metrics

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--symbol",    default=config.SYMBOL)
    p.add_argument("--start",     default="2022-01-01")
    p.add_argument("--end",       default="2024-01-01")
    p.add_argument("--timeframe", default=config.TIMEFRAME)
    p.add_argument("--capital",   default=config.CAPITAL, type=float)
    p.add_argument("--train",     action="store_true")
    a = p.parse_args()
    run_backtest(a.symbol,
                 datetime.fromisoformat(a.start).replace(tzinfo=timezone.utc),
                 datetime.fromisoformat(a.end).replace(tzinfo=timezone.utc),
                 a.timeframe, a.capital, a.train)
''')

# ─────────────────────────────────────────────────────────────
# main.py
# ─────────────────────────────────────────────────────────────
write("main.py", '''\
import os, sys, time, argparse, logging
from datetime import datetime, timezone, timedelta
import config
from logger import setup_logging, log_trade, send_alert
from data_fetcher import DataFetcher
from indicators import add_all_indicators
from ml_model import TradingModel
from strategy import TradingStrategy
from risk_manager import RiskManager
from execution import Executor

setup_logging()
logger = logging.getLogger(__name__)

SLEEP_MAP    = {"1Min":60,"5Min":300,"15Min":900,"1Hour":3600,"4Hour":14400,"1Day":86400}
LOOKBACK_DAYS = {"1Min":3,"5Min":7,"15Min":14,"1Hour":60,"4Hour":160,"1Day":400}

def wait_next_bar(tf):
    s   = SLEEP_MAP.get(tf, 3600)
    now = datetime.now(timezone.utc)
    sl  = s - (now.timestamp() % s)
    logger.info(f"Esperando {sl:.0f}s hasta la próxima vela...")
    time.sleep(sl)

def run(train=False, once=False):
    logger.info("=" * 55)
    logger.info("  🤖  TRADING BOT INICIADO")
    logger.info(f"  {config.SYMBOL} | {config.TIMEFRAME}")
    logger.info("=" * 55)

    fetcher  = DataFetcher()
    model    = TradingModel()
    risk     = RiskManager()
    executor = Executor()

    if train or not os.path.exists(config.MODEL_PATH):
        logger.info("Entrenando modelo ML...")
        end_dt   = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=730)
        df_h     = fetcher.get_historical(config.SYMBOL, start_dt, end_dt, config.TIMEFRAME)
        if not df_h.empty:
            m = model.train(add_all_indicators(df_h))
            send_alert(f"Modelo entrenado. Accuracy={m.get(\'accuracy\',0):.4f}")
    else:
        model.load_model()

    strategy = TradingStrategy(model=model)
    acc      = executor.get_account()
    if acc:
        logger.info(f"Equity: ${acc.get(\'equity\',0):.2f} | BP: ${acc.get(\'buying_power\',0):.2f}")
        risk.update(acc.get("portfolio_value", config.CAPITAL), 0.0, 0)

    current_day, trades_today = datetime.now(timezone.utc).date(), 0
    day_start_equity = None
    send_alert(f"Bot iniciado | {config.SYMBOL} @ {config.TIMEFRAME}")

    try:
        while True:
            now = datetime.now(timezone.utc)
            if now.date() != current_day:
                current_day, trades_today = now.date(), 0
                day_start_equity = None
                risk.reset_daily()

            end_dt   = now
            start_dt = now - timedelta(days=LOOKBACK_DAYS.get(config.TIMEFRAME, 60))
            df_raw   = fetcher.get_historical(config.SYMBOL, start_dt, end_dt, config.TIMEFRAME)

            if df_raw.empty or len(df_raw) < config.MA_LONG_WINDOW:
                logger.warning("Datos insuficientes. Esperando...")
                if once: break
                wait_next_bar(config.TIMEFRAME); continue

            df     = add_all_indicators(df_raw.copy())
            signal = strategy.generate_signal(df)
            logger.info(f"Señal: {signal[\'action\'].upper()} | {signal[\'reason\']}")

            price    = fetcher.get_current_price(config.SYMBOL)
            position = executor.get_position(config.SYMBOL)
            pos_qty  = position.get("qty", 0.0)
            acc      = executor.get_account()
            if acc:
                if day_start_equity is None:
                    day_start_equity = acc.get("equity", config.CAPITAL)
                daily_pnl = acc.get("equity", day_start_equity) - day_start_equity
                risk.update(acc.get("portfolio_value", config.CAPITAL), daily_pnl, trades_today)

            ok, msg = risk.validate_order(signal, price, pos_qty)
            logger.info(f"Risk: {msg}")

            if ok:
                if signal["action"] == "buy":
                    qty = risk.calc_order_qty(price)
                    oid = executor.submit_order(config.SYMBOL, qty, "buy")
                    if oid:
                        trades_today += 1
                        log_trade("buy", config.SYMBOL, price, qty, signal["reason"])
                        send_alert(f"BUY {qty}x{config.SYMBOL} @ ${price:.2f}")
                elif signal["action"] == "sell" and pos_qty > 0:
                    oid = executor.submit_order(config.SYMBOL, int(pos_qty), "sell")
                    if oid:
                        trades_today += 1
                        log_trade("sell", config.SYMBOL, price, int(pos_qty), signal["reason"])
                        send_alert(f"SELL {int(pos_qty)}x{config.SYMBOL} @ ${price:.2f}")

            if once:
                logger.info("Modo --once completado.")
                break
            wait_next_bar(config.TIMEFRAME)

    except KeyboardInterrupt:
        logger.info("Bot detenido manualmente.")
        send_alert("⛔ Bot detenido.")
    except Exception as e:
        logger.error(f"Error fatal: {e}", exc_info=True)
        send_alert(f"❌ Error: {e}")
    finally:
        logger.info("Bot cerrado.")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--train", action="store_true")
    p.add_argument("--once",  action="store_true")
    a = p.parse_args()
    run(train=a.train, once=a.once)
''')

# ─────────────────────────────────────────────────────────────
# RESUMEN FINAL
# ─────────────────────────────────────────────────────────────
print("\n" + "="*55)
print("  ✅  PROYECTO CREADO CORRECTAMENTE")
print("="*55)
print("\n📋 Próximos pasos:\n")
print("  1️⃣   pip install -r requirements.txt")
print("  2️⃣   python backtest.py --train")
print("  3️⃣   python main.py")
print("\n¡Listo para operar en paper trading! 🚀\n")