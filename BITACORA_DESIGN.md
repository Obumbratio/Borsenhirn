# Bitácora Nocturna · Sistema de diseño

**Versión:** v1.0
**Sprint:** rediseño visual completo del dashboard de Börsenhirn
**Estado:** Fase 1 (sistema visual base) y Fase 2 (datos dinámicos) implementadas
**Punto de comparación:** `uploads/borsenhirn_full_dashboard_bitacora_nocturna.html` (mockup objetivo)

---

## 1. Concepto

El dashboard de Börsenhirn ya no es un panel de control genérico. Es la **bitácora nocturna del cerebro** que opera el bot. Cada render es una entrada numerada (Eintrag) del diario que el bot lleva sobre su propia operación. El bot habla en primera persona, recuerda, y firma cada observación con el módulo que la generó.

Tres voces simultáneas, deliberadas:

1. **Alemán técnico** para etiquetas (Vermögen, Konfidenz, Bargeld, Siegrate, Angst·VIX, Leitzins, Bullenmarkt, Beobachtung, Eintrag, Exemplare, Module, Synapsen, Steuerung, Protokoll).
2. **Español castellano** para narrativa y observaciones.
3. **Inglés** para datos crudos (números, %, USD, tickers, fechas técnicas).

Toda etiqueta alemana grande lleva su traducción al español en cursiva pequeña, color atenuado.

---

## 2. Tokens de paleta

Cinco tonos principales más tres acentos. **No existe ningún otro color en el sistema.**

| Token | Hex | Uso |
| --- | --- | --- |
| `bg_noche` | `#0F0D0A` | Fondo principal · noche profunda |
| `bg_tarjeta` | `#1A1610` | Tarjetas y secciones |
| `texto_perg` | `#E8DEC9` | Texto principal · pergamino antiguo |
| `verde_oliva` | `#9BB37E` | Ganancia, status OK, regime BULL |
| `rojo_terra` | `#A86850` | Pérdida, status crítico |
| `ambar` | `#C9A96A` | Metadata, regime SIDEWAYS, acentos especiales |
| `rojo_profundo` | `#7A3525` | Regime PANIC |
| `linea` | `#3A3025` | Separadores, bordes |
| `texto_suave` | `#A89878` | Texto secundario, etiquetas, metadata |

**Reglas duras del color:**

- Verde **solo** representa ganancia o estado saludable.
- Rojo terracota **solo** representa pérdida.
- Ámbar **solo** representa regime/metadata/acción especial.
- Cero azul, cero cyan, cero magenta, cero neón, cero blancos puros.
- Cero gradients excepto el sutil del sparkline de Vermögen.
- Cero shadows, cero glows.

---

## 3. Tipografía

Dos familias, dos voces, dos pesos. Nada más.

| Familia | Cuándo | Ejemplos |
| --- | --- | --- |
| **Georgia** (serif) | Narrativa: títulos, observaciones del bot, citas, tickers, números headline | "Bitácora del cerebro", "$107,878.51", "CVX", observaciones |
| **Inter** (sans-serif) | Metadata: etiquetas alemanas, fechas técnicas, captions, botones, números secundarios | "— DAS VERMÖGEN · EQUITY", "EINTRAG №412", "FIRMA · M2.ANALYST" |

**Pesos permitidos:** 400 regular, 600 semibold. Nunca 700.

**Escala:**

| px | Familia | Uso |
| --- | --- | --- |
| 32 | Georgia 600 | Equity headline |
| 24 | Georgia 600 | Título principal "Bitácora del cerebro" |
| 16 | Georgia 600 | Subtítulos de sección ("Exemplare offen") |
| 14.5 | Georgia italic | Observaciones del bot |
| 13.5 | Georgia italic | Burbujas Hirn |
| 11–13 | Georgia italic / Inter | Datos secundarios, traducciones |
| 9–10 | Inter caps ls 1.5–2.5px | Etiquetas alemanas |
| 8–9 | Inter caps ls 2px | Metadata, fechas técnicas |

---

## 4. Voz del bot · reglas de generación

