# Plan de producción — Börsenhirn roadmap v1

**Fecha:** 2026-04-24
**Contexto:** diagnóstico ML terminado, toca pasar al resto de gaps críticos identificados.

---

## Estado de los 8 gaps originales

| # | Gap | Estado | Conclusión |
|---|---|---|---|
| 1 | ML / AUC=0.98 / walk-forward | **CERRADO** | No había AUC=0.98. Modelo RF real tiene AUC=0.50 (ruido) con/sin meta-features. No es el driver del bot. Batería de validación queda en `borsenhirn/ml/` como herramienta. |
| 2 | Circuit breakers + kill switches | **PENDIENTE P0** | Existe `circuit_breaker.py` y `risk_manager.py` — hay que auditar qué falta. |
| 3 | Seguridad de secrets | **PENDIENTE P1** | Solo envs; no hay encryption at rest para secrets de usuarios SaaS. |
| 4 | Multi-tenancy | **PENDIENTE P2** | Arquitectura actual es single-user. Costoso retroactivo. |
| 5 | Rate limiting + caching | **PENDIENTE P2** | Redis en stack pero no usado para rate-limit por tier. |
| 6 | Compliance / disclaimers | **PENDIENTE P1** | Cero disclaimer legal. Obligatorio antes del primer usuario. |
| 7 | Reproducibilidad ML | **PENDIENTE P2** | requirements.txt sin hashes, no lock, no Python version pin. |
| 8 | Tests del trading engine | **PENDIENTE P1** | Hay `tests/test_core.py` — auditar coverage real. |

---

## Priorización: qué duele hoy vs qué duele después

**P0 (el bot está vivo en paper, esto puede costar dinero real mañana):**
- Gap 2 — Circuit breakers y alertas Telegram. Si el bot se descontrola hoy, tú no te enteras. Riesgo máximo.

**P1 (antes del primer usuario externo):**
- Gap 6 — Disclaimers legales. Tomar plata de terceros sin esto es temerario.
- Gap 8 — Tests. Si no hay red de seguridad, no puedes refactorizar ni aceptar PRs.
- Gap 3 — Secrets encryption. Obligatorio antes de pedir claves Alpaca a usuarios.

**P2 (para SaaS real):**
- Gap 4 — Multi-tenancy. Bloquea escalar pero no a v1.
- Gap 5 — Rate limiting. Aparece a los 10-20 usuarios, no antes.
- Gap 7 — Reproducibilidad. Importa para CV y para defender resultados.

---

## Gap 2 — Circuit breakers + Telegram alerts

**Lo que ya existe:**
- `circuit_breaker.py` con `alpaca_cb` usado en `data_fetcher.py` para la API. Bien para outages de Alpaca.
- `risk_manager.py` existe pero no revisé qué hace aún.

**Lo que falta (hipótesis — a validar leyendo):**
- Kill switch por pérdida diaria acumulada (cierra todo y deshabilita trading si PnL < -MAX_DAILY_LOSS_PCT).
- Kill switch por drawdown rolling 7 días.
- Kill switch por error rate (si Alpaca da >N errores en M minutos, halt).
- Sanity check pre-orden: quantity razonable, precio no zero, símbolo en watchlist.
- Alertas Telegram para: FILL, REJECT, HALT, KILL, ERROR crítico, cambio de régimen.
- Health endpoint `/health` para monitoring externo (UptimeRobot).

**Plan:**
1. Auditar `risk_manager.py` y `circuit_breaker.py`. Identificar gaps vs la lista.
2. Crear `borsenhirn/safety/` con módulos:
   - `killswitch.py` — clase `KillSwitch` con reglas independientes.
   - `telegram_alerts.py` — wrapper `python-telegram-bot` con rate-limit (no spamear).
   - `health.py` — endpoint `/health` para FastAPI + check automático.
3. Integrar `KillSwitch.check()` en el loop principal de `main.py` antes de cada orden.
4. Persistir estado del kill switch en Postgres (si reinicia el proceso, sabe que estaba en HALT).

**Estimado:** 3-5 días.

**Criterios de aceptación:**
- Test manual: si fuerzo pérdida del 6% en simulación, el bot se detiene y envía alerta.
- Test manual: si mato la red durante 5 min, el bot pausa y avisa.
- `/health` devuelve 200 con JSON: `{status, regime, positions, pnl_today, last_error}`.

---

## Gap 6 — Compliance / disclaimers legales

**Lo que falta:**
- Disclaimer fuerte en README, dashboard, landing.
- Términos de uso (ToS) que dejen claro: "educational purposes, not financial advice".
- Privacy policy (qué datos guardas, por cuánto tiempo).
- Checkbox opt-in para usuarios.
- En Colombia: revisar SFC (Superfinanciera) para ver si dar señales paga cae en "asesor de inversión". En US: evitar palabras como "guaranteed", "advice", "recommendation". Usar "signal", "educational", "for informational purposes".
- Geofence opcional: bloquear IP de países donde SFC/SEC/FCA sean estrictos.

