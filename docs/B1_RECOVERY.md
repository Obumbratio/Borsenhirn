# B1 Recovery — orden EXACTO de ejecución

Pasos para recuperar el entorno del Sprint B1 después de los problemas de
lock fantasma de git, repo desactualizado y conexión Postgres por validar.

**Tiempo estimado:** 5–10 minutos.
**Pre-requisito crítico:** **CERRÁ PYCHARM ANTES DE EMPEZAR.** PyCharm
mantiene file handles y locks transitorios sobre `.git/` que pueden
re-introducir el problema.

---

## Paso 1 — Cerrar PyCharm

Cerrá la ventana de PyCharm que tiene este repo abierto.
Verificá que no quedó proceso colgado:

```powershell
# desde PowerShell
Get-Process pycharm*, idea* -ErrorAction SilentlyContinue
```

Si aparece algún proceso, matalo desde Task Manager o:

```powershell
Stop-Process -Name "pycharm*" -Force -ErrorAction SilentlyContinue
```

---

## Paso 2 — Desbloquear git

Desde **WSL bash** en la raíz del repo:

```bash
bash scripts/b1_unlock_git.sh
```

El script:
1. Chequea procesos git activos (aborta si hay alguno).
2. Detecta `.git/index.lock`, muestra antigüedad.
3. **Pide confirmación explícita** — escribí `yes` para borrarlo.
4. Verifica que `git status` responde después.

**Pegame el output completo del script.**

Exit codes:
- `0` = OK, lock borrado o no había
- `1` = había procesos git activos, detenelos vos
- `2` = cancelaste el prompt (respondiste algo distinto a "yes")
- `3` = git sigue roto post-borrado

---

## Paso 3 — Limpiar git (refuerzo .gitignore + destrackeo)

Solo si el paso 2 salió `0`:

```bash
bash scripts/b1_clean_git.sh
```

El script:
1. Agrega líneas faltantes al `.gitignore` (idempotente — no duplica).
2. Destrackea `.idea/`, `.claude/settings.local.json`, `.coverage`,
   `pytest-cache-files-*/` con manejo de error verboso.
3. Crea rama `backup-pre-b1-YYYYMMDD` desde el estado actual (sin checkout).
4. Muestra `git status` final.

**No commitea nada.** Vos revisás el `git status` y commiteás manualmente.

**Pegame el output completo.**

---

## Paso 4 — Validar conexión a Postgres

```bash
bash scripts/b1_test_postgres.sh
```

El script:
1. Lee `DB_*` de `.env`.
2. Te pide la password (prompt silencioso).
3. Prueba conexión a `DB_HOST` con `PGCONNECT_TIMEOUT=5`.
4. Si `DB_HOST=localhost` y falla, prueba automáticamente con la IP
   del Windows host (típicamente `172.25.144.1` en WSL2).
5. Si tiene éxito imprime el host que funcionó como `HOST_BLOQUE_0=...`.
6. Si fallan todos, muestra diagnóstico paso a paso (servicio, listen_addresses,
   pg_hba, firewall).

**Pegame el output completo.**

---

## Paso 5 — Si todo OK → Bloque 0

Cuando el paso 4 termine con `0` y un `HOST_BLOQUE_0=...` claro,
estamos listos para arrancar el **Bloque 0** del sprint:
- Crear rama `feature/multi-tenancy-phase-b`
- Hacer dump completo de producción a `backups/pre_b1_YYYYMMDD_HHMM.dump`
- Crear `borsenhirn_dev` y restaurar el dump ahí
- Generar `.env.dev` apuntando a la copia
- Comparar row-counts

Avisame con "ok recovery, arranca bloque 0" y te paso los comandos.

---

## Si algo falla

| Síntoma | Causa probable | Fix |
|---|---|---|
| `b1_unlock_git.sh` exit 1 | Hay proceso git real | Cerrá PyCharm + terminales con git activo |
| `b1_unlock_git.sh` exit 3 | Git roto por otro motivo | Pegame el output, diagnosticamos |
| `b1_clean_git.sh` exit 2 | `.git/index.lock` reapareció | Re-correr paso 2 |
| `b1_clean_git.sh` mensajes "FAIL" en destrack | Permisos / archivo no trackeado | Esperado en algunos casos, no es crítico |
| `b1_test_postgres.sh` exit 2 | Postgres no responde | Seguir el diagnóstico que imprime el script |
| Password rechazada | Password de `.env` incorrecta | Confirmá con `psql -U postgres` desde PowerShell |
