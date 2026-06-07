# COMANDOS MANUALES — para Uriel (WSL2 / bash)
> Cowork prepara; Uriel ejecuta y pega el output.
> Regla de oro: Cowork no hace commits ni push automáticos.
> El repo `Obumbratio/proyecto_trading` YA existe y es privado:
> NO se corre `git init` ni `gh repo create`.

---

## Estado de partida (verificado por Cowork)
- `.env` y `.env.dev` están en `.gitignore` y NUNCA entraron al historial. ✔
- Solo `.env.example` está trackeado. ✔
- `*.dump` está ignorado → `borsenhirn_dev.dump` NO puede entrar a git. ✔
- requirements.txt / .in / -dev / pyproject.toml / .python-version trackeados. ✔
- Rama actual: `feature/multi-tenancy-phase-b` (con cambios sin commitear).
- `main` sigue a `origin/main`.

---

## FASE B — Blindar secretos (ya casi resuelto)
`.env` nunca se trackeó; el `git rm --cached` es solo por seguridad:

```bash
cd ~/ruta/al/proyecto_trading
git rm --cached .env 2>/dev/null || true
git rm --cached .env.dev 2>/dev/null || true
git status -s
```

---

## FASE C — Congelar el esquema y dumpear la DB
Decisión tomada: la Nitro se clona con DUMP COMPLETO, no se reconstruye desde
scripts. El dump captura el estado real (Alembic o SQL manual, da igual).

```bash
mkdir -p db

# 1) Esquema (estructura + RLS + índices) — ESTE va a git como referencia.
pg_dump --schema-only --no-owner --no-privileges borsenhirn_dev > db/schema.sql
wc -l db/schema.sql
grep -cE '^(INSERT|COPY)' db/schema.sql      # esperado: 0 (sin datos de filas)

# 2) Dump completo (schema + 128 filas) SIN los ciphertexts de user_credentials.
#    Formato custom (-Fc). ESTE NO va a git: se mueve a mano (scp/USB).
pg_dump borsenhirn_dev --exclude-table-data=user_credentials -Fc -f borsenhirn_dev.dump
ls -lh borsenhirn_dev.dump
```
Recordatorio: `borsenhirn_dev.dump` NO entra a git (ya está cubierto por
`*.dump` en .gitignore). Lo mueves aparte a la Nitro por scp o USB.
Pega el output de `schema.sql` a Cowork para confirmar que no hay datos sensibles.

---

## FASE D — Escanear y subir (repo YA existe)

### 1) Escaneo de secretos (historial completo)
```bash
gitleaks detect --source . -v --config .gitleaks.toml
```
- `no leaks found` → seguimos.
- Si reporta algo → NO subas. Pásale la línea a Cowork, sacamos la llave a
  `.env`, y ROTAS la llave expuesta.

### 2) Revisar qué vas a subir
```bash
git add -A
git status
git diff --cached --stat
```
NO debe aparecer `.env`, `.env.dev` ni `borsenhirn_dev.dump`.

### 3) Commit + push (en la rama actual — SIN git init, SIN gh repo create)
```bash
git commit -m "chore: sistema de contexto + sync (CLAUDE.md, docs, scripts, gitleaks)"
git push -u origin feature/multi-tenancy-phase-b
```

### 4) (Opcional) Llevarlo a main para que la Nitro clone limpio
```bash
git checkout main
git merge feature/multi-tenancy-phase-b
git push origin main
git checkout feature/multi-tenancy-phase-b
# o crea un Pull Request en github.com (recomendado)
```

---

## FASE E — Hook y alias (instalar una vez por máquina)
```bash
cp scripts/git-hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
chmod +x scripts/*.sh
```
Alias `listo` al final de `~/.bashrc`:
```bash
listo() {
  git pull --rebase && git add -A && \
  git commit -m "${1:-wip: avance}" && git push && \
  echo "✓ Guardado y sincronizado"
}
```
```bash
source ~/.bashrc
```

---

## FASE NITRO — reconstruir DB + entorno en la segunda laptop
El código viaja por git; la DB, el rol de Postgres, el DB_HOST y el entorno
Python NO. Esto los reconstruye. Plantilla del `.env.dev`: ver
`docs/ENV_DEV_NITRO.md`.

### N1 — Prerrequisitos (red WSL2 ↔ Postgres del host)
```bash
# PostgreSQL 18 corriendo en el host Windows de la Nitro.
#  - pg_hba.conf permite la subnet WSL2 de ESTA laptop
#  - firewall de Windows abre el puerto 5432
psql -h <host> -U postgres -c "select version();"   # confirmar conexión
```

### N2 — Clonar el repo (URL correcta = proyecto_trading)
```bash
git clone git@github.com:Obumbratio/proyecto_trading.git
cd proyecto_trading
git checkout feature/multi-tenancy-phase-b
chmod +x scripts/*.sh
```

### N3 — Recrear el rol borsenhirn_app ANTES de restaurar
El rol es objeto de cluster; no viaja en el dump. Recréalo con tu script del
Bloque 5.2, con la MISMA password que ya usas (no cambies nada).
```bash
bash scripts/b1_block5_create_role.sh
# verifica: NOSUPERUSER, NOBYPASSRLS, sin INSERT en tenants
```
Orden importa: el dump trae GRANTs hacia borsenhirn_app; si el rol no existe,
el restore tira errores en esas líneas.

### N4 — Crear la DB y restaurar las 128 filas
```bash
createdb borsenhirn_dev
pg_restore --no-owner -d borsenhirn_dev borsenhirn_dev.dump
# user_credentials queda con estructura pero sin filas (a propósito)
```

### N5 — Recalcular DB_HOST (cambia en cada máquina)
```bash
ip route show default | awk '{print $3}'   # IP del host Windows desde WSL2
# (en WSL2 modo mirrored puede ser simplemente localhost)
```
Mete esa IP en `.env.dev` (usa la plantilla de docs/ENV_DEV_NITRO.md).

### N6 — Recrear el entorno Python (pip-tools, NO conda)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt    # para correr los tests
```

### N7 — Prueba de que todo quedó
```bash
python -c "import main"          # el bug 5.5.a NO debe reaparecer
pytest                            # objetivo: 267 passed, 55 skipped
RUN_DB_INTEGRATION=1 pytest -m integration   # cuando exista el 5.6
```

---

## FASE F — Verificación final
```bash
ls -la CLAUDE.md .gitignore .gitleaks.toml
ls -la docs/ESTADO.md docs/ERRORES.md docs/00_INDEX.md docs/COMANDOS.md docs/ENV_DEV_NITRO.md
ls -la scripts/start.sh scripts/save.sh scripts/git-hooks/pre-commit
ls -la db/schema.sql
# En github.com: repo Private · .env NO aparece · .env.example SÍ · db/schema.sql presente
```

Ritual diario: `./scripts/start.sh` al empezar · `./scripts/save.sh "mensaje"` al terminar.
Re-sincronizar datos luego: repetir `pg_dump … -Fc` en la fuente y `pg_restore`
en la otra. El código siempre por git; los datos por dump manual cuando haga falta.
