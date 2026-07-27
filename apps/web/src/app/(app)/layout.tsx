import Link from "next/link";
import { redirect } from "next/navigation";

import { SignOutButton } from "@/components/sign-out-button";
import { createClient } from "@/lib/supabase/server";
import type { Profile } from "@/lib/types";

const NAV = [
  { href: "/", label: "Tablero" },
  { href: "/revision", label: "Revisión" },
  { href: "/historial", label: "Historial" },
  { href: "/vehiculos", label: "Vehículos" },
];

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) redirect("/login");

  const { data: profile } = await supabase
    .from("profiles")
    .select("id, full_name, role, active")
    .eq("id", user.id)
    .single<Profile>();

  // A user can exist in auth without a profile row. RLS would then hide everything, which is
  // correct but looks like an empty app; say so instead of showing blank screens.
  if (!profile) {
    return (
      <main className="mx-auto max-w-[40rem] px-6 py-16">
        <h1 className="text-xl font-semibold">Cuenta sin perfil</h1>
        <p className="mt-2 text-slate-600 dark:text-slate-400">
          La cuenta existe pero no tiene un perfil asignado, así que no puede ver ningún dato.
          Un administrador debe crearlo.
        </p>
        <div className="mt-6">
          <SignOutButton />
        </div>
      </main>
    );
  }

  const pendingCount = await supabase
    .from("access_events")
    .select("id", { count: "exact", head: true })
    .eq("review_status", "pending");

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 dark:border-slate-800">
        <div className="mx-auto flex max-w-[75rem] flex-wrap items-center gap-x-6 gap-y-2 px-6 py-3">
          <span className="font-semibold">Portería</span>
          <nav className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="rounded px-2 py-1 text-slate-600 hover:bg-slate-100
                  hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800
                  dark:hover:text-slate-100"
              >
                {item.label}
                {item.href === "/revision" && (pendingCount.count ?? 0) > 0 && (
                  <span className="ml-1.5 rounded-full bg-amber-500 px-1.5 py-0.5 text-xs
                    font-medium text-white">
                    {pendingCount.count}
                  </span>
                )}
              </Link>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <span className="text-slate-500">
              {profile.full_name} · {profile.role === "admin" ? "admin" : "guardia"}
            </span>
            <SignOutButton />
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-[75rem] px-6 py-6">{children}</main>
    </div>
  );
}
