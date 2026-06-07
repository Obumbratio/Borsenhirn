# Börsenhirn — Contexto para Claude

## Qué es
Plataforma de inteligencia financiera (6 módulos) en comercialización
SaaS — Modelo A (BYO Alpaca broker).

## Dónde voy ahora
Roadmap SaaS muy avanzado (backends en dev): B1✅ B2✅ B3✅ B4✅ B5✅ B6✅ B7✅,
B8 en progreso. Branch: feature/multi-tenancy-phase-b. Estado vivo: docs/ESTADO.md.
**Pendiente operativo clave:** aplicar B1 a prod ("B1 Bloque 8") en el host de prod
(scripts en scripts/b1_block8_*; prod NO está en localhost — ver docs/B1_BLOCK8_PLAN.md).

OJO con la numeración: "B1 Bloque 8" (sub-bloque interno de B1 = aplicar a prod)
NO es lo mismo que "Roadmap B8 = Kill switch". Son cosas distintas.

## Stack
FastAPI + Python 3.13 · PostgreSQL 18 con RLS · Next.js 14 + TS + Tailwind
· Clerk (auth) · Stripe (billing) · Redis (Upstash)

## Repo
GitHub privado: Obumbratio/proyecto_trading (rama principal: main)

## Reglas de trabajo (IMPORTANTES)
- Cosas de prod / DB en el host de prod: las corre Uriel y pega el output.
- Commits automáticos OK en repos locales (sin pedir confirmación).
- SIEMPRE pedir confirmación antes de cualquier `git push` a GitHub.
- Trabajo de dev contra `borsenhirn_dev`; prod `borsenhirn` solo en "B1 Bloque 8".
- Archivos largos (>600 líneas): editar de abajo hacia arriba; verificar
  con ast.parse y wc -l.
- WSL bash no corre `git checkout` sobre rutas Windows: usar PowerShell.

## Archivos de contexto
- docs/ESTADO.md   — estado vivo del sprint
- docs/PLAN.md     — misión SaaS + decisiones clave (D1..D8)
- docs/ERRORES.md  — bitácora de bugs resueltos
- docs/00_INDEX.md — índice del vault
- docs/COMANDOS.md — hoja de comandos manuales (git/db) para Uriel

## Secuencia SaaS (10 bloqueadores) — estado
- B1 Multi-tenancy (RLS) ✅ dev · falta aplicar a prod ("B1 Bloque 8")
- B2 Vault ✅ · B3 Auth Clerk ✅ · B4 Stripe ✅ · B5 Audit log ✅
- B6 Worker isolation ✅ · B7 Legal ✅
- B8 Kill switch 🟡 per-tenant hecho; falta global/admin
- B9 Backups ⏳ · B10 Anomaly detection ⏳
Cierres por bloque: docs/B{n}_CLOSEOUT.md. Pendientes a prod: migraciones
clerk_id/billing/audit/legal van con "B1 Bloque 8".
