"""
Smoke test de los canales de alertas configurados en .env.

Verifica que:
    - DiscordChannel llega al servidor (si DISCORD_WEBHOOK_URL está seteado).
    - EmailChannel envía email (si SMTP_USER + SMTP_PASSWORD están seteados).
    - DashboardChannel escribe fila en alerts_log (si Postgres responde).

Uso:
    python scripts/test_alerts.py
    python scripts/test_alerts.py --only discord
    python scripts/test_alerts.py --only email
    python scripts/test_alerts.py --only dashboard

Requiere que la migración SQL ya esté aplicada para el test de dashboard:
    psql -U postgres -d borsenhirn -f borsenhirn/safety/migrations.sql
"""

from __future__ import annotations

import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import config  # noqa: E402
from borsenhirn.safety.alerts import (  # noqa: E402
    AlertLevel, DiscordChannel, EmailChannel, DashboardChannel, SmtpConfig,
)

# Separador visual
SEP = "=" * 60


def test_discord() -> bool:
    print(f"\n{SEP}\n[1/3] Discord\n{SEP}")
    if not config.DISCORD_WEBHOOK_URL:
        print("SKIP: DISCORD_WEBHOOK_URL no está en .env")
        return True  # no es falla
    dc = DiscordChannel(config.DISCORD_WEBHOOK_URL)
    ok = dc.send(
        AlertLevel.INFO,
        "Smoke test Börsenhirn",
        "Si ves este mensaje en Discord, el canal está OK.",
        meta={
            "ambiente": "paper",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "test": "discord_smoke",
        },
    )
    print(f"  resultado: {'OK' if ok else 'FAIL'}")
    if not ok:
        print("  → revisa: webhook válido? red?  discord.com alcanzable?")
    return ok


def test_email() -> bool:
    print(f"\n{SEP}\n[2/3] Email (SMTP)\n{SEP}")
    if not config.SMTP_USER or not config.SMTP_PASSWORD:
        print("SKIP: SMTP_USER/SMTP_PASSWORD no seteados en .env")
        return True
    if not config.ALERT_EMAIL_TO:
        print("SKIP: ALERT_EMAIL_TO vacío en .env")
        return True
    smtp = SmtpConfig(
        host=config.SMTP_HOST,
        port=config.SMTP_PORT,
        user=config.SMTP_USER,
        password=config.SMTP_PASSWORD,
        use_tls=config.SMTP_USE_TLS,
    )
    ec = EmailChannel(smtp, config.ALERT_EMAIL_TO)
    ok = ec.send(
        AlertLevel.INFO,
        "Smoke test Börsenhirn",
        "Si recibes este email, SMTP está OK.\nEste es un test automático.",
        meta={"test": "email_smoke",
              "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")},
    )
    print(f"  resultado: {'OK' if ok else 'FAIL'}")
    if not ok:
        print("  → revisa: App Password correcto (16 chars sin espacios)?")
        print("  → Gmail 2FA activado?")
        print("  → SMTP_HOST/SMTP_PORT correctos?")
    return ok


def test_dashboard() -> bool:
    print(f"\n{SEP}\n[3/3] Dashboard (Postgres alerts_log)\n{SEP}")
    try:
        import psycopg2
    except ImportError:
        print("SKIP: psycopg2 no instalado (pip install psycopg2-binary)")
        return True

    conn_kwargs = dict(
        host=config.DB_HOST, port=config.DB_PORT,
        dbname=config.DB_NAME, user=config.DB_USER,
        password=config.DB_PASSWORD,
    )
    try:
        conn = psycopg2.connect(**conn_kwargs)
    except Exception as exc:
        print(f"FAIL: no pude conectarme a Postgres: {exc}")
        print("  → revisa: DB corriendo? credentials en .env correctas?")
        return False

    try:
        # Verificar que la tabla exista
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.alerts_log')")
            exists = cur.fetchone()[0]
        if not exists:
            print("FAIL: tabla alerts_log no existe.")
            print("  → aplicá migrations.sql primero:")
            print("    psql -U postgres -d borsenhirn "
                  "-f borsenhirn/safety/migrations.sql")
            conn.close()
            return False

        # Ejecutar DashboardChannel
        from borsenhirn.safety.state_store_pg import make_dashboard_db_write
        writer = make_dashboard_db_write(lambda: conn)
        dc = DashboardChannel(writer)
        ok = dc.send(
            AlertLevel.INFO,
            "Smoke test Börsenhirn",
            "Escritura de prueba en alerts_log.",
            meta={"test": "dashboard_smoke"},
        )
        if not ok:
            print("FAIL: DashboardChannel.send devolvió False")
            conn.close()
            return False

        # Verificar que la fila se haya insertado
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, level, subject
                  FROM alerts_log
                 WHERE subject = %s
                 ORDER BY id DESC LIMIT 1
            """, ("Smoke test Börsenhirn",))
            row = cur.fetchone()
        if not row:
            print("FAIL: fila no apareció en alerts_log")
            conn.close()
            return False
        print(f"  resultado: OK (id={row[0]}, level={row[1]})")
        conn.close()
        return True
    except Exception as exc:
        print(f"FAIL: {exc}")
        conn.close()
        return False


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--only", choices=["discord", "email", "dashboard"],
                   help="correr solo un canal")
    args = p.parse_args()

    results = {}
    if args.only in (None, "discord"):
        results["discord"] = test_discord()
    if args.only in (None, "email"):
        results["email"] = test_email()
    if args.only in (None, "dashboard"):
        results["dashboard"] = test_dashboard()

    print(f"\n{SEP}")
    print("  RESUMEN")
    print(SEP)
    all_ok = True
    for channel, ok in results.items():
        status = "OK" if ok else "FAIL"
        print(f"  {channel:>12s}: {status}")
        all_ok = all_ok and ok
    print(SEP)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
