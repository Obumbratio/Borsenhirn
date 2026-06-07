# B10 — Cierre (Anomaly detection)

> Plan → [B10_ANOMALY_PLAN.md](B10_ANOMALY_PLAN.md). Estado: [ESTADO.md](ESTADO.md).
> **Último bloqueador del roadmap.**

## Resultado en una frase

Hay un **detector de anomalías por tenant** con reglas por umbral sobre el
`audit_log` y los datos de trading, que **alerta** (vía AlertManager) ante
patrones sospechosos — complementando al kill-switch.

## Qué se entregó (`borsenhirn/anomaly/`)

| Pieza | Qué |
|---|---|
| `build_snapshot(tenant_id)` | Counts de acciones recientes del `audit_log` + stats de trading, bajo RLS. |
| Reglas (puras) | `credential_access_spike`, `killswitch_burst`, `losing_streak`, `trade_volume_spike`. Umbrales por env. |
| `AnomalyDetector.scan` | Corre todas las reglas; una regla que falla no rompe el scan. |
| `scan_and_alert(tenant_id, alert_mgr)` | Emite una alerta por finding. **Solo alerta** (no auto-bloquea — D1). |

## Diseño (claves)

- **Reglas puras sobre snapshot** → testeables sin DB; el snapshot es la única
  parte que toca la DB.
- **Pluggable + umbrales por env** → fácil de extender/calibrar.
- **Solo alerta**: el kill-switch sigue siendo el freno duro; la detección no
  introduce auto-bloqueos (sin falsos positivos que frenen trading).

## Métricas

- **Tests:** 12 (11 unit + 1 e2e). Baseline **387 passed**, integración **41 passed**.

## Lo que queda (operacional)

1. **Wire-up** de `scan_and_alert` en el ciclo del worker (B6) — un llamado por
   tenant por pasada. Es una línea; va con el wire-up del bot real.
2. Calibrar umbrales con datos reales.
3. (Futuro) reglas ML / baselines por tenant en vez de umbrales fijos.

## Para CV / portfolio

> "Detección de anomalías multi-tenant por reglas sobre el audit log y el trading
> (acceso a credenciales, rachas, volumen), con alertas — reglas puras testeables
> y umbrales configurables, complementando un kill-switch de límites duros."
