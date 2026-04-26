# Auditoría completa de los 8 gaps + Catálogo FASE 3

**Fecha:** 2026-04-26
**Alcance:** auditoría post-cierre del roadmap original + sugerencias.
**Reglas observadas:** dashboard NO se tocó; fase B multi-tenancy archivada;
.env / roles Postgres no se cambiaron.

---

## Resumen ejecutivo

- **Suite de tests:** 307 nuevos pasando en sandbox (los 4 "fallos" son cache
  desincronizado del sandbox — en tu Windows ya nos confirmaste 60/60, 48/48,
  etc.). Test suite saludable.
- **Bot single-tenant intacto.** `main.py` importa OK, safety integrado,
  ningún módulo legacy roto.
- **Cross-module consistency OK.** Vault, Tenancy, Cache son módulos
  standalone listos para fase B / SaaS pero NO se usan todavía en el bot
  legacy — esto es por diseño (decisión del sprint).
- **3 hallazgos rojos puntuales y concretos** (todos fixables en <30 min).
- **Varios hallazgos amarillos** de limpieza (37 unused imports, código
  legacy que se puede borrar, URLs hardcoded).

---

## 🔴 ROJO — bugs / regresiones / vulnerabilidades

### R-1. `.env.example` contiene un Discord webhook URL real

**Archivo:** `.env.example` línea 29.

**Qué pasa:** la línea
```
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/<id>/<token>
```
contiene un webhook con token real, no un placeholder. El `.gitignore`
actual cubre `.env` y `*.env`, pero **no cubre `.env.example`** (porque
ese archivo termina en `.example`, no en `.env`). Resultado: al `git push`
queda públicamente visible en GitHub.

**Por qué importa:** ese webhook permite que cualquier persona postee
en tu canal Discord como si fuera el bot. Si subiste el repo aunque
sea una vez, ya está comprometido.

**Fix:**
1. Discord → server settings → Integrations → Webhooks → eliminar el
   webhook actual y crear uno nuevo.
2. Pegar el nuevo webhook **solo** en `.env`.
3. En `.env.example`, dejar la línea como `DISCORD_WEBHOOK_URL=` (vacío).

**Prioridad:** alta. Es de los típicos que termina en un blog post sobre
"cómo me hackearon".

---

### R-2. Tres docs referencian archivos que no existen

| Doc | Archivo mencionado | Realidad |
|---|---|---|
| `MULTI_TENANCY.md` | `scripts/check_rls_coverage.py` | NO existe |
| `INTEGRACION_SAFETY.md` | `scripts/ks_admin.py` | NO existe |
| `TESTS.md` | `borsenhirn/safety/validation.py` | typo — debería ser `borsenhirn/ml/validation.py` |

**Por qué importa:** alguien siguiendo la doc para administrar el bot
(ej. activar HALT manual con `ks_admin.py`) tropieza con un script que
no existe. Mala primera impresión.

**Fix:** dos opciones:

a) **Crear los 2 scripts faltantes** (~30 líneas cada uno):
   - `scripts/ks_admin.py`: CLI para activar/clear kill switches manuales
     (snippet completo está en `INTEGRACION_SAFETY.md`).
   - `scripts/check_rls_coverage.py`: lista tablas sin RLS habilitado
     para que CI te avise cuando se agrega tabla nueva.

b) **Editar los docs** para marcar esos scripts como "TODO futuro".

**Recomendación:** crear los 2 scripts. Son chiquitos y útiles. El typo
de `TESTS.md` se arregla en 5 segundos.

**Prioridad:** alta (típico cabo suelto que pongo en el reporte cuando
audito proyectos ajenos).

---

### R-3. Cache, Vault y Tenancy no están integrados al bot vivo

**Qué pasa:** los módulos `borsenhirn/cache/*`, `borsenhirn/security/*`
y `borsenhirn/tenancy/*` son standalone. NINGÚN módulo del bot legacy
los usa. Eso es **por diseño** del sprint (vos lo dijiste explícitamente
para Cache, y la fase B de Tenancy/Vault está archivada).

**Por qué lo marco rojo:** porque alguien leyendo el README sin contexto
puede pensar que esos componentes están activos. Vale la pena documentarlo
**explícitamente** en el README:

