# ESTADO — Börsenhirn
> Actualizar al cerrar sesión. Pegar al abrir un chat nuevo.
> Misión y decisiones de fondo: ver [PLAN.md](PLAN.md). Log por bloque: [B1_SESSION_LOG.md](B1_SESSION_LOG.md).

## Última actualización
2026-06-21

## ✅ PROD LOCAL-FIRST DESPLEGADA (2026-06-11) — DB `borsenhirn` viva y limpia
**Decisión:** local-first (en la máquina de Uriel, no nube — no rompe el principio, $0).
**Hecho (camino A, "DB nueva en el cluster local"):**
- DB `borsenhirn` creada en el Postgres local; **esquema clonado de `borsenhirn_dev`**
  (`pg_dump --schema-only`) → 21 tablas, 19 con RLS, idéntico a dev. Trae ya todo el
  multi-tenant final (RLS + clerk_id + billing + audit_log + legal_acceptance), así que
  **B1 Bloque 8 NO se necesitó** (sus scripts transformaban un prod single-user viejo
  inexistente; un prod nuevo se clona, no se transforma).
- Sembradas las 2 filas de sistema (`tenants`: SYSTEM …000 + default …001). **Sin datos
  de dev** (0 trades).
- Rol `borsenhirn_app` (ya existía en el cluster) con grants + CONNECT en `borsenhirn`.
  Smoke como rol app: NOSUPERUSER+NOBYPASSRLS, sin contexto→0 filas, RLS real ✓.
- `.env.prod` (gitignored, DB_NAME=borsenhirn) + `scripts/run_bot_prod.sh` (sourcea
  .env.prod; `config.load_dotenv()` no pisa env exportadas → prod gana sobre dev).
  Smoke del stack app contra prod: BotMemory OK (0 trades), Alpaca paper OK.

**Cómo correr el bot contra prod:** `bash scripts/run_bot_prod.sh`. Sin eso, el default
sigue siendo dev (`.env`). Plan/decisión: [DESPLIEGUE_PROD_PLAN.md](DESPLIEGUE_PROD_PLAN.md).

**Nota local-first:** prod y dev comparten cluster Postgres y el rol `borsenhirn_app`
(misma password) — la separación es a nivel DB + RLS, no de credenciales. OK para
local-first single-machine; si algún día prod sale a la nube, ahí sí rol/credenciales aparte.
**Pendiente menor:** el timer de anomalías y los systemd units apuntan a dev (`.env`);
para que monitoreen prod hay que sourcear `.env.prod` (ver run_bot_prod.sh como patrón).
Plan completo (por qué migrar + opciones L/C + secuencia): [DESPLIEGUE_PROD_PLAN.md](DESPLIEGUE_PROD_PLAN.md).
(Nota menor: ese `docker-compose.yml` tiene la password `uriel` hardcodeada y commiteada
— local/bajo riesgo, pero no reusarla si algún día prod sale de tu máquina.)

## 🧠 Re-secuenciación "un cerebro, dos caras" — Paso 1 HECHO (2026-06-12)
Pivot de producto: el auto-trader NO se mata, se SEPARA del producto de cliente (ver
[PRODUCTO_PLAN.md](PRODUCTO_PLAN.md) + [RESECUENCIACION_PLAN.md](RESECUENCIACION_PLAN.md)).
**Paso 1 (desacople behavior-preserving):** `engine.py::run_cycle` se partió en:
- `borsenhirn/signals/SignalEngine.analyze()` (cerebro compartido, read-only: régimen +
  contexto + scanner; cero `submit_order`, cero outcomes).
- `engine.py::AutoExecutor.execute()` (cara interna auto-trade: sells/TP/SL/buys/plan +
  bookkeeping, VERBATIM de hoy; las salidas y `update_highest_price` quedan acá por orden).
- `BotEngine` = orquestador (lifecycle → analyze → execute).
Verificado: 404 tests verdes + smoke real paper. **Paso 1.5 HECHO (2026-06-12):**
`AutoExecutor` + `CycleCtx` movidos a `borsenhirn/internal/autotrader/` (paquete marcado
NO-producto). Guardrail `tests/test_red_line_guardrail.py`: subproceso importa
`borsenhirn.api.main` y FALLA si carga `internal.autotrader`/`engine`/`workers.bot_cycle`
(directo o transitivo). Probado en VERDE y forzado a ROJO (import temporal en api/main.py
→ test falló → revertido). **405 tests verdes.**
**Paso 2 HECHO (Opción C — sin store, 2026-06-12):** señal del cliente = cerebro
compartido (modelo global `.pkl` + scanner con `memory=None` → score neutral 0.5 →
impersonal por construcción). `borsenhirn/signals/client_feed.py` (`get_client_signals()`,
caché TTL 1h) + endpoint `GET /signals` en `api/main.py` que NACE CERRADO con
`get_active_tenant` (Clerk + suscripción activa). Verificación dev SIN código de bypass:
se usa `AUTH_VERIFIER=static` + `AUTH_DEV_SECRET` (token de test) — en prod `AUTH_VERIFIER=clerk`
y esos tokens no validan. Probado vivo: sin token→401; 2 usuarios distintos→respuesta
byte-idéntica (impersonal). 406 tests verdes (+ test_client_feed). Decisión Opción C: el
único insumo aprendido de la señal era `symbol_score` (de UNA cuenta) → fuera del cliente,
queda solo en el auto-trader interno. B (tabla global) es upgrade futuro si hace falta.
**Paso 3 en sub-pasos (checkpoint en cada uno; frontend va en pasada aparte post-Clerk):**
- **3a HECHO (2026-06-12):** backend conectar Alpaca BYO. `POST/GET/DELETE /me/broker`
  en `api/main.py` — valida keys contra Alpaca (paper) y las guarda CIFRADAS en el vault
  (B2, scoped por tenant/RLS); GET devuelve key enmascarada (sin secreto). Nace cerrado
  (`get_current_tenant`). Smoke vivo OK (sin token→401, inválidas→400, válidas→connected+equity,
  delete→desconectado). Pendiente: form frontend (post-Clerk).
