import type { AnalysisCard } from "@/lib/signals";
import { usd } from "@/lib/signals";
import { PositionCalculator } from "@/components/PositionCalculator";

/**
 * Tarjeta de análisis (presentacional, server-safe). Muestra, por señal:
 * símbolo + precio, tesis, niveles (entrada/stop/objetivo), qué invalida la idea
 * y los factores con su PROCEDENCIA. Sin lógica de negocio: todo viene del backend.
 */
export function SignalCardView({ card }: { card: AnalysisCard }) {
  const { levels } = card;
  return (
    <article className="rounded-xl border border-bd bg-pan/40 p-5">
      {/* Encabezado: símbolo + precio */}
      <header className="flex items-baseline justify-between">
        <h3 className="font-fraunces text-xl font-bold tracking-tight text-wht">{card.symbol}</h3>
        <span className="text-sm text-dim">
          precio <span className="font-mono text-tx">{usd(card.price)}</span>
        </span>
      </header>

      {/* Tesis */}
      <p className="mt-3 text-sm leading-relaxed text-tx">{card.tesis}</p>

      {/* Niveles */}
      <div className="mt-4 grid grid-cols-3 gap-px overflow-hidden rounded-lg border border-bd bg-bd text-center">
        <Level label="Entrada" value={usd(levels.entry)} tone="neutral" hint={levels.fuentes?.entry} />
        <Level label="Stop" value={usd(levels.stop)} tone="red" hint={levels.fuentes?.stop} />
        <Level label="Objetivo" value={usd(levels.target)} tone="emerald" hint={levels.fuentes?.target} />
      </div>
      {levels.trailing_pct != null && (
        <p className="mt-1.5 text-[11px] text-dim">
          Trailing stop de referencia: {(levels.trailing_pct * 100).toFixed(1)}%
        </p>
      )}

      {/* Qué invalida la idea */}
      <div className="mt-4 rounded-lg border border-warn/20 bg-warn/5 p-3">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-warn">
          Qué invalida la idea
        </p>
        <p className="mt-1 text-sm text-tx">{card.que_invalida}</p>
      </div>

      {/* Factores con procedencia (anti-AI-washing) */}
      {card.factores.length > 0 && (
        <div className="mt-4">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-dim">
            En qué se basa
          </p>
          <ul className="mt-2 space-y-1.5">
            {card.factores.map((f, i) => (
              <li key={i} className="flex flex-wrap items-baseline gap-x-2 text-sm">
                <span className="text-dim">{f.factor}:</span>
                <span className="font-mono text-tx">{String(f.valor)}</span>
                <span className="text-[11px] text-dim2">· {f.fuente}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Calculadora de posición (el usuario la opera con sus números) */}
      <PositionCalculator symbol={card.symbol} entry={levels.entry} stop={levels.stop} target={levels.target} />

      {/* Disclaimer por tarjeta */}
      <p className="mt-4 border-t border-bd pt-3 text-[11px] leading-relaxed text-dim">
        {card.disclaimer}
      </p>
    </article>
  );
}

function Level({
  label,
  value,
  tone,
  hint,
}: {
  label: string;
  value: string;
  tone: "neutral" | "red" | "emerald";
  hint?: string;
}) {
  const toneClass =
    tone === "red" ? "text-dn" : tone === "emerald" ? "text-up" : "text-wht";
  return (
    <div className="bg-pan px-2 py-3" title={hint}>
      <p className="text-[11px] uppercase tracking-wide text-dim">{label}</p>
      <p className={`mt-1 font-mono text-base font-semibold ${toneClass}`}>{value}</p>
    </div>
  );
}
