import { Panel, PanelBody } from "@/components/ui/Panel";

/**
 * Directorio de empresas con análisis vigente: hace VISIBLE el conjunto que el
 * motor conoce (símbolos de /signals) como chips clickeables, para que la
 * búsqueda nunca apunte al vacío.
 *
 * - `notFound`: ticker buscado fuera del set → mensaje honesto arriba de la lista.
 * - `compact`: tira fina para cambiar de empresa con un research ya abierto.
 * - Sin símbolos → mensaje honesto, sin chips.
 */
export function AvailableList({
  symbols,
  selected,
  onPick,
  notFound,
  compact = false,
}: {
  symbols: string[];
  selected?: string | null;
  onPick: (s: string) => void;
  notFound?: string | null;
  compact?: boolean;
}) {
  const heading = notFound
    ? `No hay análisis para "${notFound}" ahora mismo`
    : "Empresas con análisis disponible ahora";

  if (compact) {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] text-dim2">Disponibles:</span>
        {symbols.map((s) => (
          <Chip key={s} sym={s} active={s === selected} onPick={onPick} />
        ))}
      </div>
    );
  }

  return (
    <Panel>
      <PanelBody>
        <p className={`text-[13px] font-medium ${notFound ? "text-tx" : "text-tx"}`}>{heading}</p>
        {symbols.length === 0 ? (
          <p className="mt-2 text-[12.5px] text-dim">No hay análisis disponible en este momento.</p>
        ) : (
          <>
            <p className="mt-1 text-[12px] text-dim">
              El Investigador solo cubre símbolos con análisis impersonal vigente. Elegí uno:
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {symbols.map((s) => (
                <Chip key={s} sym={s} active={s === selected} onPick={onPick} />
              ))}
            </div>
          </>
        )}
      </PanelBody>
    </Panel>
  );
}

function Chip({
  sym,
  active,
  onPick,
}: {
  sym: string;
  active?: boolean;
  onPick: (s: string) => void;
}) {
  return (
    <button
      onClick={() => onPick(sym)}
      className={`rounded-md border px-3 py-1.5 text-[12.5px] transition-colors ${
        active
          ? "border-ac2 bg-ac/15 text-ac"
          : "border-bd bg-pan2 text-ac hover:border-ac2"
      }`}
    >
      {sym}
    </button>
  );
}
