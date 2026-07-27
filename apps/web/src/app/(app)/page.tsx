import Link from "next/link";

import { createClient } from "@/lib/supabase/server";
import { formatDuration, formatTime } from "@/lib/format";
import type { AccessEvent, ParkingSession } from "@/lib/types";

export const dynamic = "force-dynamic";

function startOfTodayBogota(): string {
  // Bogota is UTC-5 year round, with no daylight saving, so the offset is a constant.
  const now = new Date();
  const bogota = new Date(now.getTime() - 5 * 3600 * 1000);
  bogota.setUTCHours(0, 0, 0, 0);
  return new Date(bogota.getTime() + 5 * 3600 * 1000).toISOString();
}

function Stat({ label, value, hint }: { label: string; value: number | string; hint?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
      <div className="text-2xl font-semibold tabular-nums">{value}</div>
      <div className="mt-0.5 text-sm text-slate-600 dark:text-slate-400">{label}</div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

export default async function DashboardPage() {
  const supabase = await createClient();
  const since = startOfTodayBogota();

  const [entries, exits, pending, openSessions, recent] = await Promise.all([
    supabase
      .from("access_events")
      .select("id", { count: "exact", head: true })
      .eq("direction", "in")
      .gte("occurred_at", since),
    supabase
      .from("access_events")
      .select("id", { count: "exact", head: true })
      .eq("direction", "out")
      .gte("occurred_at", since),
    supabase
      .from("access_events")
      .select("id", { count: "exact", head: true })
      .eq("review_status", "pending"),
    supabase
      .from("parking_sessions")
      .select("plate, entered_at, exited_at, duration, is_open")
      .eq("is_open", true)
      .order("entered_at", { ascending: false })
      .limit(50)
      .returns<ParkingSession[]>(),
    supabase
      .from("access_events")
      .select("id, occurred_at, camera_id, direction, plate_read, verdict, review_status")
      .order("occurred_at", { ascending: false })
      .limit(12)
      .returns<AccessEvent[]>(),
  ]);

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Tablero de hoy</h1>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Entradas hoy" value={entries.count ?? 0} />
        <Stat label="Salidas hoy" value={exits.count ?? 0} />
        <Stat
          label="Adentro ahora"
          value={openSessions.data?.length ?? 0}
          hint="Sesiones sin salida registrada"
        />
        <Stat label="Pendientes de revisión" value={pending.count ?? 0} />
      </div>

      <section>
        <div className="flex items-baseline justify-between">
          <h2 className="font-semibold">Últimos pasos</h2>
          <Link href="/historial" className="text-sm text-slate-500 hover:underline">
            Ver historial
          </Link>
        </div>
        {recent.data && recent.data.length > 0 ? (
          <ul className="mt-2 divide-y divide-slate-200 dark:divide-slate-800">
            {recent.data.map((event) => (
              <li key={event.id} className="flex items-center gap-3 py-2 text-sm">
                <span className="w-14 text-slate-500">{formatTime(event.occurred_at)}</span>
                <span
                  className={`w-16 text-xs font-medium ${
                    event.direction === "in" ? "text-emerald-700" : "text-slate-500"
                  }`}
                >
                  {event.direction === "in" ? "Entrada" : "Salida"}
                </span>
                <span className="font-mono">{event.plate_read ?? "—"}</span>
                {event.review_status === "pending" && (
                  <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-800">
                    revisar
                  </span>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-slate-500">Todavía no hay eventos registrados.</p>
        )}
      </section>

      <section>
        <h2 className="font-semibold">Vehículos adentro</h2>
        {openSessions.data && openSessions.data.length > 0 ? (
          <ul className="mt-2 divide-y divide-slate-200 dark:divide-slate-800">
            {openSessions.data.map((session) => (
              <li key={session.entry_event_id} className="flex items-center gap-3 py-2 text-sm">
                <span className="font-mono">{session.plate}</span>
                <span className="text-slate-500">
                  desde {formatTime(session.entered_at)}
                </span>
                <span className="ml-auto text-slate-500">
                  {formatDuration(session.duration)}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-slate-500">Ningún vehículo con entrada sin salida.</p>
        )}
      </section>
    </div>
  );
}