Implementadas en `borsenhirn/dashboard/bitacora_voice.py`.

1. Empezar con el estado del mercado en alemán: `"Bullenmarkt sostenido."` / `"Bärenmarkt débil."` / `"Seitwärts."` / `"Panik im Markt."`
2. Datos clave en inglés: `"VIX dócil en 19."` / `"CPI cooling at 3.3%."`
3. Estado del portafolio mezclando alemán + español: `"Doce posiciones — vier ganando, sieben cediendo terreno."` Los números 0–20 se usan en alemán cuando aparecen como modificadores.
4. Conclusión en castellano elevado, voz reflexiva: `"No abro nuevas hoy: la convicción sin urgencia es señal de paciencia."`
5. Cierre opcional en alemán (70% del tiempo): `"Der Markt will höher — ich folge."`
6. Longitud: 2–4 oraciones máximo.
7. Tono naturalista paciente. **Nunca** exclamativo. **Nunca** "¡vamos!" ni "great trade!".

**Generación.** El generador es procedural por defecto (plantillas hidratadas con state real). Tiene un punto de extensión LLM: si en un sprint futuro `borsenhirn.m2_analyst.generate_daily_observation(state)` existe, se usa de preferencia y se cachea igual. **Cache TTL = 6 horas.** Se invalida cuando cambia el regime o cuando el usuario hace clic en `⚡ Zyklus erzwingen`.

---

## 5. Cinco principios de diseño

1. **Cada vista es una entrada numerada de bitácora.** Eintrag №412 hoy, №411 ayer. Identidad de diario continuo.
2. **El bot habla siempre en primera persona.** "Abro 3 posiciones." NO "se abrieron 3 posiciones." Cada observación firma con su módulo.
3. **Datos sirven a la observación, no al revés.** Primero la observación, después los números que la respaldan.
4. **Color con propósito · nada decorativo.** Si una métrica no es ganancia, pérdida ni regime/metadata, va en pergamino.
5. **Sin urgencia visual.** Nada parpadea. Nada brilla. Nada grita. Transiciones de hover ≥ 280ms.

---

## 6. Componentes · API

Todos los componentes viven en `borsenhirn/dashboard/bitacora_theme.py`. Devuelven HTML strings que se inyectan vía `st.markdown(..., unsafe_allow_html=True)`.

| Helper | Renderiza | Usado por |
| --- | --- | --- |
| `render_disclaimer()` | Banner legal permanente | top de página |
| `render_kopfzeile(...)` | Cabecera con título + session line + status dots | sección 01 |
| `render_observation_card(...)` | Tarjeta de Heutige Beobachtung con borde ámbar y firma | sección 02 |
| `render_vermoegen_card(...)` | Equity grande + sparkline + delta | sección 03 izquierda |
| `render_regime_gauge(...)` | Gauge SVG circular con confidence al centro | sección 03 derecha |
| `render_regime_verlauf(daily_regimes)` | Barra horizontal segmentada de 28 días con leyenda | sección 04 |
| `render_metriken_strip(cells)` | Grid de 6 celdas separadas por línea | sección 05 |
| `render_exemplar_card(...)` | Tarjeta individual de posición con borde verde/rojo | sección 06 |
| `render_exemplare_header(...)` | Header de Exemplare con contador y net | sección 06 |
| `render_exemplare_more(remaining)` | Pie "+N más · ver protokoll completo →" | sección 06 |
| `render_sinapsen_header(healthy, total)` | Header de Module · Sechs Synapsen | sección 08 |
| `render_sinapsis_card(label, status, description)` | Card individual de un módulo | sección 08 |
| `render_sinapsen_grid(modules)` | Grid 3×2 de módulos | sección 08 |
| `derive_module_statuses(...)` | Stub heurístico desde /status | sección 08 |
| `render_hirn_header(eintrag)` | Header del chat con metadata | sección 09 |
| `render_hirn_bubble(role, content)` | Burbuja del chat (assistant: italic + ámbar; user: inter + linea) | sección 09 |
| `render_steuerung_header()` | Línea separadora + título "Steuerung · controles" | sección 10 |
| `render_footer()` | Footer legal | bottom |
| `chart_label(de, es)` | Etiqueta encima de cada chart Plotly | secciones 03, 07 |
| `plotly_layout(...)` | Layout dict con paleta correcta para Plotly | secciones 03, 07 |

