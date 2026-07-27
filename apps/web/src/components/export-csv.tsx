"use client";

import { useState } from "react";

import { downloadCsv, toCsv, type Column } from "@/lib/csv";
import { formatDateTime, formatDuration } from "@/lib/format";
import { createClient } from "@/lib/supabase/client";
import { VERDICT_LABEL, type AccessEvent, type ParkingSession } from "@/lib/types";

const EVENT_COLUMNS: Column<AccessEvent>[] = [
  { header: "Fecha y hora", value: (e) => formatDateTime(e.occurred_at) },
  { header: "Placa", value: (e) => e.corrected_plate ?? e.plate_read ?? "" },
  { header: "Lectura cruda", value: (e) => e.raw_read ?? "" },
  { header: "Sentido", value: (e) => (e.direction === "in" ? "Entrada" : "Salida") },
  { header: "Camara", value: (e) => e.camera_id },
  { header: "Veredicto", value: (e) => VERDICT_LABEL[e.verdict] },
  { header: "Estado revision", value: (e) => e.review_status },
  {
    header: "Confianza",
    value: (e) => (e.ocr_confidence === null ? "" : e.ocr_confidence.toFixed(2)),
  },
];

const SESSION_COLUMNS: Column<ParkingSession>[] = [
  { header: "Placa", value: (s) => s.plate },
  { header: "Entrada", value: (s) => formatDateTime(s.entered_at) },
  { header: "Salida", value: (s) => (s.exited_at ? formatDateTime(s.exited_at) : "") },
  { header: "Permanencia", value: (s) => formatDuration(s.duration) },
  { header: "Abierta", value: (s) => (s.is_open ? "si" : "no") },
];

/** Rows per request. PostgREST caps a single response, so large exports are paged. */
const PAGE = 1000;
const MAX_ROWS = 20000;

export function ExportCsv({ plate, direction }: { plate?: string; direction?: string }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function fetchAll<T>(
    table: "access_events" | "parking_sessions",
    columns: string,
    order: string,
  ): Promise<T[]> {
    const supabase = createClient();
    const rows: T[] = [];

    for (let from = 0; from < MAX_ROWS; from += PAGE) {
      let query = supabase
        .from(table)
        .select(columns)
        .order(order, { ascending: false })
        .range(from, from + PAGE - 1);

      if (table === "access_events") {
        if (plate) query = query.ilike("plate_read", `%${plate.toUpperCase()}%`);
        if (direction === "in" || direction === "out") {
          query = query.eq("direction", direction);
        }
      }

      const { data, error } = await query.overrideTypes<T[], { merge: false }>();
      if (error) throw new Error(error.message);
      if (!data || data.length === 0) break;
      rows.push(...data);
      if (data.length < PAGE) break;
    }
    return rows;
  }

  async function exportEvents() {
    setBusy("eventos");
    setError(null);
    try {
      const rows = await fetchAll<AccessEvent>(
        "access_events",
        "id, occurred_at, camera_id, direction, plate_read, corrected_plate, raw_read, " +
          "verdict, review_status, ocr_confidence",
        "occurred_at",
      );
      downloadCsv(`eventos-porteria-${stamp()}.csv`, toCsv(rows, EVENT_COLUMNS));
    } catch (e) {
      setError(e instanceof Error ? e.message : "fallo la exportacion");
    }
    setBusy(null);
  }

  async function exportSessions() {
    setBusy("sesiones");
    setError(null);
    try {
      const rows = await fetchAll<ParkingSession>(
        "parking_sessions",
        "entry_event_id, plate, entered_at, exited_at, duration, is_open",
        "entered_at",
      );
      downloadCsv(`sesiones-porteria-${stamp()}.csv`, toCsv(rows, SESSION_COLUMNS));
    } catch (e) {
      setError(e instanceof Error ? e.message : "fallo la exportacion");
    }
    setBusy(null);
  }

  const button =
    "rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 " +
    "disabled:opacity-50 dark:border-slate-700 dark:hover:bg-slate-800";

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button onClick={exportEvents} disabled={busy !== null} className={button}>
        {busy === "eventos" ? "Exportando…" : "Exportar eventos (CSV)"}
      </button>
      <button onClick={exportSessions} disabled={busy !== null} className={button}>
        {busy === "sesiones" ? "Exportando…" : "Exportar sesiones (CSV)"}
      </button>
      {error && (
        <span role="alert" className="text-sm text-red-700">
          {error}
        </span>
      )}
    </div>
  );
}

function stamp(): string {
  return new Date().toISOString().slice(0, 10);
}