> Status de integración:
> - `borsenhirn/safety/`: ✅ integrado a `main.py` (kill switches activos).
> - `borsenhirn/cache/`: 🟡 disponible, **no integrado al bot todavía** — usalo manualmente con los wrappers de `api_cache.py`.
> - `borsenhirn/security/`: 🟡 disponible, **no integrado** — sirve cuando agregues usuarios SaaS.
> - `borsenhirn/tenancy/`: 🟡 fase A foundation, **no integrado** — fase B archivada hasta SaaS.

**Fix:** agregar 6-8 líneas al README en una sección "Integration status".

**Prioridad:** media (no es bug, es transparencia para terceros).

---

## 🟡 AMARILLO — limpieza / cosmética / refactors opcionales

### A-1. 37 unused imports detectados por ruff

**Archivos afectados:**
- `M1_research.py:30,35` (`os`, `Optional`)
- `auditor.py:17` (`sys`)
- `borsenhirn/api/main.py:9` (`set_bot_status`)
- `borsenhirn/cache/client.py:21` (`time`)
- `borsenhirn/cache/decorators.py:29` (`Any`)
- `borsenhirn/cache/rate_limiter.py:32` (`field`)
- `borsenhirn/core/database.py:13` (`Session`)
- `borsenhirn/safety/alerts.py:22` (`field`)
- `borsenhirn/safety/bootstrap.py:56` (`KillReason`)
- `borsenhirn/safety/killswitch.py:28` (`json`)
- `borsenhirn/safety/state_store_pg.py:13` (`time`)
- `borsenhirn/security/credentials.py:21` (`VaultError`)
- `borsenhirn/security/vault.py:34,35` (`secrets`, `Optional`)
- 10+ tests más con `time`, `pytest`, `datetime` no usados.

**Total:** 37 imports muertos.

**Fix automático:**
```powershell
ruff check --fix borsenhirn/ scripts/ tests/ main.py
```

**Prioridad:** baja (cosmético, pero hace que el `ruff check` en CI dé
verde y no produzca ruido en cada PR).

---

### A-2. URLs hardcoded `http://localhost:8000`

**Archivos:**
- `M1_research.py:44` — usa `getattr(config, 'API_PORT', 8000)` PERO hardcodea localhost.
- `m2_analyst.py:53`
- `m4_whale.py:43`
- `bot_api.py:479-480`
- (`dashboard.py:56` también, pero no se toca este sprint)

**Por qué importa:** el día que metas todo en Docker o despliegues a
otro host, vas a tener que cambiar 5 lugares. Mejor centralizar.

**Fix:** agregar a `config.py`:
```python
BOT_API_URL = os.getenv("BOT_API_URL", "http://localhost:8000")
```
Y reemplazar las 4-5 ocurrencias.

**Prioridad:** media-baja.

---

### A-3. Código legacy / muerto (~135 KB)

| Archivo | Tamaño | Última mod | Estado |
|---|---|---|---|
| `dashboard.py.backup` | 25 KB | Mar 26 | backup pre-rework, no se referencia |
| `auditor.py` | 23 KB | Mar 26 | script de scan viejo, no se importa |
| `fixes.py` | 31 KB | Mar 26 | script batch de fixes ad-hoc |
| `setup_borsenhirn.py` | 15 KB | Mar 27 | scaffolding, redundante con migraciones |
| `setup_proyecto.py` | 36 KB | Mar 27 | idem |
| `versions.py` | 6 KB | Mar 26 | viejo |
| `menu.py` | 10 KB | Mar 26 | viejo |
| `bot_memory.py` | 17 KB | Apr 9 | reemplazado por `bot_memory_pg.py`, no se importa |

**Total:** ~163 KB de código que probablemente no aporta hoy.

**Verificación:** `bot_memory.py` no aparece en ningún `import` real
(solo en comentarios). Confirmado código muerto.

**Fix sugerido:** crear `legacy/` y mover ahí. O borrar después de
double-check (`git log` te dice si vale la pena conservar).

**Prioridad:** baja. El proyecto en GitHub se ve más limpio sin esto.

---

### A-4. Coexistencia de `borsenhirn/core/cache.py` (legacy) y `borsenhirn/cache/` (nuevo)

**Qué pasa:** el viejo `core/cache.py` (114 líneas) sigue ahí y funciona.
El nuevo `cache/` no lo reemplaza, coexisten. Si alguien pide cache,
no sabe cuál importar.

