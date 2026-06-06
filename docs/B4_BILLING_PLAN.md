# B4 — Billing con Stripe · Plan (para revisar)

> Plan del bloqueador B4. Documento para revisar **antes** de tocar código.
> Greenfield: hoy no hay nada de billing. Estado vivo: [ESTADO.md](ESTADO.md).
> Depende del modelo de tenants (B1) y de auth (B3, ya hechos).

## 1. Objetivo y alcance

**Objetivo:** cobrar a los tenants vía Stripe y que **el pago controle el acceso**.
Suscripción activa → tenant opera; pago falla/cancela → tenant suspendido. El
estado de la suscripción en Stripe es la fuente de verdad y se refleja en
`tenants.status`.

| | |
|---|---|
| **IN scope** | Backend: Stripe Customer por tenant, Checkout/Billing Portal, **webhook** que sincroniza la suscripción → `tenants.status`/plan, y el *gating* por estado. |
| **OUT scope** | Frontend Next.js (los botones de checkout/portal y la Publishable key viven ahí; no existe en este repo). El backend expone los endpoints que el frontend consume. |

## 2. Estado actual

- **Cero código de billing.** Sin tiers/precios definidos.
- **Gancho ya presente:** `tenants.status` (active/suspended/disabled/deleted) +
  `TenantManager.suspend()/disable()/reactivate()`. B4 solo tiene que **mover ese
  estado** según Stripe. RLS + `status` ya aíslan/gatean.
- `tenants` **no** tiene `stripe_customer_id` / `subscription_id` / `plan`.
- SDK `stripe` **no** instalado.

## 3. Modelo de pricing (a decidir — D1)

Para "Modelo A — BYO Alpaca" (traders solo), MVP recomendado: **1 plan pago
mensual + trial de N días**. Tiers (free/pro) se agregan después sin rediseño.

Mapeo Stripe `subscription.status` → `tenants.status`:

| Stripe | tenants.status |
|---|---|
| `trialing`, `active` | `active` |
| `past_due`, `unpaid`, `incomplete` | `suspended` |
| `canceled`, `incomplete_expired` | `disabled` |

## 4. Schema (a decidir — D2)

Recomendado (1:1, columnas en `tenants`):
- `stripe_customer_id text UNIQUE`
- `stripe_subscription_id text`
- `plan text` (o `tier`) + (opcional) `current_period_end timestamptz`

Migración idempotente, dev primero, prod con el flujo de B8. Alternativa: tabla
`billing` aparte (más normalizado, más complejidad ahora).

## 5. Flujo

1. **Customer:** al provisionar el tenant (B3) o en el primer checkout, crear un
   Stripe Customer con el email → guardar `stripe_customer_id` (D3).
2. **Checkout:** el frontend pide una Checkout Session; el backend la crea
   (customer + price) y devuelve la URL. El user paga en Stripe.
3. **Webhook** (`POST /webhooks/stripe`, público, **verifica firma**): Stripe
   manda `checkout.session.completed`, `customer.subscription.created/updated/
   deleted`, `invoice.payment_failed` → el backend actualiza
   `tenants.status`/`plan`/`subscription_id`. **Idempotente** por `event.id`.
4. **Billing Portal:** endpoint que crea una Portal Session para que el user
   gestione/cancele su suscripción.
5. **Gating** (D4): un tenant `suspended`/`disabled` no opera — enforce en la
   dependency de auth (rechaza con 402/403) y/o el bot no tradea para ese tenant.

## 6. Diseño (pluggable, testeable sin Stripe vivo)

Mismo patrón que B2/B3:
- **`BillingProvider`** (wrapper sobre el SDK `stripe`): `create_customer`,
  `create_checkout_session`, `create_portal_session`, `parse_webhook`.
  - `StripeBillingProvider` (real) + `FakeBillingProvider` (dev/tests).
- **Webhook:** `stripe.Webhook.construct_event(payload, sig, secret)` verifica
  firma; testeable firmando eventos de prueba con un secret de test (sin red).
- **Endpoints:** `/billing/checkout` y `/billing/portal` (protegidos con
  `get_current_tenant`), `/webhooks/stripe` (público + firma).
- Config por env: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ID`.

## 7. Dependencia

Agregar **`stripe`** (SDK oficial) a `requirements.in` + lockfile.

## 8. Config de Stripe que necesito de vos (para la parte real)

- Cuenta Stripe (modo test primero).
- **Product + Price** creados → `STRIPE_PRICE_ID`.
- **API keys**: `STRIPE_SECRET_KEY` (backend), Publishable key (frontend).
- **Webhook endpoint** configurado en Stripe → `STRIPE_WEBHOOK_SECRET`.
- (Para probar webhooks localmente: el Stripe CLI `stripe listen`.)

## 9. Testing (sin Stripe vivo)

- `FakeBillingProvider` para checkout/portal/customer.
- Webhook: construir eventos firmados con un secret de test y verificar el sync:
  `subscription.updated(active)` → tenant `active`; `payment_failed` → `suspended`;
  `subscription.deleted` → `disabled`; firma mala → 400; evento duplicado
  (mismo `event.id`) → no-op (idempotencia).
- Gating: tenant suspended → endpoint protegido responde 402/403.

## 10. Decisiones a confirmar

- **D1:** modelo de pricing (1 plan + trial recomendado; ¿cuántos días?).
- **D2:** schema en `tenants` (recomendado) vs tabla `billing` aparte.
- **D3:** crear el Stripe Customer en la provisión del tenant (B3) vs en el primer checkout.
- **D4:** dónde se enforce el gating (auth dependency rechaza suspended / el bot no opera / ambos).
- **D5:** SDK `stripe` (recomendado) vs llamadas HTTP directas.

## 11. Secuencia (sub-bloques)

| Sub-bloque | Qué | Necesita Stripe vivo? |
|---|---|---|
| B4.1 | Schema (`stripe_customer_id`, `subscription_id`, `plan`) + updates en TenantManager | no |
| B4.2 | `BillingProvider` + `FakeBillingProvider` + config | no |
| B4.3 | Webhook handler (verifica firma + sync tenant, idempotente) + tests | no (eventos de prueba) |
| B4.4 | Endpoints `/billing/checkout` + `/billing/portal` | parte (config) |
| B4.5 | Gating por `status` + docs de cierre | no |

B4.1, B4.2 (fake), B4.3 y B4.5 se pueden construir y testear **sin tu cuenta
Stripe**. Solo B4.4 (y validar el webhook real) necesita los specifics de Stripe.

## 12. Riesgos

| Riesgo | Mitigación |
|---|---|
| Webhook spoofeado | verificar firma SIEMPRE (`construct_event` con el secret) |
| Webhooks desordenados/duplicados | idempotencia por `event.id`; usar `subscription.status` como fuente de verdad |
| Estado Stripe ↔ DB desincronizado | reconciliación periódica opcional; el webhook es la vía principal |
| Sin frontend, no hay checkout real e2e | `FakeBillingProvider` + webhooks de prueba cubren el backend |
| Aplicar schema a prod | va con el flujo de B8 (mismo cuidado) |
