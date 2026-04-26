# Cache + Rate limiting — Gap 5

**Objetivo:** reducir hits redundantes a APIs externas (Alpaca, Claude,
FRED, Finnhub, Alpha Vantage, etc.) y limitar uso por usuario para
proteger costos / cuotas / proteger al bot de spikes.

---

## Componentes entregados

### `borsenhirn/cache/client.py` — `RedisCache`

Wrapper sobre `redis-py` con cliente **inyectado** (no construido
adentro). Eso permite tests con `fakeredis` sin Redis real.

```python
from borsenhirn.cache import create_default_cache

cache = create_default_cache()        # lee REDIS_HOST/PORT/DB de env
cache.set("k", {"x": 1}, ttl=60)
cache.get("k")                          # → {"x": 1}
cache.delete("k")
cache.invalidate_namespace("alpaca:bars")
cache.stats.snapshot()                  # hits/misses/sets/deletes
```

**Garantías importantes:**
- Si Redis cae, `get()` devuelve `None`/default y `set()` devuelve
  `False`. **Nunca lanza** — fail-soft. El cache nunca debe romper el
  flujo principal del bot.
- Serialización JSON automática para dict/list, prefijos `int:`/`str:`/`bool:`/`float:` para tipos primitivos (sin pérdida de tipo).
- Métricas thread-safe (`hits`, `misses`, `hit_ratio`).

### `borsenhirn/cache/decorators.py` — `@cached`

Decorator para envolver funciones puras.

```python
from borsenhirn.cache import create_default_cache, cached

cache = create_default_cache()

@cached(cache, key_fn=lambda symbol, tf: f"{symbol}:{tf}",
        ttl=300, namespace="alpaca")
def get_historical(symbol, tf):
    # ... call Alpaca API
    return df

df = get_historical("SPY", "1Hour")          # miss → API + cache
df = get_historical("SPY", "1Hour")          # hit  → cache
df = get_historical("SPY", "1Hour", skip_cache=True)  # bypass

# Invalidación
get_historical.invalidate("SPY", "1Hour")    # 1 entry
get_historical.invalidate_all()              # todas las entries de la fn
```

**Reglas:**
- No cachea `None` ni containers vacíos (`{}`, `[]`).
- `skip_kwarg` permite forzar miss sin cambiar la API de la función.
- `invalidate(*args, **kwargs)` usa la misma `key_fn` para localizar.

### `borsenhirn/cache/rate_limiter.py` — `RateLimiter`

Sliding-window con sorted sets de Redis. Tier-aware.

```python
from borsenhirn.cache import RateLimiter, RateLimitConfig, Tier

rl = RateLimiter(cache, limits={
    Tier.FREE: RateLimitConfig(max_requests=60, window_seconds=60),
    Tier.PRO: RateLimitConfig(max_requests=600, window_seconds=60),
    Tier.ENTERPRISE: RateLimitConfig(max_requests=6000, window_seconds=60),
})

# Chequeo
result = rl.check(subject="user_123", action="claude_api", tier=Tier.FREE)
if not result.allowed:
    # devolver 429 con headers result.to_headers()
    ...

# O con excepción
try:
    rl.check_or_raise("user_123", "alpaca_orders", Tier.PRO)
except RateLimitExceeded as exc:
    return JSONResponse(429, exc.result.to_headers())

# Headers estilo GitHub/Stripe
result.to_headers()
# → {"X-RateLimit-Limit": "60", "X-RateLimit-Remaining": "42",
#     "X-RateLimit-Reset": "1735689600", "Retry-After": "0", ...}
```

**Diseño:**
- **Sliding window** con sorted set: cada request es un member con
  score = epoch_ms. Limpieza pasiva con `ZREMRANGEBYSCORE`.
- **Atomic** vía pipeline (multi-exec).
- **Tier-aware**: el mismo subject puede tener distintos límites según
  el plan que pague.
