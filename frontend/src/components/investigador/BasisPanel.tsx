import type { AnalysisCard } from "@/lib/signals";
import { Panel, PanelHeader, PanelBody } from "@/components/ui/Panel";

/**
 * "En qué se basa el análisis" — el corazón anti-AI-washing (dato REAL de
 * /signals): cada factor con su PROCEDENCIA (`fuente`). Nada inventado: si no
 * hay factores, lo decimos.
 */
export function BasisPanel({ card }: { card: AnalysisCard }) {
  return (
    <Panel>
      <PanelHeader title="En qué se basa el análisis" />
      <PanelBody>
        {card.factores.length === 0 ? (
          <p className="text-[12.5px] text-dim">Este análisis no expone factores.</p>
        ) : (
          <ul className="space-y-2">
            {card.factores.map((f, i) => (
              <li key={i} className="flex flex-wrap items-baseline gap-x-2 text-[12.5px]">
                <span className="text-dim">{f.factor}:</span>
                <span className="num text-tx">{String(f.valor)}</span>
                <span className="rounded bg-ac/15 px-1.5 py-0.5 text-[10.5px] text-ac">{f.fuente}</span>
              </li>
            ))}
          </ul>
        )}
      </PanelBody>
    </Panel>
  );
}
