/**
 * Cliente de ejecución manual y posiciones (backend Paso 3d).
 *
 * - placeOrder  → POST /me/orders  (UNA orden por click; idempotente por key)
 * - getPositions→ GET  /me/positions (posiciones + alertas TP/SL, read-only)
 * - getLegalCurrent / acceptLegal → gate legal (B7): el POST /me/orders exige
 *   suscripción activa + legal aceptado; si falta legal devuelve 451 y la UI
 *   ofrece aceptar Términos+Privacidad (queda registrado quién/versión/cuándo).
 *
 * Todo paper: el front SIEMPRE manda mode:"paper"; no hay live en la UI.
 * Los resultados son discriminados y EXPONEN el status para que el diálogo
 * pueda ramificar (409 sin Alpaca, 451 legal, 502 rechazo, etc.).
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type OrderSide = "buy" | "sell";

export type PlacedOrder = {
  order_id: string;
  status: string;
  client_order_id: string | null;
  symbol: string;
  side: string;
  qty: number;
  mode: string;
  idempotent: boolean;
};

export type Alerta = {
  tipo: "objetivo_alcanzado" | "stop_tocado" | string;
  mensaje: string;
  sugerido: { side: OrderSide; qty: number; symbol: string };
};

export type Position = {
  symbol: string;
  qty: number;
  avg_entry: number;
  current: number;
  pnl_pct: number;
  alertas: Alerta[];
};

export type LegalVersions = { terms: string; privacy: string };

export type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; status: number | null; message: string };

async function call<T>(
  token: string | null,
  path: string,
  init?: RequestInit,
  { auth = true }: { auth?: boolean } = {},
): Promise<ApiResult<T>> {
  if (auth && !token) return { ok: false, status: 401, message: "Sesión no válida. Volvé a entrar." };
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        ...(auth ? { Authorization: `Bearer ${token}` } : {}),
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...(init?.headers ?? {}),
      },
      cache: "no-store",
    });
  } catch (e) {
    return {
      ok: false,
      status: null,
      message: `No se pudo contactar al backend en ${API_BASE}. ¿Está corriendo la API? (${
        e instanceof Error ? e.message : String(e)
      })`,
    };
  }
  if (res.ok) return { ok: true, data: (await res.json()) as T };
  const detail = await safeDetail(res);
  return { ok: false, status: res.status, message: detail || `El backend respondió ${res.status}.` };
}

async function safeDetail(res: Response): Promise<string | null> {
  try {
    const body = await res.json();
    return typeof body?.detail === "string" ? body.detail : null;
  } catch {
    return null;
  }
}

/** Manda UNA orden (siempre paper). `idempotencyKey` = uuid por click → dedup. */
export function placeOrder(
  token: string | null,
  order: { symbol: string; side: OrderSide; qty: number; idempotencyKey: string },
) {
  return call<PlacedOrder>(token, "/me/orders", {
    method: "POST",
    body: JSON.stringify({
      symbol: order.symbol,
      side: order.side,
      qty: order.qty,
      mode: "paper",
      idempotency_key: order.idempotencyKey,
    }),
  });
}

/** Posiciones del usuario + alertas TP/SL (read-only). */
export function getPositions(token: string | null) {
  return call<{ positions: Position[] }>(token, "/me/positions");
}

/** Versiones legales vigentes (endpoint público). */
export function getLegalCurrent() {
  return call<{ versions: LegalVersions }>(null, "/legal/current", undefined, { auth: false });
}

/** Registra la aceptación de un documento legal (queda actor + versión + fecha). */
export function acceptLegal(token: string | null, document: "terms" | "privacy", version: string) {
  return call<{ ok: boolean; compliant: boolean }>(token, "/me/legal/accept", {
    method: "POST",
    body: JSON.stringify({ document, version }),
  });
}
