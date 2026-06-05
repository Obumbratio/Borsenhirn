# Börsenhirn — Contexto para Claude

## Qué es
Plataforma de inteligencia financiera (6 módulos) en comercialización
SaaS — Modelo A (BYO Alpaca broker).

## Dónde voy ahora
Sprint B1 multi-tenancy Phase B, ~90% (Bloque 5 capa app hecho; siguiente:
5.6 tests integración RLS). Branch: feature/multi-tenancy-phase-b

## Stack
FastAPI + Python 3.13 · PostgreSQL 18 con RLS · Next.js 14 + TS + Tailwind
· Clerk (auth) · Stripe (billing) · Redis (Upstash)

## Repo
GitHub privado: Obumbratio/proyecto_trading (rama principal: main)

## Reglas de trabajo (IMPORTANTES)
- Generas scripts; yo los corro manual y pego el output.
- Commits automáticos OK en repos locales (sin pedir confirmación).
- SIEMPRE pedir confirmación antes de cualquier `git push` a GitHub.
- NUNCA tocar la DB de producción `borsenhirn` hasta el Bloque 8.
- Archivos largos (>600 líneas): editar de abajo hacia arriba; verificar
  con ast.parse y wc -l.
- WSL bash no corre `git checkout` sobre rutas Windows: usar PowerShell.

## Archivos de contexto
- docs/ESTADO.md   — estado vivo del sprint
- docs/PLAN.md     — misión SaaS + decisiones clave (D1..D8)
- docs/ERRORES.md  — bitácora de bugs resueltos
- docs/00_INDEX.md — índice del vault
- docs/COMANDOS.md — hoja de comandos manuales (git/db) para Uriel

## Secuencia SaaS (10 bloqueadores)
B2 Vault -> B3 Auth (Clerk) -> B4 Stripe -> B5 Audit log -> B6 Worker
isolation -> B7 Legal -> B8 Kill switch -> B9 Backups -> B10 Anomaly detection
