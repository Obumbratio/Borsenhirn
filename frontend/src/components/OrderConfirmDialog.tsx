"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import {
  acceptLegal,
  getLegalCurrent,
  placeOrder,
  type LegalVersions,
  type OrderSide,
  type PlacedOrder,
} from "@/lib/orders";
import { usd } from "@/lib/signals";

export type PendingOrder = {
  symbol: string;
  side: OrderSide;
  qty: number;
  estPrice: number | null; // precio de referencia (mercado); el fill real puede diferir
};

type Phase = "confirm" | "legal" | "result";
type Result =
  | { kind: "ok"; order: PlacedOrder }
  | { kind: "error"; status: number | null; message: string };

/**
 * Único camino a ejecutar una orden: confirmación explícita → POST /me/orders.
 * Reutilizado por la compra (calculadora) y la venta sugerida (alertas de
 * posiciones). Nunca ejecuta solo. Siempre PAPER.
 *
 * - Idempotencia: genera UN idempotency_key al abrirse para esta orden y lo
 *   reutiliza en cada reintento (doble-click / tras aceptar legal) → el backend
 *   devuelve la misma orden, no la duplica.
 * - 451 (legal): muestra el paso inline de aceptar Términos+Privacidad (queda
 *   registrado) y reintenta con la MISMA key.
 */
export function OrderConfirmDialog({
  order,
  onClose,
  onDone,
}: {
  order: PendingOrder | null;
  onClose: () => void;
  onDone?: () => void;
}) {
  const { getToken } = useAuth();
  const [phase, setPhase] = useState<Phase>("confirm");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [idemKey, setIdemKey] = useState("");

  // legal
  const [legalVersions, setLegalVersions] = useState<LegalVersions | null>(null);
  const [agreed, setAgreed] = useState(false);
  const [legalError, setLegalError] = useState<string | null>(null);

  const sig = order ? `${order.symbol}:${order.side}:${order.qty}` : "";

  // Orden nueva → reset + key fresca.
  useEffect(() => {
    if (order) {
      setIdemKey(crypto.randomUUID());
      setPhase("confirm");
      setResult(null);
      setAgreed(false);
      setLegalError(null);
      setLegalVersions(null);
    }
  }, [sig]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!order) return null;

  const isBuy = order.side === "buy";
  const verb = isBuy ? "COMPRAR" : "VENDER";
  const estTotal = order.estPrice != null ? order.estPrice * order.qty : null;

  async function submit(key: string) {
    setBusy(true);
    const res = await placeOrder(await getToken(), {
      symbol: order!.symbol,
      side: order!.side,
      qty: order!.qty,
      idempotencyKey: key,
    });
    setBusy(false);
    if (res.ok) {
      setResult({ kind: "ok", order: res.data });
      setPhase("result");
      onDone?.();
      return;
    }
    if (res.status === 451) {
      // Falta aceptación legal → paso inline.
      const lv = await getLegalCurrent();
      setLegalVersions(lv.ok ? lv.data.versions : null);
      setLegalError(lv.ok ? null : "No se pudieron cargar las versiones legales.");
      setPhase("legal");
      return;
    }
    setResult({ kind: "error", status: res.status, message: res.message });
    setPhase("result");
  }

  async function acceptAndRetry() {
    if (!legalVersions) return;
    setBusy(true);
    setLegalError(null);
    const token = await getToken();
    const r1 = await acceptLegal(token, "terms", legalVersions.terms);
    const r2 = r1.ok ? await acceptLegal(token, "privacy", legalVersions.privacy) : r1;
    if (!r1.ok || !r2.ok) {
      setBusy(false);
      setLegalError((!r1.ok ? r1.message : (r2 as { message: string }).message) || "No se pudo registrar la aceptación.");
      return;
    }
    // Aceptado y registrado → reintentar la MISMA orden (misma key).
    await submit(idemKey);
  }

  return (
    <Overlay onClose={onClose}>
      <div className="w-full max-w-md rounded-xl border border-neutral-700 bg-neutral-900 p-5 shadow-xl">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">
            {phase === "result" ? "Resultado" : phase === "legal" ? "Aceptación requerida" : "Confirmar orden"}
          </h2>
          <span className="rounded-full bg-sky-500/15 px-2.5 py-0.5 text-xs font-medium text-sky-300 ring-1 ring-sky-500/30">
            PAPER
          </span>
        </div>

        {phase === "confirm" && (
          <div className="mt-4">
            <p className="text-sm text-neutral-300">
              Vas a <span className="font-semibold">{verb}</span>{" "}
              <span className="font-mono text-neutral-100">{order.qty}</span> acciones de{" "}
              <span className="font-mono text-neutral-100">{order.symbol}</span>
            </p>
            <p className="mt-1 text-sm text-neutral-400">
              a precio de mercado{order.estPrice != null ? <> (~{usd(order.estPrice)})</> : null}
              {estTotal != null && (
                <>
                  {" "}· {isBuy ? "costo" : "ingreso"} estimado ≈{" "}
                  <span className="font-mono text-neutral-200">{usd(estTotal)}</span>
                </>
              )}
              .
            </p>
            <p className="mt-3 text-[11px] text-neutral-500">
              Cuenta de práctica (paper). El precio final puede variar respecto al estimado.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <button onClick={onClose} disabled={busy} className={btnGhost}>
                Cancelar
              </button>
              <button onClick={() => submit(idemKey)} disabled={busy} className={isBuy ? btnGreen : btnRed}>
                {busy ? "Enviando…" : isBuy ? "Confirmar compra" : "Confirmar venta"}
              </button>
            </div>
          </div>
        )}

        {phase === "legal" && (
          <div className="mt-4">
            <p className="text-sm text-neutral-300">
              Para operar necesitás aceptar nuestros{" "}
              <span className="text-neutral-100">Términos y Condiciones</span> y la{" "}
              <span className="text-neutral-100">Política de Privacidad</span>
              {legalVersions && (
                <span className="text-neutral-500">
                  {" "}(versión {legalVersions.terms} / {legalVersions.privacy})
                </span>
              )}
              . Tu aceptación queda registrada (usuario, versión y fecha).
            </p>
            <label className="mt-4 flex items-start gap-2 text-sm text-neutral-300">
              <input
                type="checkbox"
                checked={agreed}
                onChange={(e) => setAgreed(e.target.checked)}
                className="mt-0.5"
              />
              <span>Acepto los Términos y Condiciones y la Política de Privacidad.</span>
            </label>
            {legalError && <p className="mt-3 text-sm text-red-300">{legalError}</p>}
            <div className="mt-5 flex justify-end gap-2">
              <button onClick={onClose} disabled={busy} className={btnGhost}>
                Cancelar
              </button>
              <button
                onClick={acceptAndRetry}
                disabled={busy || !agreed || !legalVersions}
                className={btnGreen}
              >
                {busy ? "Registrando…" : "Aceptar y continuar"}
              </button>
            </div>
          </div>
        )}

        {phase === "result" && result && (
          <ResultBody result={result} idemKey={idemKey} onRetry={() => submit(idemKey)} onClose={onClose} busy={busy} />
        )}
      </div>
    </Overlay>
  );
}

