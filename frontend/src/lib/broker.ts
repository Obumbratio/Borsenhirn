/**
 * Cliente del contrato /me/broker (BYO Alpaca — backend Paso 3a).
 *
 * SEGURIDAD: el `api_secret` solo se usa para armar el body del POST. NUNCA se
 * loguea, ni se guarda en estado persistente, ni se pinta de vuelta. El backend
 * valida las keys contra Alpaca (paper) y las cifra en el vault; el GET devuelve
 * la key ENMASCARADA y jamás el secreto.
 *
 * Estas funciones corren en el cliente (toman el token de Clerk vía useAuth).
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type BrokerStatus = {
  connected: boolean;
  provider?: string;
  api_key_masked?: string;
  equity?: string | number | null;
};

export type BrokerResult<T> =
  | { ok: true; data: T }
  | { ok: false; status: number | null; message: string };

async function call<T>(
  token: string | null,
  path: string,
  init?: RequestInit,
): Promise<BrokerResult<T>> {
  if (!token) return { ok: false, status: 401, message: "Sesión no válida. Volvé a entrar." };
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...(init?.headers ?? {}),
      },
      cache: "no-store",
    });
  } catch (e) {
    return {
      ok: false,
      status: null,
      message:
        `No se pudo contactar al backend en ${API_BASE}. ¿Está corriendo la API? ` +
        `(${e instanceof Error ? e.message : String(e)})`,
    };
  }

  if (res.ok) return { ok: true, data: (await res.json()) as T };

  const detail = await safeDetail(res);
  const message =
    res.status === 401
      ? "Sesión no válida. Volvé a entrar."
      : res.status === 400
        ? detail ||
          "No pudimos validar esas credenciales con Alpaca (paper). Revisá que sean correctas."
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

/** Estado actual de la conexión (al cargar la pantalla). */
export function getBrokerStatus(token: string | null) {
  return call<BrokerStatus>(token, "/me/broker");
}

/** Conecta Alpaca (paper). El secreto viaja solo en este body, nunca se guarda local. */
export function connectBroker(token: string | null, apiKey: string, apiSecret: string) {
  return call<BrokerStatus>(token, "/me/broker", {
    method: "POST",
    body: JSON.stringify({ api_key: apiKey, api_secret: apiSecret }),
  });
}

/** Desconecta Alpaca (borra las credenciales cifradas del vault). */
export function disconnectBroker(token: string | null) {
  return call<{ connected: boolean; deleted: boolean }>(token, "/me/broker", {
    method: "DELETE",
  });
}