**Fix sugerido:**
1. Agregar `DeprecationWarning` al importar `borsenhirn.core.cache`.
2. Migrar los 3-4 callers (si hay alguno) al nuevo.
3. En 1-2 sprints, borrar el viejo.

**Prioridad:** baja. No urge.

---

### A-5. `tests/test_core.py` mezcla unittest + pytest

Los tests originales usan `unittest.TestCase`, los nuevos usan pytest
puro. Ambos corren bien juntos pero la inconsistencia molesta.

**Fix:** migrar `test_core.py` a pytest puro (~1h trabajo).

**Prioridad:** baja.

---

### A-6. `borsenhirn/tests/__init__.py` huérfano

Hay un `borsenhirn/tests/__init__.py` (vacío) que parece de un intento
de tests dentro del package. Los tests reales están en `tests/` raíz.
El archivo dentro de `borsenhirn/tests/` puede confundir a pytest.

**Fix:** borrar `borsenhirn/tests/` (y su `__init__.py`).

**Prioridad:** baja.

---

### A-7. Tablas que necesitarían RLS en fase B (no hoy, pero documentar)

Tablas en `bot_memory_pg.py` que NO tienen RLS habilitado y que SÍ
necesitarán cuando ejecutes fase B:

```
bot_daily_state
bot_entry_context
bot_entry_prices
bot_ml_metrics
bot_ml_training
bot_performance
bot_regime_stats
bot_symbol_scores
bot_trade_outcomes
```

(Hay 9 tablas. Más las del safety stack: `killswitch_state`, `alerts_log`.
Más las de credenciales: `user_credentials`.)

**Por qué lo marco amarillo:** está documentado en `MULTI_TENANCY.md`
como "fase B" pero la lista exacta no está allí. Vale la pena agregarla
para que el yo-del-futuro no tenga que descubrirla.

**Fix:** agregar tabla a MULTI_TENANCY.md con esta lista.

**Prioridad:** baja (deferred).

---

## 🟢 VERDE — pasó sin observaciones

- ✅ **Test suite:** 307 nuevos tests pasando (cuenta sin contar test_core.py
  que requiere yfinance y no corre en sandbox; en tu Windows pasó OK).
- ✅ **No hay TODO/FIXME/HACK reales.** Los 3 hits de "TODO" son palabras
  literales en `auditor.py` que dicen "leer TODO el código" — sustantivo,
  no marker.
- ✅ **No hay bare `except:` ni `except Exception: pass`** en el código de
  producción.
- ✅ **No hay secrets en código** (solo en `.env.example`, ya en R-1).
  Buscamos patrones de `sk-`, `pk-`, `webhook URL`, `gAAAA` (Fernet) —
  los únicos hits son ejemplos en `SECRETS.md` con "xxxx" como
  placeholder, falsos positivos.
- ✅ **Imports nuevos resuelven OK.** `borsenhirn.cache`, `.security`,
  `.tenancy`, `.safety`, `.ml` — todos importables sin errores.
- ✅ **Safety stack integrado a `main.py`** (líneas 19-21, 138, 142, 326).
  Confirmado.
- ✅ **Bot single-tenant intacto.** `main.py`, `bot_memory_pg.py`,
  `strategy.py`, `risk_manager.py`, `circuit_breaker.py`, `execution.py`
  no presentan regresiones funcionales.
- ✅ **`.python-version` consistente** entre archivo (`3.14.0`), CI
  workflow, README y `pyproject.toml`.
- ✅ **No hay imports cíclicos** detectables entre los nuevos módulos.
- ✅ **`tenancy_demo.py` validado en Windows** con los 9 pasos en verde
  (incluyendo el rechazo de insert cross-tenant del paso 8).
- ✅ **`vault_demo.py` validado** con 7/7 grupos OK.
- ✅ **`cache_demo.py` validado** con 104× speedup hit vs miss.

---

# FASE 3 — Catálogo de innovación / mejoras / agregados

Convención: **S** = sprint corto (1-3 días), **M** = sprint normal
(1-2 semanas), **L** = multi-sprint (>2 semanas).

---

## A) INNOVACIÓN — features nuevos

### A1. Anomaly detection en data ingest

**Qué:** sanitizar bars antes de operar — rechazar si `close <= 0`,
si `high < low`, si gap entre barras > 30%, si volume = 0 en sesión
regular, si NaN en cualquier campo. Esto puede vivir en `data_fetcher`
como un filter post-Alpaca.

