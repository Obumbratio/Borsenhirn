import type { AnalysisCard } from "@/lib/signals";
import { usd } from "@/lib/signals";
import { Panel, PanelHeader, PanelBody } from "@/components/ui/Panel";

/**
 * Resumen del análisis impersonal de la empresa (dato REAL de /signals):
 * tesis renderizada de los factores (sin LLM que rellene) + precio + niveles
 * CON SU PROCEDENCIA visible (entry/stop/target + levels.fuentes) + trailing.
 * Describe el análisis, nunca recomienda para la cuenta del usuario.
 */
export function ResumenPanel({ card }: { card: AnalysisCard }) {
  const { levels } = card;
  const trailing =
    levels.trailing_pct != null ? `${(levels.trailing_pct * 100).toFixed(1)}%` : "—";

  return (
    <Panel>
      <PanelHeader
        title="Resumen"
        action={<span className="rounded bg-ac/15 px-1.5 py-0.5 text-[10.5px] text-ac">generado de datos</span>}
      />
      <PanelBody>
        <div className="flex items-baseline justify-between">
          <span className="font-fraunces text-lg font-semibold text-wht">{card.symbol}</span>
          <span className="num text-[12.5px] text-dim">
            precio <span className="text-tx">{usd(card.price)}</span>
          </span>
        </div>

        <p className="mt-2 text-[13px] leading-relaxed text-tx">{card.tesis}</p>

        {/* Niveles CON PROCEDENCIA visible (el diferenciador de la sección) */}
        <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-3">
          <LevelCell
            label="Entrada"
            value={usd(levels.entry)}
            tone="neutral"
            fuente={levels.fuentes?.entry}
          />
          <LevelCell label="Stop" value={usd(levels.stop)} tone="dn" fuente={levels.fuentes?.stop} />
          <LevelCell
            label="Objetivo"
            value={usd(levels.target)}
            tone="up"
            fuente={levels.fuentes?.target}
          />
        </div>

        {/* Trailing de referencia */}
        <p className="num mt-2 text-[11.5px] text-dim">
          Trailing stop de referencia: <span className="text-tx">{trailing}</span>
        </p>

        {/* Qué invalida la idea (parte del análisis impersonal) */}
        {card.que_invalida && (
          <p className="mt-3 border-t border-bd2 pt-2 text-[12px] text-dim">
            <span className="font-semibold text-dim">Qué invalida la idea:</span> {card.que_invalida}
          </p>
        )}
      </PanelBody>
    </Panel>
  );
}

/**
 * Celda de nivel: etiqueta + valor (mono, coloreado) + CAPTION de procedencia
 * debajo. La fuente queda legible (no apretada): línea propia, con su tooltip de
 * refuerzo. Si no hay fuente, no se inventa.
 */
function LevelCell({
  label,
  value,
  tone,
  fuente,
}: {
  label: string;
  value: string;
  tone: "neutral" | "up" | "dn";
  fuente?: string;
}) {
  const toneClass = tone === "dn" ? "text-dn" : tone === "up" ? "text-up" : "text-wht";
  return (
    <div className="rounded-lg border border-bd bg-pan2 px-3 py-2.5">
      <div className="text-[10.5px] uppercase tracking-wide text-dim2">{label}</div>
      <div className={`num mt-0.5 text-[15px] font-semibold ${toneClass}`}>{value}</div>
      {fuente && (
        <div className="mt-1.5 text-[10.5px] leading-snug text-dim2" title={fuente}>
          fuente: {fuente}
        </div>
      )}
    </div>
  );
}
