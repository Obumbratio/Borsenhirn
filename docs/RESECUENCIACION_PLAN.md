# Plan de re-secuenciación — "un cerebro, dos caras"

> Cómo se reencuadra el código existente al modelo de [PRODUCTO_PLAN.md](PRODUCTO_PLAN.md).
> Confirmado 2026-06-11. NO se mata el auto-trader: se SEPARA y se aísla.

## Intención (1 línea)
Un cerebro (señal) produce análisis; dos caras lo consumen — el **auto-trader interno**
(privado, mío, paper + R&D + genera el track record) y el **ejecutor manual** (producto:
el usuario aprieta el botón). El auto-ejecutor nunca toca el flujo de cliente.

## Reglas que el plan respeta
1. Desacoplar señal de ejecución en el motor. → Paso 1
2. Separación **física** del auto-ejecutor (carpeta interna marcada). → Paso 1.5 + guardrail
3. Señal del **cliente** = global/impersonal; el auto-trader interno puede aprender por su cuenta. → Paso 2
4. Orden obligatorio: **primero desacoplar, después superficies nuevas.** → 1-2 antes de 3-4

## Arquitectura objetivo
| Componente | Qué hace | Dónde vive | ¿Producto? |
|---|---|---|---|
| **SignalEngine** (cerebro) | Solo produce señal/análisis. NO ejecuta, NO escribe outcomes. | `borsenhirn/signals/` | compartido |
| **AutoExecutor** (cara interna) | Toma la señal, auto-ejecuta en paper + aprende. = ejecución de hoy. | `borsenhirn/internal/autotrader/` (header: INTERNO, NO-producto) | ❌ privado |
| **ManualExecutor** (cara cliente) | Muestra la señal; ejecuta UNA orden SOLO cuando el user aprieta, con SUS creds. | `borsenhirn/api/` + frontend | ✅ producto |

**Guardrail de la línea roja:** test/CI que falla si el API de cliente importa (directa o
transitivamente) `internal/autotrader`. La separación no depende de disciplina humana.

## Orden de ejecución
### Paso 1 — Desacoplar señal de ejecución (OBLIGATORIO PRIMERO, behavior-preserving)
Partir `engine.py::run_cycle` en `SignalEngine.analyze()` (devuelve `CycleSignals`
estructurado: candidatos de compra con niveles + razón; triggers de salida; regime/ctx;
**cero `submit_order`, cero escritura de outcomes**) y `AutoExecutor` (todo lo que ejecuta
+ bookkeeping + aprendizaje). `main.py`/`run_bot_prod.sh` = SignalEngine + AutoExecutor
(mismo comportamiento). **Verificación: 404 tests verdes + smoke paper idéntico** antes de seguir.
**Checkpoint: parar y mostrar cómo quedó el split antes de continuar.**

### Paso 1.5 — Separación física + guardrail
Mover `AutoExecutor` (y el worker multi-tenant `make_bot_cycle_fn`) a
`borsenhirn/internal/autotrader/` con cabecera de advertencia + test del import prohibido.

### Paso 2 — Cerebro global (impersonal para el cliente)
El SignalEngine del cliente lee contexto global (no por-tenant) → output idéntico para todos.
**DECISIÓN DIFERIDA a este paso (no bloquea el desacople):** dónde vive el cerebro global
(tenant SYSTEM vs tabla dedicada). Exponer `GET /signals` read-only.

### Paso 3 — Superficies de cliente (en orden Fase 1)
- 3a. **Conectar Alpaca (paper):** UI + endpoint, reusa `CredentialStore`/Vault (B2).
- 3b. **Ver análisis/señales:** frontend consume `GET /signals` (tarjetas: tesis + niveles +
  qué invalida). Sub-paso = **IA explicativa** (enriquecer con `m1_research`/`m2_analyst`).
- 3c. **Calculadora de posición:** frontend puro (capital + % riesgo → qty/costo/escenarios/RR).
- 3d. **Botón comprar (ejecución manual):** `POST /me/orders` ejecuta UNA orden en el Alpaca
  del user (sus creds), solo a pedido explícito.
- **Salidas (TP/SL): ALERTA + botón**, nunca "vende" ("tu stop en $X se tocó", "estás en tu
  objetivo"); misma lógica que la calculadora — describe el escenario, el user decide y ejecuta.
  Se afina en este paso, no en el 1.

### Paso 4 — Track record público
Alimentado por el auto-trader interno en paper (Fase 3 always-on). `GET /track-record`
público, honesto (aciertos y errores). Marketing + escudo anti-AI-washing.

## Qué pasa con lo ya hecho
- Worker multi-tenant (`make_bot_cycle_fn`) → pasa a `internal/autotrader/` (cara interna), NO producto.
- Frontend login (rebanada 1) → se queda (paso 1 de Fase 1).
- Prod local + `run_bot_prod.sh` + timer anomalías → se quedan, lado interno/mío.

## Notas / decisiones abiertas
- **Salidas per-cuenta:** dependen de las posiciones que tiene cada user → son aritmética sobre
  lo propio (alerta+botón en Paso 3), no "consejo". El análisis de compra es lo impersonal (producto).
- **IA explicativa = net-new** (hoy solo `signal['reason']` corto).
- **Store del cerebro global** se resuelve en Paso 2.
