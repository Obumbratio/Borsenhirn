import type { DemoFundamentals } from "@/lib/demo-signals";
import { Panel, PanelHeader, PanelBody } from "@/components/ui/Panel";

/**
 * Fundamentales (P/E, Margen, Cap. mercado, Sector).
 * HONESTIDAD: no hay endpoint real todavía → sin datos se muestra "—" con
 * tooltip "próximamente". Sólo se llena con datos de DEMOSTRACIÓN bajo ?demo=1.
 */
export function FundamentalsPanel({ data }: { data?: DemoFundamentals }) {
  const rows: { label: string; value?: string }[] = [
    { label: "P/E", value: data?.pe },
    { label: "Margen", value: data?.margin },
    { label: "Cap. mercado", value: data?.marketCap },
    { label: "Sector", value: data?.sector },
  ];
  return (
    <Panel>
      <PanelHeader title="Fundamentales" />
      <PanelBody>
        {rows.map((r, i) => (
          <div
            key={r.label}
            className={`flex items-baseline justify-between py-1.5 text-[12.5px] ${
              i < rows.length - 1 ? "border-b border-bd2" : ""
            }`}
          >
            <span className="text-dim">{r.label}</span>
            {r.value ? (
              <span className="num text-tx">{r.value}</span>
            ) : (
              <span
                className="num text-dim2"
                title="Próximamente — aún sin fuente de dato real"
              >
                —
              </span>
            )}
          </div>
        ))}
      </PanelBody>
    </Panel>
  );
}