- **Action-aware**: `claude_api`, `alpaca_orders`, `dashboard_query`
  son buckets independientes.
- **Weight**: requests pesados (Claude con 4k tokens) pueden
  contar como `weight=3`.
- **Fail-open** si Redis cae: el rate limiter NO debe ser SPOF. Si te
  importa fail-closed, ajustá `client is None` en `check()`.

### `borsenhirn/cache/api_cache.py` — helpers para APIs externas

TTLs pre-calibrados por tipo de dato. Importá y envolvé tus funciones
existentes:

```python
from borsenhirn.cache.api_cache import (
    cache_bars, cache_latest_price, cache_macro,
    cache_news, cache_sec_filings, cache_llm_response,
    cache_whale_13f,
    TTL_BARS_INTRADAY,    # 300s
    TTL_LATEST_PRICE,     #  15s
    TTL_MACRO,            # 3600s
    TTL_LLM,              #  900s
)
```

---

## TTLs sugeridos (calibrados para trading 1h)

| Dato | TTL | Razón |
|---|---|---|
| Bars intradía (Alpaca) | **300s** | Una nueva barra cada hora, 5min margen |
| Latest price | **10-30s** | Tick rate; pero si entrás cada 30s no perdés señal |
| FRED macro series | **3600s (1h)** | Series mensuales/trimestrales |
| News (NewsAPI) | **120s** | Headlines cambian rápido |
| SEC filings (EDGAR) | **1800s (30m)** | Diarias |
| LLM responses (Claude) | **900s (15m)** | Mismo prompt = misma respuesta útil |
| Whale 13F | **14400s (4h)** | Trimestrales |
| Alpaca bars históricas (>30 días viejas) | **86400s (1 día)** | Cambian solo por adjustments |

---

## Setup

### 1. Verificar que Redis está corriendo

```powershell
# Windows con WSL2:
wsl -d Ubuntu redis-cli ping     # debería responder PONG

# O si tenés Redis instalado nativo en Windows:
redis-cli ping
```

Si no tenés Redis, instalación rápida en WSL2:

```bash
sudo apt install redis-server
sudo service redis-server start
redis-cli ping
```

### 2. Verificar variables de entorno (`.env`)

```env
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
```

### 3. Smoke test

```powershell
python scripts/cache_demo.py
```

Esperado:

```
[1] Redis conectado

==================================================
  [2] Round-trip set/get
==================================================
  OK string
  OK dict
  OK list

==================================================
  [3] @cached decorator (latencia)
==================================================
  miss: 51.3ms
  hit:  0.7ms (75x más rápido)
  función ejecutada 1 veces (esperado 1)
  OK invalidate

==================================================
  [4] RateLimiter — Tier FREE limit=5/60s
==================================================
  req 1: ALLOW  remaining=4 retry_after=0s
  req 2: ALLOW  remaining=3 retry_after=0s
  req 3: ALLOW  remaining=2 retry_after=0s
  req 4: ALLOW  remaining=1 retry_after=0s
  req 5: ALLOW  remaining=0 retry_after=0s
  req 6: BLOCK  remaining=0 retry_after=60s
  req 7: BLOCK  remaining=0 retry_after=60s
  OK other_user no afectado (allowed=True)

[5] invalidate_namespace
  borradas 4 keys del namespace 'bars'

[6] Stats finales
            hits: 3
          misses: 6
            sets: 5
         ...
        hit_ratio: 0.333

DEMO COMPLETO ✓
```

### 4. Tests

```powershell
pytest tests/test_cache_client.py tests/test_cache_decorators.py tests/test_rate_limiter.py -v
# Esperado: 60 tests pasando
```

Estos tests usan `fakeredis` y NO requieren Redis corriendo.

---

## Integración con FastAPI (snippet listo para copiar)

En tu `borsenhirn/api/main.py` (o donde tengas FastAPI):

