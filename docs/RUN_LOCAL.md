# Correr Börsenhirn local (single-user, paper)

Stack local: **bot** (`main.py`) + **API** (`bot_api.py` :8000) + **dashboard**
(Streamlit :8501), contra **`borsenhirn_dev`** (no prod) y **Alpaca paper**.
El `.env` ya apunta ahí. Imposible tocar producción.

## Flujo diario (3 terminales WSL)

```bash
# 1) El BOT (loop, paper) — se auto-gatea por horario de mercado
bash scripts/run_bot.sh
#    (o en background, queda corriendo: nohup bash scripts/run_bot.sh >/dev/null 2>&1 & )

# 2) La API que alimenta el dashboard
venv/bin/python bot_api.py            # :8000

# 3) El dashboard
venv/bin/streamlit run dashboard.py --server.port 8501 --server.headless true
```
Abrir en el browser de Windows: **http://localhost:8501**

## Qué esperar

- **Horario:** el bot opera **9:30–16:00 ET** (mercado USA). Fuera de eso duerme
  y reintenta — podés dejarlo corriendo 24/7, solo tradea cuando abre.
- **Bars de 1 hora:** decide una vez por barra (`TIMEFRAME=1Hour`).
- **Alertas a Discord** en cada trade / arranque (webhook ya configurado).
- **Modelo:** reentrena solo cada 7 días; el resto de los días carga el `.pkl`.

## Parar / monitorear

```bash
pkill -f "python main.py"     # parar el bot
pkill -f "bot_api:app"        # parar la API
# dashboard: Ctrl-C en su terminal
tail -f logs/bot_*.log        # ver el bot en vivo
```

## Notas

- **Es PAPER:** dinero de práctica de Alpaca (~$109k). Cero riesgo.
- Para pasar a **plata real** algún día: cuenta Alpaca live + `LIVE_ALPACA_*` en
  `.env` + correr con `python main.py --live` (¡con cuidado!). No hace falta ahora.
- Reentrenar a mano: `python main.py --train --once`.
