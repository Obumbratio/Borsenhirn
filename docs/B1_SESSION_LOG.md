# B1 Multi-tenancy Phase B — Session Log

**Sprint:** Fase B — Habilitar Row-Level Security en tablas legacy del bot
**Branch:** `feature/multi-tenancy-phase-b`
**Inicio:** _pendiente confirmación bloque -1_
**DB producción (NO TOCAR hasta bloque 8):** `borsenhirn`
**DB de trabajo:** `borsenhirn_dev` (copia de producción)

Cada entrada lleva: timestamp UTC, bloque, qué se hizo, resultado.
Este archivo es nuestro audit trail si algo falla.

---

## Entradas

### 2026-04-26 — Bloque -1: Setup previo

**Pendiente outputs del usuario.**

Lado-IA (completado por Claude):
- [ ] `docs/B1_SESSION_LOG.md` creado.
- [ ] `.gitignore` actualizado con `backups/`, `*.dump`, `*.sql.gz`, `.env.dev`, `.env.local`.
- [ ] Carpeta `backups/` creada con `.gitkeep`.
- [ ] `scripts/b1_env_check.ps1` generado (PowerShell para Windows/WSL).
- [ ] `scripts/b1_env_check.sh` generado (bash equivalente).

Lado-usuario (Uriel, en Windows/WSL):
- [ ] Correr `scripts/b1_env_check.ps1` (o `.sh`) y pegar output.
- [ ] Confirmar versión de Postgres + host:port + user para conexión.
- [ ] Confirmar que NO hay procesos del bot corriendo, o detenerlos.

---

<!-- Próximas entradas se agregan abajo -->

### 2026-04-26 — Bloque -1: Recovery from environment issues

**Problema detectado:** después del primer intento de Bloque -1 quedaron
3 issues bloqueantes:

1. **Lock fantasma `.git/index.lock`** que silenciosamente hacía fallar
   comandos como `git stash`, `git rm`, `git add`. Causa: comando git
   interrumpido (PyCharm o antivirus de Windows).
2. **Repo MUY desactualizado:** 42 modificados + 30+ untracked,
   incluyendo archivos críticos del proyecto (`borsenhirn/`, tests,
   docs nuevos del Sprint completo).
3. **Conexión Postgres por validar:** WSL2 sobre Windows con Postgres
   en Windows host. IP detectada `172.25.144.1` pero conexión no
   probada end-to-end con password real.

**Lado-IA (completado por Claude):**
- [x] `scripts/b1_unlock_git.sh` — desbloquea `.git/index.lock` con
      confirmación explícita y diagnóstico de procesos git activos.
- [x] `scripts/b1_clean_git.sh` — refuerza `.gitignore` (idempotente) +
      destrackea archivos basura + crea rama `backup-pre-b1-YYYYMMDD`.
- [x] `scripts/b1_test_postgres.sh` — prueba conexión a Postgres con
      fallback automático a IP de Windows host.
- [x] `docs/B1_RECOVERY.md` — orden exacto de ejecución (5 pasos).

**Lado-usuario (Uriel, en WSL):**
- [x] Cerrar PyCharm. (asumido — el lock no apareció)
- [x] `b1_unlock_git.sh` no fue necesario (clean_git no abortó por lock).
- [x] `bash scripts/b1_clean_git.sh` → **OK**. 7 líneas agregadas a
      .gitignore (idempotente). `.idea/` (6 archivos) y
      `.claude/settings.local.json` destrackeados. Rama
      `backup-pre-b1-20260426` creada.
- [x] `bash scripts/b1_test_postgres.sh` → **FAIL**.
      - localhost: Connection refused
      - 172.25.144.1: Timeout expired
- [ ] Si todo OK → "ok recovery, arranca bloque 0".

**Análisis del fallo Postgres:** Postgres en Windows escucha solo en
localhost por default. Hay que abrir TCP a la subnet WSL2 antes de
poder hacer dump/restore desde WSL.

### 2026-04-26 — Bloque -1: Postgres listen_addresses fix

**Lado-IA (completado por Claude):**
- [x] `scripts/b1_diagnose_postgres.ps1` — diagnóstico read-only (servicio,
      listen_addresses actual, pg_hba.conf reglas, firewall, IP host WSL).
- [x] `docs/B1_POSTGRES_FIX.md` — instrucciones manuales paso a paso
      (4 pasos) + Plan B (Postgres en WSL si Windows fix es muy doloroso).

**Lado-usuario (Uriel):**
- [ ] PowerShell admin → `b1_diagnose_postgres.ps1` → pegar output.
- [ ] Editar `postgresql.conf` → `listen_addresses = '*'`.
- [ ] Editar `pg_hba.conf` → agregar `host all all 172.16.0.0/12 scram-sha-256`.
- [ ] `Restart-Service postgresql-x64-18` (admin).
- [ ] (Si hace falta) Abrir firewall puerto 5432.
- [ ] Re-correr `b1_test_postgres.sh` → confirmar `HOST_BLOQUE_0=...`.

**Restricciones aplicadas en este lote:**
- Solo modificados/creados: `scripts/`, `docs/`, `.gitignore` (este
  último a través del propio script clean para que sea idempotente).
- NO se tocó código del proyecto (`borsenhirn/`, `main.py`, tests, etc.).
- NO se ejecutaron operaciones de red ni tocó Postgres real.
- NO se hicieron commits.


