"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { SignedIn, SignedOut, SignInButton, SignUpButton, UserButton } from "@clerk/nextjs";

/**
 * Barra superior del sistema de diseño (Fusión A+B): logo Börsen·hirn (hirn en
 * morado, Fraunces) + navegación entre secciones + auth de Clerk.
 *
 * La navegación lista las 6 secciones del producto. Se construyen una a una
 * (Tablero primero); las que aún no existen llevan `soon` y se muestran
 * atenuadas y sin link, para no romper con un 404 en el checkpoint.
 */
const NAV: { label: string; href: string; soon?: boolean }[] = [
  { label: "Tablero", href: "/dashboard" },
  { label: "Análisis", href: "/dashboard/analisis" },
  { label: "Investigador", href: "/dashboard/investigador", soon: true },
  { label: "Noticias", href: "/dashboard/noticias", soon: true },
  { label: "Whale", href: "/dashboard/whale", soon: true },
  { label: "Hirn", href: "/dashboard/hirn", soon: true },
  { label: "Track", href: "/dashboard/track", soon: true },
  { label: "Posiciones", href: "/dashboard/positions" },
  { label: "Alpaca", href: "/dashboard/broker" },
];

export function TopBar() {
  const pathname = usePathname();

  return (
    <header className="flex items-center gap-4 border-b border-bd bg-gradient-to-r from-[#0f0c17] to-[#120e1d] px-4 py-2.5">
      <Link href="/" className="font-fraunces text-lg font-semibold text-wht">
        Börsen<span className="text-ac">hirn</span>
      </Link>

      <SignedIn>
        <nav className="flex flex-wrap gap-0.5">
          {NAV.map((item) => {
            const active =
              item.href === "/dashboard"
                ? pathname === "/dashboard"
                : pathname.startsWith(item.href);
            if (item.soon) {
              return (
                <span
                  key={item.href}
                  title="Próximamente"
                  className="cursor-default rounded-md px-2.5 py-1.5 text-[12.5px] text-dim2/70"
                >
                  {item.label}
                </span>
              );
            }
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded-md px-2.5 py-1.5 text-[12.5px] transition-colors ${
                  active ? "bg-ac/15 text-ac" : "text-dim hover:text-tx"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </SignedIn>

      <div className="ml-auto flex items-center gap-3">
        <SignedOut>
          <SignInButton mode="modal">
            <button className="rounded-md px-3 py-1.5 text-sm text-dim hover:text-tx">
              Entrar
            </button>
          </SignInButton>
          <SignUpButton mode="modal">
            <button className="rounded-md bg-gradient-to-br from-ac2 to-[#7c3aed] px-3 py-1.5 text-sm font-medium text-white">
              Crear cuenta
            </button>
          </SignUpButton>
        </SignedOut>
        <SignedIn>
          <UserButton />
        </SignedIn>
      </div>
    </header>
  );
}