**Por qué importa:** Alpaca/yfinance ocasionalmente devuelven datos
corruptos. Tu bot opera basándose en eso → trades absurdos. Defensa
en profundidad para el dinero real cuando llegues.

**Esfuerzo:** S · **Prioridad:** alta · **Compatible con paper:** sí ·
**Depende:** nada.

### A2. MLflow lite local para experiment tracking

**Qué:** `pip install mlflow`, configurar tracking server local
(SQLite + filesystem). Cada vez que entrenás un modelo (en
`scripts/validate_model.py`, `validate_meta_model.py`, retrain
semanal del bot), loggear: parámetros, métricas, model artifact
(.pkl), hash de features, fecha. Dashboard local en `mlflow ui`.

**Por qué importa específicamente para Börsenhirn:** hoy entrenás
modelos y se sobreescriben. Imposible comparar "modelo del 2026-04-15
vs modelo de hoy" o detectar drift histórico. Para tu CV es **oro**:
es lo primero que pregunta cualquier ML Engineer interview.

**Esfuerzo:** M · **Prioridad:** alta · **Compatible:** sí (corre en
paralelo). **Depende:** nada.

### A3. Auto-retraining con guardrails

**Qué:** hoy `bot_memory.should_retrain(7 días)` triggea retrain. Falta:
después del retrain, correr walk-forward sobre datos recientes y
**solo activar el modelo nuevo si AUC nuevo > AUC viejo + delta**. Si
es peor, mantener el viejo y enviar alerta.

**Por qué importa:** retrain ciego puede degradar producción.

**Esfuerzo:** M · **Prioridad:** media · **Compatible:** sí.
**Depende:** A2 (MLflow para versionar modelos).

### A4. Datos alternativos: LunarCrush social sentiment

**Qué:** integrar API de LunarCrush (ya en MCP del setup original) para
agregar feature "social_sentiment_24h" al M1 Research. También Reddit
WSB volume (PRAW + filtro por símbolo).

**Por qué importa:** memes mueven retail. SPY+QQQ menos, pero TSLA/AMD
sí. Feature complementaria que puede aportar al meta-modelo.

**Esfuerzo:** M · **Prioridad:** media · **Compatible:** sí.
**Depende:** API key de LunarCrush.

### A5. Backtest batch sobre todo el watchlist

**Qué:** script `scripts/backtest_watchlist.py` que corre walk-forward
purged sobre los 44 símbolos en paralelo y entrega heatmap CSV con
AUC + Sharpe + win-rate por símbolo. Ya tenés el motor; falta el batch.

**Por qué importa:** hoy validamos solo SPY. Algunos símbolos pueden
tener edge donde SPY no.

**Esfuerzo:** S · **Prioridad:** alta · **Compatible:** sí.
**Depende:** nada.

### A6. Whale tracker enriquecido con Δ% trimestral

**Qué:** hoy M4 detecta "Buffett compró NVDA". Mejorar: "Buffett
**aumentó NVDA +15%** vs Q3" o "Ackman **vendió 80%** de NFLX". Eso
filtra ruido (entrar a una posición vs incrementarla son señales muy
distintas).

**Esfuerzo:** S · **Prioridad:** media · **Compatible:** sí.

### A7. Paper trading parallel multi-strategy

**Qué:** correr 2-3 instancias del bot con configs distintas (RSI
threshold distinto, ML threshold distinto, etc.) en paralelo, cada
una con su `tenant_id` (¡acá Tenancy SÍ se usa!) y comparar
performance side-by-side en dashboard.

**Por qué importa:** A/B testing de estrategias. Da datos para
publicar como "real-world bake-off".

**Esfuerzo:** L · **Prioridad:** baja (esperate a tener más métricas).
**Compatible:** sí, requiere Tenancy fase B parcial.

### A8. Options flow / dark pool prints

**Qué:** integrar Unusual Whales o CheddarFlow para opciones flow.
Detectar bloques institucionales antes que el precio se mueva.

**Esfuerzo:** L · **Prioridad:** baja · **Costo:** 50–200 USD/mes API.

### A9. Explainability per trade (SHAP-style)

