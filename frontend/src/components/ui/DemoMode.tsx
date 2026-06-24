"use client";

import { createContext, useContext, type ReactNode } from "react";

/**
 * Modo demo (?demo=1) propagado por contexto.
 *
 * PRINCIPIO: en demo, NINGUNA acción debe tener efectos reales. El punto de
 * ejecución (OrderConfirmDialog) lee este contexto y simula en vez de pegarle al
 * backend. Cualquier componente montado bajo un <DemoModeProvider demo> hereda
 * la simulación sin que el caller tenga que acordarse de pasar un prop.
 *
 * Default `false` → fuera de demo todo es real (path normal intacto).
 */
const DemoModeContext = createContext(false);

export function DemoModeProvider({ demo, children }: { demo: boolean; children: ReactNode }) {
  return <DemoModeContext.Provider value={demo}>{children}</DemoModeContext.Provider>;
}

/** ¿Estamos en modo demo? Úsalo en el punto de ejecución para simular. */
export function useDemoMode(): boolean {
  return useContext(DemoModeContext);
}
