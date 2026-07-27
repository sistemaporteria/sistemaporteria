import { ExportCsv } from "@/components/export-csv";
import { getProfile } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";
import { formatDateTime, formatDuration } from "@/lib/format";
import { VERDICT_LABEL, type AccessEvent, type ParkingSession } from "@/lib/types";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{ placa?: string; direccion?: string }>;

export default async function HistorialPage({
  searchParams,
}: Readonly<{ searchParams: SearchParams }>) {
  const { placa, direccion } = await searchParams;
  const [supabase, profile] = await Promise.all([createClient(), getProfile()]);
  const isAdmin = profile?.role === "admin";

  let eventsQuery = supabase
    .from("access_events")
    .select(
      "id, occurred_at, camera_id, direction, plate_read, corrected_plate, raw_read, " +
        "verdict, review_status, ocr_confidence",
    )
    .order("occurred_at", { ascending: false })
    .limit(200);

  if (placa) eventsQuery = eventsQuery.ilike("plate_read", `%${placa.toUpperCase()}%`);
  if (direccion === "in" || direccion === "out") {
    eventsQuery = eventsQuery.eq("direction", direccion);
  }

  const [{ data: events, error }, { data: sessions }] = await Promise.all([
    eventsQuery.overrideTypes<AccessEvent[], { merge: false }>(),
    supabase
      .from("parking_sessions")
      .select("entry_event_id, plate, entered_at, exited_at, duration, is_open")
      .order("entered_at", { ascending: false })
      .limit(50)
      .overrideTypes<ParkingSession[], { merge: false }>(),
  ]);

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Historial</h1>
          {!isAdmin && (
            <p className="mt-1 text-sm text-slate-500">
              Como guardia ves las últimas 24 horas y lo que esté pendiente de revisión. El
              histórico completo es material administrativo.
            </p>
          )}
        </div>
        {isAdmin && <ExportCsv plate={placa} direction={direccion} />}
      </header>

      <form className="flex flex-wrap items-end gap-3" method="get">
        <label className="block">
          <span className="text-sm font-medium">Placa</span>
          <input
            name="placa"
            defaultValue={placa ?? ""}
            placeholder="ABC123"
            className="mt-1 w-[9rem] rounded border border-slate-300 px-2 py-1.5 font-mono
              uppercase dark:border-slate-700 dark:bg-slate-900"
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium">Sentido</span>
          <select
            name="direccion"
            defaultValue={direccion ?? ""}
            className="mt-1 rounded border border-slate-300 px-2 py-1.5
              dark:border-slate-700 dark:bg-slate-900"
          >
            <option value="">Todos</option>
            <option value="in">Entrada</option>
            <option value="out">Salida</option>
          </select>
        </label>
        <button
          type="submit"
          className="rounded bg-slate-900 px-3 py-1.5 text-sm font-medium text-white
            hover:bg-slate-800 dark:bg-slate-100 dark:text-slate-900"
        >
          Filtrar
        </button>
      </form>

      {error && (
        <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          {error.message}
        </p>
      )}

      <section>
        <h2 className="font-semibold">Eventos</h2>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[42rem] text-sm">
            <thead className="border-b border-slate-200 text-left text-slate-500
              dark:border-slate-800">
              <tr>
                <th className="py-2 pr-3 font-medium">Fecha y hora</th>
                <th className="py-2 pr-3 font-medium">Placa</th>
                <th className="py-2 pr-3 font-medium">Sentido</th>
                <th className="py-2 pr-3 font-medium">Cámara</th>
                <th className="py-2 pr-3 font-medium">Veredicto</th>
                <th className="py-2 font-medium">Estado</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {(events ?? []).map((event) => (
                <tr key={event.id}>
                  <td className="py-2 pr-3 whitespace-nowrap">
                    {formatDateTime(event.occurred_at)}
                  </td>
                  <td className="py-2 pr-3 font-mono">
                    {event.corrected_plate ?? event.plate_read ?? (
                      <span className="text-slate-400">{event.raw_read ?? "—"}</span>
                    )}
                  </td>
                  <td className="py-2 pr-3">
                    {event.direction === "in" ? "Entrada" : "Salida"}
                  </td>
                  <td className="py-2 pr-3 text-slate-500">{event.camera_id}</td>
                  <td className="py-2 pr-3 text-slate-500">{VERDICT_LABEL[event.verdict]}</td>
                  <td className="py-2 text-slate-500">{event.review_status}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {(events ?? []).length === 0 && (
            <p className="py-6 text-center text-sm text-slate-500">Sin resultados.</p>
          )}
        </div>
      </section>

      <section>
        <h2 className="font-semibold">Sesiones de parqueo</h2>
        <p className="mt-0.5 text-xs text-slate-500">
          Calculadas por la base a partir de los eventos: al corregir una placa, las sesiones se
          recalculan solas.
        </p>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[34rem] text-sm">
            <thead className="border-b border-slate-200 text-left text-slate-500
              dark:border-slate-800">
              <tr>
                <th className="py-2 pr-3 font-medium">Placa</th>
                <th className="py-2 pr-3 font-medium">Entrada</th>
                <th className="py-2 pr-3 font-medium">Salida</th>
                <th className="py-2 font-medium">Permanencia</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {(sessions ?? []).map((session) => (
                <tr key={session.entry_event_id}>
                  <td className="py-2 pr-3 font-mono">{session.plate}</td>
                  <td className="py-2 pr-3 whitespace-nowrap">
                    {formatDateTime(session.entered_at)}
                  </td>
                  <td className="py-2 pr-3 whitespace-nowrap">
                    {session.exited_at ? (
                      formatDateTime(session.exited_at)
                    ) : (
                      <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-xs
                        text-emerald-800">
                        adentro
                      </span>
                    )}
                  </td>
                  <td className="py-2">{formatDuration(session.duration)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {(sessions ?? []).length === 0 && (
            <p className="py-6 text-center text-sm text-slate-500">Sin sesiones.</p>
          )}
        </div>
      </section>
    </div>
  );
}
