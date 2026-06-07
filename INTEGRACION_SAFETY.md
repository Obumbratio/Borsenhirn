# Integración del módulo `borsenhirn/safety/` — pasos concretos

Ya tienes el código escrito y probado. Ahora hay que conectar tres cosas al bot:

1. Aplicar el schema SQL a tu Postgres.
2. Configurar `.env` con Discord webhook + SMTP.
3. Cablear `AlertManager`, `KillSwitch` y `SanityChecker` al loop principal (`main.py`).

---

## 1. Schema SQL

```bash
psql -h localhost -U postgres -d borsenhirn -f borsenhirn/safety/migrations.sql
```

Esto crea dos tablas:
- `killswitch_state` — estado persistente de kill switches.
- `alerts_log` — log de alertas para el dashboard Streamlit.

Verificar:

```sql
\dt killswitch_state
\dt alerts_log
```

---

## 2. Variables `.env`

Copia `.env.example` → `.env` si no lo tienes. Añade:

```env
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...     # NUEVO webhook rotado
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=tu_email@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx                            # app password de Gmail
SMTP_USE_TLS=true
ALERT_EMAIL_TO=tu_email@gmail.com
```

Para Gmail App Password:
1. Activar 2FA en tu cuenta.
2. https://myaccount.google.com/apppasswords → generar "Borsenhirn Bot".
3. Copiar los 16 caracteres sin espacios a `SMTP_PASSWORD`.

Verificar que funciona:

```python
# test_alerts.py (corrélo manualmente una vez)
from borsenhirn.safety.alerts import (
    DiscordChannel, EmailChannel, SmtpConfig, AlertLevel
)
import config

dc = DiscordChannel(config.DISCORD_WEBHOOK_URL)
print("Discord:", dc.send(AlertLevel.INFO, "Test desde Börsenhirn",
                          "Si ves este mensaje, Discord está OK."))

smtp = SmtpConfig(host=config.SMTP_HOST, port=config.SMTP_PORT,
                  user=config.SMTP_USER, password=config.SMTP_PASSWORD,
                  use_tls=config.SMTP_USE_TLS)
ec = EmailChannel(smtp, config.ALERT_EMAIL_TO)
print("Email:", ec.send(AlertLevel.INFO, "Test desde Börsenhirn",
                        "Si ves este email, SMTP está OK."))
```

---

## 3. Cablear al loop principal

Abrí `main.py`. Al inicio, junto a la construcción del bot:

```python
# Imports nuevos
from borsenhirn.safety import (
    AlertManager, DiscordChannel, EmailChannel, DashboardChannel, AlertLevel,
    KillSwitch, KillReason, SanityChecker,
)
from borsenhirn.safety.alerts import SmtpConfig, build_default_manager
from borsenhirn.safety.killswitch import (
    KillSwitchConfig, KillSnapshot, InMemoryStateStore,
)
from borsenhirn.safety.sanity import SanityConfig, OrderContext
from borsenhirn.safety.state_store_pg import (
    PostgresStateStore, make_dashboard_db_write,
)
from borsenhirn.safety.health import BotStateSnapshot, get_health_snapshot
from circuit_breaker import get_all_status as get_cb_status
import config

# ── Construcción del stack de safety ──────────────────────────
# Supongo que ya tenés una función get_conn() que devuelve conexión psycopg2.
# Si no, mirá borsenhirn/core/database.py o el módulo que uses.
from borsenhirn.core.database import get_conn    # ajustar al nombre real

alerts = build_default_manager(
    discord_webhook_url=config.DISCORD_WEBHOOK_URL,
    smtp=(SmtpConfig(config.SMTP_HOST, config.SMTP_PORT,
                     config.SMTP_USER, config.SMTP_PASSWORD,
                     config.SMTP_USE_TLS)
          if config.SMTP_USER else None),
    email_to=config.ALERT_EMAIL_TO or None,
    db_write_fn=make_dashboard_db_write(get_conn),
    dedupe_window_sec=config.ALERT_DEDUPE_WINDOW_SEC,
    min_level=AlertLevel.INFO,
)

ks_store = PostgresStateStore(get_conn)
killswitch = KillSwitch(
    store=ks_store,
    alert_send=lambda subject, body, **meta:
        alerts.critical(subject, body, **meta),
    config=KillSwitchConfig(
        max_daily_loss_pct=config.KS_MAX_DAILY_LOSS_PCT,
        max_drawdown_7d_pct=config.KS_MAX_DRAWDOWN_7D_PCT,
        max_consecutive_failures=config.KS_MAX_CONSECUTIVE_FAILURES,
    ),
)

sanity = SanityChecker(SanityConfig(
    max_position_pct=config.MAX_POSITION_PCT,
    max_qty_per_order=config.SANITY_MAX_QTY_PER_ORDER,
    min_price=config.SANITY_MIN_PRICE,
    max_price=config.SANITY_MAX_PRICE,
    wash_trade_min_gap_sec=config.SANITY_WASH_GAP_SEC,
    watchlist_required=True,
))

alerts.info("Bot arrancado", f"{len(config.WATCHLIST)} símbolos en watchlist",
            regime="?", equity=str(config.CAPITAL))
```

