import type { Metadata } from "next";
import { Fraunces, Inter, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import { ClerkProvider } from "@clerk/nextjs";
import { TopBar } from "@/components/ui/TopBar";

/*
 * Tipografía del sistema de diseño (Fusión A+B):
 * Fraunces (serif) para logo/títulos/símbolos · Inter para el resto ·
 * IBM Plex Mono para números/datos. Se exponen como CSS vars que consume
 * tailwind.config.ts (font-fraunces / font-sans / font-mono).
 */
const fraunces = Fraunces({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-fraunces",
  display: "swap",
});
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});
const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Börsenhirn",
  description: "Plataforma de inteligencia financiera — análisis impersonal, vos decidís.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <ClerkProvider>
      <html lang="es" className={`${fraunces.variable} ${inter.variable} ${plexMono.variable}`}>
        <body className="min-h-screen bg-bg text-tx antialiased">
          <TopBar />
          <main className="px-3 py-3 sm:px-4">{children}</main>
        </body>
      </html>
    </ClerkProvider>
  );
}
