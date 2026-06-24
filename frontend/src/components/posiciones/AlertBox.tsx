import type { Alerta } from "@/lib/orders";
import type { PendingOrder } from "@/components/OrderConfirmDialog";

/**
 * Alerta TP/SL de una posición. ALERTA, nunca "vendé".
 *
 * - `a.mensaje` viene del BACKEND (position_alerts) — describe el escenario; no
 *   se hardcodea lenguaje de venta en el frontend.
 * - El botón "Revisar orden sugerida" abre el OrderConfirmDialog con el
 *   `a.sugerido` del backend (side/qty/symbol). El frontend NO fabrica la orden:
 *   pasa lo que el backend sugirió y el usuario confirma. `estPrice` es solo
 *   precio de referencia para el estimado, no parte de la semántica de la orden.
 */
export function AlertBox({
  a,
  current,
  onReview,
}: {
  a: Alerta;
  current: number;
  onReview: (o: PendingOrder) => void;
}) {
  const isTarget = a.tipo === "objetivo_alcanzado";
  const tone = isTarget ? "border-up/25 bg-up/5" : "border-warn/30 bg-warn/10";
  const labelColor = isTarget ? "text-up" : "text-warn";

  return (
    <div className={`mt-3 rounded-lg border p-3 ${tone}`}>
      <p className={`text-[11px] font-semibold uppercase tracking-wide ${labelColor}`}>
        {a.tipo.replace("_", " ")}
      </p>
      <p className="mt-1 text-[12.5px] leading-snug text-tx">{a.mensaje}</p>
      <button
        onClick={() =>
          onReview({
            symbol: a.sugerido.symbol,
            side: a.sugerido.side,
            qty: a.sugerido.qty,
            estPrice: current,
          })
        }
        className="mt-3 rounded-md border border-bd bg-pan2 px-3 py-1.5 text-[12.5px] text-ac hover:border-ac2"
      >
        Revisar orden sugerida
      </button>
      <p className="mt-2 text-[10.5px] text-dim2">
        Es una sugerencia para que la revises — no ejecutamos nada hasta que confirmes.
      </p>
    </div>
  );
}
