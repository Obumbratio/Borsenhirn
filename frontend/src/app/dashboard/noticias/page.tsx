import { auth } from "@clerk/nextjs/server";
import { fetchNoticias, type NoticiasPayload } from "@/lib/news";
import { NewsCard } from "@/components/noticias/NewsCard";
import { Panel, PanelBody } from "@/components/ui/Panel";

// Por-sesión: nunca se prerenderea estático.
export const dynamic = "force-dynamic";

/**
 * Noticias — feed IMPERSONAL (Benzinga vía Alpaca), mismo para todos.
 * Server component: toma el JWT de Clerk y pide GET /noticias. NO mira la
 * cartera del usuario. Sin datos fake: si no hay noticias, estado vacío.
 */
export default async function Noticias() {
  const { getToken } = await auth();
  const token = await getToken();
  const result = await fetchNoticias(token);

  return (
    <div className="mx-auto flex max-w-[1100px] flex-col gap-2">
      <header className="px-1 pt-1">
        <h1 className="font-fraunces text-[22px] font-semibold text-wht">Noticias</h1>
        <p className="mt-0.5 text-[13px] text-dim">
          Mercado en tiempo real — hechos públicos de terceros. Información, no recomendación.
        </p>
      </header>

      {!result.ok ? (
        <ErrorState status={result.status} message={result.message} />
      ) : (
        <Feed data={result.data} />
      )}

      <p className="mt-2 px-1 text-[11px] leading-snug text-dim2">
        Noticias informativas de terceros (Benzinga vía Alpaca). No son consejo de inversión.
        Para leer cada artículo completo, abrís el original en su fuente.
      </p>
    </div>
  );
}

function Feed({ data }: { data: NoticiasPayload }) {
  if (data.noticias.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-bd bg-pan/40 p-10 text-center">
        <p className="text-[14px] font-medium text-tx">
          {data.degraded ? "No se pudieron cargar las noticias" : "No hay noticias por ahora"}
        </p>
        <p className="mx-auto mt-2 max-w-md text-[12.5px] text-dim">
          {data.degraded
            ? "La fuente de noticias está temporariamente no disponible y no hay nada en cache todavía. Volvé en unos minutos."
            : "Cuando haya novedades del mercado, aparecerán acá. No inventamos noticias."}
        </p>
      </div>
    );
  }

  return (
    <>
      {data.degraded && (
        <div className="rounded-lg border border-warn/30 bg-warn/10 px-3.5 py-2 text-[12px] text-warn">
          Mostrando las últimas noticias en cache — la actualización en vivo está
          temporariamente no disponible.
        </div>
      )}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {data.noticias.map((a) => (
          <NewsCard key={a.id} a={a} />
        ))}
      </div>
    </>
  );
}

function ErrorState({ status, message }: { status: number | null; message: string }) {
  return (
    <Panel>
      <PanelBody>
        <p className="text-[13px] font-semibold text-dn">
          No se pudieron cargar las noticias{status ? ` (HTTP ${status})` : ""}
        </p>
        <p className="mt-2 text-[13px] text-dim">{message}</p>
        {status === 402 && (
          <p className="mt-2 text-[13px] text-dim">Activá un plan para ver las noticias.</p>
        )}
      </PanelBody>
    </Panel>
  );
}
