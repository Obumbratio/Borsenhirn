"""
versions.py - Sistema de versiones y backups del proyecto.
No modifica ningún archivo, solo guarda y restaura.

Uso directo:
    python versions.py --save "descripción"
    python versions.py --list
    python versions.py --restore v1
    python versions.py --diff v1
"""

import os, json, shutil, hashlib, argparse
from datetime import datetime

BASE         = os.path.dirname(os.path.abspath(__file__))
VERSIONS_DIR = os.path.join(BASE, "versions")
VERSION_LOG  = os.path.join(VERSIONS_DIR, "version_log.json")

PROJECT_FILES = [
    "config.py", "data_fetcher.py", "indicators.py",
    "ml_model.py", "strategy.py", "risk_manager.py",
    "execution.py", "logger.py", "backtest.py",
    "main.py", "reporter.py", "auditor.py",
    "setup_proyecto.py", "fixes.py", "versions.py", "menu.py",
]


def load_log() -> list:
    if os.path.exists(VERSION_LOG):
        with open(VERSION_LOG, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_log(log: list):
    os.makedirs(VERSIONS_DIR, exist_ok=True)
    with open(VERSION_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def save_version(description: str = "") -> str:
    """Guarda snapshot completa del proyecto. Retorna el ID (ej: v3)."""
    os.makedirs(VERSIONS_DIR, exist_ok=True)
    log     = load_log()
    version = f"v{len(log) + 1}"
    ts      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    dest    = os.path.join(VERSIONS_DIR, version)
    os.makedirs(dest, exist_ok=True)

    saved, checksums = [], {}
    for fname in PROJECT_FILES:
        src = os.path.join(BASE, fname)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(dest, fname))
            with open(src, "rb") as f:
                checksums[fname] = hashlib.md5(f.read()).hexdigest()
            saved.append(fname)

    log.append({
        "version":     version,
        "timestamp":   ts,
        "description": description or "Sin descripcion",
        "files":       saved,
        "checksums":   checksums,
    })
    save_log(log)

    print(f"\n{'═'*50}")
    print(f"  💾  VERSION GUARDADA: {version}")
    print(f"  📅  {ts}")
    print(f"  📝  {description or 'Sin descripcion'}")
    print(f"  📁  {len(saved)} archivos guardados en versions/{version}/")
    print(f"{'═'*50}\n")
    return version


def list_versions():
    """Muestra todas las versiones guardadas."""
    log = load_log()
    if not log:
        print("\n  ⚠️  No hay versiones guardadas todavia.\n")
        return
    print(f"\n{'═'*55}")
    print(f"  📚  VERSIONES GUARDADAS ({len(log)} total)")
    print(f"{'═'*55}")
    for e in reversed(log):
        print(f"\n  🔖  {e['version']}  |  {e['timestamp']}")
        print(f"      📝  {e['description']}")
        print(f"      📁  {len(e['files'])} archivos")
    print(f"\n{'═'*55}\n")


def restore_version(version: str) -> bool:
    """Restaura una versión anterior. Guarda backup automático antes."""
    log      = load_log()
    versions = [e["version"] for e in log]

    if version not in versions:
        print(f"\n  ❌ Version '{version}' no encontrada.")
        print(f"     Disponibles: {', '.join(versions)}\n")
        return False

    src_dir = os.path.join(VERSIONS_DIR, version)
    if not os.path.exists(src_dir):
        print(f"\n  ❌ Carpeta no encontrada: {src_dir}\n")
        return False

    print(f"\n  💾 Guardando estado actual antes de restaurar...")
    backup_v = save_version(f"Auto-backup antes de restaurar {version}")

    entry    = next(e for e in log if e["version"] == version)
    restored = []
    for fname in entry["files"]:
        src = os.path.join(src_dir, fname)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(BASE, fname))
            restored.append(fname)

    print(f"\n{'═'*50}")
    print(f"  ✅  VERSION {version} RESTAURADA")
    print(f"  📅  Original: {entry['timestamp']}")
    print(f"  📝  {entry['description']}")
    print(f"  📁  {len(restored)} archivos restaurados")
    print(f"  💾  Backup actual guardado como: {backup_v}")
    print(f"{'═'*50}\n")
    return True


def diff_versions(version: str):
    """Muestra qué archivos cambiaron entre una versión y el estado actual."""
    log   = load_log()
    entry = next((e for e in log if e["version"] == version), None)
    if not entry:
        print(f"\n  ❌ Version '{version}' no encontrada.\n")
        return

    print(f"\n{'═'*55}")
    print(f"  🔍  DIFERENCIAS: {version} vs ACTUAL")
    print(f"  📅  Version guardada: {entry['timestamp']}")
    print(f"  📝  {entry['description']}")
    print(f"{'═'*55}\n")

    changed, unchanged, new_files = [], [], []
    for fname in PROJECT_FILES:
        fpath        = os.path.join(BASE, fname)
        old_checksum = entry["checksums"].get(fname)
        if not os.path.exists(fpath):
            continue
        with open(fpath, "rb") as f:
            cur = hashlib.md5(f.read()).hexdigest()
        if old_checksum is None:
            new_files.append(fname)
        elif old_checksum != cur:
            changed.append(fname)
        else:
            unchanged.append(fname)

    if changed:
        print(f"  ✏️   MODIFICADOS ({len(changed)}):")
        for f in changed:   print(f"       •  {f}")
    if new_files:
        print(f"\n  🆕  NUEVOS ({len(new_files)}):")
        for f in new_files: print(f"       +  {f}")
    if unchanged:
        print(f"\n  ✅  SIN CAMBIOS ({len(unchanged)}):")
        for f in unchanged: print(f"       =  {f}")
    print()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Sistema de versiones")
    p.add_argument("--save",    type=str, help="Guardar version con descripcion")
    p.add_argument("--list",    action="store_true", help="Ver versiones")
    p.add_argument("--restore", type=str, help="Restaurar version (ej: v1)")
    p.add_argument("--diff",    type=str, help="Ver cambios vs version (ej: v1)")
    a = p.parse_args()

    if a.list:             list_versions()
    elif a.restore:        restore_version(a.restore)
    elif a.diff:           diff_versions(a.diff)
    elif a.save is not None: save_version(a.save)
    else:
        print("\nUso:")
        print("  python versions.py --save 'descripcion'")
        print("  python versions.py --list")
        print("  python versions.py --restore v1")
        print("  python versions.py --diff v1\n")