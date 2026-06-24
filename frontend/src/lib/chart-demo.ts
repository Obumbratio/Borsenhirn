/**
 * Generador de velas de DEMOSTRACIÓN para el panel del gráfico.
 *
 * HONESTIDAD: todavía no hay endpoint de OHLC, así que las velas son
 * sintéticas y se etiquetan como demostración en la UI. Lo que SÍ es real y se
 * dibuja encima son las líneas de entrada/stop/objetivo de la señal.
 *
 * La serie es DETERMINISTA (sembrada del símbolo): mismo símbolo → mismas velas
 * en server y cliente, sin Math.random ni Date → sin desajustes de hidratación.
 */

export type Candle = { x: number; bodyY: number; bodyH: number; wickY1: number; wickY2: number; up: boolean };

export type ChartGeom = {
  width: number;
  height: number;
  candles: Candle[];
  /** Y de cada nivel real (null si el nivel no vino). */
  lineY: { entry: number | null; stop: number | null; target: number | null };
  /** Líneas de la grilla (Y). */
  gridY: number[];
};

const W = 640;
const H = 260;
const PAD = 30; // margen vertical para que niveles y velas respiren
const N = 22; // cantidad de velas

/** PRNG simple (mulberry32) sembrado para reproducibilidad. */
function seeded(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function seedFromSymbol(symbol: string): number {
  let h = 2166136261;
  for (let i = 0; i < symbol.length; i++) {
    h ^= symbol.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export function buildChartGeom(opts: {
  symbol: string;
  price: number | null;
  entry: number | null;
  stop: number | null;
  target: number | null;
}): ChartGeom {
  const { symbol, price, entry, stop, target } = opts;

  // Rango de precios: usa los niveles reales disponibles + el precio.
  const refs = [price, entry, stop, target].filter((v): v is number => v != null && Number.isFinite(v));
  let lo: number;
  let hi: number;
  if (refs.length >= 2) {
    lo = Math.min(...refs);
    hi = Math.max(...refs);
  } else if (refs.length === 1) {
    lo = refs[0] * 0.9;
    hi = refs[0] * 1.1;
  } else {
    lo = 90;
    hi = 110;
  }
  // Margen del 6% arriba/abajo para que stop/objetivo no queden pegados al borde.
  const span = hi - lo || hi * 0.1 || 1;
  lo -= span * 0.06;
  hi += span * 0.06;

  const yFor = (p: number) => PAD + ((hi - p) / (hi - lo)) * (H - 2 * PAD);

  // Serie sintética: camina entre stop y objetivo, terminando cerca del precio.
  const rand = seeded(seedFromSymbol(symbol));
  const startP = stop != null ? stop + span * 0.15 : lo + span * 0.3;
  const endP = price ?? (entry ?? (lo + hi) / 2);
  const candles: Candle[] = [];
  const step = (W - 24) / (N - 1);
  let cur = startP;
  for (let i = 0; i < N; i++) {
    const t = i / (N - 1);
    // Tendencia lineal hacia endP + ruido determinista.
    const trend = startP + (endP - startP) * t;
    const noise = (rand() - 0.45) * span * 0.18;
    const open = cur;
    const close = trend + noise;
    cur = close;
    const high = Math.max(open, close) + rand() * span * 0.05;
    const low = Math.min(open, close) - rand() * span * 0.05;
    const up = close >= open;
    const x = 12 + i * step;
    const oY = yFor(open);
    const cY = yFor(close);
    candles.push({
      x,
      bodyY: Math.min(oY, cY),
      bodyH: Math.max(2, Math.abs(oY - cY)),
      wickY1: yFor(high),
      wickY2: yFor(low),
      up,
    });
  }

  return {
    width: W,
    height: H,
    candles,
    lineY: {
      entry: entry != null ? yFor(entry) : null,
      stop: stop != null ? yFor(stop) : null,
      target: target != null ? yFor(target) : null,
    },
    gridY: [PAD, H * 0.4, H * 0.6, H - PAD],
  };
}
