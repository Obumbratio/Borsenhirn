"use client";

import { useMemo, useState } from "react";
import { calcPosition, type CalcResult } from "@/lib/position-calculator";
import { usd } from "@/lib/signals";
import { OrderConfirmDialog, type PendingOrder } from "@/components/OrderConfirmDialog";

/**
 * Calculadora de tamaño de posición (Paso 3c — UI).
 *
 * El USUARIO la opera con SUS números: capital + % de riesgo. Los niveles
 * (entrada/stop/objetivo) los toma del análisis. La aritmética es pura
 * (`calcPosition`, ya testeada): el tamaño sale de la REGLA del usuario, no de
 * una opinión nuestra. Recalcula solo cuando cambia un input (useMemo).
 *
 * NO ejecuta nada — es una herramienta de cuentas, no un consejo.
 */
export function PositionCalculator({
  symbol,
  entry,
  stop,
  target,
}: {
  symbol: string;
  entry: number | null;
  stop: number | null;
  target: number | null;
}) {
  const [open, setOpen] = useState(false);
  const [capital, setCapital] = useState("");
  const [riskPct, setRiskPct] = useState("1");
  const [buy, setBuy] = useState<PendingOrder | null>(null);

  // Recalcula SOLO cuando cambia un input (capital / riesgo / niveles).
  const result = useMemo<CalcResult | null>(() => {
    const cap = parseFloat(capital);
    const risk = parseFloat(riskPct);
    if (entry == null || stop == null) return null; // el análisis no trae niveles
    if (!Number.isFinite(cap) || capital.trim() === "") return null; // todavía sin capital
    return calcPosition({ capital: cap, riskPct: risk, entry, stop, target: target ?? undefined });
  }, [capital, riskPct, entry, stop, target]);

  const hasLevels = entry != null && stop != null;

  return (
    <div className="mt-4 border-t border-bd pt-3">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between text-left text-sm font-medium text-dim hover:text-tx"
        aria-expanded={open}
      >
        <span>🧮 Calcular tamaño de posición</span>
        <span className="text-dim">{open ? "−" : "+"}</span>
      </button>

      {open && (
        <div className="mt-3">
          {!hasLevels ? (
            <p className="text-sm text-dim">
              Este análisis no tiene niveles de entrada/stop para calcular.
            </p>
          ) : (
            <>
              {/* Niveles tomados del análisis (solo lectura) */}
              <p className="text-[11px] text-dim">
                Sobre los niveles del análisis — entrada{" "}
                <span className="font-mono text-tx">{usd(entry)}</span>, stop{" "}
                <span className="font-mono text-tx">{usd(stop)}</span>
                {target != null && (
                  <>
                    , objetivo <span className="font-mono text-tx">{usd(target)}</span>
                  </>
                )}
                .
              </p>

              {/* Inputs del usuario */}
              <div className="mt-3 grid grid-cols-2 gap-3">
                <Field
                  label="Tu capital (USD)"
                  value={capital}
                  onChange={setCapital}
                  placeholder="Ej. 10000"
                  min={0}
                  step="any"
                />
                <Field
                  label="Riesgo por operación (%)"
                  value={riskPct}
                  onChange={setRiskPct}
                  placeholder="Ej. 1"
                  min={0}
                  step="any"
                />
              </div>

              {/* Resultado en vivo */}
              <div className="mt-4">
                {result === null ? (
                  <p className="text-sm text-dim">
                    Ingresá tu capital para ver el cálculo.
                  </p>
                ) : result.valid ? (
                  <>
                    <ResultView r={result} target={target} />
                    {/* Comprar: sale de lo que el usuario YA calculó (qty = acciones).
                        Abre el diálogo de confirmación; nunca ejecuta con un click. */}
                    <button
                      onClick={() =>
                         setBuy({ symbol, side: "buy", qty: result.shares, estPrice: entry })
                      }
                      className="mt-3 w-full rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-wht hover:bg-emerald-500"
                    >
                      Comprar {result.shares} {result.shares === 1 ? "acción" : "acciones"} de {symbol} (paper)
                    </button>
                  </>
                ) : (
                  <p className="rounded-md border border-warn/25 bg-warn/5 px-3 py-2 text-sm text-warn">
                    {result.note}
                  </p>
                )}
              </div>

              {/* Disclaimer (lo legal) */}
              <p className="mt-3 text-[11px] leading-relaxed text-dim">
                Calculadora: hace cuentas con tus números. Vos elegís y ejecutás —
                no es recomendación de inversión.
              </p>
            </>
          )}
        </div>
      )}

      {/* Confirmación de compra (paso obligatorio antes de ejecutar) */}
      <OrderConfirmDialog order={buy} onClose={() => setBuy(null)} />
    </div>
  );
}

function ResultView({ r, target }: { r: CalcResult; target: number | null }) {
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-bd bg-bd text-center">
        <Stat label="Acciones" value={String(r.shares)} tone="neutral" />
        <Stat
          label="Costo posición"
          value={usd(r.positionCost)}
          sub={`${r.positionPct}% del capital`}
          tone="neutral"
        />
        <Stat label="Pérdida si toca el stop" value={usd(r.lossAtStop)} tone="red" />
        {target != null && r.gainAtTarget != null ? (
          <Stat label="Ganancia al objetivo" value={usd(r.gainAtTarget)} tone="emerald" />
        ) : (
          <Stat label="Ganancia al objetivo" value="—" tone="neutral" />
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 px-1 text-xs text-dim">
        <span>
          Arriesgás <span className="font-mono text-tx">{usd(r.riskAmount)}</span>{" "}
          ({usd(r.riskPerShare)} por acción)
        </span>
        {r.riskReward != null && (
          <span>
            Riesgo / Beneficio:{" "}
            <span className="font-mono font-semibold text-wht">1 : {r.riskReward.toFixed(2)}</span>
          </span>
        )}
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  min,
  step,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  min?: number;
  step?: string;
}) {
  return (
    <label className="block">
      <span className="text-[11px] text-dim">{label}</span>
      <input
        type="number"
        inputMode="decimal"
        min={min}
        step={step}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-md border border-bd bg-pan2 px-3 py-2 font-mono text-sm text-tx outline-none focus:border-ac/60"
      />
    </label>
  );
}

function Stat({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub?: string;
  tone: "neutral" | "red" | "emerald";
}) {
  const toneClass =
    tone === "red" ? "text-dn" : tone === "emerald" ? "text-up" : "text-wht";
  return (
    <div className="bg-pan px-2 py-3">
      <p className="text-[11px] uppercase tracking-wide text-dim">{label}</p>
      <p className={`mt-1 font-mono text-base font-semibold ${toneClass}`}>{value}</p>
      {sub && <p className="mt-0.5 text-[11px] text-dim">{sub}</p>}
    </div>
  );
}
