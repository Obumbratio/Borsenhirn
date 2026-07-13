import type { NewsArticle } from "@/lib/news";
import { Panel, PanelBody } from "@/components/ui/Panel";
import { RelativeTime } from "@/components/ui/RelativeTime";

/**
 * Tarjeta de noticia (estilo SignalCard). COPYRIGHT: solo headline + summary +
 * metadatos + link al original. El headline linkea AFUERA (target=_blank,
 * rel=noopener noreferrer) — para leer el artículo se sale de la plataforma.
 * Los símbolos van como tags (solo visuales en este MVP).
 */
export function NewsCard({ a }: { a: NewsArticle }) {
  return (
    <Panel>
      <PanelBody>
        {a.url ? (
          <a
            href={a.url}
            target="_blank"
            rel="noopener noreferrer"
            className="font-fraunces text-[15px] font-semibold leading-snug text-wht hover:text-ac"
          >
            {a.headline}
          </a>
        ) : (
          <span className="font-fraunces text-[15px] font-semibold leading-snug text-wht">
            {a.headline}
          </span>
        )}

        {a.summary && <p className="mt-1.5 text-[12.5px] leading-relaxed text-dim">{a.summary}</p>}

        {a.symbols.length > 0 && (
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {a.symbols.slice(0, 8).map((s) => (
              <span key={s} className="rounded bg-ac/15 px-1.5 py-0.5 text-[10.5px] font-semibold text-ac">
                {s}
              </span>
            ))}
          </div>
        )}

        <div className="mt-2.5 flex items-center gap-1.5 text-[10.5px] text-dim2">
          {a.source && <span>{a.source}</span>}
          {a.source && <span>·</span>}
          <RelativeTime iso={a.published_at} />
        </div>
      </PanelBody>
    </Panel>
  );
}
