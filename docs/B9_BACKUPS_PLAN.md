# B9 — Backups · Plan (para revisar)

> Plan del bloqueador B9. Estado: [ESTADO.md](ESTADO.md).

## 1. Objetivo y alcance

**Objetivo:** backups **automatizables, verificados y con retención** de la DB,
un **runbook de restore**, y (opcional) **export por tenant** (portabilidad de
datos / offboarding / GDPR).

| | |
|---|---|
| **IN scope** | Script de backup reusable (rotación + retención + verificación), script/runbook de restore, agenda (cron), y opcionalmente `export_tenant`. |
| **OUT scope** | Infra de almacenamiento offsite (S3/GCS) y PITR/WAL (mención, no implementación). |

## 2. Estado actual

- Solo `scripts/b1_block8_backup.sh` (one-shot para la migración B8; sin rotación).
- `.gitignore` cubre `backups/`, `*.dump`, `*.sql.gz`.
- Sin export por tenant.
- Nota: la DB contiene credenciales **cifradas** (Fernet); un dump robado es
  inútil sin la master key (que vive en otro lado — B2). Igual: cuidar dónde
  queda el dump.

## 3. Diseño

- **`scripts/db_backup.sh`**: `pg_dump -F c` con timestamp, **verifica** el dump
  (`pg_restore --list`), aplica **retención** (mantiene N diarios + M semanales),
  y es apto para cron. Parametrizable por env (DB, ENV_FILE, RETENTION_DAILY...).
- **`scripts/db_restore.sh`**: restore a una DB nueva (nunca in-place), valida.
- **Runbook** `docs/B9_BACKUP_RUNBOOK.md`: agenda (cron diario), verificación
  periódica de restore, retención, y dónde guardar (offsite).
- **(Opcional) `export_tenant(tenant_id)`**: dump JSON de todas las filas del
  tenant (17 tablas A + audit + legal), vía admin/bypass. Endpoint
  `GET /me/export` (el tenant exporta lo suyo). Testeable.

## 4. Decisiones a confirmar

- **D1 (clave):** ¿incluimos el **export por tenant** (endpoint + función) además
  de los scripts de backup/restore, o solo los scripts/runbook?
- **D2 → default:** retención 7 diarios + 4 semanales (configurable por env).
- **D3 → default:** `pg_dump -F c` (no PITR/WAL en este sprint).

## 5. Secuencia

| Sub-bloque | Qué |
|---|---|
| B9.1 | `db_backup.sh` (rotación/retención/verificación) + `db_restore.sh` + runbook |
| B9.2 | (si D1) `export_tenant` + endpoint `/me/export` + tests |

## 6. Riesgos

| Riesgo | Mitigación |
|---|---|
| Backup corrupto/silencioso | verificación con `pg_restore --list` + alerta si falla |
| Restore destructivo | restore SIEMPRE a DB nueva, nunca in-place |
| Dump con secretos | credenciales cifradas (master key aparte); guardar offsite con cuidado |
| Disco lleno por dumps viejos | retención automática (borra fuera de la ventana) |
