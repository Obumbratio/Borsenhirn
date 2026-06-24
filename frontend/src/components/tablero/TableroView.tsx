"use client";

import { useState } from "react";
import type { SignalsPayload } from "@/lib/signals";
import { StatsBar, type Stat } from "@/components/ui/StatsBar";
import { SignalsRail } from "@/components/tablero/SignalsRail";
import { ChartPanel } from "@/components/tablero/ChartPanel";
import { CalcRail } from "@/components/tablero/CalcRail";

/**
 * Tablero (Fusión A+B): barra de stats arriba + tres columnas
 * (señales · gráfica · calculadora/herramientas). Maneja el símbolo
 * seleccionado, que comparten la gráfica y la calculadora.
 *
 * HONESTIDAD: la barra de stats sólo muestra datos con fuente real (régimen,
 * nº de señales). Cuenta/VIX/sentimiento van como "—" hasta tener endpoint.
 */
export function TableroView({ payload, demo = false }: { payload: SignalsPayload; demo?: boolean }) {
  const cards = payload.signals;
  const [selected, setSelected] = useState<string | null>(cards[0]?.symbol ?? null);
  const selectedCard = cards.find((c) => c.symbol === selected) ?? cards[0] ?? null;

  const regime = payload.regime;
  const stats: Stat[] = [
    { label: "Cuenta (paper)", value: "—", pending: true },
    { label: "Hoy", value: "—", pending: true },
    { label: "Régimen", value: regime ?? "—", tone: "accent", pending: regime == null },
    { label: "VIX", value: "—", pending: true },
    { label: "Señales hoy", value: String(cards.length), tone: "default" },
    { label: "Sentimiento", value: "—", pending: true },
  ];

  return (
    <div className="mx-auto flex max-w-[1340px] flex-col gap-2">
      {demo && (
        <div className="rounded-lg border border-warn/30 bg-warn/10 px-3.5 py-2 text-[12px] text-warn">
          ⚠️ <span className="font-semibold">MODO DEMO</span> — señales de ejemplo solo para revisar
          el diseño. No son datos reales. Quitá <code className="font-mono">?demo=1</code> de la URL
          para volver al estado real.
        </div>
      )}
      <StatsBar stats={stats} />

      <div className="grid grid-cols-1 gap-2 lg:grid-cols-[0.85fr_1.4fr_0.95fr]">
        <SignalsRail cards={cards} selected={selected} onSelect={setSelected} />
        <ChartPanel card={selectedCard} />
        <CalcRail card={selectedCard} />
      </div>
    </div>
  );
}