- **3b HECHO (2026-06-12):** tarjeta de análisis honesta+impersonal. `borsenhirn/signals/cards.py::build_card`
  arma tesis + niveles + qué invalida + `factores` (con PROCEDENCIA de cada dato) a partir de los
  campos REALES de la señal (rsi/ma_trend/ml_prob/confidence/reason de strategy + régimen + stop).
  Determinista (no LLM → no AI-washing); `client_feed` ahora devuelve tarjetas en `/signals`.
  Verificado: guardrail verde, tarjeta real de ejemplo (AAPL, cada factor con fuente), 2 usuarios→
  byte-idéntico. 410 tests (+ test_cards). Decisión: NO usar `m1_research` (LLM) para inventar prosa;
  si se quiere narrador LLM, sería capa aparte CONSTREÑIDA a estos factores (riesgo a evaluar).
- **3c HECHO (2026-06-12):** calculadora de posición, **lógica TS pura sin backend**
  (`frontend/src/lib/position-calculator.ts`). El user mete capital + %riesgo sobre los
  niveles del análisis → qty/costo/escenarios/RR; el tamaño sale de SU regla, no de una
  opinión. Tests vitest (`npm test`): **8 verdes** incl. bordes — stop>=entrada (riesgo/acción
  ≤0, sin div por cero ni negativos), capital insuficiente→0 acciones (no fracciones),
  redondeo (acciones enteras, dinero 2 decimales). Frontend UI: pasada post-Clerk.
- **3d HECHO (2026-06-13):** ejecución MANUAL. `POST /me/orders` (gating `get_compliant_tenant`:
  activa+legal): UNA orden por request, creds del PROPIO user (vault), paper-first (live→403),
  sanity cap al qty (`SANITY_MAX_QTY_PER_ORDER`), idempotencia vía `client_order_id` de Alpaca
  (doble click→misma orden, sin tabla), rechazo Alpaca→502 sin crash, audita (B5).
  `GET /me/positions`: alertas TP/SL como ALERTA+botón (read-only, nunca "vendé"/auto).
  `execution.py`: `submit_order` INTACTO (diff aditivo, 0 deletions) + nuevos `place_order`/
  `get_order_by_client_order_id`; auto-trader sin afectar (test_workers/test_bot_cycle verdes).
  Math de salidas: `borsenhirn/signals/exits.py` (pura). Smoke vivo: 401/400/400(sanity)/403/
  502/orden ok/doble-click→misma orden/alertas. 414 tests (+test_exits). Frontend UI: post-Clerk.
**Paso 3 backend COMPLETO (3a–3d), 414 tests verdes.** Contratos cliente listos:
`/me/broker` (conectar Alpaca), `/signals` (tarjetas), `/me/orders` (ejecución manual),
`/me/positions` (alertas TP/SL). Calculadora en TS puro (frontend).
Nota: `make_bot_cycle_fn` sigue en `workers/` (no se relocó); cubierto porque el
guardrail también prohíbe `workers.bot_cycle` en el cliente.

## 👉 PASO ACTUAL (2026-06-16): pasada FRONTEND, de a UNA superficie
**Clerk CERRADO al 100%** (login real punta a punta verificado: dashboard cargó,
`GET /me`→200 con tenant_id `314e32f1-53d0-4efa-8579-df84f6a552a4` + Clerk userId).
Desbloqueó el frontend. Vamos superficie por superficie, **Uriel decide el orden y
da el OK de arranque de cada una** (no adelantarse — ver memoria de flujo).

**Pasada FE #1 — Tarjetas de análisis ✅ (commit f3e9d6e).** `/dashboard` consume
`GET /signals`: símbolo+precio, tesis, niveles (entrada/stop/objetivo), qué invalida,
régimen, factores con PROCEDENCIA, disclaimer visible. Estados vacío/error manejados.
Archivos: `frontend/src/lib/signals.ts`, `components/SignalCard.tsx`, `app/dashboard/page.tsx`.

