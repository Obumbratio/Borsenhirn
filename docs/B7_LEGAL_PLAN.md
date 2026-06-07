# B7 — Legal (aceptación + gating) · Plan (para revisar)

> Plan del bloqueador B7. Los docs legales existen (`legal/`); falta el tracking
> de aceptación y el gating. Estado: [ESTADO.md](ESTADO.md).

## 1. Objetivo y alcance

**Objetivo:** registrar de forma auditable **qué versión de los términos/privacidad
aceptó cada tenant, cuándo y desde dónde**, y (opcional) **gatear** el acceso al
producto hasta que el usuario acepte la versión vigente.

| | |
|---|---|
| **IN scope** | Versionado de los docs, tabla `legal_acceptance` (RLS, append-only), módulo + endpoints (current/accept/status), y gating por aceptación. |
| **OUT scope** | El contenido legal en sí (revisión por abogado) y la UI (modal de aceptación en el frontend). |

## 2. Estado actual

- `legal/TERMS.md`, `legal/PRIVACY.md`, `legal/DISCLAIMER.md` (drafts, effective 2026-04-24).
- **Cero tracking** de aceptación.

## 3. Diseño

- **Versiones vigentes** en `config`/constantes: `LEGAL_TERMS_VERSION`,
  `LEGAL_PRIVACY_VERSION` (string, p.ej. `'2026-04-24'`). Al cambiar un doc, se
  bumpea la versión → el usuario debe re-aceptar.
- **Tabla `legal_acceptance`** (tenant-scoped + RLS, append-only como `audit_log`):
  `id, tenant_id, document ('terms'|'privacy'), version, accepted_at, actor, metadata(jsonb ip/ua)`.
  Cada aceptación = una fila. "¿aceptó la versión X de terms?" = EXISTS.
- **Módulo `borsenhirn/legal`**: `record_acceptance(...)`, `is_compliant(tenant_id)`
  (aceptó las versiones vigentes de los docs requeridos), `current_versions()`.

## 4. Endpoints

- `GET /legal/current` (público): versiones vigentes + identificadores de doc.
- `POST /me/legal/accept` (auth): body `{document, version}` → registra aceptación.
- `GET /me/legal` (auth): qué versiones aceptó el tenant.

## 5. Gating (decisión D1)

`get_compliant_tenant` (dependency): exige que el tenant haya aceptado las
versiones vigentes de los docs requeridos → sino **451** (Unavailable For Legal
Reasons). Se aplica a endpoints de producto. Los endpoints `/legal/*` y billing
quedan accesibles (para poder aceptar / pagar).

## 6. Decisiones a confirmar

- **D1 (clave):** ¿gatear el producto por aceptación (recomendado) o solo trackear?
- **D2:** docs que requieren aceptación explícita — **Terms + Privacy** (recomendado)
  vs solo Terms. (El Disclaimer es un aviso, no requiere "aceptar".)
- **D3 → default:** versiones vigentes en config/constantes (no tabla).
- **D4 → default:** `legal_acceptance` append-only (como `audit_log`).

## 7. Secuencia

| Sub-bloque | Qué |
|---|---|
| B7.1 | Tabla `legal_acceptance` (RLS + append-only) + versiones en config |
| B7.2 | Módulo `borsenhirn/legal` (`record_acceptance` / `is_compliant`) + tests |
| B7.3 | Endpoints (current/accept/status) + gating `get_compliant_tenant` + tests |

Todo buildeable sin dependencias externas.

## 8. Riesgos

| Riesgo | Mitigación |
|---|---|
| Usuario opera sin aceptar | gating `get_compliant_tenant` (451) |
| Disputa "no acepté" | registro append-only con version + timestamp + actor + ip |
| Doc cambia y nadie re-acepta | bump de versión → is_compliant falla → re-aceptación forzada |
| Bloquear la propia aceptación | `/legal/*` nunca gateados |
