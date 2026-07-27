/** Formatting helpers. Everything is shown in Bogota time, never in the browser's zone. */

const TIME_ZONE = "America/Bogota";

export function formatDateTime(iso: string): string {
  return new Intl.DateTimeFormat("es-CO", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: TIME_ZONE,
  }).format(new Date(iso));
}

export function formatTime(iso: string): string {
  return new Intl.DateTimeFormat("es-CO", {
    timeStyle: "short",
    timeZone: TIME_ZONE,
  }).format(new Date(iso));
}

/** Postgres intervals arrive as `HH:MM:SS`, which reads badly in a report. */
export function formatDuration(interval: string | null): string {
  if (!interval) return "—";
  const [hours, minutes] = interval.split(":").map(Number);
  if (Number.isNaN(hours)) return interval;
  if (hours === 0) return `${minutes} min`;
  return minutes === 0 ? `${hours} h` : `${hours} h ${minutes} min`;
}
