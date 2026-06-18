import { PositionsPanel } from "@/components/PositionsPanel";

// Por-sesión: nunca se prerenderea estático.
export const dynamic = "force-dynamic";

export default function PositionsPage() {
  return <PositionsPanel />;
}
