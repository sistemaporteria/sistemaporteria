"use client";

import { useRouter } from "next/navigation";

import { createClient } from "@/lib/supabase/client";

export function SignOutButton() {
  const router = useRouter();

  async function signOut() {
    await createClient().auth.signOut();
    router.push("/login");
    router.refresh();
  }

  return (
    <button
      onClick={signOut}
      className="rounded border border-slate-300 px-2.5 py-1 text-sm hover:bg-slate-100
        dark:border-slate-700 dark:hover:bg-slate-800"
    >
      Salir
    </button>
  );
}
