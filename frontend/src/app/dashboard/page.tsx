import { auth } from "@clerk/nextjs/server";

// El dashboard es por-sesión: nunca se prerenderea estático.
export const dynamic = "force-dynamic";

async function fetchMe(token: string | null) {
  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const res = await fetch(`${base}/me`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    cache: "no-store",
  });
  return { status: res.status, body: await res.text() };
}

export default async function Dashboard() {
  // El middleware ya exige sesión para /dashboard; acá tomamos el JWT de Clerk
  // y se lo mandamos al backend, que lo verifica (JWKS) y resuelve el tenant.
  const { userId, getToken } = await auth();
  const token = await getToken();

  let me: { status: number; body: string } | null = null;
  let error: string | null = null;
  try {
    me = await fetchMe(token);
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-2xl font-bold">Dashboard</h1>
      <p className="mt-2 text-sm text-neutral-400">Clerk userId: {userId}</p>

      <section className="mt-6 rounded-lg border border-neutral-800 p-4">
        <h2 className="font-semibold">
          GET <code className="text-emerald-400">/me</code> (backend)
        </h2>
        <p className="mt-1 text-xs text-neutral-500">
          Verifica el cableado Clerk → JWT → FastAPI → tenant (RLS).
        </p>
        {error && (
          <p className="mt-3 text-sm text-red-400">
            No se pudo llamar al backend: {error}
            <br />
            <span className="text-neutral-500">
              ¿Está corriendo la API en {process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}?
            </span>
          </p>
        )}
        {me && (
          <pre className="mt-3 overflow-x-auto rounded bg-neutral-900 p-3 text-sm text-neutral-300">
            HTTP {me.status}
            {"\n"}
            {me.body}
          </pre>
        )}
      </section>
    </div>
  );
}