### Helpers de fecha y números

- `format_session_line(now, eintrag, bot_mode, days_in_paper)` → `"SONNTAG · DOMINGO 26 ABRIL 2026 · 08:15 PST · EINTRAG №412"`
- `count_healthy(modules)` → cuenta módulos con status `ok`/`info`.

---

## 7. Persistencia · Eintrag counter

Implementado en `borsenhirn/dashboard/bitacora_state.py`. Sin tocar el schema de Postgres (regla dura del sprint).

**Localización:** `~/.borsenhirn/bitacora_state.json`

```json
{
  "entry_number": 412,
  "first_session_date": "2026-03-28",
  "last_increment_date": "2026-04-26",
  "manual_cycles_today": 0
}
```

**Reglas de incremento:**

- Una vez por día calendario, en el primer render del día.
- Idempotente dentro del mismo día (repetir `current_eintrag()` devuelve el mismo número).
- `force_increment()` agrega 1 al contador independientemente — atado al botón `⚡ Zyklus erzwingen`.

---

## 8. Stub heurístico · Module statuses

Como el backend no expone aún un endpoint `/modules/health` (regla dura: no tocar `bot_api.py` este sprint), `derive_module_statuses()` deriva el estado de cada Sinapsis del payload existente de `/status`. Heurísticas documentadas:

- **M1 (Nachrichten):** ok si `confidence > 0`. El componente nominal del análisis regime requiere noticias.
- **M2 (Makro-Analyst):** ok si `regime != '—'`. Convergencia = `int(confidence × 100)`.
- **M3 (Risiko):** ok si `equity > 0` y `cash > 0`. Stress derivado de VIX (< 20 niedrig, 20-30 mittel, > 30 hoch).
- **M4 (Wale):** siempre ok (los whales scrapers corren independientes).
- **BOT (Ausführung):** ok si `bot.last_cycle` existe. Ámbar si paper.
- **M5 (Hirn):** ok si `trades_count >= 0` (memoria operativa).

**Sprint siguiente** (cuando se levante la regla del backend): reemplazar este stub por una llamada a `/modules/health` real.

---

## 9. Layout · arquitectura del dashboard

Diez secciones en orden vertical:

1. Kopfzeile · cabecera
2. Heutige Beobachtung · lectura del día (la observación destacada)
3. Vermögen + Zustand · equity + regime (grid 1.7fr / 1fr)
4. Regime-Verlauf · 28 días en barra horizontal
5. Metriken · 6 columnas (Bargeld, Positionen, Siegrate, Angst·VIX, Inflation·CPI, Leitzins·FED)
6. Exemplare offen · top 6 posiciones por |P&L| en grid 3 cols
7. Tägliche Performance · equity diario + P&L diario lado a lado
8. Module · Sechs Synapsen · grid 3×2
9. Im Gespräch mit Hirn · chat con pills horizontales
10. Steuerung · 4 controles (Aktualisieren, Zyklus erzwingen, Protokoll, Auto)

---

## 10. Checklist de validación visual

Antes de declarar el sprint completo:

- [x] Cero gradientes excepto el sutil del Vermögen sparkline
- [x] Cero animaciones que parpadeen, brillen o pulsen rápido
- [x] Cero azul, cyan, magenta en ningún lado
- [x] Cero emoji decorativo (solo ▸ ◆ ↻ ⚡ 📖 funcionales)
- [x] Toda etiqueta alemana tiene su traducción al español al lado en pequeño cursiva atenuado
- [x] Cada observación del bot está firmada por su módulo
- [x] Cada vista tiene número de Eintrag visible
- [x] Verde solo gana, rojo solo pierde, ámbar solo regime/metadata
- [x] Georgia para narrativa, Inter para etiquetas, sin mezclar
- [x] Regime gauge circular con confidence al centro
- [x] Regime-Verlauf bar muestra los 28 días completos
- [x] Exemplare con borde izquierdo de color según P&L
- [x] Module · Sechs Synapsen muestra los 6 módulos en grid 3x2
- [x] Im Gespräch mit Hirn integra los comandos rápidos como pills
- [x] Steuerung tiene los 4 controles esperados
- [x] Modo oscuro consistente — ninguna sección queda blanca

