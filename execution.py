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
                     "market_value":float(p.market_value),
                     "unrealized_pl":float(p.unrealized_pl)} for p in self.client.get_all_positions()]
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