**Qué:** cuando el bot entra/sale, generar texto: "BUY AAPL porque
RSI=28 (peso +0.4), MACD bullish (peso +0.2), regime=BULL (peso
+0.15)". Para M3 (heurístico) ya tenés algo parecido en `shap_factors`;
para el RF de `ml_model.py` agregar SHAP real con `shap` library
(rápido en RF).

**Por qué importa:** explicabilidad es el #1 que piden auditores
financieros y CV reviewers.

**Esfuerzo:** M · **Prioridad:** media · **Compatible:** sí.

### A10. Feature store local

**Qué:** cuando varias estrategias necesitan los mismos features
(SMA, RSI, ATR, regime), hoy se recalculan cada vez. Feature store
con cache (¡ahí va el `borsenhirn/cache/`!) reduce recálculo a 0.
`feast` overkill — implementación casera con Redis es suficiente.

**Esfuerzo:** M · **Prioridad:** media · **Compatible:** sí.
**Depende:** integrar cache nuevo (B2 abajo).

---

## B) MEJORAS DE CÓDIGO

### B1. Connection pooling Postgres

**Qué:** hoy cada `_get_conn()` abre conexión nueva. Postgres soporta
~100 conexiones por default — con 44 símbolos × queries por ciclo,
podés agotar el pool. Usar `psycopg2.pool.ThreadedConnectionPool`.

**Por qué importa:** latencia y estabilidad. En SaaS es obligatorio.

**Esfuerzo:** S · **Prioridad:** alta · **Compatible:** sí.

### B2. Integrar `borsenhirn/cache/` al `data_fetcher`

**Qué:** lo que dejaste opcional en RATE_LIMITING.md. Wrap
`DataFetcher.get_historical` con `cache_bars(cache)`. 5 líneas. Reduce
hits a Alpaca 80%+ en backtest/scanner.

**Esfuerzo:** S · **Prioridad:** alta · **Compatible:** sí.
**Depende:** cleanup de R-3 (documentar primero el estado).

### B3. Rate limiter middleware en FastAPI

**Qué:** snippet listo en RATE_LIMITING.md. 30 líneas en
`borsenhirn/api/main.py`.

**Esfuerzo:** S · **Prioridad:** media · **Compatible:** sí.

### B4. Structured logging con contexto

**Qué:** migrar de `logger.info(f"trade {symbol} ...")` a
`logger.info("trade_executed", extra={"symbol": s, "tenant_id": t,
"action": a})` + `python-json-logger` para output JSON.

**Por qué importa:** indispensable para que un Loki/Elasticsearch
pueda filtrar/agregar. Hoy los logs son texto-only.

**Esfuerzo:** M · **Prioridad:** media · **Compatible:** sí.

### B5. Métricas Prometheus-compatibles

**Qué:** exponer `/metrics` con `prometheus-client`. Counters:
`bh_trades_total{symbol,side,tenant}`, histograms:
`bh_order_latency_seconds`, `bh_alpaca_request_seconds`. Gauges:
`bh_positions_open`, `bh_equity_usd`.

**Esfuerzo:** S · **Prioridad:** media · **Compatible:** sí.

### B6. Pre-commit hooks

**Qué:** `.pre-commit-config.yaml` con `ruff`, `ruff format`, `mypy`,
`pytest -q --co` (collection only). Garantiza que nadie commitea con
imports muertos / lint warnings.

**Esfuerzo:** S · **Prioridad:** alta · **Compatible:** sí.

### B7. Limpiar 37 unused imports

**Qué:** `ruff check --fix`. 1 comando.

**Esfuerzo:** S (15 min) · **Prioridad:** alta · **Compatible:** sí.

### B8. Mover archivos legacy a `legacy/`

**Qué:** lo de A-3 arriba. ~163 KB de cleanup.

**Esfuerzo:** S · **Prioridad:** media · **Compatible:** sí.

### B9. Retries con backoff exponential vía `tenacity`

**Qué:** hoy `data_fetcher` tiene retry lineal. `tenacity` da exponential
backoff + jitter + circuit breaker en una línea.

**Esfuerzo:** S · **Prioridad:** media · **Compatible:** sí.

### B10. Type hints en M1-M5

**Qué:** los módulos AI casi no tienen types. `mypy --strict
borsenhirn/ml/` ya pasa, pero los M* no. Agregar.

**Esfuerzo:** M · **Prioridad:** baja · **Compatible:** sí.

### B11. Dataclasses para `Signal`, `Order`, `Position`