function ResultBody({
  result,
  onRetry,
  onClose,
  busy,
}: {
  result: Result;
  idemKey: string;
  onRetry: () => void;
  onClose: () => void;
  busy: boolean;
}) {
  if (result.kind === "ok") {
    const o = result.order;
    return (
      <div className="mt-4">
        {o.idempotent ? (
          <p className="text-sm text-neutral-300">
            Ya habías enviado esta orden — <span className="text-neutral-100">no se duplicó</span>.
          </p>
        ) : (
          <p className="text-sm text-emerald-300">✅ Orden enviada.</p>
        )}
        <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
          <Row k="Orden" v={`${o.side.toUpperCase()} ${o.qty} ${o.symbol}`} />
          <Row k="Estado" v={o.status || "—"} />
          <Row k="ID" v={o.order_id ? `${o.order_id.slice(0, 8)}…` : "—"} mono />
          <Row k="Modo" v={o.mode} />
        </dl>
        <div className="mt-5 flex justify-end">
          <button onClick={onClose} className={btnGreen}>
            Cerrar
          </button>
        </div>
      </div>
    );
  }

  // error
  const is409 = result.status === 409;
  const is502 = result.status === 502;
  return (
    <div className="mt-4">
      <p className="text-sm font-semibold text-red-300">
        No se pudo enviar la orden{result.status ? ` (HTTP ${result.status})` : ""}
      </p>
      <p className="mt-2 text-sm text-neutral-400">{result.message}</p>
      {is409 && (
        <a href="/dashboard/broker" className="mt-3 inline-block text-sm text-emerald-400 underline underline-offset-2">
          Conectar Alpaca →
        </a>
      )}
      <div className="mt-5 flex justify-end gap-2">
        <button onClick={onClose} disabled={busy} className={btnGhost}>
          Cerrar
        </button>
        {is502 && (
          <button onClick={onRetry} disabled={busy} className={btnGreen}>
            {busy ? "Reintentando…" : "Reintentar"}
          </button>
        )}
      </div>
    </div>
  );
}

function Overlay({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div onClick={(e) => e.stopPropagation()}>{children}</div>
    </div>
  );
}

function Row({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <>
      <dt className="text-neutral-500">{k}</dt>
      <dd className={mono ? "font-mono text-neutral-200" : "text-neutral-200"}>{v}</dd>
    </>
  );
}

const btnGhost = "rounded-md border border-neutral-700 px-3 py-1.5 text-sm hover:bg-neutral-800 disabled:opacity-50";
const btnGreen = "rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium hover:bg-emerald-500 disabled:opacity-50";
const btnRed = "rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium hover:bg-red-500 disabled:opacity-50";