**Pasada FE #2 — Calculadora de posición ✅ (commit a81fd58).** `components/PositionCalculator.tsx`
(client island, embebido colapsable en cada tarjeta): usuario mete capital + %riesgo,
toma niveles del análisis, recalcula en vivo (useMemo) vía `calcPosition` (lib pura, 8 tests):
acciones, costo+%capital, pérdida al stop, ganancia al objetivo, R/B. Bordes OK (stop≥entrada,
capital insuficiente). Disclaimer "herramienta, no recomendación". Verificado por Uriel (ej. UNH).
- **TODO futuro (NO ahora, anotado a pedido de Uriel):** cuando el %capital de UNA posición
  es alto (~40%+), mostrar un aviso informativo SUAVE (solo dato, sin aconsejar nada).

**Pasada FE #3 — Conectar Alpaca (`/me/broker`) ✅ CERRADA Y VERIFICADA CON KEYS REALES
(2026-06-17).** Uriel conectó su cuenta Alpaca paper de verdad: la pantalla muestra
"Alpaca conectado (paper)" con la key enmascarada. `app/dashboard/broker/page.tsx` (client,
wizard 3 pasos + link al panel paper) + `lib/broker.ts` (GET/POST/DELETE tipados). Secret en
input type=password, nunca se loguea ni se re-pinta; form se limpia al guardar. Solo PAPER.
DELETE con confirmación. Link en el header (`layout.tsx`).
- **Seguridad verificada (2026-06-17):** secret cifrado en `user_credentials.api_secret_ciphertext`
  (token Fernet, 140 bytes, `enc_version=1`, NO texto plano); uvicorn loguea solo método+path+status
  (sin body); `.env`/`.env.local`/`.env.dev`/`.env.prod` gitignored y NO trackeados.
- **DEV ENABLER:** `BORSENHIRN_MASTER_KEY` (Fernet) en el `.env` LOCAL para que el vault cifre
  (el POST tiraba 500 sin ella). **Solo dev** — prod usa secrets manager (pendiente operativo).
- **Bugs de arranque resueltos (ver [ERRORES.md](ERRORES.md) 2026-06-17):** la API "no levantaba"
  desde el browser por (1) bind `127.0.0.1` en vez de `0.0.0.0` (WSL no reenvía loopback a Windows)
  y (2) falta de CORS (preflight OPTIONS→405). Fixes: `--host 0.0.0.0` + CORSMiddleware en
  `api/main.py`. **Arranque de TODO el stack de un tirón:** `bash scripts/run_dev_stack.sh`
  (Postgres + Redis-si-está + API:8000 host 0.0.0.0 + Front:3000, con healthchecks).

**Pasada FE #4 — Ejecución (`/me/orders`) + posiciones/alertas (`/me/positions`) ✅.**
- `components/OrderConfirmDialog.tsx`: ÚNICO camino a ejecutar. Confirmación explícita
  (verb + qty + symbol + ~precio, badge PAPER) → POST. Idempotencia: 1 `idempotency_key`
  (crypto.randomUUID) por apertura, reusado en reintentos → doble-click no duplica. Maneja
  200/idempotent, 409 (link broker), 502 (reintentar), 402, 400. **451 → paso legal inline**
  (D-1a): acepta Términos+Privacidad (`POST /me/legal/accept`, queda actor+versión+fecha) y
  reintenta con la MISMA key. Live nunca se ofrece (siempre mode:paper).
- Botón "Comprar (paper)" DENTRO de la calculadora (D-2): qty = acciones ya calculadas.
- `components/PositionsPanel.tsx` + ruta `/dashboard/positions` (D-3): read-only; alertas TP/SL
  como ALERTA + botón "Revisar orden sugerida" (NUNCA "vendé") que pre-llena el mismo diálogo.
- `lib/orders.ts` (placeOrder/getPositions/getLegalCurrent/acceptLegal, errores discriminados con status).
  Link "Posiciones" en el header.
- **Verificado a nivel código (2026-06-17):** guardrail línea-roja verde; tsc + 8 tests vitest;
  estados del diálogo probados a nivel HTTP con TestClient (200/idempotent/400×3/403/451/409/502)
  + panel con alerta de ejemplo (objetivo_alcanzado → sugerido sell).
- **✅ VERIFICADO EN BROWSER PUNTA A PUNTA (2026-06-21) — CIERRE DE LA PASADA #4.** Uriel probó
  el flujo completo en el navegador con datos reales: (1) comprar con confirmación previa →
  la orden **llegó a Alpaca paper** ("Orden enviada · ACCEPTED · paper"); (2) las alertas TP/SL
  salieron como **"Revisar orden sugerida"** sin ejecutarse solas (NUNCA auto-vende). Las 4
  superficies funcionando con datos reales de punta a punta.
- **Nota:** el tenant de Uriel aún NO tiene legal aceptado → al primer "Comprar" verá el paso 451→aceptar.

