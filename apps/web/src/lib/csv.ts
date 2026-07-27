/** CSV generation for administrative reports. */

/**
 * Quote a value for CSV.
 *
 * Plates are alphanumeric and names may contain commas, so quoting is not optional. Internal
 * quotes are doubled, per RFC 4180.
 */
function quote(value: unknown): string {
  if (value === null || value === undefined) return "";
  const text = String(value);
  return /[",\n\r;]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

export interface Column<T> {
  header: string;
  value: (row: T) => unknown;
}

export function toCsv<T>(rows: T[], columns: Column<T>[]): string {
  const header = columns.map((c) => quote(c.header)).join(";");
  const body = rows.map((row) => columns.map((c) => quote(c.value(row))).join(";"));
  // Semicolons and a BOM: Excel in a Spanish locale splits on semicolons, and without the
  // BOM it renders accented characters as mojibake.
  return `﻿${[header, ...body].join("\r\n")}\r\n`;
}

export function downloadCsv(filename: string, content: string): void {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
