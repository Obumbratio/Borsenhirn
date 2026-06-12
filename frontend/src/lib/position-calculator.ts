/**
 * Calculadora de tamaño de posición (Paso 3c) — aritmética PURA, sin backend.
 *
 * El usuario la opera con SUS números (capital + % de riesgo) sobre los niveles
 * del análisis (entrada/stop/objetivo). La herramienta solo hace cuentas: el
 * tamaño sale de la REGLA DEL USUARIO, no de una opinión nuestra. Escenarios
 * neutrales, no un empujón a actuar. NO es recomendación de inversión.
 *
 * Invariantes (casos borde cubiertos por los tests):
 *  - stop >= entrada → riesgo por acción <= 0: inválido, 0 acciones, sin dividir por cero ni negativos.
 *  - capital insuficiente para 1 acción → 0 acciones (nunca fracciones).
 *  - acciones siempre enteras (Math.floor); dinero a 2 decimales.
 */

export interface CalcInput {
  capital: number;   // capital total del usuario
  riskPct: number;   // % de riesgo por operación (ej. 1 = 1%)
  entry: number;     // precio de entrada (del análisis, editable por el usuario)
  stop: number;      // precio de stop
  target?: number;   // precio objetivo (opcional)
}

export interface CalcResult {
  valid: boolean;
  shares: number;            // entero, >= 0
  riskAmount: number;        // capital * riskPct% → dinero arriesgado
  riskPerShare: number;      // entrada - stop
  positionCost: number;      // shares * entrada
  positionPct: number;       // % del capital invertido
  lossAtStop: number;        // si toca el stop (negativo)
  gainAtTarget?: number;     // si llega al objetivo
  riskReward?: number;       // (objetivo - entrada) / (entrada - stop)
  note?: string;             // por qué 0 / inválido
}

const round2 = (x: number): number => Math.round(x * 100) / 100;

function invalid(note: string, riskPerShare = 0): CalcResult {
  return {
    valid: false, shares: 0, riskAmount: 0, riskPerShare,
    positionCost: 0, positionPct: 0, lossAtStop: 0, note,
  };
}

export function calcPosition(input: CalcInput): CalcResult {
  const { capital, riskPct, entry, stop, target } = input;

  // Inputs básicos válidos
  if (![capital, riskPct, entry, stop].every((n) => Number.isFinite(n)) ||
      capital <= 0 || entry <= 0 || riskPct <= 0) {
    return invalid("Capital, entrada y % de riesgo deben ser números > 0.");
  }

  // Riesgo por acción: el stop DEBE estar por debajo de la entrada.
  const riskPerShare = round2(entry - stop);
  if (riskPerShare <= 0) {
    return invalid("El stop debe estar por debajo de la entrada (riesgo por acción > 0).", riskPerShare);
  }

  const riskAmount = round2(capital * (riskPct / 100));
  const byRisk = Math.floor(riskAmount / riskPerShare);   // por la regla de riesgo del usuario
  const byCapital = Math.floor(capital / entry);          // tope: lo que alcanza el capital
  const shares = Math.max(0, Math.min(byRisk, byCapital));

  if (shares < 1) {
    const note = byCapital < 1
      ? "Capital insuficiente para 1 acción a este precio."
      : "Tu regla de riesgo no alcanza ni para 1 acción con estos niveles.";
    return {
      valid: false, shares: 0, riskAmount, riskPerShare,
      positionCost: 0, positionPct: 0, lossAtStop: 0, note,
    };
  }

  const positionCost = round2(shares * entry);
  const result: CalcResult = {
    valid: true,
    shares,
    riskAmount,
    riskPerShare,
    positionCost,
    positionPct: round2((positionCost / capital) * 100),
    lossAtStop: -round2(shares * riskPerShare),
  };

  if (typeof target === "number" && Number.isFinite(target)) {
    result.gainAtTarget = round2(shares * (target - entry));
    result.riskReward = round2((target - entry) / riskPerShare);
  }

  return result;
}