### En cada tick del loop principal

```python
while running:
    # 1. Refrescar estado
    portfolio_value = fetch_current_equity()       # tu función existente
    daily_pnl       = compute_daily_pnl()          # idem
    equity_hist_7d  = fetch_equity_last_n_days(7)  # idem
    failures        = count_recent_order_failures()

    # 2. Check kill switches
    snap = KillSnapshot(
        equity_now=portfolio_value,
        equity_day_start=get_equity_day_start(),
        daily_pnl=daily_pnl,
        equity_history_7d=equity_hist_7d,
        consecutive_order_failures=failures,
    )
    killswitch.check_all(snap)

    if killswitch.is_halted():
        # Modo seguro: sigue monitoreando pero no manda órdenes.
        time.sleep(60)
        continue

    # 3. Generar señal como antes
    signal = strategy.generate_signal(df, market_ctx)
    if signal["action"] == "hold":
        continue

    # 4. Construir contexto de la orden y validar con sanity
    qty = risk_manager.calc_order_qty(price)
    ctx = OrderContext(
        symbol=symbol, action=signal["action"], qty=qty, price=price,
        portfolio_value=portfolio_value,
        watchlist=config.WATCHLIST,
        current_positions=get_current_positions(),    # {symbol: qty}
        recent_trades=get_recent_trades(minutes=60),  # lista dicts
    )
    result = sanity.validate(ctx)
    if not result.ok:
        alerts.warn(
            f"Orden rechazada [{result.check}]",
            result.reason,
            symbol=symbol, action=signal["action"], qty=qty, price=price,
        )
        continue

    # 5. Enviar orden como antes
    try:
        execution.send_order(...)
        reset_consecutive_failures()
        alerts.info(f"Orden ejecutada: {signal['action'].upper()} {qty} {symbol}",
                    reason=signal["reason"])
    except Exception as exc:
        increment_consecutive_failures()
        alerts.warn(f"Orden falló: {symbol}", str(exc))
```

### Endpoint `/health` en FastAPI

En `borsenhirn/api/main.py`:

```python
from borsenhirn.safety.health import (
    register_fastapi_route, get_health_snapshot, BotStateSnapshot,
)
from borsenhirn.safety.state_store_pg import PostgresStateStore
from borsenhirn.core.database import get_conn
from circuit_breaker import get_all_status
import config

ks_store = PostgresStateStore(get_conn)

def _snapshot():
    bs = BotStateSnapshot(
        equity_now=fetch_current_equity(),
        equity_day_start=get_equity_day_start(),
        daily_pnl=compute_daily_pnl(),
        open_positions=len(get_current_positions()),
        regime=fetch_current_regime(),
        last_trade_at=fetch_last_trade_iso(),
        last_error=fetch_last_error(),
    )
    return get_health_snapshot(
        bot_state=bs,
        killswitch_active=ks_store.list_active(),
        circuit_breakers=get_all_status(),
        version="1.0.0",
    )

register_fastapi_route(app, _snapshot, path="/health")
```

