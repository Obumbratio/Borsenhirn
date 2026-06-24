import type { DemoNews } from "@/lib/demo-signals";
import { Panel, PanelHeader, PanelBody } from "@/components/ui/Panel";

/**
 * Noticias recientes de la empresa.
 * HONESTIDAD: no hay endpoint real todavía → sin datos se muestra "—
 * próximamente". Sólo se llena con datos de DEMOSTRACIÓN bajo ?demo=1.
 */
export function NewsPanel({ items }: { items?: DemoNews[] }) {
  return (
    <Panel>
      <PanelHeader title="Noticias recientes" icon="📰" grip={false} />
      <PanelBody>
        {!items || items.length === 0 ? (
          <p className="text-[12.5px] text-dim2" title="Próximamente — aún sin fuente de dato real">
            — Próximamente: feed de noticias por empresa.
          </p>
        ) : (
          items.map((n, i) => (
            <div
              key={i}
              className={`py-2 text-[12px] ${i < items.length - 1 ? "border-b border-bd2" : ""}`}
            >
              <div className="text-tx">{n.title}</div>
              <div className="mt-0.5 text-[10.5px] text-dim2">
                {n.source} · {n.when}
              </div>
            </div>
          ))
        )}
      </PanelBody>
    </Panel>
  );
}
