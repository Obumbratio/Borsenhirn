"use client";

import { useState } from "react";
import type { SignalsPayload } from "@/lib/signals";
import type { DemoFundamentals, DemoNews } from "@/lib/demo-signals";
import { StatsBar, type Stat } from "@/components/ui/StatsBar";
import { SearchBar } from "@/components/ui/SearchBar";
import { Panel, PanelBody } from "@/components/ui/Panel";
import { ResumenPanel } from "@/components/investigador/ResumenPanel";
import { BasisPanel } from "@/components/investigador/BasisPanel";
import { FundamentalsPanel } from "@/components/investigador/FundamentalsPanel";
import { NewsPanel } from "@/components/investigador/NewsPanel";
import { AvailableList } from "@/components/investigador/AvailableList";
import { Freshness } from "@/components/investigador/Freshness";
import { DemoModeProvider } from "@/components/ui/DemoMode";

/** Único fallback: solo cuando /signals no trae ninguna card de donde tomar el disclaimer del backend. */
const FALLBACK_DISCLAIMER =
  "Análisis informativo e impersonal (igual para todos). No es recomendación de inversión; " +
  "tú eliges, calculas tu tamaño y ejecutas.";

/**
 * Investigador: research de UNA empresa buscada por ticker.
 *
 * El motor solo conoce los símbolos con análisis impersonal vigente (de
 * /signals). Para que la búsqueda nunca apunte al vacío:
 *  - Estado por defecto = DIRECTORIO de símbolos disponibles (chips).
 *  - Buscar dentro del set → selecciona; fuera del set → mensaje honesto +
 *    re-muestra el directorio. Nunca silencio.
 *
 * Fundamentales/Noticias van "—" salvo bajo ?demo=1 (datos de demostración).
 */
export function InvestigadorView({
  payload,
  demo = false,
  fundamentals,
  news,
}: {
  payload: SignalsPayload;
  demo?: boolean;
  fundamentals?: Record<string, DemoFundamentals>;
  news?: Record<string, DemoNews[]>;
}) {
  const cards = payload.signals;
  const symbols = cards.map((c) => c.symbol);

  // Arranca SIN selección y con el input vacío: el landing es el directorio.
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  // Último término buscado que NO está en el set (para el feedback honesto).
  const [notFound, setNotFound] = useState<string | null>(null);

  /** Selecciona un símbolo conocido (chip o búsqueda con match). */
  function pick(sym: string) {
    setSelected(sym);
    setQuery(sym);
    setNotFound(null);
  }

  /** Submit de la barra: vacío → directorio; en el set → selecciona; fuera → honesto. */
  function search(raw: string) {
    const sym = raw.trim().toUpperCase();
    if (!sym) {
      setSelected(null);
      setNotFound(null);
      return;
    }
    if (symbols.includes(sym)) {
      pick(sym);
    } else {
      setSelected(null);
      setNotFound(sym);
    }
  }

  const card = cards.find((c) => c.symbol === selected) ?? null;

  // Disclaimer canónico del backend como fuente única (todas las cards comparten
  // el mismo texto). Fallback constante SOLO si /signals viene sin cards.
  const disclaimer = card?.disclaimer ?? cards[0]?.disclaimer ?? FALLBACK_DISCLAIMER;

  const regime = payload.regime;
  const stats: Stat[] = [
    { label: "Cuenta", value: "—", pending: true },
    { label: "Régimen", value: regime ?? "—", tone: "accent", pending: regime == null },
    { label: "VIX", value: "—", pending: true },
  ];

  return (
    <DemoModeProvider demo={demo}>
    <div className="mx-auto flex max-w-[1340px] flex-col gap-2">
      {demo && (
        <div className="rounded-lg border border-warn/30 bg-warn/10 px-3.5 py-2 text-[12px] text-warn">
          ⚠️ <span className="font-semibold">MODO DEMO</span> — empresas de ejemplo (con
          fundamentales y noticias de demostración) solo para revisar el diseño. No son datos
          reales. Quitá <code className="font-mono">?demo=1</code> de la URL para volver al estado real.
        </div>
      )}

      <StatsBar stats={stats} />

      <Panel>
        <PanelBody>
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="font-fraunces text-[22px] font-semibold text-wht">Investigador</h1>
            {payload.impersonal && (
              <span className="rounded-full bg-ac/15 px-2.5 py-0.5 text-[11px] font-medium text-ac ring-1 ring-ac/30">
                Impersonal · igual para todos
              </span>
            )}
          </div>
          <p className="mt-0.5 text-[13px] text-dim">
            Research a fondo de cualquier empresa con análisis vigente. Información, no recomendación.
          </p>

          <div className="mt-3.5">
            <SearchBar
              value={query}
              onChange={setQuery}
              onSubmit={() => search(query)}
              placeholder="Buscá un ticker… ej: UNH, NVDA, MSFT"
              buttonLabel="Investigar"
            />
          </div>

          {/* Disclaimer impersonal — texto canónico del backend (fuente única) */}
          <div className="mt-3.5 rounded-lg border border-bd bg-pan2 px-3 py-2.5 text-[11px] leading-snug text-dim2">
            {disclaimer}
          </div>

          {/* Frescura del análisis (timestamp + TTL), sin mismatch de hidratación */}
          <Freshness generatedAt={payload.generated_at} ttlSec={payload.ttl_sec} />

          {/* Contenido */}
          <div className="mt-3.5">
            {card ? (
              <div className="flex flex-col gap-3">
                {/* Tira de disponibles: nunca se queda sin salida */}
                <AvailableList symbols={symbols} selected={card.symbol} onPick={pick} compact />
                <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1.4fr_1fr]">
                  <div className="flex flex-col gap-3">
                    <ResumenPanel card={card} />
                    <BasisPanel card={card} />
                  </div>
                  <div className="flex flex-col gap-3">
                    <FundamentalsPanel data={demo ? fundamentals?.[card.symbol] : undefined} />
                    <NewsPanel items={demo ? news?.[card.symbol] : undefined} />
                  </div>
                </div>
              </div>
            ) : (
              // Directorio (landing) o feedback de "no encontrado" + directorio.
              <AvailableList symbols={symbols} onPick={pick} notFound={notFound} />
            )}
          </div>
        </PanelBody>
      </Panel>
    </div>
    </DemoModeProvider>
  );
}
