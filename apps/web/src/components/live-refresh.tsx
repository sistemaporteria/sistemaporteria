"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { createClient } from "@/lib/supabase/client";

type Status = "connecting" | "live" | "offline";

/**
 * Refreshes the page when access_events changes.
 *
 * It re-runs the server components instead of patching local state: the dashboard shows
 * aggregates and a database view, and recomputing those in the browser would be a second
 * implementation of logic Postgres already owns. Events arrive a handful of times per minute,
 * so the cost of a refresh is irrelevant.
 *
 * Realtime honours RLS, so a guard is only notified about rows their policies would let them
 * read.
 */
export function LiveRefresh() {
  const router = useRouter();
  const [status, setStatus] = useState<Status>("connecting");

  useEffect(() => {
    const supabase = createClient();
    const channel = supabase
      .channel("access-events")
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "access_events" },
        () => router.refresh(),
      )
      .subscribe((state) => {
        if (state === "SUBSCRIBED") setStatus("live");
        else if (state === "CHANNEL_ERROR" || state === "TIMED_OUT") setStatus("offline");
      });

    return () => {
      supabase.removeChannel(channel);
    };
  }, [router]);

  const tone =
    status === "live"
      ? "bg-emerald-500"
      : status === "connecting"
        ? "bg-amber-400"
        : "bg-slate-400";

  const label =
    status === "live"
      ? "En vivo"
      : status === "connecting"
        ? "Conectando…"
        : "Sin conexión en vivo";

  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-slate-500" title={label}>
      <span className={`inline-block h-2 w-2 rounded-full ${tone}`} aria-hidden />
      {label}
    </span>
  );
}