**Qué:** hoy son dicts. `@dataclass class Signal` + validación con
Pydantic. Más legible, menos errores tipográficos.

**Esfuerzo:** M · **Prioridad:** media · **Compatible:** sí (refactor
gradual).

### B12. Vectorización del scanner

**Qué:** scanner itera 44 símbolos serial. Async con `asyncio.gather`
o threading reduce 44× lookups secuenciales a paralelos.

**Esfuerzo:** S · **Prioridad:** media · **Compatible:** sí.

---

## C) AGREGADOS — production-ready de verdad

### C1. Health endpoint `/health` en FastAPI

**Qué:** ya tenés `borsenhirn.safety.health.get_health_snapshot`
escrito. Falta wirearlo a `bot_api.py` (FastAPI). 10 líneas.

**Esfuerzo:** S · **Prioridad:** alta · **Compatible:** sí.

### C2. Uptime monitoring con Uptime Kuma o UptimeRobot

**Qué:** apuntar el monitor al `/health` cada 60s. Free tier alcanza.
Te avisa por email/discord si el bot deja de responder >2 min.

**Esfuerzo:** S (setup en 10 min) · **Prioridad:** alta.

### C3. Backups automáticos Postgres

**Qué:** cron diario que hace `pg_dump | gzip > backup-YYYYMMDD.sql.gz`
y lo sube a S3 (o Backblaze B2 que es 4× más barato). Retención 30 días.

**Esfuerzo:** S · **Prioridad:** alta · **Compatible:** sí.

### C4. Restore probado mensualmente

**Qué:** script que descarga el último backup, lo restaura en un
Postgres efímero (Docker), corre 5 queries de validación, lo destruye.
Cron mensual.

**Por qué importa:** "tengo backups" sin "los probé" no es backup.

**Esfuerzo:** M · **Prioridad:** media · **Compatible:** sí.

### C5. Runbooks

**Qué:** carpeta `docs/runbooks/` con 6-8 markdown:
- `bot-crashed.md` (logs a revisar, cómo reiniciar)
- `postgres-down.md`
- `alpaca-rate-limited.md`
- `kill-switch-active.md` (cómo investigar y clear)
- `model-drift-alert.md`
- `redis-down.md`

**Esfuerzo:** S · **Prioridad:** media · **Compatible:** sí.

### C6. Master key rescue plan

**Qué:** documento + script para restaurar `BORSENHIRN_MASTER_KEY` desde
un password manager. Sin esto, si tu disco se rompe, perdés todas las
credenciales encriptadas.

**Esfuerzo:** S · **Prioridad:** alta (cuando empiece a haber
credenciales reales encriptadas) · **Compatible:** sí.

### C7. Dockerización completa con `docker-compose.yml`

**Qué:** el `docker-compose.yml` actual es minimal. Completar con
servicios: postgres, redis, bot, api, dashboard. Health checks +
restart policies.

**Esfuerzo:** M · **Prioridad:** alta · **Compatible:** sí (testing
en otro env).

### C8. CI con `--cov-fail-under` más estricto

**Qué:** hoy CI corre con `--cov-fail-under=60`. Subirlo a 70 (módulos
de safety/ y ml/ pasan 90%+; lo que baja el promedio es el código
viejo). Definir gate por módulo en `pyproject.toml`.

**Esfuerzo:** S · **Prioridad:** baja · **Compatible:** sí.

### C9. Feature flagging

**Qué:** toggle features en runtime sin redeploy. `borsenhirn/flags.py`
con dict en Postgres. Ejemplo: `if flag("enable_meta_model"): ...`.

**Esfuerzo:** S · **Prioridad:** baja · **Compatible:** sí.

---

## D) DISEÑO / ARQUITECTURA

### D1. `main.py` está creciendo demasiado

**Síntoma:** 31 KB, 600+ líneas. Hace: arranque, loop principal, MI
PLAN handler, retraining schedule, kill switch checks, sells, buys,
TP/SL.

**Sugerencia:** extraer:
- `borsenhirn/bot/loop.py` (BotLoop class con `run()`)
- `borsenhirn/bot/handlers/scanner.py` (handle_buys, handle_sells)
- `borsenhirn/bot/handlers/exits.py` (TP/SL/trailing)
- `borsenhirn/bot/handlers/plan.py` (lo de `_handle_plan`)

