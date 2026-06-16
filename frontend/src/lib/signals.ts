/**
 * Contrato de GET /signals (cerebro compartido, impersonal — Paso 2/3b del backend).
 *
 * El payload NO depende del usuario: es el mismo análisis para todos. El backend lo
 * arma determinísticamente a partir de datos REALES (RSI, medias, prob. del modelo,
 * confianza, régimen, razón del scanner) — sin narrativa inventada. Cada `factor`
 * expone su PROCEDENCIA (`fuente`). Ver borsenhirn/signals/cards.py.
 */

export type Factor = {
  factor: string;
  valor: string | number;
  fuente: string;
};

export type Levels = {
  entry: number | null;
  stop: number | null;
  target: number | null;
  trailing_pct: number | null;
  fuentes: { entry: string; stop: string; target: string };
};

export type AnalysisCard = {
  symbol: string;
  price: number | null;
  levels: Levels;
  tesis: string;
  que_invalida: string;
  factores: Factor[];
  disclaimer: string;
};

export type SignalsPayload = {
  regime: string | null;
  generated_at: string;
  impersonal: boolean;
  ttl_sec: number;
  signals: AnalysisCard[];
};

export type SignalsResult =
  | { ok: true; data: SignalsPayload }
  | { ok: false; status: number | null; message: string };

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * Llama al backend con el JWT de Clerk. Devuelve un resultado discriminado para
 * que la UI pueda mostrar estados (sin sesión / suscripción inactiva / API caída)
 * sin reventar el render.
 */
export async function fetchSignals(token: string | null): Promise<SignalsResult> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/signals`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      cache: "no-store",
    });
  } catch (e) {
    return {
      ok: false,
      status: null,
      message:
        `No se pudo contactar al backend en ${API_BASE}. ` +
        `¿Está corriendo la API? (${e instanceof Error ? e.message : String(e)})`,
    };
  }

  if (res.status === 200) {
    return { ok: true, data: (await res.json()) as SignalsPayload };
  }

  // Mapear los gates del backend a mensajes claros.
  const detail = await safeDetail(res);
  const message =
    res.status === 401
      ? "Sesión no válida. Volvé a entrar."
      : res.status === 402
        ? "Tu suscripción no está activa. Activá un plan para ver el análisis."
        : detail || `El backend respondió ${res.status}.`;
  return { ok: false, status: res.status, message };
}

async function safeDetail(res: Response): Promise<string | null> {
  try {
    const body = await res.json();
    return typeof body?.detail === "string" ? body.detail : null;
  } catch {
    return null;
  }
}

/** Formatea un precio a USD; tolera null. */
export function usd(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** Etiqueta + color del chip de régimen. */
export function regimeChip(regime: string | null): { label: string; className: string } {
  const r = (regime ?? "").toUpperCase();
  if (r.includes("BULL"))
    return { label: regime!, className: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30" };
  if (r.includes("BEAR"))
    return { label: regime!, className: "bg-red-500/15 text-red-300 ring-red-500/30" };
  if (r)
    return { label: regime!, className: "bg-amber-500/15 text-amber-300 ring-amber-500/30" };
  return { label: "desconocido", className: "bg-neutral-700/40 text-neutral-300 ring-neutral-600/40" };
}
