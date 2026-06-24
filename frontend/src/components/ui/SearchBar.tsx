"use client";

import type { FormEvent } from "react";

/**
 * Barra de búsqueda del sistema de diseño morado (input + botón).
 * Presentacional/controlada: el padre maneja el valor y el submit.
 * Reutilizable en Investigador y, más adelante, en Noticias.
 */
export function SearchBar({
  value,
  onChange,
  onSubmit,
  placeholder,
  buttonLabel = "Buscar",
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  placeholder?: string;
  buttonLabel?: string;
}) {
  function handle(e: FormEvent) {
    e.preventDefault();
    onSubmit();
  }
  return (
    <form onSubmit={handle} className="flex gap-2">
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        spellCheck={false}
        className="flex-1 rounded-lg border border-bd bg-pan2 px-3.5 py-2.5 text-[13px] text-wht outline-none placeholder:text-dim2 focus:border-ac2"
      />
      <button
        type="submit"
        className="rounded-lg bg-gradient-to-br from-ac2 to-[#7c3aed] px-4 py-2.5 text-[12.5px] font-semibold text-white"
      >
        {buttonLabel}
      </button>
    </form>
  );
}