**Plan:**
1. Escribir `legal/DISCLAIMER.md`, `legal/TERMS.md`, `legal/PRIVACY.md` con plantilla conservadora.
2. Mostrar disclaimer en cada inicio del dashboard Streamlit (banner amarillo top).
3. Checkbox obligatorio en signup "he leído y acepto los términos".
4. Auditar lenguaje en todo el UI: reemplazar "recomendación" por "señal educativa", "COMPRAR" por "oportunidad detectada", etc.
5. Bonus: geofence con `GeoIP2-City` si decides no aceptar usuarios US/UE.

**Estimado:** 2 días (texto + integración UI).

**Criterios:**
- Ningún string del UI dice "recomendación de inversión" o "guaranteed".
- El dashboard muestra banner visible.
- Imposible hacer signup sin marcar el checkbox.

---

## Gap 8 — Tests del trading engine

**Lo que ya existe:**
- `tests/test_core.py`. Hay que leer y medir coverage.

**Lo que probablemente falta:**
- Tests de `strategy.py` generando señales (buy/sell/hold con varios inputs).
- Tests de `risk_manager.py` con escenarios de pérdida límite.
- Tests de `execution.py` con mocks de Alpaca (ordenes fills, rejects, partial fills).
- Tests de `regime_detector.py` con series sintéticas que deberían activar cada régimen.
- Property-based tests con `hypothesis` para invariantes: "shares >= 0 siempre", "stop_loss < entry siempre".

**Plan:**
1. `pip install pytest pytest-cov hypothesis --break-system-packages`
2. Medir baseline: `pytest --cov=. --cov-report=html`
3. Apuntar a 70%+ cobertura en: `strategy`, `risk_manager`, `execution`, `regime_detector`, `borsenhirn/safety/*`.
4. Property-based test para `strategy.generate_signal` con dfs sintéticos.
5. Meter en `.github/workflows/ci.yml` para que corra en cada push.

**Estimado:** 3-4 días.

**Criterios:**
- Coverage > 70% en los módulos de trading.
- CI corre `pytest` en cada commit.
- Al menos 5 tests property-based pasando.

---

## Gap 3 — Secrets encryption

**Lo que falta:**
- Claves Alpaca de usuarios SaaS almacenadas en DB: necesitan encryption at rest.
- Master key: en env var local → Vault / AWS Secrets Manager en prod.
- Rotación de claves: cómo reencriptar toda la DB si cambias el master.

**Plan:**
1. `pip install cryptography` (ya instalado en tu stack ML probablemente).
2. `borsenhirn/security/vault.py` con:
   - `encrypt(plaintext, master_key) -> bytes`
   - `decrypt(ciphertext, master_key) -> str`
   - Usa `cryptography.fernet.Fernet` (AES-128-CBC + HMAC).
3. Tabla `user_credentials`:
   ```sql
   CREATE TABLE user_credentials (
       user_id uuid PRIMARY KEY,
       alpaca_key_ciphertext bytea NOT NULL,
       alpaca_secret_ciphertext bytea NOT NULL,
       created_at timestamptz DEFAULT now(),
       updated_at timestamptz DEFAULT now()
   );
   ```
4. Master key en env var `BORSENHIRN_MASTER_KEY`. En prod: AWS Secrets Manager o Doppler.
5. Rotación: script que lee todas las rows, reencripta con nueva master, reemplaza.

**Estimado:** 2 días.

**Criterios:**
- Ninguna API key en plaintext en DB.
- Test de roundtrip encrypt/decrypt.
- Documentado cómo rotar master key.

---

## Gap 4 — Multi-tenancy

**Lo que falta:**
- Tablas actuales sin `tenant_id` (o `user_id`).
- Memoria de "Hirn" (M5) en `bot_memory_pg.py` compartida globalmente.
- Row-Level Security desactivado.

**Plan:**
1. Migración Alembic: añadir `user_id uuid` a tablas: `trades`, `positions`, `equity_snapshots`, `hirn_memory`, `signals`, `regime_states`.
2. Backfill `user_id = SYSTEM_USER_UUID` para datos existentes (single-tenant histórico).
3. Activar RLS en Postgres:
   ```sql
   ALTER TABLE trades ENABLE ROW LEVEL SECURITY;
   CREATE POLICY trades_isolation ON trades
       USING (user_id = current_setting('app.current_user_id')::uuid);
   ```
4. Cada conexión debe ejecutar `SET app.current_user_id = '<uuid>'` al inicio.
5. Refactor `bot_memory_pg.py` para aceptar `user_id` en cada query.
6. Tests de aislamiento: crear 2 users, plantar data, confirmar que user A no ve nada de user B.

