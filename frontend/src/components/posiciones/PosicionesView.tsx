"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { getPositions, type Position } from "@/lib/orders";
import { usd } from "@/lib/signals";
import { StatsBar, type Stat } from "@/components/ui/StatsBar";
import { OrderConfirmDialog, type PendingOrder } from "@/components/OrderConfirmDialog";
import { PositionCard } from "@/components/posiciones/PositionCard";

/**
 * Posiciones (Fusión morado). Datos REALES de GET /me/positions; READ-ONLY.
 *
 * Ejecución: SOLO vía el botón de la alerta → OrderConfirmDialog (confirmación +
 * gate 451). No hay flujo de orden nuevo ni botón genérico de venta.
 *
 * Stats bar HONESTA: "valor de posiciones" y "P&L no realizado" se DERIVAN de las
 * posiciones (etiquetados como tales); el equity de cuenta (con efectivo) no
 * tiene GET → "—/próximamente". No se inventa.
 *
 * ?demo=1: recibe `demoPositions` y no llama al backend (banner MODO DEMO).
 */
export function PosicionesView({ demoPositions }: { demoPositions?: Position[] }) {
  const demo = demoPositions != null;
  const { getToken } = useAuth();
  const [positions, setPositions] = useState<Position[] | null>(demoPositions ?? null);
  const [error, setError] = useState<{ status: number | null; message: string } | null>(null);
  const [pending, setPending] = useState<PendingOrder | null>(null);

  const load = useCallback(async () => {
    if (demo) return; // en demo no se pega al backend
    setError(null);
    const res = await getPositions(await getToken());
    if (res.ok) setPositions(res.data.positions);
    else {
      setPositions(null);
      setError({ status: res.status, message: res.message });
    }
  }, [getToken, demo]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="mx-auto flex max-w-[1340px] flex-col gap-2">
      {demo && (
        <div className="rounded-lg border border-warn/30 bg-warn/10 px-3.5 py-2 text-[12px] text-warn">
          ⚠️ <span className="font-semibold">MODO DEMO</span> — posiciones de ejemplo solo para
          revisar el diseño. No son datos reales. Quitá <code className="font-mono">?demo=1</code> de
          la URL para volver al estado real.
        </div>
      )}

      <StatsBar stats={deriveStats(positions)} />

      <div className="flex flex-wrap items-center gap-2 px-1 pt-1">
        <h1 className="font-fraunces text-[22px] font-semibold text-wht">Posiciones</h1>
        <span className="rounded-full bg-ac/15 px-2.5 py-0.5 text-[11px] font-medium text-ac ring-1 ring-ac/30">
          PAPER
        </span>
      </div>

      {positions === null && !error && (
        <p className="px-1 text-[13px] text-dim">Cargando posiciones…</p>
      )}

      {error && <ErrorState status={error.status} message={error.message} onRetry={load} />}

      {positions !== null && positions.length === 0 && (
        <div className="rounded-xl border border-dashed border-bd bg-pan/40 p-10 text-center">
          <p className="text-[14px] font-medium text-tx">No tenés posiciones abiertas</p>
          <p className="mt-2 text-[12.5px] text-dim">Cuando ejecutes una orden, aparecerá acá.</p>
        </div>
      )}

      {positions && positions.length > 0 && (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {positions.map((p) => (
            <PositionCard key={p.symbol} p={p} onReview={setPending} />
          ))}
        </div>
      )}

      {/* Único camino de ejecución: el modal existente (confirmación + gate 451). */}
      <OrderConfirmDialog order={pending} onClose={() => setPending(null)} onDone={load} />
    </div>
  );
}

/** Deriva la stats bar SOLO de lo que las posiciones permiten honestamente. */
function deriveStats(positions: Position[] | null): Stat[] {
  if (!positions || positions.length === 0) {
    return [
      { label: "Valor posiciones", value: "—", pending: true },
      { label: "P&L no realizado", value: "—", pending: true },
      { label: "Posiciones", value: positions ? "0" : "—", pending: !positions },
      { label: "Equity cuenta", value: "—", pending: true },
    ];
  }
  const valor = positions.reduce((s, p) => s + p.current * p.qty, 0);
  const cost = positions.reduce((s, p) => s + p.avg_entry * p.qty, 0);
  const pnl = valor - cost;
  const pnlPct = cost > 0 ? (pnl / cost) * 100 : null;
  return [
    { label: "Valor posiciones", value: usd(valor) },
    {
      label: "P&L no realizado",
      value: `${usd(pnl)}${pnlPct != null ? ` (${pnlPct >= 0 ? "+" : ""}${pnlPct.toFixed(2)}%)` : ""}`,
      tone: pnl >= 0 ? "up" : "dn",
    },
    { label: "Posiciones", value: String(positions.length) },
    // Equity de cuenta (con efectivo) NO tiene GET → no se deriva ni se inventa.
    { label: "Equity cuenta", value: "—", pending: true },
  ];
}

function ErrorState({
  status,
  message,
  onRetry,
}: {
  status: number | null;
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="rounded-xl border border-dn/25 bg-dn/5 p-5">
      <p className="text-[13px] font-semibold text-dn">
        No se pudieron cargar las posiciones{status ? ` (HTTP ${status})` : ""}
      </p>
      <p className="mt-2 text-[13px] text-dim">{message}</p>
      {status === 409 && (
        <a href="/dashboard/broker" className="mt-3 inline-block text-[13px] text-ac underline underline-offset-2">
          Conectar Alpaca →
        </a>
      )}
      <button
        onClick={onRetry}
        className="mt-3 block rounded-md border border-bd px-3 py-1.5 text-[13px] text-tx hover:border-ac2"
      >
        Reintentar
      </button>
    </div>
  );
}
