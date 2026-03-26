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
        logger.info(f"Accuracy: {m.get('accuracy',0):.4f}")
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
    p.add_argument("--end",       default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    p.add_argument("--timeframe", default=config.TIMEFRAME)
    p.add_argument("--capital",   default=config.CAPITAL, type=float)
    p.add_argument("--train",     action="store_true")
    a = p.parse_args()
    run_backtest(a.symbol,
                 datetime.fromisoformat(a.start).replace(tzinfo=timezone.utc),
                 datetime.fromisoformat(a.end).replace(tzinfo=timezone.utc),
                 a.timeframe, a.capital, a.train)
