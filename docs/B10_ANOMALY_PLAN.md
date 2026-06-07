# B10 — Anomaly detection · Plan (para revisar)

> Último bloqueador del roadmap. Estado: [ESTADO.md](ESTADO.md).

## 1. Objetivo y alcance

**Objetivo:** detectar comportamiento **anómalo por tenant** (seguridad + operación)
a partir del `audit_log` y los datos de trading, y **alertar** (vía AlertManager).
Complementa al kill-switch (que ya frena los límites duros de trading).

| | |
|---|---|
| **IN scope** | Detector con **reglas pluggables** sobre un snapshot por tenant, findings con severidad, y emisión de alertas. Función `scan(tenant_id)` integrable al worker. |
| **OUT scope** | ML de detección de anomalías (esto es por reglas/umbral). Respuesta automática agresiva (ver D1). |

## 2. Estado actual

- `AlertManager` (INFO/WARN/CRITICAL, canales) — se reusa para emitir.
- Kill-switch: daily-loss / drawdown / consecutive-failures (anomalías de trading duro).
- Señales: `audit_log` (actor/action/at/metadata), `bot_trade_outcomes` (pnl/win),
  `bot_daily_state` (trades_today, equity).

## 3. Diseño (pluggable + testeable)

```
build_snapshot(tenant_id, window) -> dict
    cuenta acciones recientes del audit_log + stats de trading, bajo RLS.

AnomalyRule(snapshot) -> [AnomalyFinding(rule, severity, message, metadata)]
    reglas PURAS sobre el snapshot (testeables sin DB).

AnomalyDetector(rules).scan(tenant_id) -> [findings]
    build_snapshot + corre todas las reglas.

scan_and_alert(tenant_id, alert_mgr) -> emite una alerta por finding.
```

Reglas iniciales:
- **Seguridad:** pico de `credentials.read` (acceso a claves) en la ventana;
  ráfaga de eventos de kill-switch (halt repetidos).
- **Trading:** racha de pérdidas; volumen de trades anómalo vs umbral.

## 4. Respuesta (decisión D1)

- **Solo alertar** (recomendado MVP): cada finding → alerta (WARN/CRITICAL). El
  kill-switch sigue siendo el que frena lo duro.
- **Alertar + auto-trip** del kill-switch en findings CRITICAL: más agresivo;
  riesgo de falsos positivos que frenan trading. Configurable.

## 5. Secuencia

| Sub-bloque | Qué |
|---|---|
| B10.1 | `borsenhirn/anomaly/`: snapshot + reglas + detector + tests (reglas puras) |
| B10.2 | `scan_and_alert` (integra AlertManager) + integración con el worker + tests |

## 6. Riesgos

| Riesgo | Mitigación |
|---|---|
| Falsos positivos ruidosos | umbrales configurables; severidad; solo alertar (D1) |
| Auto-trip frena trading sano | D1 default = solo alertar; auto-trip opt-in por severidad |
| Costo de queries por tenant | ventana corta + counts agregados; corre en el ciclo del worker |
