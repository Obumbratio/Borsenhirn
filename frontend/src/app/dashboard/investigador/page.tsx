import { auth } from "@clerk/nextjs/server";
import { fetchSignals } from "@/lib/signals";
import { InvestigadorView } from "@/components/investigador/InvestigadorView";
import { DEMO_PAYLOAD, DEMO_FUNDAMENTALS, DEMO_NEWS } from "@/lib/demo-signals";

// Por-sesión: nunca se prerenderea estático.
export const dynamic = "force-dynamic";

/**
 * Investigador — research impersonal de una empresa.
 *
 * Server component: usa GET /signals (mismo cerebro impersonal que el Tablero).
 * NO toca backend ni contratos. Sin botón Comprar → sin superficie de ejecución.
 *
 * ⚠️ TEMPORAL: con `?demo=1` muestra una empresa de DEMOSTRACIÓN (banner visible)
 * con fundamentales y noticias de ejemplo. Quitar junto con lib/demo-signals.ts.
 */
export default async function Investigador({
  searchParams,
}: {
  searchParams: { demo?: string };
}) {
  if (searchParams?.demo === "1") {
    return (
      <InvestigadorView
        payload={DEMO_PAYLOAD}
        demo
        fundamentals={DEMO_FUNDAMENTALS}
        news={DEMO_NEWS}
      />
    );
  }

  const { getToken } = await auth();
  const token = await getToken();
  const result = await fetchSignals(token);

  if (!result.ok) {
    return <ErrorState status={result.status} message={result.message} />;
  }

  return <InvestigadorView payload={result.data} />;
}

function ErrorState({ status, message }: { status: number | null; message: string }) {
  return (
    <div className="mx-auto mt-10 max-w-lg rounded-xl border border-dn/25 bg-dn/5 p-6">
      <p className="text-sm font-semibold text-dn">
        No se pudo cargar el análisis{status ? ` (HTTP ${status})` : ""}
      </p>
      <p className="mt-2 text-sm text-dim">{message}</p>
      {status === 402 && <p className="mt-2 text-sm text-dim">Activá un plan para ver el análisis.</p>}
    </div>
  );
}
