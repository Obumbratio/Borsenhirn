import { Panel, PanelBody } from "@/components/ui/Panel";
import { RelativeTime } from "@/components/ui/RelativeTime";

export const dynamic = "force-dynamic";

type WhaleAlert = {
  id: string;
  symbol: string;
  type: "BLOCK_BUY" | "BLOCK_SELL" | "SWEEP_BUY" | "OPTION_CALL" | "OPTION_PUT";
  qty: number;
  price: number;
  value: number;
  timestamp: string;
  details?: string;
};

const MOCK_ALERTS: WhaleAlert[] = [
  {
    id: "w1",
    symbol: "NVDA",
    type: "BLOCK_BUY",
    qty: 55000,
    price: 128.4,
    value: 7062000,
    timestamp: new Date(Date.now() - 12 * 60 * 1000).toISOString(),
    details: "Operación en bloque en mercado secundario.",
  },
  {
    id: "w2",
    symbol: "AAPL",
    type: "BLOCK_SELL",
    qty: 115000,
    price: 178.2,
    value: 20493000,
    timestamp: new Date(Date.now() - 28 * 60 * 1000).toISOString(),
    details: "Liquidación institucional detectada en cruce de bloques.",
  },
  {
    id: "w3",
    symbol: "MSFT",
    type: "OPTION_CALL",
    qty: 1200,
    price: 4.5,
    value: 540000,
    timestamp: new Date(Date.now() - 48 * 60 * 1000).toISOString(),
    details: "Opción Call 18-Ago-2026 $450.00 · Cerca del Ask.",
  },
  {
    id: "w4",
    symbol: "AMD",
    type: "SWEEP_BUY",
    qty: 78000,
    price: 154.6,
    value: 12058800,
    timestamp: new Date(Date.now() - 75 * 60 * 1000).toISOString(),
    details: "Barrido agresivo a través de múltiples exchanges.",
  },
  {
    id: "w5",
    symbol: "TSLA",
    type: "OPTION_PUT",
    qty: 2500,
    price: 6.2,
    value: 1550000,
    timestamp: new Date(Date.now() - 120 * 60 * 1000).toISOString(),
    details: "Opción Put 18-Sep-2026 $180.00 · Apertura inusual.",
  },
];

export default function WhalePage() {
  return (
    <div className="mx-auto flex max-w-[1000px] flex-col gap-2">
      <header className="px-1 pt-1">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="font-fraunces text-[22px] font-semibold text-wht">Whale Alerts</h1>
          <span className="rounded-full bg-ac/15 px-2.5 py-0.5 text-xs font-semibold text-ac border border-ac/20">
            MAQUETA DEMO
          </span>
        </div>
        <p className="mt-0.5 text-[13px] text-dim">
          Flujo de transacciones institucionales inusuales y sweeps de opciones. Datos mock para desarrollo.
        </p>
      </header>

      <div className="mt-2 flex flex-col gap-3">
        {MOCK_ALERTS.map((alert) => (
          <AlertCard key={alert.id} alert={alert} />
        ))}
      </div>

      <p className="mt-4 px-1 text-[11px] leading-snug text-dim2">
        Los datos de ballenas son informativos y no constituyen recomendaciones de inversión.
        Datos simulados con fines de validación estética y de interfaz de usuario.
      </p>
    </div>
  );
}

function AlertCard({ alert }: { alert: WhaleAlert }) {
  const typeLabels: Record<WhaleAlert["type"], { label: string; tone: "up" | "dn" | "neutral" }> = {
    BLOCK_BUY: { label: "Block Buy", tone: "up" },
    BLOCK_SELL: { label: "Block Sell", tone: "dn" },
    SWEEP_BUY: { label: "Sweep Buy", tone: "up" },
    OPTION_CALL: { label: "Option Call", tone: "up" },
    OPTION_PUT: { label: "Option Put", tone: "dn" },
  };

  const info = typeLabels[alert.type];
  const badgeClass =
    info.tone === "up"
      ? "bg-up/10 text-up border border-up/25"
      : info.tone === "dn"
        ? "bg-dn/10 text-dn border border-dn/25"
        : "bg-dim/15 text-dim border border-dim/20";

  return (
    <Panel>
      <PanelBody>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <span className="font-fraunces text-base font-bold text-wht">{alert.symbol}</span>
            <span className={`rounded-md px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${badgeClass}`}>
              {info.label}
            </span>
          </div>
          <span className="text-[11px] text-dim2">
            <RelativeTime iso={alert.timestamp} />
          </span>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Stat label="Volumen" value={alert.qty.toLocaleString()} />
          <Stat label="Precio Est." value={`$${alert.price.toFixed(2)}`} />
          <Stat label="Valor Total" value={`$${(alert.value / 1e6).toFixed(2)}M`} tone={info.tone} />
          <Stat label="Tipo" value={alert.type.replace("_", " ")} />
        </div>

        {alert.details && (
          <p className="mt-2.5 border-t border-bd2 pt-2.5 text-xs text-dim leading-relaxed">
            {alert.details}
          </p>
        )}
      </PanelBody>
    </Panel>
  );
}

function Stat({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "up" | "dn" | "neutral" }) {
  const toneClass =
    tone === "up" ? "text-up" : tone === "dn" ? "text-dn" : "text-tx";
  return (
    <div>
      <span className="block text-[10px] uppercase tracking-wider text-dim">{label}</span>
      <span className={`mt-0.5 block font-mono text-sm font-semibold ${toneClass}`}>{value}</span>
    </div>
  );
}
