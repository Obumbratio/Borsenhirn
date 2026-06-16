import type { AnalysisCard } from "@/lib/signals";
import { usd } from "@/lib/signals";

/**
 * Tarjeta de análisis (presentacional, server-safe). Muestra, por señal:
 * símbolo + precio, tesis, niveles (entrada/stop/objetivo), qué invalida la idea
 * y los factores con su PROCEDENCIA. Sin lógica de negocio: todo viene del backend.
 */
export function SignalCardView({ card }: { card: AnalysisCard }) {
  const { levels } = card;
  return (
    <article className="rounded-xl border border-neutral-800 bg-neutral-900/40 p-5">
      {/* Encabezado: símbolo + precio */}
      <header className="flex items-baseline justify-between">
        <h3 className="text-xl font-bold tracking-tight">{card.symbol}</h3>
        <span className="text-sm text-neutral-400">
          precio <span className="font-mono text-neutral-200">{usd(card.price)}</span>
        </span>
      </header>

      {/* Tesis */}
      <p className="mt-3 text-sm leading-relaxed text-neutral-300">{card.tesis}</p>

      {/* Niveles */}
      <div className="mt-4 grid grid-cols-3 gap-px overflow-hidden rounded-lg border border-neutral-800 bg-neutral-800 text-center">
        <Level label="Entrada" value={usd(levels.entry)} tone="neutral" hint={levels.fuentes?.entry} />
        <Level label="Stop" value={usd(levels.stop)} tone="red" hint={levels.fuentes?.stop} />
        <Level label="Objetivo" value={usd(levels.target)} tone="emerald" hint={levels.fuentes?.target} />
      </div>
      {levels.trailing_pct != null && (
        <p className="mt-1.5 text-[11px] text-neutral-500">
          Trailing stop de referencia: {(levels.trailing_pct * 100).toFixed(1)}%
        </p>
      )}

      {/* Qué invalida la idea */}
      <div className="mt-4 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-amber-300/90">
          Qué invalida la idea
        </p>
        <p className="mt-1 text-sm text-neutral-300">{card.que_invalida}</p>
      </div>

      {/* Factores con procedencia (anti-AI-washing) */}
      {card.factores.length > 0 && (
        <div className="mt-4">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-neutral-500">
            En qué se basa
          </p>
          <ul className="mt-2 space-y-1.5">
            {card.factores.map((f, i) => (
              <li key={i} className="flex flex-wrap items-baseline gap-x-2 text-sm">
                <span className="text-neutral-400">{f.factor}:</span>
                <span className="font-mono text-neutral-200">{String(f.valor)}</span>
                <span className="text-[11px] text-neutral-600">· {f.fuente}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Disclaimer por tarjeta */}
      <p className="mt-4 border-t border-neutral-800 pt-3 text-[11px] leading-relaxed text-neutral-500">
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
    tone === "red" ? "text-red-300" : tone === "emerald" ? "text-emerald-300" : "text-neutral-100";
  return (
    <div className="bg-neutral-900 px-2 py-3" title={hint}>
      <p className="text-[11px] uppercase tracking-wide text-neutral-500">{label}</p>
      <p className={`mt-1 font-mono text-base font-semibold ${toneClass}`}>{value}</p>
    </div>
  );
}
