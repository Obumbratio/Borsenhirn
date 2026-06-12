import { describe, it, expect } from "vitest";
import { calcPosition } from "./position-calculator";

describe("calcPosition — caso normal (ejemplo del PRODUCTO_PLAN)", () => {
  it("capital 10k, riesgo 1%, entrada 190, stop 180, objetivo 210", () => {
    const r = calcPosition({ capital: 10000, riskPct: 1, entry: 190, stop: 180, target: 210 });
    expect(r.valid).toBe(true);
    expect(r.riskAmount).toBe(100);       // 1% de 10.000
    expect(r.riskPerShare).toBe(10);      // 190 - 180
    expect(r.shares).toBe(10);            // 100 / 10
    expect(r.positionCost).toBe(1900);    // 10 * 190
    expect(r.positionPct).toBe(19);       // 1900 / 10000
    expect(r.lossAtStop).toBe(-100);      // toca stop → -1% (su riesgo)
    expect(r.gainAtTarget).toBe(200);     // 10 * (210-190)
    expect(r.riskReward).toBe(2);         // 20 / 10
  });
});

describe("BORDE 1 — stop >= entrada (riesgo por acción <= 0)", () => {
  it("stop = entrada → inválido, 0 acciones, sin dividir por cero", () => {
    const r = calcPosition({ capital: 10000, riskPct: 1, entry: 190, stop: 190 });
    expect(r.valid).toBe(false);
    expect(r.shares).toBe(0);
    expect(r.riskPerShare).toBe(0);
    expect(Number.isFinite(r.shares)).toBe(true);   // nada de Infinity/NaN
    expect(r.note).toMatch(/stop/i);
  });
  it("stop > entrada → riesgo por acción negativo → inválido, no da acciones negativas", () => {
    const r = calcPosition({ capital: 10000, riskPct: 1, entry: 180, stop: 200 });
    expect(r.valid).toBe(false);
    expect(r.shares).toBe(0);
    expect(r.riskPerShare).toBeLessThanOrEqual(0);
    expect(r.shares).toBeGreaterThanOrEqual(0);     // nunca negativo
  });
});

describe("BORDE 2 — capital insuficiente para 1 acción", () => {
  it("capital 100, entrada 291 → 0 acciones (no fracciones)", () => {
    const r = calcPosition({ capital: 100, riskPct: 1, entry: 291, stop: 285 });
    expect(r.valid).toBe(false);
    expect(r.shares).toBe(0);
    expect(Number.isInteger(r.shares)).toBe(true);
    expect(r.note).toMatch(/insuficiente/i);
  });
  it("la regla de riesgo no alcanza ni 1 acción (riesgo muy chico)", () => {
    // riesgo $1 (0.01% de 10k), riesgo por acción $10 → 0.1 acciones → 0
    const r = calcPosition({ capital: 10000, riskPct: 0.01, entry: 190, stop: 180 });
    expect(r.valid).toBe(false);
    expect(r.shares).toBe(0);
    expect(Number.isInteger(r.shares)).toBe(true);
  });
});

describe("BORDE 3 — redondeo (acciones enteras, dinero 2 decimales)", () => {
  it("acciones siempre enteras (floor), nunca fracciones", () => {
    // 100 / 7 = 14.28… → 14 acciones
    const r = calcPosition({ capital: 100000, riskPct: 1, entry: 100, stop: 93 });
    expect(r.riskPerShare).toBe(7);
    expect(r.shares).toBe(Math.floor(1000 / 7));   // 142
    expect(Number.isInteger(r.shares)).toBe(true);
  });
  it("el dinero se redondea a 2 decimales", () => {
    const r = calcPosition({ capital: 9999, riskPct: 1.5, entry: 33.33, stop: 30.10, target: 40 });
    for (const v of [r.riskAmount, r.riskPerShare, r.positionCost, r.positionPct, r.lossAtStop, r.gainAtTarget!, r.riskReward!]) {
      expect(Math.round(v * 100) / 100).toBe(v);   // ya redondeado a 2 decimales
    }
  });
});

describe("inputs inválidos", () => {
  it("capital 0 / NaN → inválido, sin crash", () => {
    expect(calcPosition({ capital: 0, riskPct: 1, entry: 190, stop: 180 }).valid).toBe(false);
    expect(calcPosition({ capital: NaN, riskPct: 1, entry: 190, stop: 180 }).valid).toBe(false);
  });
});
