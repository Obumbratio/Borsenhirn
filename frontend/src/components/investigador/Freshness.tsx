"use client";

import { useEffect, useState } from "react";

/**
 * Frescura del análisis: "generado hace X · se refresca cada Y min".
 *
 * Sin mismatch de hidratación: en SSR (y primer render del cliente) muestra la
 * hora ABSOLUTA derivada del ISO (determinista). Recién TRAS montar calcula el
 * relativo "hace X" con el reloj del cliente. Así el HTML del server y el primer
 * render del cliente coinciden byte a byte.
 */
export function Freshness({
  generatedAt,
  ttlSec,
}: {
  generatedAt?: string | null;
  ttlSec?: number | null;
}) {
  const [rel, setRel] = useState<string | null>(null);

  useEffect(() => {
    if (!generatedAt) return;
    const t = new Date(generatedAt).getTime();
    if (!Number.isFinite(t)) return;
    setRel(relativeFrom(t));
    const id = setInterval(() => setRel(relativeFrom(t)), 60_000);
    return () => clearInterval(id);
  }, [generatedAt]);

  if (!generatedAt) return null;

  const refresh = ttlSec ? ` · se refresca cada ${Math.max(1, Math.round(ttlSec / 60))} min` : "";

  return (
    <p className="mt-2 text-[11px] text-dim2">
      Generado {rel ?? abs(generatedAt)}
      {refresh}
    </p>
  );
}

function abs(iso: string): string {
  try {
    return new Date(iso).toLocaleString("es-AR", { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return iso;
  }
}

function relativeFrom(t: number): string {
  const secs = Math.round((Date.now() - t) / 1000);
  if (secs < 0) return "recién";
  if (secs < 60) return "hace unos segundos";
  const mins = Math.round(secs / 60);
  if (mins < 60) return `hace ${mins} min`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `hace ${hrs} h`;
  const days = Math.round(hrs / 24);
  return `hace ${days} d`;
}
