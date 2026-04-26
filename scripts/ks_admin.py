"""
Control manual del kill switch desde línea de comandos.

Subcomandos:
    status              Lista los kill switches activos.
    halt --reason TEXT  Activa el manual halt — el bot se detiene en el
                        próximo ciclo y NO envía órdenes hasta que limpies.
    clear --key KEY     Limpia un kill switch específico.
    clear-all           Limpia TODOS los kill switches activos (cuidado).

Uso:
    python scripts/ks_admin.py status
    python scripts/ks_admin.py halt --reason "vacaciones / mantenimiento"
    python scripts/ks_admin.py clear --key manual_halt --note "de vuelta"
    python scripts/ks_admin.py clear-all --note "all clear"

Las claves válidas para --key son las que aparecen en `status`.
Las más comunes: max_daily_loss, max_drawdown_7d,
consecutive_failures, manual_halt.
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import config  # noqa: E402
from borsenhirn.safety.killswitch import KillReason  # noqa: E402
from borsenhirn.safety.state_store_pg import PostgresStateStore  # noqa: E402

SEP = "=" * 64


def get_conn():
    import psycopg2
    return psycopg2.connect(
        host=config.DB_HOST, port=config.DB_PORT,
        dbname=config.DB_NAME, user=config.DB_USER,
        password=config.DB_PASSWORD,
    )


def cmd_status(store: PostgresStateStore, _args) -> int:
    rows = store.list_active()
    print(f"\n{SEP}\n  KILL SWITCH STATUS\n{SEP}")
    if not rows:
        print("\n  ✓ Sin kill switches activos. Bot OK para operar.")
        print(f"\n{SEP}")
        return 0
    print(f"\n  {len(rows)} kill switch(es) activo(s):\n")
    for r in rows:
        triggered_at = r.get("triggered_at") or "?"
        print(f"  ⚠ {r['key']:25s}  triggered_at={triggered_at}")
        print(f"      reason: {r.get('reason') or '-'}")
        data = r.get("data") or {}
        if data:
            for k, v in list(data.items())[:5]:
                print(f"        {k}: {v}")
    print(f"\n{SEP}")
    print("  Para limpiar uno: python scripts/ks_admin.py clear --key <KEY>")
    print("  Para limpiar todos: python scripts/ks_admin.py clear-all")
    print(SEP)
    return 0


def cmd_halt(store: PostgresStateStore, args) -> int:
    reason = args.reason or "manual halt via CLI"
    store.set(KillReason.MANUAL.value, True, reason, {"source": "ks_admin"})
    print(f"\n  ⚠ MANUAL HALT activado: {reason}")
    print(f"  El bot dejará de enviar órdenes en el próximo ciclo.")
    print(f"  Para reactivar:")
    print(f"    python scripts/ks_admin.py clear --key manual_halt --note \"motivo\"")
    return 0


def cmd_clear(store: PostgresStateStore, args) -> int:
    if not args.key:
        print("ERROR: --key es requerido. Valores válidos:")
        for r in KillReason:
            print(f"  - {r.value}")
        return 2
    note = args.note or ""
    store.clear(args.key, note=note)
    print(f"  ✓ Cleared: {args.key} (note: {note or '-'})")
    return 0


def cmd_clear_all(store: PostgresStateStore, args) -> int:
    rows = store.list_active()
    if not rows:
        print("  Nada que limpiar — ya estaba todo OK.")
        return 0
    note = args.note or "bulk clear via ks_admin"
    for r in rows:
        store.clear(r["key"], note=note)
        print(f"  ✓ Cleared: {r['key']}")
    print(f"\n  {len(rows)} kill switch(es) limpiados.")
    return 0


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="lista kill switches activos")

    p_halt = sub.add_parser("halt", help="activa manual halt")
    p_halt.add_argument("--reason", default="manual halt via CLI")

    p_clear = sub.add_parser("clear", help="limpia un kill switch")
    p_clear.add_argument("--key", required=False,
                         choices=[k.value for k in KillReason],
                         help="qué key limpiar")
    p_clear.add_argument("--note", default="")

    p_all = sub.add_parser("clear-all", help="limpia TODOS los activos")
    p_all.add_argument("--note", default="bulk clear")

    return p.parse_args()


def main():
    args = parse_args()
    store = PostgresStateStore(get_conn)
    handlers = {
        "status": cmd_status,
        "halt": cmd_halt,
        "clear": cmd_clear,
        "clear-all": cmd_clear_all,
    }
    sys.exit(handlers[args.cmd](store, args))


if __name__ == "__main__":
    main()
