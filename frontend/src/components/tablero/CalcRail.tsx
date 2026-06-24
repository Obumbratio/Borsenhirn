"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { AnalysisCard } from "@/lib/signals";
import { usd } from "@/lib/signals";
import { calcPosition, type CalcResult } from "@/lib/position-calculator";
import { OrderConfirmDialog, type PendingOrder } from "@/components/OrderConfirmDialog";
import { Panel, PanelHeader } from "@/components/ui/Panel";

/**
 * Columna derecha del Tablero: calculadora de posición + herramientas.
 *
 * El USUARIO mete capital + % de riesgo; el tamaño sale de `calcPosition` (regla
 * del usuario, pura y testeada), no de una opinión. Comprar abre el
 * OrderConfirmDialog (confirmación + gate legal) — NUNCA ejecuta de un click.
 */
const TOOLS: { icon: string; label: string; href: string; soon?: boolean }[] = [
  { icon: "🔍", label: "Investigar", href: "/dashboard/investigador" },
  { icon: "📰", label: "Noticias", href: "/dashboard/noticias", soon: true },
  { icon: "🐋", label: "Whale", href: "/dashboard/whale", soon: true },
  { icon: "💬", label: "Hirn", href: "/dashboard/hirn", soon: true },
];

export function CalcRail({ card }: { card: AnalysisCard | null }) {
  const [capital, setCapital] = useState("");
  const [riskPct, setRiskPct] = useState("1");
  const [buy, setBuy] = useState<PendingOrder | null>(null);

  const entry = card?.levels.entry ?? null;
  const stop = card?.levels.stop ?? null;
  const target = card?.levels.target ?? null;

  const result = useMemo<CalcResult | null>(() => {
    const cap = parseFloat(capital);
    const risk = parseFloat(riskPct);
    if (entry == null || stop == null) return null;
    if (!Number.isFinite(cap) || capital.trim() === "") return null;
    return calcPosition({ capital: cap, riskPct: risk, entry, stop, target: target ?? undefined });
  }, [capital, riskPct, entry, stop, target]);

  return (
    <div id="calc" className="flex flex-col gap-2">
      <Panel>
        <PanelHeader title="Calcular y operar" icon="🧮" action="⋯" />
        <div className="p-3.5">
          {!card ? (
            <p className="text-[12.5px] text-dim">Elegí una señal para calcular.</p>
          ) : (
            <>
              <p className="mb-2 text-[11px] text-dim2">
                {card.symbol} · sobre los niveles del análisis
              </p>

              {/* Inputs del usuario */}
              <div className="mb-2 grid grid-cols-2 gap-2">
                <Field label="Tu capital (USD)" value={capital} onChange={setCapital} placeholder="Ej. 3000" />
                <Field label="Riesgo %" value={riskPct} onChange={setRiskPct} placeholder="Ej. 1" />
              </div>

              {/* Resultado */}
              {result === null ? (
                <p className="py-2 text-[12px] text-dim">Ingresá tu capital para ver el cálculo.</p>
              ) : result.valid ? (
                <>
                  <Row k="Acciones que encajan" v={String(result.shares)} />
                  <Row k="Costo posición" v={usd(result.positionCost)} sub={`${result.positionPct}% del capital`} />
                  <Row k="Si toca el stop" v={usd(result.lossAtStop)} tone="dn" />
                  {target != null && result.gainAtTarget != null && (
                    <Row k="Si llega al objetivo" v={usd(result.gainAtTarget)} tone="up" />
                  )}
                  {result.riskReward != null && (
                    <Row k="Riesgo / beneficio" v={`1 : ${result.riskReward.toFixed(2)}`} last />
                  )}
                  <button
                    onClick={() => setBuy({ symbol: card.symbol, side: "buy", qty: result.shares, estPrice: entry })}
                    className="mt-3 w-full rounded-lg bg-gradient-to-br from-ac2 to-[#7c3aed] px-3 py-2.5 text-[12.5px] font-semibold text-white"
                  >
                    Comprar {result.shares} {result.shares === 1 ? "acción" : "acciones"} (paper) — tú ejecutas
                  </button>
                </>
              ) : (
                <p className="rounded-md border border-warn/25 bg-warn/5 px-3 py-2 text-[12px] text-warn">
                  {result.note}
                </p>
              )}

              <p className="mt-3 text-[10.5px] leading-snug text-dim2">
                Hace cuentas con tus números. Vos elegís y ejecutás — no es recomendación.
              </p>
            </>
          )}
        </div>
      </Panel>

      {/* Herramientas */}
      <Panel>
        <PanelHeader title="Herramientas" grip />
        <div className="grid grid-cols-2 gap-2 p-3.5">
          {TOOLS.map((t) => {
            const inner = (
              <>
                <div className="text-base">{t.icon}</div>
                <div className="mt-1 text-[12.5px] font-semibold text-wht">{t.label}</div>
                {t.soon && <div className="mt-0.5 text-[10px] text-dim2">próximamente</div>}
              </>
            );
            const cls = "rounded-lg border border-bd bg-pan2 p-2.5 transition-colors hover:border-ac2";
            return t.soon ? (
              <div key={t.label} className={`${cls} cursor-default opacity-70`} title="Próximamente">
                {inner}
              </div>
            ) : (
              <Link key={t.label} href={t.href} className={cls}>
                {inner}
              </Link>
            );
          })}
        </div>
      </Panel>

      <OrderConfirmDialog order={buy} onClose={() => setBuy(null)} />
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="block rounded-lg border border-bd bg-pan2 px-2.5 py-1.5">
      <span className="text-[9.5px] text-dim2">{label}</span>
      <input
        type="number"
        inputMode="decimal"
        min={0}
        step="any"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="num w-full bg-transparent text-[12px] text-wht outline-none placeholder:text-dim2"
      />
    </label>
  );
}

function Row({
  k,
  v,
  sub,
  tone,
  last,
}: {
  k: string;
  v: string;
  sub?: string;
  tone?: "up" | "dn";
  last?: boolean;
}) {
  const toneClass = tone === "up" ? "text-up" : tone === "dn" ? "text-dn" : "text-wht";
  return (
    <div className={`flex items-baseline justify-between py-1.5 text-[12.5px] ${last ? "" : "border-b border-bd2"}`}>
      <span className="text-dim">{k}</span>
      <span className="text-right">
        <span className={`num font-semibold ${toneClass}`}>{v}</span>
        {sub && <span className="ml-1 text-[10px] text-dim2">{sub}</span>}
      </span>
    </div>
  );
}