---

## 11. Lo que NO se tocó (regla dura del sprint)

- `bot_api.py`, `data_fetcher.py`, `borsenhirn/api/main.py`
- Módulos de M1, M2, M3, M4, M5 (solo se invocan, no se editan)
- Lógica de trading, vault, tenancy, ML, rate limiter, kill switch
- Schema de Postgres
- El subprocess actual a `m5_assistant.py --once` (re-estilizado nomás)

---

## 12. Sprint futuro · TODOs documentados

- **Vista Protokoll completa.** Hoy es un expander con tabla simple. Sprint siguiente: vista dedicada con filtros por regime/fecha/símbolo, paginación de Eintragen.
- **Endpoint `/modules/health` real** en `bot_api.py` para reemplazar el stub heurístico.
- **Generación LLM real de observaciones** vía M2. El hook ya existe en `bitacora_voice._generate_text` y solo requiere que `m2_analyst.generate_daily_observation(state)` exista.
- **Tests visuales** con Playwright o equivalente. Hoy hay smoke test funcional en `tests/test_dashboard_bitacora.py`.
- **Localización del calendar/timezone**. Hoy usa el TZ local del proceso para los nombres de día. En multi-tenancy, deberá tomar la TZ del tenant.

---

## 13. Cómo extender o cambiar

**Cambiar un color.** Edita `PALETTE` en `bitacora_theme.py`. Los componentes leen del dict, no de literales hex.

**Agregar una nueva sinapsis.** Agregá una entrada en `SINAPSEN_DEFAULT` y lógica nueva en `derive_module_statuses()`. El grid 3×2 se ajusta sin cambios CSS si mantenés 6 totales.

**Cambiar el tono de la voz del bot.** Editá los pools en `bitacora_voice.py` (`REGIME_OPENERS_*`, `DECISION_*`). Mantené el balance trilingüe.

**Migrar a otra fuente.** Cambiá los `@import` en `GLOBAL_CSS` y los `font-family` de los helpers. Mantené dos familias máximo.

---

## 14. Data source map · v1.1

Esta sección existe para que cuando una métrica aparezca vacía o stale en el dashboard, sepas en 5 segundos dónde mirar. El mapping vive como datos en `borsenhirn/dashboard/bitacora_data.py::DATA_SOURCE_MAP` y los tests lo verifican (`test_source_map_covers_all_visible_metrics`).

### Capa de datos unificada

Toda la lectura del dashboard pasa por `bitacora_data.build_payload()`. El dashboard nunca llama a `requests.get(/status)` directamente — siempre lee del `DataPayload` que devuelve la capa de datos. Esto resuelve los tres bugs reportados post-deploy:

- **BUG 1 (datos vacíos)**: `/status.account` puede devolver `{}` cuando el SDK de Alpaca tiene hiccups, mientras que `/portfolio.account` (que reabre el cliente) sí responde. La capa prioriza `/portfolio` y cae a `/status`. Para CPI/Fed Rate, llama directamente a `m2_analyst.MacroFetcher` (read-only). Para VIX, cae a yFinance si `/status.regime.vix` está vacío.
- **BUG 2 (HTML escapado)**: el header de Täglicher Gewinn ahora usa `render_daily_pnl_header()` que devuelve HTML inline (sin newlines internos) y un test (`test_render_daily_pnl_header_no_newlines`) lo previene como regresión.
- **BUG 3 (delta sin equity)**: el `DataPayload` es un único snapshot — `equity`, `day_pl_pct` y `cumulative_pnl` se hidratan en la misma llamada, no pueden desincronizarse.

### Tabla de fuentes

