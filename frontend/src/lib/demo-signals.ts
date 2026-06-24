import type { SignalsPayload } from "@/lib/signals";

/**
 * ⚠️ TEMPORAL — datos de DEMOSTRACIÓN para revisar el diseño del Tablero.
 *
 * Sólo se usa cuando la URL trae `?demo=1` (ver dashboard/page.tsx) y SIEMPRE
 * con un banner "MODO DEMO" visible. No toca el flujo real: sin el parámetro, el
 * Tablero muestra los datos reales de GET /signals.
 *
 * BORRAR este archivo (y el manejo de `?demo=1`) una vez aprobado el diseño.
 */
const DISCLAIMER =
  "Análisis general, no es recomendación. Información impersonal — igual para todos. " +
  "No mira tu cuenta. Vos decidís, calculás tu tamaño y ejecutás.";

export const DEMO_PAYLOAD: SignalsPayload = {
  regime: "BULL",
  generated_at: "2026-06-23T13:30:00Z",
  impersonal: true,
  ttl_sec: 900,
  signals: [
    {
      symbol: "UNH",
      price: 407.95,
      levels: {
        entry: 407.95,
        stop: 398.49,
        target: 440.59,
        trailing_pct: 0.03,
        fuentes: { entry: "scanner", stop: "ATR(14)", target: "R/B 1:3" },
      },
      tesis: "Setup alcista en zona neutral de RSI con tendencia de medias al alza (datos de ejemplo).",
      que_invalida: "Cierre por debajo del stop de referencia $398.49 invalida la idea.",
      factores: [
        { factor: "RSI", valor: 48.3, fuente: "indicators" },
        { factor: "Tendencia de medias", valor: "alcista", fuente: "strategy" },
        { factor: "Probabilidad del modelo ML", valor: 0.83, fuente: "ml_model (.pkl)" },
        { factor: "Régimen", valor: "BULL", fuente: "regime_detector" },
      ],
      disclaimer: DISCLAIMER,
    },
    {
      symbol: "NVDA",
      price: 134.1,
      levels: {
        entry: 134.1,
        stop: 128.74,
        target: 144.83,
        trailing_pct: 0.04,
        fuentes: { entry: "scanner", stop: "ATR(14)", target: "R/B 1:2" },
      },
      tesis: "Continuación de momentum tras consolidación corta (datos de ejemplo).",
      que_invalida: "Pérdida del soporte $128.74 invalida la idea.",
      factores: [
        { factor: "RSI", valor: 56.1, fuente: "indicators" },
        { factor: "Tendencia de medias", valor: "alcista", fuente: "strategy" },
        { factor: "Probabilidad del modelo ML", valor: 0.66, fuente: "ml_model (.pkl)" },
        { factor: "Régimen", valor: "BULL", fuente: "regime_detector" },
      ],
      disclaimer: DISCLAIMER,
    },
    {
      symbol: "MSFT",
      price: 498.2,
      levels: {
        entry: 498.2,
        stop: 479.1,
        target: 531.0,
        trailing_pct: 0.03,
        fuentes: { entry: "scanner", stop: "ATR(14)", target: "R/B 1:1.7" },
      },
      tesis: "Cruce de medias reciente con volumen sostenido (datos de ejemplo).",
      que_invalida: "Cierre bajo $479.10 invalida la idea.",
      factores: [
        { factor: "RSI", valor: 52.4, fuente: "indicators" },
        { factor: "Tendencia de medias", valor: "alcista", fuente: "strategy" },
        { factor: "Probabilidad del modelo ML", valor: 0.71, fuente: "ml_model (.pkl)" },
        { factor: "Régimen", valor: "BULL", fuente: "regime_detector" },
      ],
      disclaimer: DISCLAIMER,
    },
  ],
};
