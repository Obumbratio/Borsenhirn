import { Panel, PanelBody } from "@/components/ui/Panel";

export const dynamic = "force-dynamic";

type TradeRecord = {
  id: string;
  symbol: string;
  side: "LONG" | "SHORT";
  entryPrice: number;
  exitPrice: number;
  pctChange: number;
  closedAt: string;
};

const MOCK_CLOSED_TRADES: TradeRecord[] = [
  {
    id: "t1",
    symbol: "NVDA",
    side: "LONG",
    entryPrice: 112.5,
    exitPrice: 126.4,
    pctChange: 12.35,
    closedAt: "2026-07-10",
  },
  {
    id: "t2",
    symbol: "MSFT",
    side: "LONG",
    entryPrice: 420.1,
    exitPrice: 440.5,
    pctChange: 4.85,
    closedAt: "2026-07-08",
  },
  {
    id: "t3",
    symbol: "AAPL",
    side: "LONG",
    entryPrice: 182.3,
    exitPrice: 178.5,
    pctChange: -2.08,
    closedAt: "2026-07-05",
  },
  {
    id: "t4",
    symbol: "AMD",
    side: "LONG",
    entryPrice: 142.0,
    exitPrice: 154.6,
    pctChange: 8.87,
    closedAt: "2026-07-02",
  },
  {
    id: "t5",
    symbol: "TSLA",
    side: "LONG",
    entryPrice: 186.5,
    exitPrice: 180.0,
    pctChange: -3.48,
    closedAt: "2026-06-29",
  },
];

export default function TrackPage() {
  return (
    <div className="mx-auto flex max-w-[1000px] flex-col gap-3">
      <header className="px-1 pt-1">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="font-fraunces text-[22px] font-semibold text-wht">Desempeño de Estrategia</h1>
          <span className="rounded-full bg-ac/15 px-2.5 py-0.5 text-xs font-semibold text-ac border border-ac/20">
            MAQUETA DEMO
          </span>
        </div>
        <p className="mt-0.5 text-[13px] text-dim">
          Historial de desempeño y track record público de las señales en paper trading. Datos mock de ejemplo.
        </p>
      </header>

      {/* Grid de Métricas */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricCard label="Retorno Acumulado" value="+42.8%" tone="up" />
        <MetricCard label="Win Rate" value="68.2%" />
        <MetricCard label="Max Drawdown" value="-6.4%" tone="dn" />
        <MetricCard label="Profit Factor" value="2.15" />
      </div>

      {/* Gráfica de Equity (SVG Puro) */}
      <Panel>
        <PanelBody>
          <h3 className="text-sm font-semibold text-tx">Curva de Capital (Equity Curve)</h3>
          <p className="text-[11px] text-dim">Rendimiento acumulado simulado · base 100%</p>

          <div className="mt-4 h-[200px] w-full">
            <svg viewBox="0 0 1000 200" className="h-full w-full" preserveAspectRatio="none">
              <defs>
                <linearGradient id="equity-grad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#8b5cf6" stopOpacity="0.25" />
                  <stop offset="100%" stopColor="#8b5cf6" stopOpacity="0.0" />
                </linearGradient>
              </defs>
              {/* Grid Lines */}
              <line x1="0" y1="50" x2="1000" y2="50" stroke="#241d36" strokeDasharray="4 4" />
              <line x1="0" y1="100" x2="1000" y2="100" stroke="#241d36" strokeDasharray="4 4" />
              <line x1="0" y1="150" x2="1000" y2="150" stroke="#241d36" strokeDasharray="4 4" />

              {/* Area */}
              <path
                d="M 0 150 Q 250 140, 500 110 T 1000 50 L 1000 200 L 0 200 Z"
                fill="url(#equity-grad)"
              />

              {/* Line */}
              <path
                d="M 0 150 Q 250 140, 500 110 T 1000 50"
                fill="none"
                stroke="#a78bfa"
                strokeWidth="2.5"
                strokeLinecap="round"
              />

              {/* Dots */}
              <circle cx="0" cy="150" r="4" fill="#8b5cf6" />
              <circle cx="250" cy="142" r="4" fill="#8b5cf6" />
              <circle cx="500" cy="110" r="4" fill="#8b5cf6" />
              <circle cx="750" cy="78" r="4" fill="#8b5cf6" />
              <circle cx="1000" cy="50" r="4" fill="#4ade80" />
            </svg>
          </div>
          <div className="mt-2 flex justify-between text-[10px] text-dim2 font-mono">
            <span>Inicio (May 2026)</span>
            <span>Jun 2026</span>
            <span>Hoy (Jul 2026)</span>
          </div>
        </PanelBody>
      </Panel>

      {/* Historial de Trades */}
      <Panel>
        <PanelBody>
          <h3 className="text-sm font-semibold text-tx">Últimos Trades Cerrados</h3>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-bd text-dim">
                  <th className="py-2">Símbolo</th>
                  <th className="py-2">Dirección</th>
                  <th className="py-2">Entrada</th>
                  <th className="py-2">Salida</th>
                  <th className="py-2 text-right">Resultado</th>
                  <th className="py-2 text-right">Cerrado el</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-bd2">
                {MOCK_CLOSED_TRADES.map((trade) => {
                  const isWin = trade.pctChange >= 0;
                  return (
                    <tr key={trade.id} className="text-tx">
                      <td className="py-2.5 font-bold">{trade.symbol}</td>
                      <td className="py-2.5">
                        <span className="rounded bg-bd px-1.5 py-0.5 text-[10px] font-semibold">
                          {trade.side}
                        </span>
                      </td>
                      <td className="py-2.5 font-mono">${trade.entryPrice.toFixed(2)}</td>
                      <td className="py-2.5 font-mono">${trade.exitPrice.toFixed(2)}</td>
                      <td className={`py-2.5 font-mono text-right font-semibold ${isWin ? "text-up" : "text-dn"}`}>
                        {isWin ? "+" : ""}
                        {trade.pctChange.toFixed(2)}%
                      </td>
                      <td className="py-2.5 font-mono text-right text-dim">{trade.closedAt}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </PanelBody>
      </Panel>

      <p className="mt-2 px-1 text-[11px] leading-snug text-dim2">
        Rendimientos pasados no garantizan rendimientos futuros. Todas las operaciones
        mostradas corresponden al robot de pruebas y se ejecutan en cuentas de simulación (paper trading).
      </p>
    </div>
  );
}

function MetricCard({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "up" | "dn" | "neutral" }) {
  const toneClass =
    tone === "up" ? "text-up" : tone === "dn" ? "text-dn" : "text-wht";
  return (
    <Panel>
      <PanelBody className="py-3 text-center">
        <span className="block text-[10px] uppercase tracking-wider text-dim">{label}</span>
        <span className={`mt-1 block font-mono text-lg font-bold ${toneClass}`}>{value}</span>
      </PanelBody>
    </Panel>
  );
}