**PASADA FRONTEND COMPLETA Y VERIFICADA EN BROWSER (2026-06-21):** tarjetas · calculadora ·
conectar Alpaca · ejecución+posiciones — las 4 superficies probadas punta a punta con datos
reales y una orden real en Alpaca paper. Pendiente: pulido visual (diferido a pedido de Uriel)
+ el aviso suave de %capital alto (TODO) + separar la cuenta paper del auto-trader (TODO ↓).

### 📌 TODO (producto, NO ahora — anotado a pedido de Uriel 2026-06-21): separar cuentas paper
Hoy la cuenta de cliente (BYO Alpaca de Uriel) y el **auto-trader interno** comparten la **MISMA
cuenta de Alpaca paper** → por eso en el panel de posiciones aparecen muchas posiciones que el
usuario NO compró (las abrió el auto-trader). **Para probar está bien.** Cuando esto sea producto,
el auto-trader interno debería correr en **su propia cuenta paper**, separada de lo que ve un
usuario (cada tenant ve solo lo suyo). Encaja con la separación "un cerebro, dos caras" ya hecha
(el auto-trader vive aislado en `internal/autotrader/`); falta que sus credenciales Alpaca sean
distintas de las del cliente. **No arreglar ahora.**

---
### (histórico) Clerk — cómo se cableó. Checklist (Uriel hizo A y B; Claude hizo C):
- **A. Crear app Clerk** (dashboard.clerk.com, free): copiar **publishable key** (`pk_test_…`,
  pública) + **secret key** (`sk_test_…`, privada) + el **Frontend API URL** (= issuer,
  `https://<slug>.clerk.accounts.dev`). JWKS = issuer + `/.well-known/jwks.json`.
- **B. Pegar las vars (a mano, la secret NO va al chat):**
  - `frontend/.env.local` (NO existe aún — crear; gitignored):
    `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=` · `CLERK_SECRET_KEY=` · `NEXT_PUBLIC_API_URL=http://localhost:8000`
  - Backend `.env` (existe; AGREGAR 3 líneas, no clobbear): `AUTH_VERIFIER=clerk` ·
    `CLERK_ISSUER=https://<slug>.clerk.accounts.dev` · `CLERK_JWKS_URL=<issuer>/.well-known/jwks.json`
  - Nombres exactos que lee el código (auth/verifier.py): `AUTH_VERIFIER`, `CLERK_ISSUER`,
    `CLERK_JWKS_URL` (+ `CLERK_AUDIENCE` opcional). Frontend: `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`.
  - OJO: con `AUTH_VERIFIER=clerk`, el backend deja de aceptar los tokens `static` de dev.
- **C. Verificar (Claude, tras confirmar B):** `/me` sin token pasa de **500 → 401** (prueba
  que el verifier se construye). El **200 con token real** lo prueba Uriel en el browser:
  `cd frontend && npm run dev` → :3000 → login Clerk → `/dashboard` llama `GET /me`.
- **Estado (2026-06-16): CLERK CABLEADO Y VERIFICADO (paso C ✅).** `frontend/.env.local`
  creado por Uriel con las 3 vars OK (pk_test/sk_test/API URL). Faltaban las 3 líneas del
  `.env` del backend → agregadas (derivadas de la publishable key: issuer
  `https://fancy-drum-15.clerk.accounts.dev`). Verificado vivo: JWKS HTTP 200,
  `build_verifier_from_env()`→`clerk`, **`/me` sin token = 401** (antes 500), token basura=401.
  **Falta solo:** el 200 con token real en el browser (Uriel: API:8000 + `npm run dev` :3000 →
  login → /dashboard llama GET /me). Con eso, Clerk queda 100% y se desbloquea la pasada frontend.

## ⏭️ LO QUE FALTA PARA COMPLETAR (orden de impacto)
1. **Cablear Clerk** (paso actual ↑) — desbloquea todo el frontend.
2. **Pasada FRONTEND** (post-Clerk): cablear las 4 superficies en Next.js (form conectar
   Alpaca → tarjetas de análisis → calculadora UI → botón comprar + panel posiciones/alertas).
   Backend/contratos y la lógica de la calculadora ya están.
3. **Paso 4 — track record público** (alimentado por el auto-trader interno en paper). Diferido.
4. **Operativos previos** (no bloquean el producto local): `BORSENHIRN_MASTER_KEY` real,
   keys Stripe live, cron backups, apuntar timer de anomalías a prod.

## 🖥️ Frontend Next.js — REBANADA 1 SCAFFOLDEADA (2026-06-11), falta app Clerk
Construir en rebanadas verticales. **Rebanada 1 (HECHA a nivel código):** `frontend/`
= Next.js 14 (App Router) + TS + Tailwind + `@clerk/nextjs` **v6** (v7 exige Next 15;
quedamos en Next 14). Node v24.16.0 vía nvm (sourcear `~/.nvm/nvm.sh` en shells no-interactivos).
Archivos: `src/middleware.ts` (protege /dashboard), `src/app/layout.tsx` (ClerkProvider +
header), `src/app/page.tsx` (landing), `src/app/dashboard/page.tsx` (server component:
toma JWT de Clerk y llama `GET /me`), `.env.local.example`. **TypeScript COMPILA**; el
build solo falla en prerender por `Missing publishableKey` (esperado sin keys).
Correr: `cd frontend && npm run dev` (tras poner keys). Después de R1: gate legal → billing → dashboard.

