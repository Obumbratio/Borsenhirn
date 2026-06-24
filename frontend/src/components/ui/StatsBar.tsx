import { Panel } from "@/components/ui/Panel";

export type Stat = {
  label: string;
  value: string;
  /** Color del valor. */
  tone?: "default" | "accent" | "up" | "dn";
  /** Si no hay fuente de dato real todavía: muestra "—" + tooltip. */
  pending?: boolean;
};

const toneClass: Record<NonNullable<Stat["tone"]>, string> = {
  default: "text-wht",
  accent: "text-ac",
  up: "text-up",
  dn: "text-dn",
};

/**
 * Barra de stats siempre visible (cuenta, régimen, VIX, sentimiento…).
 * HONESTIDAD: las métricas sin fuente real se marcan `pending` → se muestran
 * como "—" con un tooltip "próximamente", en vez de inventar números. La
 * identidad del producto es la transparencia.
 */
export function StatsBar({ stats }: { stats: Stat[] }) {
  return (
    <Panel>
      <div className="flex flex-wrap gap-x-7 gap-y-2 px-3.5 py-3">
        {stats.map((s) => (
          <div key={s.label} title={s.pending ? "Próximamente — aún sin fuente de dato real" : undefined}>
            <div className="text-[10px] text-dim2">{s.label}</div>
            {s.pending ? (
              <div className="num text-sm font-semibold text-dim2">—</div>
            ) : (
              <div className={`num text-sm font-semibold ${toneClass[s.tone ?? "default"]}`}>
                {s.value}
              </div>
            )}
          </div>
        ))}
      </div>
    </Panel>
  );
}