Ahora `curl http://localhost:8000/health` devuelve JSON y puedes apuntar a él con **UptimeRobot** (gratis, alerta si el endpoint no responde 200 en N minutos).

### Dashboard: banner rojo de alertas

En `dashboard.py`, al inicio del layout:

```python
from borsenhirn.core.database import get_conn
import streamlit as st

def fetch_unacked_alerts():
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, level, subject, body, created_at
              FROM alerts_log
             WHERE acknowledged = false
               AND created_at > now() - interval '48 hours'
             ORDER BY created_at DESC
             LIMIT 10
        """)
        return cur.fetchall()

alerts = fetch_unacked_alerts()
if alerts:
    for aid, level, subject, body, ts in alerts:
        color = {"CRITICAL": "red", "WARN": "orange", "INFO": "blue"}[level]
        st.markdown(
            f"<div style='background:{color};color:white;padding:8px;"
            f"border-radius:6px;margin-bottom:6px'>"
            f"<b>[{level}] {subject}</b> <small>({ts})</small><br>{body}</div>",
            unsafe_allow_html=True,
        )
```

---

## 4. Kill switch manual (herramienta CLI)

Crear `scripts/ks_admin.py`:

```python
"""Control manual del kill switch desde línea de comandos."""
import argparse, sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from borsenhirn.safety.killswitch import KillReason
from borsenhirn.safety.state_store_pg import PostgresStateStore
from borsenhirn.core.database import get_conn

store = PostgresStateStore(get_conn)

p = argparse.ArgumentParser()
sub = p.add_subparsers(dest="cmd")

p_halt = sub.add_parser("halt")
p_halt.add_argument("--reason", default="manual halt via CLI")

p_clear = sub.add_parser("clear")
p_clear.add_argument("--key", choices=[k.value for k in KillReason])
p_clear.add_argument("--note", default="")

sub.add_parser("status")

args = p.parse_args()

if args.cmd == "halt":
    store.set(KillReason.MANUAL.value, True, args.reason, {})
    print(f"HALT activado: {args.reason}")
elif args.cmd == "clear":
    store.clear(args.key, args.note)
    print(f"Cleared: {args.key}")
elif args.cmd == "status":
    rows = store.list_active()
    if not rows:
        print("Sin kill switches activos. Bot OK.")
    else:
        for r in rows:
            print(f"  {r['key']:25s} | {r['triggered_at']} | {r['reason']}")
```

Uso:

```bash
python scripts/ks_admin.py status
python scripts/ks_admin.py halt --reason "vacaciones"
python scripts/ks_admin.py clear --key manual_halt --note "de vuelta"
```

---

## 5. Criterios de aceptación

Para dar por terminado el Gap 2:

- [ ] `psql -f migrations.sql` ejecutado y tablas creadas.
- [ ] Test manual: `python test_alerts.py` recibe mensaje en Discord y email.
- [ ] Bot arranca y alerta "Bot arrancado" en Discord + email.
- [ ] `python scripts/ks_admin.py halt --reason "test"` → próximo ciclo del bot NO manda órdenes y envía alerta CRITICAL.
- [ ] `python scripts/ks_admin.py clear --key manual_halt` → bot vuelve a operar.
- [ ] `curl http://localhost:8000/health` devuelve JSON con status coherente.
- [ ] Dashboard Streamlit muestra banner cuando hay alertas no ack-eadas.

Cuando todo eso ande: cierras Gap 2 y pasamos al siguiente (tests o legal, el que prefieras).
