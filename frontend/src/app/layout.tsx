import type { Metadata } from "next";
import "./globals.css";
import Link from "next/link";
import {
  ClerkProvider,
  SignedIn,
  SignedOut,
  SignInButton,
  SignUpButton,
  UserButton,
} from "@clerk/nextjs";

export const metadata: Metadata = {
  title: "Börsenhirn",
  description: "Plataforma de inteligencia financiera — trading bot SaaS",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <ClerkProvider>
      <html lang="es">
        <body className="min-h-screen bg-neutral-950 text-neutral-100 antialiased">
          <header className="flex items-center justify-between border-b border-neutral-800 px-6 py-4">
            <Link href="/" className="text-lg font-semibold">
              Börsenhirn
            </Link>
            <nav className="flex items-center gap-3">
              <SignedOut>
                <SignInButton mode="modal">
                  <button className="rounded-md px-3 py-1.5 text-sm hover:bg-neutral-800">
                    Entrar
                  </button>
                </SignInButton>
                <SignUpButton mode="modal">
                  <button className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium hover:bg-emerald-500">
                    Crear cuenta
                  </button>
                </SignUpButton>
              </SignedOut>
              <SignedIn>
                <Link href="/dashboard" className="text-sm hover:underline">
                  Dashboard
                </Link>
                <Link href="/dashboard/positions" className="text-sm hover:underline">
                  Posiciones
                </Link>
                <Link href="/dashboard/broker" className="text-sm hover:underline">
                  Conectar Alpaca
                </Link>
                <UserButton />
              </SignedIn>
            </nav>
          </header>
          <main className="px-6 py-10">{children}</main>
        </body>
      </html>
    </ClerkProvider>
  );
}
