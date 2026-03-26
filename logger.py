import os, csv, logging, logging.handlers, requests
from datetime import datetime
import config

def setup_logging():
    import sys
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
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
    row = {"timestamp":datetime.utcnow().isoformat(),"action":action,
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
                          json={"chat_id":config.TELEGRAM_CHAT_ID,"text":f"🤖 Bot\n{message}"},
                          timeout=5)
        except Exception as e:
            logging.getLogger(__name__).error(f"Telegram: {e}")
