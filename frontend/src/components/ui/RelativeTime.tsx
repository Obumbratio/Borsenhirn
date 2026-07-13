"use client";

import { useEffect, useState } from "react";

/**
 * Timestamp relativo ("hace X") sin mismatch de hidratación.
 *
 * En SSR (y primer render del cliente) muestra la hora ABSOLUTA derivada del ISO
 * (determinista). Tras montar calcula el relativo con el reloj del cliente, así
 * el HTML del server y el primer render del cliente coinciden byte a byte.
 */
export function RelativeTime({ iso, className }: { iso: string; className?: string }) {
  const [rel, setRel] = useState<string | null>(null);

  useEffect(() => {
    const t = new Date(iso).getTime();
    if (!Number.isFinite(t)) return;
    const tick = () => setRel(relativeFrom(t));
    tick();
    const id = setInterval(tick, 60_000);
    return () => clearInterval(id);
  }, [iso]);

  return (
    <time dateTime={iso} className={className} title={absolute(iso)}>
      {rel ?? absolute(iso)}
    </time>
  );
}

function absolute(iso: string): string {
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
