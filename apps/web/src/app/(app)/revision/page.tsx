import { LiveRefresh } from "@/components/live-refresh";
import { ReviewQueue } from "@/components/review-queue";
import { createClient } from "@/lib/supabase/server";
import type { AccessEvent } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function RevisionPage() {
  const supabase = await createClient();

  const { data: events, error } = await supabase
    .from("access_events")
    .select(
      "id, occurred_at, camera_id, direction, raw_read, plate_read, corrected_plate, " +
        "vehicle_id, ocr_confidence, verdict, detected_class, plate_class, frames_agreed, " +
        "frames_total, image_url, review_status",
    )
    .eq("review_status", "pending")
    .order("occurred_at", { ascending: false })
    .limit(100)
    .overrideTypes<AccessEvent[], { merge: false }>();

  return (
    <section className="space-y-4">
      <header>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-semibold">Cola de revisión</h1>
          <LiveRefresh />
        </div>
        <p className="mt-1 text-sm text-slate-500">
          Lecturas que el sistema no pudo resolver solo: placas desconocidas, conflictos entre
          la placa y lo que vio la cámara, o pasos ilegibles. Confirmar o corregir aquí es lo
          que alimenta el reentrenamiento del modelo.
        </p>
      </header>

      {error && (
        <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          No se pudieron cargar los eventos: {error.message}
        </p>
      )}

      <ReviewQueue events={events ?? []} />
    </section>
  );
}