**Estimado:** 1-2 semanas. Es el gap más pesado.

**Criterios:**
- Test automático que prueba aislamiento de 2 users.
- `explain analyze` muestra que RLS se aplica.
- Dashboard muestra solo data del user autenticado.

---

## Gap 5 — Rate limiting + caching

**Lo que falta:**
- Redis está en stack pero no veo que se use para cache de APIs externas.
- Ninguna rate-limit por tier.

**Plan:**
1. Wrapper `borsenhirn/core/cache.py` con decorator:
   ```python
   @redis_cache(key_fn=lambda s, tf: f"bars:{s}:{tf}", ttl=300)
   def get_historical(...): ...
   ```
2. Cachear: `get_historical`, `market_context.get_full_context`, FRED calls, yfinance calls.
3. Rate limiter por usuario con `slowapi` (FastAPI):
   - Tier free: 60 req/min.
   - Tier pro: 600 req/min.
   - Tier enterprise: sin límite.
4. Budget por tier para APIs costosas (Claude): límite mensual de tokens por user.

**Estimado:** 3-4 días.

**Criterios:**
- `get_historical(SPY, 1Hour)` llamado 1000 veces en 1 min toca Alpaca solo N veces.
- User free que intenta 100 req/min recibe 429.

---

## Gap 7 — Reproducibilidad ML

**Lo que falta:**
- `requirements.txt` sin hashes → instalación no bit-exact.
- No hay Python version pinned.
- `random_state` fijo en `ml_model.py` ✓ pero no auditado en todo el código.

**Plan:**
1. `pip install pip-tools`
2. Crear `requirements.in` con dependencias top-level (sin versiones exactas).
3. `pip-compile --generate-hashes requirements.in` → genera `requirements.txt` con hashes.
4. `.python-version` con `3.14.x` exacto.
5. Audit: grep por `RandomForestClassifier`, `XGBoost`, `KMeans` etc. Asegurar `random_state` en todos.
6. Script `scripts/verify_reproducibility.py` que entrena modelo 2 veces con mismo seed y verifica que output sea bit-identical.

**Estimado:** 1 día.

**Criterios:**
- `pip install -r requirements.txt` es determinístico.
- Dos entrenamientos con mismo seed producen modelos idénticos (hash de bytes).

---

## Orden de ejecución propuesto

```
Semana 1: Gap 2 (circuit breakers + Telegram)      [P0 — seguridad operacional]
Semana 2: Gap 8 (tests al 70% coverage)             [P1 — red para refactor]
Semana 3: Gap 6 (disclaimers + terms)               [P1 — legal block]
Semana 3: Gap 7 (reproducibilidad, pip-compile)     [P1 — 1 día, meter con disclaimers]
Semana 4-5: Gap 3 + Gap 4 (secrets + multi-tenancy) [P1/P2 — infra SaaS]
Semana 6: Gap 5 (rate limiting + Redis cache)       [P2 — pre-lanzamiento]
Semana 7: Auth (Clerk/Supabase) + Stripe MCP        [Monetización]
```

**Total a SaaS MVP:** 7 semanas si dedicas tiempo completo, 3-4 meses si es part-time.

---

## Qué sugiero hacer primero

**Gap 2 — circuit breakers + Telegram.** Una tarde de auditoría, 3-5 días de implementación. Te da:

1. Paz mental: si el bot se rompe a las 3 AM en producción, te enteras por Telegram.
2. Protección de capital: si el bot empieza a hacer trades absurdos (bug mío o tuyo en alguna actualización), se detiene solo.
3. Portfolio-ready: poder decir en una entrevista "el bot tiene kill switches independientes con alertas" vale oro frente a un CV de junior típico.

Después de eso, tests (gap 8), disclaimers (gap 6) y reproducibilidad (gap 7) son las siguientes tres piezas que se pueden hacer relativamente rápido y dejan el proyecto listo para el mundo real.

Gap 3/4/5 son infra SaaS — conviene hacerlos juntos cuando vayas a lanzar la primera beta con usuarios reales.

---

## Notas al margen

- **El AUC=0.98 que describiste originalmente** probablemente fue overfit / measured-on-train. Ya tienes la batería de validación; si vuelves a tocar ML, úsala siempre.
- **El modelo actual no es inútil** — es marginal. Puedes seguir usándolo como *uno de muchos inputs* en `strategy.py`, pero no como el motor principal. Tu motor son las reglas técnicas + el régimen detector.
- **El roadmap de carrera** pide NO ML Engineer sino **ML Ops / Data Engineer** con este proyecto: lo que vende es la infra (circuit breakers, tests, CI, secrets, multi-tenancy, monitoring). Un CV que muestra "escribí un modelo con AUC=0.98" se vuelve sospechoso; uno que muestra "escribí la batería de validación que detecta leakage, kill switches, tests al 80% y deploy CI/CD" vende.
