"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { getPositions, type Alerta, type Position } from "@/lib/orders";
import { usd } from "@/lib/signals";
import { OrderConfirmDialog, type PendingOrder } from "@/components/OrderConfirmDialog";

/**
 * Panel de posiciones (GET /me/positions). READ-ONLY: nunca ejecuta.
 * Las alertas TP/SL se muestran como ALERTA + botón "Revisar orden sugerida"
 * (jamás "vendé"): el botón pre-llena el diálogo de confirmación y el usuario
 * decide. Toda ejecución pasa por OrderConfirmDialog.
 */
export function PositionsPanel() {
  const { getToken } = useAuth();
  const [positions, setPositions] = useState<Position[] | null>(null);
  const [error, setError] = useState<{ status: number | null; message: string } | null>(null);
  const [pending, setPending] = useState<PendingOrder | null>(null);

  const load = useCallback(async () => {
    setError(null);
    const res = await getPositions(await getToken());
    if (res.ok) setPositions(res.data.positions);
    else {
      setPositions(null);
      setError({ status: res.status, message: res.message });
    }
  }, [getToken]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="mx-auto max-w-2xl">
      <header className="mb-6 flex flex-wrap items-center gap-2">
        <h1 className="text-2xl font-bold tracking-tight">Posiciones</h1>
        <span className="rounded-full bg-sky-500/15 px-2.5 py-0.5 text-xs font-medium text-sky-300 ring-1 ring-sky-500/30">
          PAPER
        </span>
      </header>

      {positions === null && !error && <p className="text-sm text-neutral-500">Cargando posiciones…</p>}

      {error && <ErrorState status={error.status} message={error.message} onRetry={load} />}

      {positions !== null && positions.length === 0 && (
        <div className="rounded-xl border border-dashed border-neutral-800 bg-neutral-900/30 p-10 text-center">
          <p className="text-base font-medium text-neutral-300">No tenés posiciones abiertas</p>
          <p className="mt-2 text-sm text-neutral-500">Cuando ejecutes una orden, aparecerá acá.</p>
        </div>
      )}

      {positions && positions.length > 0 && (
        <div className="space-y-4">
          {positions.map((p) => (
            <PositionCard key={p.symbol} p={p} onReview={setPending} />
          ))}
        </div>
      )}

      <OrderConfirmDialog order={pending} onClose={() => setPending(null)} onDone={load} />
    </div>
  );
}

function PositionCard({ p, onReview }: { p: Position; onReview: (o: PendingOrder) => void }) {
  const up = p.pnl_pct >= 0;
  return (
    <article className="rounded-xl border border-neutral-800 bg-neutral-900/40 p-5">
      <header className="flex items-baseline justify-between">
        <h3 className="text-lg font-bold">{p.symbol}</h3>
        <span className={`font-mono text-sm font-semibold ${up ? "text-emerald-300" : "text-red-300"}`}>
          {up ? "+" : ""}
          {p.pnl_pct}%
        </span>
      </header>
      <p className="mt-1 text-sm text-neutral-400">
        {p.qty} acciones · entrada <span className="font-mono text-neutral-300">{usd(p.avg_entry)}</span> · actual{" "}
        <span className="font-mono text-neutral-300">{usd(p.current)}</span>
      </p>

      {p.alertas.map((a, i) => (
        <AlertBox key={i} a={a} current={p.current} onReview={onReview} />
      ))}
    </article>
  );
}

function AlertBox({
  a,
  current,
  onReview,
}: {
  a: Alerta;
  current: number;
  onReview: (o: PendingOrder) => void;
}) {
  const isTarget = a.tipo === "objetivo_alcanzado";
  const tone = isTarget
    ? "border-emerald-500/25 bg-emerald-500/5"
    : "border-amber-500/25 bg-amber-500/5";
  const label = isTarget ? "text-emerald-300/90" : "text-amber-300/90";
  return (
    <div className={`mt-4 rounded-lg border p-3 ${tone}`}>
      <p className={`text-[11px] font-semibold uppercase tracking-wide ${label}`}>{a.tipo.replace("_", " ")}</p>
      <p className="mt-1 text-sm text-neutral-300">{a.mensaje}</p>
      <button
        onClick={() =>
          onReview({
            symbol: a.sugerido.symbol,
            side: a.sugerido.side,
            qty: a.sugerido.qty,
            estPrice: current,
          })
        }
        className="mt-3 rounded-md border border-neutral-700 px-3 py-1.5 text-sm text-neutral-200 hover:bg-neutral-800"
      >
        Revisar orden sugerida
      </button>
      <p className="mt-2 text-[11px] text-neutral-500">
        Es una sugerencia para que la revises — no ejecutamos nada hasta que confirmes.
      </p>
    </div>
  );
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
    <div className="rounded-xl border border-red-500/25 bg-red-500/5 p-5">
      <p className="text-sm font-semibold text-red-300">
        No se pudieron cargar las posiciones{status ? ` (HTTP ${status})` : ""}
      </p>
      <p className="mt-2 text-sm text-neutral-400">{message}</p>
      {status === 409 && (
        <a href="/dashboard/broker" className="mt-3 inline-block text-sm text-emerald-400 underline underline-offset-2">
          Conectar Alpaca →
        </a>
      )}
      <button onClick={onRetry} className="mt-3 ml-0 block rounded-md border border-neutral-700 px-3 py-1.5 text-sm hover:bg-neutral-800">
        Reintentar
      </button>
    </div>
  );
}
