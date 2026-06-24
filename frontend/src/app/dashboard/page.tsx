import { auth } from "@clerk/nextjs/server";
import { fetchSignals } from "@/lib/signals";
import { TableroView } from "@/components/tablero/TableroView";
import { DEMO_PAYLOAD } from "@/lib/demo-signals";

// Por-sesión: nunca se prerenderea estático.
export const dynamic = "force-dynamic";

/**
 * Tablero (Fusión A+B) — superficie principal.
 *
 * Server component: toma el JWT de Clerk y pide GET /signals (el backend lo
 * verifica y resuelve el tenant). El payload se pasa a TableroView (client),
 * que maneja la selección de símbolo. NO toca backend ni contratos.
 *
 * ⚠️ TEMPORAL: con `?demo=1` muestra datos de DEMOSTRACIÓN (banner visible) para
 * revisar el diseño cuando no hay señales. Quitar junto con lib/demo-signals.ts.
 */
export default async function Tablero({
  searchParams,
}: {
  searchParams: { demo?: string };
}) {
  if (searchParams?.demo === "1") {
    return <TableroView payload={DEMO_PAYLOAD} demo />;
  }

  const { getToken } = await auth();
  const token = await getToken();
  const result = await fetchSignals(token);

  if (!result.ok) {
    return <ErrorState status={result.status} message={result.message} />;
  }

  if (result.data.signals.length === 0) {
    return <EmptyState regime={result.data.regime} />;
  }

  return <TableroView payload={result.data} />;
}

function EmptyState({ regime }: { regime: string | null }) {
  return (
    <div className="mx-auto mt-10 max-w-md rounded-xl border border-dashed border-bd bg-pan/40 p-10 text-center">
      <p className="text-base font-medium text-tx">No hay setups en este momento</p>
      <p className="mt-2 text-sm text-dim">
        El escáner no encontró oportunidades que cumplan los criterios ahora mismo
        {regime ? ` (régimen ${regime})` : ""}. No tener señal también es información:
        cuando no hay un setup claro, lo honesto es no inventarlo.
      </p>
    </div>
  );
}

function ErrorState({ status, message }: { status: number | null; message: string }) {
  return (
    <div className="mx-auto mt-10 max-w-lg rounded-xl border border-dn/25 bg-dn/5 p-6">
      <p className="text-sm font-semibold text-dn">
        No se pudo cargar el análisis{status ? ` (HTTP ${status})` : ""}
      </p>
      <p className="mt-2 text-sm text-dim">{message}</p>
      {status === 402 && (
        <p className="mt-2 text-sm text-dim">Activá un plan para ver el análisis.</p>
      )}
    </div>
  );
}