**Esfuerzo:** M · **Prioridad:** media · **Compatible:** sí (refactor
incremental, conservar `main.py` como entry point).

### D2. `bot_memory_pg.py` — God object

**Síntoma:** 31 KB, una sola clase BotMemory con ~30 métodos
heterogéneos.

**Sugerencia:** dividir en:
- `borsenhirn/persistence/trades.py` (TradeStore)
- `borsenhirn/persistence/metrics.py` (MetricsStore)
- `borsenhirn/persistence/ml.py` (MLMetricsStore + retrain schedule)
- `borsenhirn/persistence/regime.py` (RegimeStatsStore)
- `borsenhirn/persistence/symbols.py` (SymbolScoresStore)
- `BotMemory` queda como facade que compone los anteriores
  (back-compat).

**Esfuerzo:** M · **Prioridad:** media · **Compatible:** sí (facade).

### D3. M1-M5 son módulos enormes

`m2_analyst.py` 46 KB, `m4_whale.py` 43 KB. Cada uno con muchas
funciones helper que podrían ser sub-módulos.

**Sugerencia:** convertir cada Mx en un package: `borsenhirn/m4_whale/`
con `loader.py`, `parser.py`, `scorer.py`. Hoy `borsenhirn/m4_whale/`
existe pero solo con `__init__.py`.

**Esfuerzo:** L (cada uno es M, son 4 módulos) · **Prioridad:** baja.

### D4. Patrón Adapter para brokers

**Qué:** hoy `data_fetcher` y `execution` están acoplados a Alpaca.
Cuando quieras usar IBKR (>$25k cuenta) o Polygon (data), refactor
masivo. Mejor: `borsenhirn/brokers/base.py` con interface +
implementaciones concretas.

**Esfuerzo:** M · **Prioridad:** baja (YAGNI hasta que lo necesites).

### D5. Acoplamiento bot ↔ Postgres

**Qué:** todo el bot hardcodea `psycopg2`. Si quisieras testear con
SQLite in-memory, no se puede. Pasar al patrón Repository:
`MemoryRepository` (interface) → `PostgresMemoryRepository`,
`SqliteMemoryRepository`.

**Esfuerzo:** L · **Prioridad:** baja.

### D6. Tests nuevos vs `test_core.py` (unittest)

**Qué:** los tests viejos usan `unittest.TestCase`, los nuevos pytest
puro. Convivencia OK pero inconsistente.

**Sugerencia:** migrar `test_core.py` a pytest puro (~1h).

**Esfuerzo:** S · **Prioridad:** baja.

### D7. Doc del repo: separar "lo que está integrado" de "lo que está disponible"

**Qué:** R-3 arriba — README necesita una sección clara de
"integration status" para que el lector entienda que cache/vault/tenancy
son foundation modules, no usados por el bot legacy.

**Esfuerzo:** S (15 min) · **Prioridad:** alta.

---

# 🎯 TOP 5 RECOMENDADO (orden de ejecución)

Mi opinión, mirando: (a) cierre de cabos sueltos del propio sprint,
(b) impacto en bot vivo, (c) preparación para job/internships,
(d) máximo ROI por hora de trabajo.

### #1 — Limpieza inmediata (un sprint cortísimo, 1-2 días)

Bundle: **R-1 + R-2 + B-7 + B-8 + D-7**.

- Rotar webhook + arreglar `.env.example` (R-1).
- Crear los 2 scripts faltantes (`ks_admin.py`, `check_rls_coverage.py`)
  + arreglar typo del TESTS.md (R-2).
- `ruff check --fix` (B-7).
- Mover legacy a `legacy/` (B-8).
- Agregar sección "integration status" al README (D-7).

**Por qué primero:** son cabos sueltos del sprint que acabamos de
cerrar. Dejarlos abiertos los olvidás en un mes. Total: ~3 horas de
trabajo, cero riesgo.

### #2 — Cache integration + Connection pool + Pre-commit hooks

Bundle: **B-1 + B-2 + B-6**.

- Connection pool Postgres (B-1) — antes que el bot agote conexiones.
- Wrap `data_fetcher.get_historical` con `cache_bars` (B-2) — usás
  por fin el módulo cache que escribimos.
- Pre-commit con ruff + mypy (B-6) — evita regresiones.

