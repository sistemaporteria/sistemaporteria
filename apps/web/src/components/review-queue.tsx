"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { createClient } from "@/lib/supabase/client";
import { formatDateTime } from "@/lib/format";
import { VERDICT_LABEL, type AccessEvent } from "@/lib/types";

const PLATE_PATTERN = /^[A-Z0-9]{5,9}$/;

function VerdictBadge({ event }: { event: AccessEvent }) {
  const tone =
    event.verdict === "conflict"
      ? "bg-red-100 text-red-800"
      : event.verdict === "unrecognized_pattern"
        ? "bg-amber-100 text-amber-800"
        : "bg-slate-100 text-slate-700";

  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${tone}`}>
      {VERDICT_LABEL[event.verdict]}
    </span>
  );
}

function ConflictExplanation({ event }: { event: AccessEvent }) {
  if (event.verdict !== "conflict") return null;
  return (
    <p className="mt-1 text-xs text-red-700">
      La placa sugiere un <strong>{event.plate_class === "car" ? "carro" : "moto"}</strong> pero
      la cámara vio un <strong>{event.detected_class === "car" ? "carro" : "moto"}</strong>.
      Casi siempre significa que el OCR leyó mal un carácter.
    </p>
  );
}

export function ReviewQueue({ events }: { events: AccessEvent[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  async function resolve(event: AccessEvent, status: "confirmed" | "corrected" | "discarded") {
    setBusy(event.id);
    setError(null);

    const corrected = (drafts[event.id] ?? "").toUpperCase().trim();
    if (status === "corrected" && !PLATE_PATTERN.test(corrected)) {
      setError("La placa corregida debe tener entre 5 y 9 caracteres alfanuméricos.");
      setBusy(null);
      return;
    }

    const patch: Record<string, unknown> = {
      review_status: status,
      reviewed_at: new Date().toISOString(),
    };
    if (status === "corrected") patch.corrected_plate = corrected;

    const { error } = await createClient()
      .from("access_events")
      .update(patch)
      .eq("id", event.id);

    if (error) {
      setError(error.message);
      setBusy(null);
      return;
    }
    router.refresh();
    setBusy(null);
  }

  if (events.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-slate-300 px-4 py-8 text-center
        text-sm text-slate-500 dark:border-slate-700">
        No hay nada pendiente de revisión.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {error && (
        <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      )}

      {events.map((event) => {
        const readable = event.plate_read ?? event.raw_read;
        return (
          <article
            key={event.id}
            className="rounded-lg border border-slate-200 p-4 dark:border-slate-800"
          >
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="font-mono text-lg font-semibold">
                {event.plate_read ?? "sin lectura"}
              </span>
              <VerdictBadge event={event} />
              <span className="text-sm text-slate-500">
                {event.direction === "in" ? "Entrada" : "Salida"} · {event.camera_id}
              </span>
              <span className="ml-auto text-sm text-slate-500">
                {formatDateTime(event.occurred_at)}
              </span>
            </div>

            <ConflictExplanation event={event} />

            <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-500">
              {event.raw_read && event.raw_read !== event.plate_read && (
                <div>
                  <dt className="inline">Lectura cruda: </dt>
                  <dd className="inline font-mono">{event.raw_read}</dd>
                </div>
              )}
              {event.ocr_confidence !== null && (
                <div>
                  <dt className="inline">Confianza: </dt>
                  <dd className="inline">{(event.ocr_confidence * 100).toFixed(0)}%</dd>
                </div>
              )}
              {event.frames_total !== null && (
                <div>
                  <dt className="inline">Concordancia: </dt>
                  <dd className="inline">
                    {event.frames_agreed}/{event.frames_total} frames
                  </dd>
                </div>
              )}
            </dl>

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <input
                type="text"
                inputMode="text"
                placeholder={readable ?? "Placa correcta"}
                value={drafts[event.id] ?? ""}
                onChange={(e) =>
                  setDrafts((d) => ({ ...d, [event.id]: e.target.value.toUpperCase() }))
                }
                maxLength={9}
                className="w-[9rem] rounded border border-slate-300 px-2 py-1.5 font-mono
                  uppercase focus:border-slate-900 focus:outline-none dark:border-slate-700
                  dark:bg-slate-900"
              />
              <button
                disabled={busy === event.id}
                onClick={() => resolve(event, "corrected")}
                className="rounded bg-slate-900 px-3 py-1.5 text-sm font-medium text-white
                  hover:bg-slate-800 disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900"
              >
                Corregir
              </button>
              <button
                disabled={busy === event.id || !event.plate_read}
                onClick={() => resolve(event, "confirmed")}
                className="rounded border border-slate-300 px-3 py-1.5 text-sm
                  hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700
                  dark:hover:bg-slate-800"
              >
                Confirmar
              </button>
              <button
                disabled={busy === event.id}
                onClick={() => resolve(event, "discarded")}
                className="rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-500
                  hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700
                  dark:hover:bg-slate-800"
              >
                Descartar
              </button>
            </div>
          </article>
        );
      })}
    </div>
  );
}