**Falta SOLO (del usuario) para correr/verificar R1 end-to-end:** crear app Clerk dev →
poner `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`/`CLERK_SECRET_KEY` en `frontend/.env.local` +
`AUTH_VERIFIER=clerk`/`CLERK_ISSUER`/`CLERK_JWKS_URL` en el `.env` del backend. Ahí
levantamos API (:8000) + `npm run dev` (:3000) y verificamos login → `/me`.

**Contrato del backend** (`borsenhirn/api/main.py`, FastAPI :8000) — verificado vivo:
`/health`, `/`, `/legal/current` responden OK. `/me`, `/me/legal*`, `/billing/*`,
`/me/audit`, `/me/export` requieren JWT Bearer (Clerk).

**Prerequisitos:** Node.js ✅ instalado (v24.16.0 vía nvm). Falta solo la **app de Clerk
+ las vars** — ver "👉 PASO ACTUAL" arriba (es la fuente de verdad del estado de Clerk).
   HALLAZGO: hoy `/me` sin token da **HTTP 500** (no 401) — NO es bug: `build_verifier_from_env`
   tira `ValueError` porque no hay `AUTH_VERIFIER`/`AUTH_DEV_SECRET`. Con `AUTH_VERIFIER=clerk`
   se resuelve (sin token → 401 limpio; con token → OK). Stripe puede esperar (test mode).

Nada de frontend generado aún (no genero archivos que no puedo correr sin Node).

## 🔌 Wire-up del ciclo real del bot al worker multi-tenant (2026-06-11)
Hecho: la lógica del motor se extrajo de `main.run()` (656 líneas) a
`borsenhirn/engine.py::BotEngine` (setup en `__init__` + un ciclo en `run_cycle()`,
sin dormir). `main.py` quedó fino (61 líneas, misma firma `run(train,once,live)`
— no rompe `bot_api`). Nuevo `borsenhirn/workers/bot_cycle.py::make_bot_cycle_fn()`
cachea un `BotEngine` por tenant y lo inyecta a `run_all_tenants`/`WorkerOrchestrator`.
Tests: 393 passed (387 baseline + 5 wiring + 1 fix). **Smoke real validado**
(2026-06-11, mercado abierto): `run_all_tenants(make_bot_cycle_fn())` corrió un
ciclo real del DEFAULT contra Alpaca paper (regime BULL, trades OK). Destapó y
arregló un bug: el tenant SYSTEM (control-plane) figuraba ACTIVE y el orquestador
lo corría como tenant de trading → RLS violation; ahora `run_once` lo saltea
siempre (`67c494b`).
**Aislamiento per-tenant (2026-06-11, opción C):** cada `BotEngine` rutea sus
alertas a su propia `alert_mgr` (`_alert`, ya no al `send_alert` global), escribe
el trade-log CSV a ruta por-tenant (`_log_trade`) y lee/guarda el plan por tenant
(`my_plan.*(tenant_id=...)`). El DEFAULT conserva rutas/archivos globales (compat
dashboard/bot_api). `_handle_plan` pasó a método de `BotEngine`. Suite: 400 passed.
**Pendiente para tenants reales (no-default):** `BORSENHIRN_MASTER_KEY` (vault) +
creds por tenant; canales de alerta (Discord/email) por tenant en su `alert_mgr`.

## 🏁 Dónde voy — ROADMAP SaaS B1..B10 COMPLETO y MERGEADO A MAIN
Los 10 bloqueadores (backends) construidos y testeados en `borsenhirn_dev`, en
**PR #1 mergeado a `main`** (`e483556`). Tests: 387 baseline + 41 integración
(gated `RUN_DB_INTEGRATION`), todo verde. **No hay `borsenhirn` de producción
desplegada** (ver aviso ⛔ arriba) — todo el trabajo vive en `borsenhirn_dev`.
Cierres por bloque en `docs/B{n}_CLOSEOUT.md`.

### ✅ Pendientes OPERACIONALES (no es código nuevo; checklist próxima sesión)
- [ ] **DECISIÓN de despliegue (BLOQUEA B1 Bloque 8):** ¿SaaS en VPS de tercero sí/no?
      (rompe local-first). NO hay prod desplegado — ver el aviso ⛔ arriba.
- [ ] **Ejecutar "B1 Bloque 8"** — SOLO cuando exista prod. Scripts `scripts/b1_block8_*`
      (core + extras) listos/validados. Plan: [B1_BLOCK8_PLAN.md](B1_BLOCK8_PLAN.md).
      Hoy NO hay DB de prod a la que apuntar.
- [ ] **Migrar a prod** las tablas/columnas de B3..B7: `clerk_user_id`, billing en
      `tenants`, `audit_log`, `legal_acceptance`. **Variantes prod LISTAS y validadas
      (2026-06-11):** `scripts/b1_block8_extras_prod_migration.sql` + `_extras_apply.sh`
      (consolidado, guard prod, atómico/idempotente, validado en DB scratch). Corre como
      Paso 4.5 (tras rol + verify core). Los `b{3,4,5,7}_block1_*.sql` originales son dev-only.
