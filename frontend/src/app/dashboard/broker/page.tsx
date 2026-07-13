"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import {
  connectBroker,
  disconnectBroker,
  getBrokerStatus,
  type BrokerStatus,
} from "@/lib/broker";
import { usd } from "@/lib/signals";

const ALPACA_PAPER_KEYS_URL = "https://app.alpaca.markets/paper/dashboard/overview";

export default function BrokerPage() {
  const { getToken } = useAuth();

  const [status, setStatus] = useState<BrokerStatus | null>(null); // null = cargando
  const [loadError, setLoadError] = useState<string | null>(null);

  const loadStatus = useCallback(async () => {
    setLoadError(null);
    const res = await getBrokerStatus(await getToken());
    if (res.ok) setStatus(res.data);
    else setLoadError(res.message);
  }, [getToken]);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  return (
    <div className="mx-auto max-w-2xl">
      <header className="mb-6">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="font-fraunces text-2xl font-bold tracking-tight text-wht">Conectar Alpaca</h1>
          <span className="rounded-full bg-ac2/15 px-2.5 py-0.5 text-xs font-medium text-ac ring-1 ring-ac/30">
            PAPER
          </span>
        </div>
        <p className="mt-1 text-sm text-dim">
          Conectá tu cuenta de práctica (paper) de Alpaca. Guardamos tus claves{" "}
          <span className="text-tx">cifradas</span> — nunca custodiamos tu dinero ni
          operamos por vos; sos vos quien ejecuta.
        </p>
      </header>

      {status === null && !loadError && (
        <p className="text-sm text-dim">Cargando estado de la conexión…</p>
      )}

      {loadError && (
        <div className="rounded-xl border border-dn/25 bg-dn/5 p-4">
          <p className="text-sm text-dn">No se pudo cargar el estado: {loadError}</p>
          <button
            onClick={loadStatus}
            className="mt-3 rounded-md border border-bd px-3 py-1.5 text-sm text-tx hover:bg-pan"
          >
            Reintentar
          </button>
        </div>
      )}

      {status?.connected && (
        <ConnectedView status={status} onDisconnected={loadStatus} getToken={getToken} />
      )}

      {status !== null && !status.connected && (
        <ConnectForm onConnected={loadStatus} getToken={getToken} />
      )}
    </div>
  );
}

