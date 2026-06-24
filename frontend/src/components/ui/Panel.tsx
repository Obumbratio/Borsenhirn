import type { ReactNode } from "react";

/**
 * Panel del sistema de diseño (Fusión A+B): caja morada oscura con borde
 * redondeado. Opcionalmente con cabecera (grip ⠿ + título con ícono de acento
 * + acción a la derecha). Presentacional puro.
 */
export function Panel({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`overflow-hidden rounded-xl border border-bd bg-pan ${className}`}
    >
      {children}
    </div>
  );
}

export function PanelHeader({
  title,
  icon,
  action,
  grip = true,
}: {
  title: ReactNode;
  /** Ícono/emoji que va antes del título, pintado con el acento. */
  icon?: ReactNode;
  /** Contenido a la derecha (botón ⋯, +, tag…). */
  action?: ReactNode;
  grip?: boolean;
}) {
  return (
    <div className="flex items-center justify-between border-b border-bd2 px-3.5 py-2.5 text-[12.5px]">
      <span className="flex items-center">
        {grip && (
          <span className="mr-1.5 cursor-grab tracking-widest text-dim2 select-none">
            ⠿
          </span>
        )}
        <span className="font-semibold text-tx">
          {icon && <span className="mr-1.5 text-ac">{icon}</span>}
          {title}
        </span>
      </span>
      {action && <span className="text-dim2">{action}</span>}
    </div>
  );
}

/** Cuerpo con padding estándar del panel. */
export function PanelBody({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={`p-3.5 ${className}`}>{children}</div>;
}