- [ ] **Keys reales en `.env` de prod:** Clerk (`AUTH_VERIFIER=clerk`,
      `CLERK_ISSUER`, `CLERK_JWKS_URL`), Stripe (`BILLING_PROVIDER=stripe`,
      `STRIPE_*`), `ADMIN_API_KEY`, master key vía secret manager.
- [ ] **Cron de backups** (`scripts/db_backup.sh`) + destino offsite — [B9_BACKUP_RUNBOOK.md](B9_BACKUP_RUNBOOK.md).
- [ ] **Frontend Next.js** (Clerk + checkout/portal + modal legal) — esfuerzo aparte.
- [x] **Wire-up del ciclo real del bot** en el worker (`cycle_fn`) — hecho 2026-06-11
      (`BotEngine` + `make_bot_cycle_fn`); smoke real paper validado.
- [x] **`scan_and_alert` por tenant** — hecho 2026-06-11: pase de anomalías
      `borsenhirn/workers/anomaly_scan.py::scan_anomalies_all_tenants` (itera ACTIVE
      excl. SYSTEM, alert_mgr scoped por tenant, no saltea HALT, aísla errores).
      AlertManager factorizado a `bootstrap.build_alert_manager_from_config`. Suite: 404 passed.
- [x] **Agendado cada hora** (2026-06-11): systemd timer `scripts/borsenhirn-anomaly.timer`
      + service oneshot + entrypoint `scripts/run_anomaly_scan.py`. Instalación en
      [DEPLOY_ALWAYS_ON.md](DEPLOY_ALWAYS_ON.md) (la corre Uriel: `cp` units → `enable --now` el timer).

### Estado por bloque (todos ✅ backend)
B1 RLS · B2 Vault · B3 Auth Clerk · B4 Stripe · B5 Audit · B6 Workers ·
B7 Legal · B8 Kill-switch (per-tenant+global) · B9 Backups+export · B10 Anomaly.

> El detalle histórico por sub-bloque está más abajo (log del sprint).

**B3 (Auth Clerk): en progreso.** Decidido: 1 user Clerk = 1 tenant, pyjwt, provisión
lazy, user_id=tenant_id, solo endpoints nuevos protegidos. Plan: [B3_AUTH_PLAN.md](B3_AUTH_PLAN.md).
- B3.1 ✅ schema `clerk_user_id` + provisión (`provision_for_clerk_user`).
- B3.2 ✅ `borsenhirn/auth/` — `TokenVerifier` + `StaticTokenVerifier` (HS256, pyjwt). 11 tests.
- B3.3 ✅ `ClerkJWKSVerifier` (RS256+JWKS) + factory `build_verifier_from_env`.
  Config-driven (env); testeado con JWKS mockeado. Vars en `.env.example`.
  **Falta solo poner los valores reales de tu Clerk** (CLERK_ISSUER/JWKS_URL).
- B3.4 ✅ FastAPI `get_current_tenant` (`borsenhirn/auth/deps.py`) + endpoints
  `/me` y `/me/trades/count` en `api/main.py`. e2e: JWT→verify→provisión→RLS.
**Backend de B3 COMPLETO.** Para Clerk real en prod: poner `AUTH_VERIFIER=clerk`
+ `CLERK_ISSUER`/`CLERK_JWKS_URL` en el `.env`. Falta (aparte): frontend Next.js.
`api/main.py` ahora importa LAZY redis/sqlalchemy (solo en `/status` y `/signal`),
así la API y los endpoints `/me` corren sin esas libs. Baseline 323 passed.

**B4 (Stripe billing): en progreso.** Plan: [B4_BILLING_PLAN.md](B4_BILLING_PLAN.md).
- B4.1 ✅ columnas de billing en `tenants` (stripe_customer_id UNIQUE, subscription_id,
  plan, current_period_end) + `TenantManager.get_tenant_by_stripe_customer_id` / `set_billing`.
- B4.2 ✅ `borsenhirn/billing/`: `BillingProvider` + `StripeBillingProvider` +
  `FakeBillingProvider` + factory + mapeo stripe_status→tenant_status. 16 tests
  (firma de webhook verificada offline). SDK `stripe==12.5.1` en requirements.
- B4.3 ✅ `apply_stripe_event` + endpoint `/webhooks/stripe` (verifica firma, sync tenant.status). 8 tests.
- B4.4 ✅ endpoints `/billing/checkout` + `/billing/portal` (trial vía `STRIPE_TRIAL_DAYS`).
- B4.5 ✅ gating: `get_active_tenant` (402 si no active) en `/me/trades/count`;
  billing endpoints usan `get_current_tenant` (suspendido puede ir a pagar).
**Backend de B4 COMPLETO.** Para Stripe real: `BILLING_PROVIDER=stripe` + STRIPE_* en `.env`.
Falta (aparte): frontend (botones checkout/portal) + migración billing a prod. Baseline 354 passed.