**Por qué segundo:** mejoras de performance + DX. Una semana.
**Por qué este orden:** B-1 mejora estabilidad, B-2 mejora costo, B-6
te ahorra futuras revisiones.

### #3 — Health endpoint + Uptime monitoring + Runbooks

Bundle: **C-1 + C-2 + C-5 + B-5**.

- Wirear `/health` a FastAPI (C-1).
- Configurar Uptime Kuma o UptimeRobot apuntando ahí (C-2).
- Escribir 6-8 runbooks (C-5).
- Métricas Prometheus en `/metrics` (B-5).

**Por qué tercero:** "operations stack" mínimo. Cuando el bot se rompa
a las 3 AM (y se romperá), te enterás Y sabés qué hacer. Esto vale
ORO en una entrevista de SRE/MLOps. Una semana.

### #4 — MLflow lite + Experiment tracking

**A-2.**

- `pip install mlflow`, `mlflow ui` local, instrument `validate_model.py`
  + `validate_meta_model.py` + retrain del bot.
- Cada modelo entrenado deja artifact + métricas en MLflow.

**Por qué cuarto:** es el hito que más sube tu CV de "estudiante con
proyecto" a "junior ML Engineer". Concreto: en una entrevista podés
abrir MLflow UI y mostrar 50 modelos trackeados con métricas, lineage
de features, comparación A/B. Una semana.

### #5 — Anomaly detection en data ingest + Backups Postgres + Master key rescue

Bundle: **A-1 + C-3 + C-6**.

- Anomaly filter en `data_fetcher` (A-1) — defensa en profundidad.
- `pg_dump` diario + retention 30d (C-3).
- Documentar + script para restaurar master key desde password manager
  (C-6).

**Por qué quinto:** triple defense para que el bot pueda **fallar
seguro**. Esto es lo que separa "demo en mi laptop" de "producción".
Una semana.

---

## 📝 Notas para sprint dashboard (registro, NO actuar ahora)

Durante la verificación final post-fixes detectamos que dos archivos de
test del dashboard están rotos y bloquean `pytest` collection. **No se
tocaron** porque la regla del sprint actual es "dashboard NO se modifica".
Quedan documentados acá para que el sprint dedicado de dashboard los
incluya en su scope.

### D-S1. `tests/test_dashboard_bitacora.py:581`

```
NameError: name 'RCE_MAP' is not defined
```

Símbolo `RCE_MAP` referenciado pero no definido en el módulo. Probable
import faltante o typo. Bloquea pytest collection del archivo entero.

### D-S2. `tests/test_dashboard_smoke.py:299`

```
IndentationError: unexpected indent
  cwd=str(REPO_ROOT),
```

Indentation extra en un kwarg que rompe el parse del módulo. Probable
edit manual que dejó un nivel de espacios extra. Bloquea pytest
collection.

### Mitigación temporal aplicada

`pyproject.toml [tool.pytest.ini_options].addopts` lleva dos
`--ignore=` para excluir esos archivos del collection. El resto de
los 307+ tests vuelve a correr normalmente. **Acción al abrir sprint
dashboard:** quitar esos `--ignore` y arreglar los 2 errores reales.

---

## Lo que NO recomendaría hacer en los próximos 2-3 sprints

- **Fase B de Multi-tenancy** — esperá a tener un usuario externo
  pidiéndolo.
- **Datos alternativos premium** (LunarCrush pago, Unusual Whales) —
  esperá a tener edge demostrado.
- **Refactor masivo `main.py` o `bot_memory_pg.py`** — funcionan,
  el ROI de tocarlos es bajo hasta que metas multi-tenancy real.
- **Dashboard rework** — ya dijiste sprint dedicado.
- **Type hints completos en M1-M5** — bajo impacto vs el esfuerzo.

---

## Decisión sobre fixes inmediatos

Gap 1-8 están limpios — la auditoría no encontró regresiones de los
sprints anteriores. Los 3 hallazgos rojos son cabos sueltos puntuales
del sprint reciente, no roturas. Los amarillos son cosmética
mejorable.

**Recomendación:** ejecutar el TOP #1 (limpieza inmediata) en el
próximo sprint corto, después decidir entre #2 vs #4 según prioridad
de carrera vs operación.

Si querés, en este mismo turno te puedo aplicar los fixes de R-1, R-2,
B-7, B-8, D-7 — son rápidos y dejan el repo 100% limpio.
