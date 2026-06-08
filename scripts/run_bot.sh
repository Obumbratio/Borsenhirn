#!/usr/bin/env bash
# scripts/run_bot.sh
# Corre el bot Börsenhirn (loop continuo, PAPER) contra borsenhirn_dev.
# Se auto-gatea por horario de mercado: si está cerrado, duerme y reintenta.
# Loggea a consola + logs/bot_<timestamp>.log.
#
# Uso:
#   bash scripts/run_bot.sh                 # foreground (Ctrl-C para parar)
#   nohup bash scripts/run_bot.sh >/dev/null 2>&1 &   # background (queda corriendo)
#   pkill -f "python main.py"               # parar el bot en background
set -uo pipefail
cd "$(dirname "$0")/.."

[ -f .env ] || { echo "ERROR: falta .env (DB -> borsenhirn_dev + Alpaca paper)."; exit 2; }
mkdir -p logs
LOG="logs/bot_$(date +%Y%m%d_%H%M%S).log"

echo "================================================================"
echo "  Börsenhirn — bot (PAPER, loop) | log: $LOG"
echo "  Self-gates por horario de mercado. Alertas -> Discord."
echo "  Parar: Ctrl-C (foreground) o pkill -f 'python main.py'"
echo "================================================================"
exec venv/bin/python main.py 2>&1 | tee "$LOG"
