import type { Config } from "tailwindcss";

/*
 * Sistema de diseño Börsenhirn (Fusión A+B).
 * Los colores referencian las CSS vars de globals.css para tener una sola
 * fuente de verdad. Uso: bg-pan, border-bd, text-ac, text-up/text-dn, etc.
 */
const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        bg2: "var(--bg2)",
        ac: "var(--ac)",
        ac2: "var(--ac2)",
        acg: "var(--acg)",
        pan: "var(--pan)",
        pan2: "var(--pan2)",
        bd: "var(--bd)",
        bd2: "var(--bd2)",
        tx: "var(--tx)",
        dim: "var(--dim)",
        dim2: "var(--dim2)",
        wht: "var(--wht)",
        up: "var(--up)",
        dn: "var(--dn)",
        warn: "var(--warn)",
      },
      fontFamily: {
        fraunces: ["var(--font-fraunces)", "Fraunces", "serif"],
        sans: ["var(--font-inter)", "Inter", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "IBM Plex Mono", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;