**B5 (Audit log): en progreso.** Plan: [B5_AUDIT_PLAN.md](B5_AUDIT_PLAN.md). Decidido:
append-only por permisos, las 4 categorías, soft-fail.
- B5.1 ✅ tabla `audit_log` (RLS + append-only: app role solo INSERT+SELECT). 18/18 con RLS.
- B5.2 ✅ `borsenhirn/audit/` (`AuditLogger.record` + actor contextvar + soft-fail). 4 unit + 3 e2e.
- B5.3 ✅ hooks en las 4 categorías (credenciales set/get/delete, billing webhook,
  tenant lifecycle, kill-switch) + actor desde la auth dependency. Lazy + soft-fail.
- B5.4 ✅ endpoint `GET /me/audit` (el tenant ve su traza, RLS). e2e completo.
**Backend de B5 COMPLETO.** Falta (aparte): migración `audit_log` a prod (con B8). Baseline 361 passed.

**B6 (Worker isolation): framework COMPLETO.** Plan: [B6_WORKERS_PLAN.md](B6_WORKERS_PLAN.md).
Decidido: secuencial con aislamiento de errores. `borsenhirn/workers/`:
`load_broker_credentials` (vault + fallback), `TenantWorker` (contexto aislado),
`WorkerOrchestrator` (recorre activos, saltea HALT, try/except por tenant),
`run_all_tenants`/`make_halted_check`. 8 tests (7 unit + 1 e2e). Baseline 368.
Falta (aparte): wire-up del ciclo real del bot (reusar `main`) — el `cycle_fn` es inyectable.

**B7 (Legal): backend COMPLETO.** Plan: [B7_LEGAL_PLAN.md](B7_LEGAL_PLAN.md). Decidido:
gatear + Terms+Privacy. Tabla `legal_acceptance` (RLS + append-only), `borsenhirn/legal/`
(`record_acceptance`/`is_compliant`/`current_versions`), endpoints `/legal/current`,
`POST /me/legal/accept`, `GET /me/legal`, y gating `get_compliant_tenant` (451) en
`/me/trades/count`. Versiones en config. Suite integración completa: **35 passed**.
(De paso: fix de cleanups e2e por FK del hook de audit de B5.) Falta: migración a prod ("B1 Bloque 8").

**B8 (Kill switch): COMPLETO.** Per-tenant ya estaba (manual halt/clear + checks
automáticos; B6 lo respeta). Nuevo: kill-switch GLOBAL (`borsenhirn/safety/global_killswitch.py`
sobre el tenant SYSTEM), el orquestador saltea todo si está activo, endpoints admin
`/admin/killswitch/global` (GET/POST/clear, auth por `X-Admin-Key`=`ADMIN_API_KEY`).
Audita global_halt/clear. Suite integración: 37 passed. CLAUDE.md sincronizado.
Ojo numeración: "B1 Bloque 8" (aplicar a prod) ≠ "Roadmap B8 Kill switch".

**B9 (Backups): COMPLETO.** Plan: [B9_BACKUPS_PLAN.md](B9_BACKUPS_PLAN.md) ·
runbook: [B9_BACKUP_RUNBOOK.md](B9_BACKUP_RUNBOOK.md). `scripts/db_backup.sh`
(pg_dump -F c + verificación + retención KEEP, cron-friendly), `scripts/db_restore.sh`
(restore a DB nueva), y export por tenant (`borsenhirn/backups/export_tenant` +
`GET /me/export`, excluye user_credentials). Integración completa: 40 passed.
Falta (aparte): agendar cron + destino offsite en prod.

**B10 (Anomaly detection): COMPLETO.** Plan: [B10_ANOMALY_PLAN.md](B10_ANOMALY_PLAN.md).
`borsenhirn/anomaly/`: `build_snapshot` (audit_log + trading bajo RLS), reglas puras
(cred-access spike, killswitch burst, losing streak, volume spike), `AnomalyDetector.scan`
+ `scan_and_alert` (AlertManager; solo alerta — D1). Umbrales por env. 12 tests.
Integración completa: 41 passed.

## 🏁 ROADMAP SaaS COMPLETO (backends): B1..B10 ✅
Los 10 bloqueadores construidos y testeados en dev. **Pendientes operativos
(todos bloqueados por la decisión de despliegue — NO hay prod, ver ⛔ arriba):**
"B1 Bloque 8" + migraciones clerk_id/billing/audit/legal (scripts listos); keys
reales (Clerk/Stripe); cron de backups; frontend Next.js. Cierres: docs/B{n}_CLOSEOUT.md.

