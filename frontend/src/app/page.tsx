import Link from "next/link";
import { SignedIn, SignedOut, SignInButton } from "@clerk/nextjs";

export default function Home() {
  return (
    <div className="mx-auto max-w-2xl text-center">
      <h1 className="text-4xl font-bold tracking-tight">Börsenhirn</h1>
      <p className="mt-4 text-neutral-400">
        Trading bot multi-tenant. Conectá tu cuenta de Alpaca y dejá que el bot
        opere por vos, con aislamiento de datos por usuario.
      </p>
      <div className="mt-8 flex justify-center gap-3">
        <SignedOut>
          <SignInButton mode="modal">
            <button className="rounded-md bg-emerald-600 px-5 py-2.5 font-medium hover:bg-emerald-500">
              Entrar
            </button>
          </SignInButton>
        </SignedOut>
        <SignedIn>
          <Link
            href="/dashboard"
            className="rounded-md bg-emerald-600 px-5 py-2.5 font-medium hover:bg-emerald-500"
          >
            Ir al dashboard
          </Link>
        </SignedIn>
      </div>
    </div>
  );
}
