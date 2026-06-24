import type { AnalysisCard } from "@/lib/signals";
import { usd } from "@/lib/signals";
import { Panel } from "@/components/ui/Panel";
import { buildChartGeom } from "@/lib/chart-demo";

const TIMEFRAMES = ["1D", "1S", "1M", "3M", "1A"];

/**
 * Columna central del Tablero: el gráfico protagonista.
 *
 * - Cabecera: símbolo + precio (reales) + botón Comprar (lleva a la calculadora,
 *   nunca ejecuta de un click → la ejecución pasa por la calculadora + diálogo).
 * - Disclaimer impersonal CONSERVADO textual (línea legal).
 * - Velas: DEMOSTRACIÓN etiquetada (aún sin feed OHLC). Encima, las líneas
 *   reales de entrada/stop/objetivo de la señal seleccionada.
 */
export function ChartPanel({ card }: { card: AnalysisCard | null }) {
  if (!card) {
    return (
      <Panel className="flex min-h-[360px] items-center justify-center">
        <p className="text-[13px] text-dim">Elegí una señal a la izquierda para ver su gráfico.</p>
      </Panel>
    );
  }

  const { levels } = card;
  const geom = buildChartGeom({
    symbol: card.symbol,
    price: card.price,
    entry: levels.entry,
    stop: levels.stop,
    target: levels.target,
  });

  return (
    <Panel>
      {/* Cabecera: símbolo + precio + Comprar */}
      <div className="flex items-center gap-3 border-b border-bd2 px-3.5 py-2.5 text-[12.5px] text-dim">
        <span className="font-fraunces text-lg font-semibold text-wht">{card.symbol}</span>
        <span className="num font-semibold text-up">{usd(card.price)}</span>
        <a
          href="#calc"
          title="Calculá tu tamaño abajo y confirmá — nunca se ejecuta de un click"
          className="ml-auto rounded-md bg-gradient-to-br from-ac2 to-[#7c3aed] px-4 py-1.5 font-semibold text-white"
        >
          Comprar
        </a>
      </div>

      {/* Disclaimer impersonal — línea legal conservada */}
      <div className="border-b border-bd2 px-3.5 py-2 text-[11px] leading-snug text-dim2">
        <span className="font-semibold text-dim">Análisis general, no es recomendación.</span>{" "}
        Información impersonal — igual para todos. No mira tu cuenta. Vos decidís, calculás tu
        tamaño y ejecutás.
      </div>

      {/* Gráfico */}
      <div className="px-3 pt-3">
        <svg viewBox={`0 0 ${geom.width} ${geom.height}`} className="h-[260px] w-full" preserveAspectRatio="none">
          {/* grilla */}
          <g stroke="var(--bd2)">
            {geom.gridY.map((y, i) => (
              <line key={i} x1="0" y1={y} x2={geom.width} y2={y} />
            ))}
          </g>

          {/* líneas reales: objetivo / stop / entrada */}
          {geom.lineY.target != null && (
            <>
              <line x1="0" y1={geom.lineY.target} x2={geom.width} y2={geom.lineY.target} stroke="var(--up)" strokeWidth="1" strokeDasharray="4 4" />
              <text x="6" y={geom.lineY.target - 4} fontSize="9.5" fill="var(--up)" className="font-mono">
                objetivo {usd(levels.target)}
              </text>
            </>
          )}
          {geom.lineY.stop != null && (
            <>
              <line x1="0" y1={geom.lineY.stop} x2={geom.width} y2={geom.lineY.stop} stroke="var(--dn)" strokeWidth="1" strokeDasharray="4 4" />
              <text x="6" y={geom.lineY.stop - 4} fontSize="9.5" fill="var(--dn)" className="font-mono">
                stop {usd(levels.stop)}
              </text>
            </>
          )}
          {geom.lineY.entry != null && (
            <>
              <line x1="0" y1={geom.lineY.entry} x2={geom.width} y2={geom.lineY.entry} stroke="var(--ac)" strokeWidth="1" strokeDasharray="2 3" />
              <text x="6" y={geom.lineY.entry - 4} fontSize="9.5" fill="var(--ac)" className="font-mono">
                entrada {usd(levels.entry)}
              </text>
            </>
          )}

          {/* velas (demostración) */}
          <g>
            {geom.candles.map((c, i) => {
              const color = c.up ? "var(--up)" : "var(--dn)";
              return (
                <g key={i}>
                  <line x1={c.x} y1={c.wickY1} x2={c.x} y2={c.wickY2} stroke={color} />
                  <rect x={c.x - 4} y={c.bodyY} width="8" height={c.bodyH} fill={color} />
                </g>
              );
            })}
          </g>
        </svg>
      </div>

      {/* timeframe + etiqueta de honestidad sobre las velas */}
      <div className="flex items-center gap-3.5 border-t border-bd2 px-4 py-2.5 text-[11.5px] text-dim2">
        {TIMEFRAMES.map((tf) => (
          <span key={tf} className={tf === "1S" ? "text-ac" : ""}>
            {tf}
          </span>
        ))}
        <span className="ml-auto">Velas ▾</span>
      </div>
      <div className="border-t border-bd2 px-4 py-2 text-[10.5px] leading-snug text-dim2">
        ⚠️ Velas de <span className="text-dim">demostración</span> — el feed de precios reales
        está en camino. Las líneas de <span className="text-ac">entrada</span>,{" "}
        <span className="text-dn">stop</span> y <span className="text-up">objetivo</span> sí son
        datos reales de la señal.
      </div>
    </Panel>
  );
}
