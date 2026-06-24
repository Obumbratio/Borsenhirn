import type { Position } from "@/lib/orders";
import { usd } from "@/lib/signals";
import type { PendingOrder } from "@/components/OrderConfirmDialog";
import { Panel, PanelBody } from "@/components/ui/Panel";
import { AlertBox } from "@/components/posiciones/AlertBox";

/**
 * Tarjeta de una posición (datos REALES de GET /me/positions). READ-ONLY: la
 * única vía a ejecutar es el botón de la alerta → OrderConfirmDialog. Si hay
 * alerta, el borde se tiñe de ámbar para destacarla.
 */
export function PositionCard({
  p,
  onReview,
}: {
  p: Position;
  onReview: (o: PendingOrder) => void;
}) {
  const up = p.pnl_pct >= 0;
  const hasAlert = p.alertas.length > 0;

  return (
    <Panel className={hasAlert ? "border-warn/40" : ""}>
      <PanelBody>
        <div className="flex items-baseline justify-between">
          <span className="font-fraunces text-lg font-semibold text-wht">{p.symbol}</span>
          <span className={`num text-[14px] font-semibold ${up ? "text-up" : "text-dn"}`}>
            {up ? "+" : ""}
            {p.pnl_pct}%
          </span>
        </div>
        <p className="num mt-1 text-[12px] text-dim">
          {p.qty} acciones · entrada <span className="text-tx">{usd(p.avg_entry)}</span> · actual{" "}
          <span className="text-tx">{usd(p.current)}</span>
        </p>

        {p.alertas.map((a, i) => (
          <AlertBox key={i} a={a} current={p.current} onReview={onReview} />
        ))}
      </PanelBody>
    </Panel>
  );
}
