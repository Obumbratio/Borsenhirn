"""Circuit Breaker para APIs externas."""
import time
import logging

log = logging.getLogger(__name__)

class CircuitBreaker:
    """Protege llamadas a APIs externas con patron circuit breaker."""

    CLOSED = "closed"      # Normal - calls pass through
    OPEN = "open"          # Blocked - too many failures
    HALF_OPEN = "half_open" # Testing - one call allowed

    def __init__(self, name: str, max_failures: int = 3, cooldown: int = 300):
        self.name = name
        self.max_failures = max_failures
        self.cooldown = cooldown  # seconds
        self.state = self.CLOSED
        self.failures = 0
        self.last_failure_time = 0
        self.total_trips = 0

    def can_call(self) -> bool:
        if self.state == self.CLOSED:
            return True
        if self.state == self.OPEN:
            if time.time() - self.last_failure_time >= self.cooldown:
                self.state = self.HALF_OPEN
                log.info(f"[CB:{self.name}] half-open — probando una llamada")
                return True
            return False
        # HALF_OPEN
        return True

    def record_success(self):
        if self.state == self.HALF_OPEN:
            log.info(f"[CB:{self.name}] recuperado — circuito cerrado")
        self.failures = 0
        self.state = self.CLOSED

    def record_failure(self):
        self.failures += 1
        self.last_failure_time = time.time()
        if self.state == self.HALF_OPEN:
            self.state = self.OPEN
            log.warning(f"[CB:{self.name}] fallo en half-open — circuito abierto ({self.cooldown}s)")
        elif self.failures >= self.max_failures:
            self.state = self.OPEN
            self.total_trips += 1
            log.warning(f"[CB:{self.name}] {self.failures} fallos — circuito ABIERTO (cooldown {self.cooldown}s)")

    def get_status(self) -> dict:
        return {
            "name": self.name,
            "state": self.state,
            "failures": self.failures,
            "total_trips": self.total_trips,
            "cooldown": self.cooldown,
        }


# Instancias globales para cada API
alpaca_cb = CircuitBreaker("Alpaca", max_failures=3, cooldown=300)
yfinance_cb = CircuitBreaker("yfinance", max_failures=3, cooldown=180)
finnhub_cb = CircuitBreaker("Finnhub", max_failures=3, cooldown=300)
alphavantage_cb = CircuitBreaker("AlphaVantage", max_failures=3, cooldown=300)
newsapi_cb = CircuitBreaker("NewsAPI", max_failures=3, cooldown=300)
fred_cb = CircuitBreaker("FRED", max_failures=3, cooldown=600)
polygon_cb = CircuitBreaker("Polygon", max_failures=3, cooldown=300)
claude_cb = CircuitBreaker("Claude", max_failures=3, cooldown=120)

def get_all_status() -> list:
    return [cb.get_status() for cb in [alpaca_cb, yfinance_cb, finnhub_cb, alphavantage_cb, newsapi_cb, fred_cb, polygon_cb, claude_cb]]