## Estado del Bloque 5 (refactor capa de app)
| Sub-bloque | Qué | Estado | Commit |
|---|---|---|---|
| 5.1 | `tenancy/constants.py` (SYSTEM/DEFAULT tenant UUIDs) | ✅ | `f02002d` |
| 5.2 | Rol `borsenhirn_app` (NOSUPERUSER/NOBYPASSRLS) + rename GUC `app.current_tenant_id` | ✅ | DB-only |
| 5.3 | `borsenhirn/db.py` (pools app/admin, `get_conn`, `bypass_rls`) | ✅ | `f02002d` |
| 5.4.a | refactor `bot_memory_pg.py` → tenant context | ✅ | `8ea2bb6` |
| 5.4.b | refactor `borsenhirn/security/credentials.py` | ✅ | `72ee927` |
| 5.4.c | refactor `borsenhirn/safety/state_store_pg.py` | ✅ | `64321ce` |
| 5.5.b | `bootstrap.py` + `api/main.py` wire-up | ✅ | `5678d24` |
| 5.5.a | `main.py` wire-up + fix bug import `_get_conn` | ✅ | `e6fec1a` |
| 5.6 | Tests integración RLS end-to-end (rol app real) | ✅ verificado | sin commit aún |
| 5.7 | Docs `B1_APP_LAYER.md` + cierre log Bloque 5 | ✅ | sin commit aún |

## Hecho (resumen físico en DB dev)
- 17 tablas con `tenant_id` NOT NULL + FK + index + RLS forzado + 2 policies c/u (34 policies).
- 128 filas legacy backfilled al default tenant `00000000-…001`.
- 4 legacy dropeadas en dev (`bot_state`, `entry_context`, `regime_stats`, `symbol_memory`).
- Rol `borsenhirn_app` creado; `config.py` lee `APP_DB_USER`/`APP_DB_PASSWORD` con fallback a admin.
- Bug latente arreglado: `main.py` importaba `_get_conn` borrado en 5.4.a → `import main` OK.

## ⏳ B1 Bloque 8 — BLOQUEADO: no hay prod desplegado (corregido 2026-06-11)
**Corrección importante:** la suposición previa de que "la prod real vive en otra
máquina/host inalcanzable" era **errónea**. Verificado en WSL (2026-06-11): NO hay
ningún server/VPS — `~/.ssh/config` no existe, `known_hosts` solo tiene GitHub, la
máquina nunca se conectó a ningún host. **No existe `borsenhirn` de producción en
ningún lado.** El único Postgres es el local (`borsenhirn_dev` + `postgres`).

**Por lo tanto B1 Bloque 8 NO se puede ni se debe ejecutar todavía** — no hay DB a
la que apuntar. Los scripts (`b1_block8_*` core + extras) están listos/validados y
esperan. **El paso previo obligatorio es la DECISIÓN de despliegue** (SaaS en VPS de
tercero sí/no — rompe local-first), que Uriel toma en frío. Ver el aviso ⛔ al inicio.

## Hallazgo RESUELTO (B7) — pool-leak en safety stack
`PostgresStateStore` sacaba conn con `self.get_conn()` y nunca la devolvía → el bot
agotaba el pool (max 10) tras ~10 iteraciones del loop. Fix: helper `_acquire` en
`state_store_pg.py` que entra/sale del context manager `bdb.get_conn` (devuelve la
conn al pool); `main._safety_get_conn` ahora devuelve `bdb.get_conn(role="app")`.
Backward-compat con conn plano (ks_admin/test_alerts) preservada. Test de regresión
`test_safety_no_pool_leak` (3× el pool sin agotarse).

## Métricas
- pytest baseline: **267 passed, 57 skipped** (los módulos de integración 5.6 +
  Bloque 6 se saltan por default sin `RUN_DB_INTEGRATION`).
- Integración (con `RUN_DB_INTEGRATION=1`): **13 passed** (6 de 5.6 + 7 de B6).
- `check_rls_coverage.py --strict`: 17/17 tablas con RLS, 0 sin RLS. Exit 0.
- Backup branch pre-sprint: `backup-pre-b1-20260426`.

## 5.6 — hecho (2026-06-05)
Artefactos: `tests/test_b1_rls_integration.py` (6 tests), gate en `tests/conftest.py`
(`RUN_DB_INTEGRATION`), `scripts/b1_block4_test_isolation.sh` (equivalente bash).
Resultado verificado contra `borsenhirn_dev` con el rol `borsenhirn_app` real:
sin contexto→0 · default→31 · UUID ajeno→0 · bypass_rls→31 · rol NOSUPERUSER+NOBYPASSRLS.
Correr: `RUN_DB_INTEGRATION=1 venv/bin/pytest tests/test_b1_rls_integration.py`
(tras `source .env.dev`), o `bash scripts/b1_block4_test_isolation.sh`.

**Pendiente de commit** (workflow manual): artefactos de 5.6 + 5.7 + Bloque 6
(`tests/test_b1_rls_isolation_full.py`) + fix `config.py` (alias `DB_PASS`) + docs.

## Notas / reglas vivas
- Prod `borsenhirn` intacta (vive en otro host; ver pendiente B8). Trabajo en `borsenhirn_dev`.
- Commits automáticos OK en local; **push a GitHub requiere confirmación**. Cosas de prod las corre Uriel.
- GUC canónico de RLS: `app.current_tenant_id` (alineado al módulo `tenancy/db.py` existente).
