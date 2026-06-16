import { auth } from "@clerk/nextjs/server";
import { fetchSignals, regimeChip, type SignalsPayload } from "@/lib/signals";
import { SignalCardView } from "@/components/SignalCard";

// Por-sesión: nunca se prerenderea estático.
export const dynamic = "force-dynamic";

export default async function Dashboard() {
  // El middleware ya exige sesión para /dashboard; acá tomamos el JWT de Clerk y
  // lo mandamos al backend, que lo verifica (JWKS) y resuelve el tenant (RLS).
  const { getToken } = await auth();
  const token = await getToken();
  const result = await fetchSignals(token);

  return (
    <div className="mx-auto max-w-3xl">
      <Header payload={result.ok ? result.data : null} />

      {result.ok ? (
        <SignalsList data={result.data} />
      ) : (
        <ErrorState status={result.status} message={result.message} />
      )}
    </div>
  );
}

function Header({ payload }: { payload: SignalsPayload | null }) {
  const chip = regimeChip(payload?.regime ?? null);
  return (
    <header className="mb-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight">Análisis de mercado</h1>
        {payload && (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ring-1 ${chip.className}`}
          >
            Régimen: {chip.label}
          </span>
        )}
      </div>
      <p className="mt-1 text-sm text-neutral-400">
        Setups detectados por el cerebro compartido. El mismo análisis para todos —
        impersonal por construcción.
      </p>

      {/* Disclaimer visible (informativo / no recomendación) */}
      <div className="mt-4 rounded-lg border border-neutral-800 bg-neutral-900/60 px-4 py-3">
        <p className="text-xs leading-relaxed text-neutral-400">
          <span className="font-semibold text-neutral-300">Análisis general, no es recomendación de inversión.</span>{" "}
          Es información impersonal (igual para todos los usuarios), construida con datos
          técnicos del sistema. No mira tu cuenta. Vos decidís, calculás tu tamaño y ejecutás.
        </p>
      </div>

      {payload && (
        <p className="mt-2 text-[11px] text-neutral-600">
          Generado: {fmtTime(payload.generated_at)} · se refresca cada{" "}
          {Math.round(payload.ttl_sec / 60)} min
        </p>
      )}
    </header>
  );
}

function SignalsList({ data }: { data: SignalsPayload }) {
  if (data.signals.length === 0) {
    return <EmptyState regime={data.regime} />;
  }
  return (
    <div className="space-y-4">
      {data.signals.map((card) => (
        <SignalCardView key={card.symbol} card={card} />
      ))}
    </div>
  );
}

function EmptyState({ regime }: { regime: string | null }) {
  return (
    <div className="rounded-xl border border-dashed border-neutral-800 bg-neutral-900/30 p-10 text-center">
      <p className="text-base font-medium text-neutral-300">
        No hay setups en este momento
      </p>
      <p className="mx-auto mt-2 max-w-md text-sm text-neutral-500">
        El escáner no encontró oportunidades que cumplan los criterios ahora mismo
        {regime ? ` (régimen ${regime})` : ""}. No tener señal también es información:
        cuando no hay un setup claro, lo honesto es no inventarlo.
      </p>
      <p className="mt-4 text-[11px] text-neutral-600">
        Volvé más tarde — el análisis se recalcula periódicamente.
      </p>
    </div>
  );
}

function ErrorState({ status, message }: { status: number | null; message: string }) {
  return (
    <div className="rounded-xl border border-red-500/25 bg-red-500/5 p-6">
      <p className="text-sm font-semibold text-red-300">
        No se pudo cargar el análisis{status ? ` (HTTP ${status})` : ""}
      </p>
      <p className="mt-2 text-sm text-neutral-400">{message}</p>
    </div>
  );
}

function fmtTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("es-AR", {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}
