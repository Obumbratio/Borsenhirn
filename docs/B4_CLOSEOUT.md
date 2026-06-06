# B4 — Cierre (Billing con Stripe, backend)

> Síntesis. Diseño/decisiones → [B4_BILLING_PLAN.md](B4_BILLING_PLAN.md). Estado: [ESTADO.md](ESTADO.md).

## Resultado en una frase

El backend cobra vía Stripe y **el pago controla el acceso**: el webhook de
Stripe sincroniza el estado de la suscripción a `tenants.status`, y los endpoints
de producto exigen tenant `active` (402 si no). **Backend completo y testeado**;
falta poner las keys de Stripe en prod + el frontend (botones).

## Qué se entregó

| Sub-bloque | Resultado |
|---|---|
| B4.1 | `tenants`: `stripe_customer_id` (UNIQUE), `stripe_subscription_id`, `plan`, `current_period_end` + `TenantManager.get_tenant_by_stripe_customer_id` / `get_stripe_customer_id` / `set_billing`. |
| B4.2 | `borsenhirn/billing/`: `BillingProvider` pluggable (`StripeBillingProvider` real + `FakeBillingProvider`) + factory + mapeo `subscription.status → tenants.status`. |
| B4.3 | `apply_stripe_event` + endpoint `POST /webhooks/stripe` (verifica firma, idempotente). |
| B4.4 | `POST /billing/checkout` (trial vía `STRIPE_TRIAL_DAYS`) + `POST /billing/portal`. |
| B4.5 | Gating: `get_active_tenant` (402 si no active) en endpoints de producto; billing usa `get_current_tenant` (un suspendido puede ir a pagar). |

## Diseño (claves)

- **Provider pluggable** (como B2/B3): Stripe real o Fake; webhook testeable
  offline (firma HMAC computada en el test).
- **Estado = Stripe es la fuente de verdad**; el webhook mueve `tenants.status`.
  `set_billing` es idempotente → reprocesar eventos converge.
- **Gating en dos niveles**: `get_active_tenant` bloquea producto; los endpoints
  de billing quedan accesibles para que un suspendido re-suscriba.

## Métricas

- **Tests:** 41 nuevos (provider 16, webhook 8, checkout/gating 13, columnas 4) →
  baseline **267 → 354 passed**.
- **Dep:** `stripe==12.5.1` (requirements.in + lockfile con hashes).
- Producción intacta; todo testeado contra `borsenhirn_dev`.

## Cómo activar Stripe real (prod)

```
BILLING_PROVIDER=stripe
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID=price_...
STRIPE_TRIAL_DAYS=14        # opcional
BILLING_SUCCESS_URL=...  BILLING_CANCEL_URL=...  BILLING_PORTAL_RETURN_URL=...
```
+ configurar el endpoint `/webhooks/stripe` en el dashboard de Stripe.
+ aplicar la migración `b4_block1_billing_columns` a prod (con el flujo de B8).

## Lo que queda (fuera del backend)

1. **Frontend**: botones de checkout/portal (consumen los endpoints).
2. **Migración billing a prod** (junto con B8).
3. **Decisión de pricing final** (Product/Price en Stripe).

## Para CV / portfolio

> "Billing SaaS con Stripe: webhooks verificados por firma que sincronizan el
> estado de la suscripción a la DB, gating de acceso por estado de pago (402),
> provider pluggable testeable sin Stripe vivo, y trial configurable — todo sobre
> el aislamiento multi-tenant (RLS) ya existente."