| Métrica | Sección visible | Fuente primaria | Fallback | TTL cache |
| --- | --- | --- | --- | --- |
| `equity` | Vermögen · número grande | `/portfolio.account.equity` (Alpaca SDK directo) | `/status.account.equity` → cache | 30 s |
| `cash` | Bargeld | `/portfolio.account.cash` | `/status.account.cash` → cache | 30 s |
| `buying_power` | (no visible directo) | `/portfolio.account.buying_power` | `/status.account.buying_power` → cache | 30 s |
| `day_pl` | Vermögen delta | `/portfolio.account.day_pl` | `/status.account.day_pl` → cache | 30 s |
| `day_pl_pct` | Vermögen "+3.76%" | `/portfolio.account.day_pl_pct` | `/status.account.day_pl_pct` → cache | 30 s |
| `cumulative_pnl` | Vermögen "acumulado" | sum de `/trades/list[pnl is not None]` | spark_values delta → cache | 30 s |
| `regime` | Der Zustand label | `/status.regime.regime` (M2 cached en backend) | cache local 10 min | 600 s |
| `confidence` | Der Zustand gauge % | `/status.regime.confidence` (M2) | cache local | 600 s |
| `vix` | Angst · VIX | `/status.regime.vix` | `yfinance:^VIX → close last day` → cache | 300 s |
| `cpi` | Inflation · CPI | `m2_analyst.MacroFetcher` → `FRED:CPIAUCSL.value` | cache local | 6 h |
| `cpi_change` | Inflation · subtítulo ↑/↓ | `m2_analyst.MacroFetcher` → `FRED:CPIAUCSL.change` | cache local | 6 h |
| `fed_rate` | Leitzins · FED | `m2_analyst.MacroFetcher` → `FRED:FEDFUNDS.value` | cache local | 6 h |
| `fed_rate_trend` | Leitzins · subtítulo ↑/↓/→ | `m2_analyst.MacroFetcher` → `FRED:FEDFUNDS.trend` | cache local | 6 h |
| `win_rate` | Siegrate | computed from `/trades/list[pnl>0] / total_closed` | `memory.wins_today / memory.trades_today` → cache | 30 s |
| `trades_today` | Siegrate subtítulo | `/status.memory.trades_today` | 0 | live |
| `trades_closed` | Siegrate subtítulo | `len([t for t in /trades/list if t.pnl is not None])` | 0 | live |
| `positions` | Exemplare offen | `/portfolio.positions` | `[]` | live |
| `equity_history` | Vermögen sparkline | `/portfolio.equity_history` | `[]` | live |
| `perf_history` | Tägliche Performance | `/performance/history?days=30` | `[]` | live |

### Indicador de frescura · ámbar dot

Cuando una métrica viene de cache (porque la API primaria falló) o de fallback (porque la primaria no expuso el campo), aparece un dot ámbar de 6px al lado del valor. El title HTML del dot explica de dónde viene:

- `cache` → "valor cacheado · API no respondió"
- `fallback` → "fuente secundaria activa"
- `missing` → "sin dato"

Implementado en `bitacora_theme.staleness_dot()`. Cero altura extra cuando el valor es live — no afecta el diseño aprobado.

### Localización del cache

`~/.borsenhirn/bitacora_market_cache.json` — JSON con `{key: {value, ts}}`. Compatible con migración futura a Redis (mismo shape de key/value/TTL). Hoy es file-based porque la regla dura del sprint prohíbe tocar `borsenhirn/cache/`.

### Diagnóstico

`DataPayload.metrics_with_indicator()` devuelve la lista de métricas no-live. El dashboard renderiza esa lista al pie como tira ámbar discreta (cero peso visual cuando todo está live). En logs/debugging futuro, basta inspeccionar ese campo para saber qué se cayó.

### Cuándo actualizar este map

Si agregás una métrica nueva al dashboard:
1. Agregala como campo en `DataPayload`.
2. Hidratala en `build_payload()`.
3. Agregá la entrada correspondiente a `DATA_SOURCE_MAP`.
4. El test `test_source_map_covers_all_visible_metrics` te recordará si te olvidaste.
