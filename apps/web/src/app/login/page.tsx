"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { createClient } from "@/lib/supabase/client";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);

    const supabase = createClient();
    const { error } = await supabase.auth.signInWithPassword({ email, password });

    if (error) {
      setError("Correo o contraseña incorrectos");
      setLoading(false);
      return;
    }
    router.push(params.get("redirect") ?? "/");
    router.refresh();
  }

  return (
    <form onSubmit={onSubmit} className="w-full max-w-[24rem] space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Portería vehicular</h1>
        <p className="mt-1 text-sm text-slate-500">UNAL — Sede Manizales</p>
      </div>

      <label className="block">
        <span className="text-sm font-medium">Correo</span>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="username"
          className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-base
            focus:border-slate-900 focus:outline-none dark:border-slate-700 dark:bg-slate-900"
        />
      </label>

      <label className="block">
        <span className="text-sm font-medium">Contraseña</span>
        <input
          type="password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-base
            focus:border-slate-900 focus:outline-none dark:border-slate-700 dark:bg-slate-900"
        />
      </label>

      {error && (
        <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={loading}
        className="w-full rounded-lg bg-slate-900 px-4 py-2.5 font-medium text-white
          hover:bg-slate-800 disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900"
      >
        {loading ? "Entrando…" : "Entrar"}
      </button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <main className="flex min-h-screen items-center justify-center px-6">
      <Suspense>
        <LoginForm />
      </Suspense>
    </main>
  );
}
