import { PosicionesView } from "@/components/posiciones/PosicionesView";
import { DEMO_POSITIONS } from "@/lib/demo-signals";

// Por-sesión: nunca se prerenderea estático.
export const dynamic = "force-dynamic";

/**
 * Posiciones — posiciones reales del usuario (Alpaca BYO, paper) + alertas TP/SL.
 * La vista (client) hace GET /me/positions. NO toca backend ni contratos; la
 * única ejecución pasa por OrderConfirmDialog (modal + gate 451).
 *
 * ⚠️ TEMPORAL: con `?demo=1` usa posiciones de DEMOSTRACIÓN (banner visible).
 * Quitar junto con lib/demo-signals.ts.
 */
export default function PositionsPage({
  searchParams,
}: {
  searchParams: { demo?: string };
}) {
  if (searchParams?.demo === "1") {
    return <PosicionesView demoPositions={DEMO_POSITIONS} />;
  }
  return <PosicionesView />;
}
