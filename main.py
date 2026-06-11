"""
Entry point single-user del bot Börsenhirn.

La lógica del motor (setup + un ciclo) vive en `borsenhirn.engine.BotEngine`;
acá `run()` la corre en loop contra el DEFAULT tenant. El worker multi-tenant
reusa el mismo `BotEngine` por tenant (ver `borsenhirn.workers.bot_cycle`).
"""

import argparse
import logging

from logger import setup_logging, send_alert
from borsenhirn.engine import BotEngine, wait_next_bar
from borsenhirn.tenancy import DEFAULT_TENANT_UUID
import config

setup_logging()
logger = logging.getLogger(__name__)


def run(train=False, once=False, live=False):
    """
    Corre el bot single-user (DEFAULT tenant) en loop.

    `BotEngine.run_cycle()` hace un ciclo y devuelve un status; este loop decide
    la cadencia: duerme hasta la próxima barra, y respeta `--once` (un ciclo OK
    y termina; si está en HALT o mercado cerrado, sigue reintentando como antes).
    """
    try:
        eng = BotEngine(DEFAULT_TENANT_UUID, credentials=None, train=train, live=live)
    except ValueError as e:
        logger.error(f"{e} — abortando.")
        return

    try:
        while True:
            res = eng.run_cycle()
            if res.get("status") in ("halted", "market_closed"):
                wait_next_bar(config.TIMEFRAME)
                continue
            if once:
                logger.info("Modo --once completado.")
                break
            wait_next_bar(config.TIMEFRAME)
    except KeyboardInterrupt:
        logger.info("Bot detenido manualmente.")
        send_alert("Bot detenido.")
    except Exception as e:
        logger.error(f"Error fatal: {e}", exc_info=True)
        send_alert(f"Error: {e}")
    finally:
        logger.info("Bot cerrado.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--train", action="store_true")
    p.add_argument("--once",  action="store_true")
    p.add_argument("--live",  action="store_true", help="Operar con cuenta real (dinero real)")
    a = p.parse_args()
    run(train=a.train, once=a.once, live=a.live)
