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