function ConnectedView({
  status,
  onDisconnected,
  getToken,
}: {
  status: BrokerStatus;
  onDisconnected: () => Promise<void>;
  getToken: () => Promise<string | null>;
}) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const equityNum =
    status.equity == null ? null : typeof status.equity === "string" ? parseFloat(status.equity) : status.equity;

  async function doDisconnect() {
    setBusy(true);
    setError(null);
    const res = await disconnectBroker(await getToken());
    setBusy(false);
    if (res.ok) {
      setConfirming(false);
      await onDisconnected();
    } else {
      setError(res.message);
    }
  }

  return (
    <div className="rounded-xl border border-up/25 bg-up/5 p-5">
      <div className="flex items-center gap-2">
        <span className="text-lg">✅</span>
        <h2 className="font-semibold text-up">Alpaca conectado (paper)</h2>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className="text-dim">API Key</dt>
          <dd className="font-mono text-tx">{status.api_key_masked ?? "••••"}</dd>
        </div>
        {equityNum != null && Number.isFinite(equityNum) && (
          <div>
            <dt className="text-dim">Equity (paper)</dt>
            <dd className="font-mono text-tx">{usd(equityNum)}</dd>
          </div>
        )}
      </dl>

      <p className="mt-4 text-[11px] text-dim">
        Tu clave secreta queda cifrada en el vault y no se muestra nunca de vuelta. Si la rotás en
        Alpaca, desconectá y volvé a conectar con el par nuevo.
      </p>

      {error && <p className="mt-3 text-sm text-dn">{error}</p>}

      <div className="mt-4">
        {!confirming ? (
          <button
            onClick={() => setConfirming(true)}
            className="rounded-md border border-bd px-3 py-1.5 text-sm text-tx hover:bg-pan"
          >
            Desconectar
          </button>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-dim">¿Borrar las credenciales guardadas?</span>
            <button
              onClick={doDisconnect}
              disabled={busy}
              className="rounded-md bg-dn px-3 py-1.5 text-sm font-medium text-wht hover:bg-red-500 disabled:opacity-50"
            >
              {busy ? "Desconectando…" : "Sí, desconectar"}
            </button>
            <button
              onClick={() => setConfirming(false)}
              disabled={busy}
              className="rounded-md border border-bd px-3 py-1.5 text-sm text-tx hover:bg-pan disabled:opacity-50"
            >
              Cancelar
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function ConnectForm({
  onConnected,
  getToken,
}: {
  onConnected: () => Promise<void>;
  getToken: () => Promise<string | null>;
}) {
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!apiKey.trim() || !apiSecret.trim()) {
      setError("Completá tu API Key y tu Secret Key de Alpaca (paper).");
      return;
    }
    setBusy(true);
    const res = await connectBroker(await getToken(), apiKey.trim(), apiSecret.trim());
    setBusy(false);
    if (res.ok) {
      // SEGURIDAD: limpiamos el form (sobre todo el secreto) apenas se guarda.
      setApiKey("");
      setApiSecret("");
      await onConnected();
    } else {
      // No tocamos el secreto en el error: el usuario corrige y reintenta.
      setError(res.message);
    }
  }

  return (
    <div>
      {/* Wizard: conectá en 3 pasos */}
      <ol className="mb-6 space-y-3">
        <Step n={1}>
          Entrá a tu{" "}
          <a
            href={ALPACA_PAPER_KEYS_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="text-ac underline underline-offset-2 hover:text-acg font-medium"
          >
            panel de Paper Trading de Alpaca
          </a>{" "}
          y, en la sección <span className="text-tx">“API Keys”</span>, generá un par
          nuevo.
        </Step>
        <Step n={2}>
          Copiá el <span className="text-tx">API Key ID</span> y la{" "}
          <span className="text-tx">Secret Key</span>. La secret se muestra{" "}
          <span className="text-tx">una sola vez</span> en Alpaca — copiala en el momento.
        </Step>
        <Step n={3}>
          Pegalas acá abajo y dale <span className="text-tx">Conectar</span>. Validamos
          contra Alpaca (paper) y las guardamos cifradas.
        </Step>
      </ol>

      <form onSubmit={onSubmit} className="rounded-xl border border-bd bg-pan/40 p-5">
        <label className="block">
          <span className="text-sm text-tx">API Key ID</span>
          <input
            type="text"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="PK…"
            autoComplete="off"
            spellCheck={false}
            className="mt-1 w-full rounded-md border border-bd bg-pan px-3 py-2 font-mono text-sm text-tx outline-none focus:border-ac/60"
          />
        </label>

        <label className="mt-4 block">
          <span className="text-sm text-tx">Secret Key</span>
          <input
            type="password"
            value={apiSecret}
            onChange={(e) => setApiSecret(e.target.value)}
            placeholder="••••••••••••••••"
            autoComplete="off"
            spellCheck={false}
            className="mt-1 w-full rounded-md border border-bd bg-pan px-3 py-2 font-mono text-sm text-tx outline-none focus:border-ac/60"
          />
          <span className="mt-1 block text-[11px] text-dim">
            Se envía cifrada y no se muestra nunca de vuelta.
          </span>
        </label>

        {error && (
          <p className="mt-4 rounded-md border border-dn/25 bg-dn/5 px-3 py-2 text-sm text-dn">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={busy}
          className="mt-5 rounded-md bg-ac2 px-4 py-2 text-sm font-medium text-wht hover:bg-ac disabled:opacity-50"
        >
          {busy ? "Validando con Alpaca…" : "Conectar"}
        </button>
      </form>

      <p className="mt-4 text-[11px] leading-relaxed text-dim">
        Solo cuentas <span className="text-tx font-medium">paper</span> (práctica) en esta pantalla.
        No custodiamos tu dinero: tus claves son tuyas y vos ejecutás cada orden.
      </p>
    </div>
  );
}

function Step({ n, children }: { n: number; children: React.ReactNode }) {
  return (
    <li className="flex gap-3">
      <span className="flex h-6 w-6 flex-none items-center justify-center rounded-full border border-bd bg-pan text-xs font-semibold text-tx">
        {n}
      </span>
      <p className="text-sm leading-relaxed text-dim">{children}</p>
    </li>
  );
}
