import type { AnalysisCard } from "@/lib/signals";
import { usd } from "@/lib/signals";
import { Panel, PanelHeader } from "@/components/ui/Panel";

/** Extrae la prob. del modelo ML de los factores (dato real) para el badge. */
function mlProb(card: AnalysisCard): string | null {
  const f = card.factores.find((x) => /probabilidad/i.test(x.factor));
  if (!f || f.valor == null) return null;
  const n = typeof f.valor === "number" ? f.valor : parseFloat(String(f.valor));
  return Number.isFinite(n) ? n.toFixed(2) : null;
}

/**
 * Columna izquierda del Tablero: lista compacta de señales (impersonal, con
 * niveles reales). Click → selecciona el símbolo que ve la gráfica y la
 * calculadora. Todo el dato viene de GET /signals.
 */
export function SignalsRail({
  cards,
  selected,
  onSelect,
}: {
  cards: AnalysisCard[];
  selected: string | null;
  onSelect: (symbol: string) => void;
}) {
  return (
    <Panel>
      <PanelHeader title="Señales · impersonal" icon="◆" action="⋯" />
      <div className="px-3.5 py-1">
        {cards.length === 0 && (
          <p className="py-4 text-[12.5px] text-dim">
            No hay setups ahora mismo. No tener señal también es información.
          </p>
        )}
        {cards.map((card) => {
          const prob = mlProb(card);
          const active = card.symbol === selected;
          return (
            <button
              key={card.symbol}
              type="button"
              onClick={() => onSelect(card.symbol)}
              className={`block w-full border-b border-bd2 py-2 text-left last:border-0 ${
                active ? "-mx-2 rounded-md bg-ac/10 px-2" : ""
              }`}
            >
              <div className="flex items-center justify-between">
                <span className={`text-[13px] font-bold ${active ? "text-ac" : "text-wht"}`}>
                  {card.symbol}
                </span>
                {prob && (
                  <span className="rounded bg-ac/15 px-1.5 py-0.5 text-[11px] font-semibold text-ac">
                    ML {prob}
                  </span>
                )}
              </div>
              <div className="num mt-0.5 text-[11.5px] text-dim">
                {usd(card.levels.entry)} · stop <span className="text-dn">{usd(card.levels.stop)}</span> · obj{" "}
                <span className="text-up">{usd(card.levels.target)}</span>
              </div>
            </button>
          );
        })}
      </div>
    </Panel>
  );
}
