/**
 * Contrato de GET /noticias — feed IMPERSONAL de noticias (Benzinga vía Alpaca).
 *
 * Mismo modelo que /signals: idéntico para todos los tenants. El backend sirve
 * de una cache compartida; si Alpaca falla, degrada a la última cache
 * (`degraded: true`) sin romper. COPYRIGHT: el artículo trae SOLO headline +
 * summary + metadatos + link (jamás el cuerpo completo).
 */

export type NewsImage = { size: string | null; url: string | null };

export type NewsArticle = {
  id: number;
  headline: string;
  summary: string;
  source: string;
  url: string;
  symbols: string[];
  images: NewsImage[];
  published_at: string; // ISO
};

export type NoticiasPayload = {
  impersonal: boolean;
  generated_at: string;
  ttl_sec: number;
  degraded: boolean;
  count: number;
  noticias: NewsArticle[];
};

export type NoticiasResult =
  | { ok: true; data: NoticiasPayload }
  | { ok: false; status: number | null; message: string };

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Pide el feed al backend con el JWT de Clerk. `symbol` opcional (dentro del universo). */
export async function fetchNoticias(
  token: string | null,
  symbol?: string,
): Promise<NoticiasResult> {
  const qs = symbol ? `?symbol=${encodeURIComponent(symbol)}` : "";
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/noticias${qs}`, {
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
    return { ok: true, data: (await res.json()) as NoticiasPayload };
  }

  const detail = await safeDetail(res);
  const message =
    res.status === 401
      ? "Sesión no válida. Volvé a entrar."
      : res.status === 402
        ? "Tu suscripción no está activa. Activá un plan para ver las noticias."
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
