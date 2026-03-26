"""
menu.py - Panel de control principal del proyecto.
Uso: python menu.py
"""

import os, subprocess, sys, json
from dotenv import dotenv_values
from my_plan import load_plan

BASE = os.path.dirname(os.path.abspath(__file__))


def run(cmd: str):
    subprocess.run([sys.executable] + cmd.split(), cwd=BASE)


def confirm(question: str) -> bool:
    while True:
        r = input(f"\n  {question} (s/n): ").strip().lower()
        if r in ("s","si","sí","y","yes"): return True
        if r in ("n","no"):                return False
        print("  Escribe 's' o 'n'.")


def header(title: str):
    print(f"\n{'═'*55}")
    print(f"  {title}")
    print(f"{'═'*55}")


def get_versions_log() -> list:
    log_path = os.path.join(BASE, "versions", "version_log.json")
    if os.path.exists(log_path):
        with open(log_path, encoding="utf-8") as f:
            return json.load(f)
    return []


def menu_principal():
    while True:
        plan = load_plan()
        plan_tag = ""
        if plan and plan.get("activo"):
            plan_tag = f"  [MI PLAN ACTIVO: {plan.get('symbol')} | {plan.get('capital_pct',0.3)*100:.0f}% capital]"

        header("🤖  PANEL DE CONTROL — TRADING BOT")
        print("  ── BOT ──────────────────────────────────────")
        print("  1.  Arrancar el bot (paper trading)")
        print("  2.  Arrancar el bot (cuenta REAL ⚠️ )")
        print("  3.  Ejecutar backtest")
        print("  4.  Re-entrenar modelo ML")
        print("")
        print("  ── MI PLAN DE TRADING ───────────────────────")
        if plan_tag:
            print(f" {plan_tag}")
        print("  14. Crear / cambiar mi plan con IA")
        print("  15. Ver mi plan activo")
        print("  16. Desactivar mi plan")
        print("")
        print("  ── INFORMES ─────────────────────────────────")
        print("  5.  Reporte diario PDF")
        print("  6.  Chat con asesor IA")
        print("  7.  Gestionar planes y misión")
        print("")
        print("  ── CÓDIGO ───────────────────────────────────")
        print("  8.  Auditar el proyecto")
        print("  9.  Aplicar fixes con IA")
        print("")
        print("  ── VERSIONES ────────────────────────────────")
        print("  10. Guardar versión actual (backup)")
        print("  11. Ver versiones guardadas")
        print("  12. Restaurar versión anterior")
        print("  13. Ver qué cambió vs versión anterior")
        print("")
        print("  0.  Salir")
        print(f"{'═'*55}")

        opt = input("\n  Elige una opción: ").strip()

        # ── BOT ──────────────────────────────────────────────
        if opt == "1":
            header("🟢  ARRANCAR BOT — PAPER TRADING")
            print("  Simulado. Sin dinero real.")
            print("  Para detenerlo presiona Ctrl+C")
            if confirm("¿Arrancar el bot ahora?"):
                run("main.py")

        elif opt == "2":
            header("🔴  ARRANCAR BOT — CUENTA REAL ⚠️")
            env = dotenv_values(os.path.join(BASE, ".env"))
            live_key = env.get("LIVE_ALPACA_API_KEY", "")
            if not live_key or live_key == "YOUR_LIVE_API_KEY_HERE":
                print("\n  ❌ No tienes las API keys de la cuenta real configuradas.")
                print("  Pasos:")
                print("  1. Ve a alpaca.markets → Live Trading → API Keys")
                print("  2. Genera tus keys para la cuenta #192324566")
                print("  3. Agrégalas en el archivo .env:")
                print("     LIVE_ALPACA_API_KEY=tu_key_aqui")
                print("     LIVE_ALPACA_SECRET_KEY=tu_secret_aqui")
            else:
                print(f"\n  Cuenta: Individual Brokerage #192324566")
                print(f"  API Key: {live_key[:8]}{'*' * (len(live_key)-8)}")
                print("\n  ⚠️  ADVERTENCIA IMPORTANTE:")
                print("  El bot comprará y venderá SPY con DINERO REAL.")
                print("  Puede perder dinero. Asegúrate de entender la estrategia.")
                print("  Para detenerlo: Ctrl+C")
                if confirm("¿Primera confirmación — operar con dinero REAL?"):
                    if confirm("¿Segunda confirmación — estás SEGURO?"):
                        run("main.py --live")

        elif opt == "3":
            header("📊  BACKTEST")
            sym   = input("  Símbolo (Enter = SPY): ").strip() or "SPY"
            start = input("  Fecha inicio (Enter = 2022-01-01): ").strip() or "2022-01-01"
            end   = input("  Fecha fin    (Enter para hoy): ").strip() or ""
            train = confirm("¿Re-entrenar el modelo ML también?")
            cmd   = f"backtest.py --symbol {sym} --start {start}"
            if end:
                cmd += f" --end {end}"
            if train:
                cmd += " --train"
            run(cmd)

        elif opt == "4":
            header("🧠  RE-ENTRENAR MODELO ML")
            if confirm("¿Re-entrenar ahora?"):
                run("main.py --train --once")

        # ── INFORMES ─────────────────────────────────────────
        elif opt == "5":
            header("📄  REPORTE DIARIO")
            run("reporter.py --daily")

        elif opt == "6":
            header("🧠  ASESOR IA")
            run("reporter.py --advisor")

        elif opt == "7":
            header("📋  GESTIONAR PLANES")
            run("reporter.py --planes")

        # ── CÓDIGO ───────────────────────────────────────────
        elif opt == "8":
            header("🔍  AUDITORÍA DEL PROYECTO")
            run("auditor.py")

        elif opt == "9":
            header("🔧  APLICAR FIXES CON IA")
            print("  ⚠️  Asegúrate de tener un backup guardado (opción 10)")
            log = get_versions_log()
            if not log:
                print("\n  ❌ No tienes backups guardados todavía.")
                if confirm("¿Guardar backup AHORA antes de continuar?"):
                    desc = input("  Descripción: ").strip() or "Backup antes de fixes"
                    subprocess.run(
                        [sys.executable, "versions.py", "--save", desc],
                        cwd=BASE
                    )
                else:
                    print("  Cancelado. Guarda un backup primero.\n")
                    input("\n  Presiona Enter para continuar...")
                    continue
            else:
                ultimo = log[-1]
                print(f"\n  Último backup: {ultimo['version']} — {ultimo['timestamp']}")
                print(f"  Descripción:   {ultimo['description']}")
                if not confirm("¿Tienes backup reciente y quieres continuar?"):
                    print("  Cancelado.\n")
                    input("\n  Presiona Enter para continuar...")
                    continue
            run("fixes.py --auto")

        # ── VERSIONES ────────────────────────────────────────
        elif opt == "10":
            header("💾  GUARDAR VERSIÓN")
            desc = input("  Descripción (ej: 'antes de cambiar strategy'): ").strip()
            if desc:
                if confirm(f"¿Guardar versión: '{desc}'?"):
                    subprocess.run(
                        [sys.executable, "versions.py", "--save", desc],
                        cwd=BASE
                    )
            else:
                print("  Cancelado — escribe una descripción.\n")

        elif opt == "11":
            header("📚  VERSIONES GUARDADAS")
            run("versions.py --list")

        elif opt == "12":
            header("⏪  RESTAURAR VERSIÓN")
            run("versions.py --list")
            version = input("  ¿Qué versión restaurar? (ej: v1): ").strip()
            if version:
                print(f"\n  ⚠️  Esto reemplazará tu código con {version}.")
                print(f"  (Se guardará backup automático antes)")
                if confirm(f"¿Confirmas restaurar {version}?"):
                    subprocess.run(
                        [sys.executable, "versions.py", "--restore", version],
                        cwd=BASE
                    )
            else:
                print("  Cancelado.\n")

        elif opt == "13":
            header("🔍  VER CAMBIOS")
            run("versions.py --list")
            version = input("  ¿Comparar con qué versión? (ej: v1): ").strip()
            if version:
                subprocess.run(
                    [sys.executable, "versions.py", "--diff", version],
                    cwd=BASE
                )

        # ── MI PLAN ──────────────────────────────────────────
        elif opt == "14":
            header("MI PLAN DE TRADING — Crear con IA")
            print("  Describe tu idea y la IA la convierte en reglas ejecutables.")
            print("  El bot operara tu plan + la estrategia segura SPY en paralelo.")
            run("my_plan.py")

        elif opt == "15":
            header("MI PLAN ACTIVO")
            run("my_plan.py --status")

        elif opt == "16":
            header("DESACTIVAR MI PLAN")
            plan = load_plan()
            if not plan or not plan.get("activo"):
                print("\n  No hay ningun plan activo.")
            else:
                print(f"\n  Plan activo: {plan.get('symbol')} — {plan.get('idea_refinada','')[:60]}")
                if confirm("¿Desactivar y borrar el plan?"):
                    run("my_plan.py --clear")

        elif opt == "0":
            print("\n  Hasta luego.\n")
            break

        else:
            print("\n  Opción no válida.\n")

        input("\n  Presiona Enter para continuar...")


if __name__ == "__main__":
    menu_principal()