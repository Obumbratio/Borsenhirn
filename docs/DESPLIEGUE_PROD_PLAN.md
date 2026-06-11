# Despliegue de prod por primera vez — plan + decisión

> ⚠️ **Esto es INSUMO PARA DECIDIR, no una orden de ejecutar.** No hay prod
> desplegado (ver aviso ⛔ en [ESTADO.md](ESTADO.md)). Nada de acá se corre hasta
> que Uriel tome, en frío, la decisión de despliegue. Escrito 2026-06-11.

---

## 1. ¿Por qué íbamos a "migrar"? (el porqué, fundamentado)

"Migrar" acá significaba **aplicar la multi-tenancy (B1) a una base de datos de
producción viva** — el paso "B1 Bloque 8" del roadmap.

El porqué, según la misión real del proyecto ([PLAN.md](PLAN.md)):

- El bot nació **single-user**: las tablas asumían un único dueño. Con dos usuarios,
  sus datos se mezclarían (trades, scores, **credenciales de Alpaca**).
- Börsenhirn se comercializa como **SaaS (Modelo A — BYO Alpaca broker)**. El
  aislamiento por tenant (RLS) debe existir **antes del primer cliente pago**.
- Todo el sprint B1..B10 se construyó hacia eso. Cita textual de PLAN.md:
  *"Misión cumplida = tras el Bloque 8 (B1 aplicado a prod), el SaaS técnicamente
  puede empezar a vender."*

**En una frase:** íbamos a migrar porque no podés tener clientes pagos registrándose
contra una DB `borsenhirn_dev` en una laptop. Migrar = poner la infra multi-tenant
**viva** para poder dar de alta usuarios reales.

**El matiz que cambió hoy:** descubrimos que **no hay prod**. Así que antes de
"migrar a prod" hay que **crear prod**. Y eso obliga a una decisión de fondo (§2)
que toca el principio **local-first** del proyecto.

---

## 2. La decisión de fondo (a tomar en frío) — ¿dónde vive prod?

El roadmap SaaS empuja hacia "vender a clientes", lo que sugiere un server 24/7.
Pero el proyecto es **local-first**. Hay dos caminos honestos, no uno:

### Opción L — Local-first (no rompe el principio)
Prod corre en una máquina **tuya** (la misma WSL, u otra PC/mini-PC tuya), con el
stack ya scaffoldeado: **`docker-compose.yml`** levanta Postgres + bot + dashboard
en un `docker compose up` (DB `borsenhirn` en un volumen local; sin nube, sin alquilar).
- ✅ Coherente con local-first; vos controlás la data; costo $0.
- ⚠️ "Prod" disponible solo mientras tu máquina esté prendida (mismo matiz que C1
  de [DEPLOY_ALWAYS_ON.md](DEPLOY_ALWAYS_ON.md)); no es 24/7 real.
- ⚠️ Para vender a terceros de verdad, un Postgres en tu casa expuesto a internet
  es frágil/inseguro — sirve para *vos* o un círculo chico, no para escala.

### Opción C — Nube / VPS de tercero (rompe local-first)
Una maquinita en Hetzner/DigitalOcean/Fly (~$5/mes) siempre prendida —
guía en [DEPLOY_ALWAYS_ON.md](DEPLOY_ALWAYS_ON.md) (C2).
- ✅ 24/7 real, independiente de tu PC; lo que un SaaS con clientes necesita.
- ⛔ **Rompe local-first**: la data y las credenciales de broker de los usuarios
  viven en infra de un tercero. Es una decisión consciente, no un default.
- ⚠️ Costo mensual + superficie expuesta (SSH con clave, firewall, no abrir puertos).

> **La pregunta a responder en frío:** ¿el SaaS multi-tenant justifica salir de
> local-first? Si la respuesta es "todavía no / nunca", la Opción L alcanza para
> probar el modelo. Si es "sí, voy a vender en serio", la Opción C es el camino.
> **No hace falta decidir hoy.** Mientras tanto, dev (`borsenhirn_dev`) sigue
> sirviendo para todo el desarrollo.

---

## 3. El plan (una vez decidido dónde vive prod)

Stand-up de prod por primera vez + aplicar B1. Reutiliza scripts/docs que YA existen
(no se duplica nada acá):

1. **Parar prod** (la infra: docker compose o VPS), con su `.env` apuntando a `borsenhirn`.
   - Opción L: `docker compose up -d` (crea un `borsenhirn` vacío en el volumen).
   - Opción C: seguir C2 de [DEPLOY_ALWAYS_ON.md](DEPLOY_ALWAYS_ON.md) (clonar repo, venv, DB).
2. **¿Datos?** Prod arranca **limpio** (DB nueva). La data de `borsenhirn_dev` son
   trades de prueba del single-user bajo el default tenant — normalmente NO se migra
   a un prod SaaS. (Si se quisiera, sería un `pg_dump`/restore aparte, a decidir.)
3. **Aplicar B1 Bloque 8** — el runbook ya existe y está validado
   ([B1_BLOCK8_PLAN.md](B1_BLOCK8_PLAN.md)):
   `backup → apply (core 17 tablas) → create_role → verify → extras_apply (clerk/billing/audit/legal)`.
4. **Keys reales en el `.env` de prod:** Clerk, Stripe, `ADMIN_API_KEY`, master key (B2).
5. **Re-arranque controlado** (`--once` primero) + agendar el timer de anomalías.

> Sobre una DB recién creada (paso 1), las tablas de las migraciones B1..B10 tienen
> que existir primero (el esquema base, no solo la transformación multi-tenant de B8).
> Detalle a resolver cuando se ejecute: B1 Bloque 8 asume el esquema base ya presente
> (como en dev). Si prod arranca de cero, hay que correr antes las migraciones de
> creación de tablas del proyecto. **Marcar este punto** antes de ejecutar.

---

## 4. Estado / gates

- **Bloqueado** por la decisión §2. Hasta entonces: no se despliega ni se migra nada.
- Cuando se decida y se despliegue: los gates de [B1_BLOCK8_PLAN.md](B1_BLOCK8_PLAN.md)
  aplican tal cual (backup verificado → migración atómica → verify → extras).