```python
from fastapi import FastAPI, Request, Response, HTTPException
from borsenhirn.cache import (
    create_default_cache, RateLimiter, Tier, RateLimitExceeded,
)

app = FastAPI()

# Singleton: una vez al arrancar
cache = create_default_cache(namespace="bh_api")
rl = RateLimiter(cache)

def get_user_tier(request: Request) -> Tier:
    """Resolvé el tier desde el JWT/sesión. Default FREE."""
    return Tier.FREE   # placeholder

def get_user_id(request: Request) -> str:
    """Subject único: user_id o IP."""
    return request.headers.get("X-User-Id") or request.client.host

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    subject = get_user_id(request)
    tier = get_user_tier(request)
    action = request.url.path   # bucket por endpoint
    result = rl.check(subject, action, tier)
    if not result.allowed:
        return Response(
            status_code=429,
            content="Rate limit exceeded",
            headers=result.to_headers(),
        )
    response = await call_next(request)
    for k, v in result.to_headers().items():
        response.headers[k] = v
    return response
```

---

## Integración con `data_fetcher.py`

```python
from borsenhirn.cache import create_default_cache
from borsenhirn.cache.api_cache import cache_bars

cache = create_default_cache()

class DataFetcher:
    def __init__(self, ...):
        ...
        # Wrap el método costoso UNA vez al construir
        self.get_historical = cache_bars(cache)(self.get_historical)
```

Después llamás `fetcher.get_historical(...)` igual que siempre — la
diferencia es que se cachea automáticamente.

---

## Checklist Gap 5

- [ ] `redis-server` corriendo (verificá con `redis-cli ping`).
- [ ] `pip install redis fakeredis` (en `requirements*.in` ya están).
- [ ] `python scripts/cache_demo.py` → 7 secciones OK.
- [ ] `pytest tests/test_cache_*.py tests/test_rate_limiter.py` → 60 pasan.
- [ ] (Opcional) Wrap `data_fetcher.get_historical` con `cache_bars`.
- [ ] (Opcional) Wrap llamadas a Claude con `cache_llm_response`.
- [ ] (Opcional) Middleware FastAPI con `RateLimiter` + tier=FREE
      por default hasta que tengas billing.

Cuando todo verde → Gap 5 cerrado.

---

## Decisiones de diseño explícitas

### Por qué fail-open en RateLimiter

Si Redis cae, **permitir todo** es preferible a bloquear todo:
- El bot principal sigue operando (no se pierde dinero por inacción).
- Las APIs externas tienen sus propios rate limits — nadie te va a
  banear de Alpaca por unos minutos sin tu rate limiter.
- Logs marcan el evento para investigación posterior.

Si tu caso requiere fail-closed (regulatorio, etc.), buscá
`# fail-open` en `rate_limiter.py:check()` y cambialo.

### Por qué cache fail-soft

Igual razonamiento: si Redis cae mientras el bot está operando, querés
que las queries vayan directo a la API origen, no que el bot se
detenga. Las stats te avisan que algo anda mal sin romper la operación.

### Por qué namespaces

`invalidate_namespace("alpaca:bars")` te permite borrar todas las bars
cacheadas (después de un retroactive split, por ejemplo) sin tocar
otros caches. Patrón estándar.

### Por qué sliding window vs token bucket

Sliding window es más justo para usuarios humanos (no permite "guardar
tokens" para spikes). Token bucket es mejor para máquinas con bursts
predecibles. Para SaaS de retail, sliding window es la elección
estándar (Stripe, GitHub, Twitter usan variantes de esto).

---

## Para CV / portfolio

Línea defendible:

> "Cache layer sobre Redis con cliente inyectable (testeable con
> fakeredis), decorator `@cached` con invalidación selectiva por
> namespace, rate limiter sliding-window tier-aware (free/pro/enterprise)
> con headers estilo Stripe, fail-soft + fail-open por diseño, 60 unit
> tests + smoke test contra Redis real."
