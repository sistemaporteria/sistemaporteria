"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { createClient } from "@/lib/supabase/client";
import { OWNER_KIND_LABEL, type OwnerKind, type VehicleClass } from "@/lib/types";

const PLATE_PATTERN = /^[A-Z0-9]{5,9}$/;

const EMPTY = {
  plate: "",
  vehicleClass: "car" as VehicleClass,
  brand: "",
  color: "",
  ownerName: "",
  documentId: "",
  kind: "student" as OwnerKind,
  phone: "",
};

export function RegisterVehicle() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function set<K extends keyof typeof EMPTY>(key: K, value: (typeof EMPTY)[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    const plate = form.plate.toUpperCase().trim();
    if (!PLATE_PATTERN.test(plate)) {
      setError("La placa debe tener entre 5 y 9 caracteres alfanuméricos, sin guiones.");
      return;
    }

    setBusy(true);
    const supabase = createClient();

    // The owner may already exist; reuse the record instead of creating a duplicate person.
    // Guards cannot read `owners` at all, so this goes through a SECURITY DEFINER function
    // that returns only an id — never the name, document or phone.
    let ownerId: string | null = null;
    if (form.ownerName.trim()) {
      if (form.documentId.trim()) {
        const { data: existing } = await supabase.rpc("find_owner_id_by_document", {
          document: form.documentId.trim(),
        });
        ownerId = (existing as string | null) ?? null;
      }

      if (!ownerId) {
        const { data: owner, error: ownerError } = await supabase
          .from("owners")
          .insert({
            full_name: form.ownerName.trim(),
            document_id: form.documentId.trim() || null,
            kind: form.kind,
            phone: form.phone.trim() || null,
          })
          .select("id")
          .single();

        if (ownerError) {
          setError(`No se pudo guardar el dueño: ${ownerError.message}`);
          setBusy(false);
          return;
        }
        ownerId = owner.id;
      }
    }

    const { error: vehicleError } = await supabase.from("vehicles").insert({
      plate,
      class: form.vehicleClass,
      brand: form.brand.trim() || null,
      color: form.color.trim() || null,
      owner_id: ownerId,
    });

    if (vehicleError) {
      setError(
        vehicleError.code === "23505"
          ? `La placa ${plate} ya está registrada.`
          : vehicleError.message,
      );
      setBusy(false);
      return;
    }

    setForm(EMPTY);
    setOpen(false);
    setBusy(false);
    router.refresh();
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="rounded bg-slate-900 px-3 py-2 text-sm font-medium text-white
          hover:bg-slate-800 dark:bg-slate-100 dark:text-slate-900"
      >
        Registrar vehículo
      </button>
    );
  }

  const field =
    "mt-1 w-full rounded border border-slate-300 px-2 py-1.5 focus:border-slate-900 " +
    "focus:outline-none dark:border-slate-700 dark:bg-slate-900";

  return (
    <form
      onSubmit={submit}
      className="rounded-lg border border-slate-200 p-4 dark:border-slate-800"
    >
      <h2 className="font-semibold">Nuevo vehículo</h2>

      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <label className="block">
          <span className="text-sm font-medium">Placa *</span>
          <input
            required
            value={form.plate}
            onChange={(e) => set("plate", e.target.value.toUpperCase())}
            maxLength={9}
            placeholder="ABC123"
            className={`${field} font-mono uppercase`}
          />
        </label>

        <label className="block">
          <span className="text-sm font-medium">Tipo</span>
          <select
            value={form.vehicleClass}
            onChange={(e) => set("vehicleClass", e.target.value as VehicleClass)}
            className={field}
          >
            <option value="car">Carro</option>
            <option value="motorcycle">Moto</option>
            <option value="trailer">Remolque</option>
          </select>
        </label>

        <label className="block">
          <span className="text-sm font-medium">Marca</span>
          <input
            value={form.brand}
            onChange={(e) => set("brand", e.target.value)}
            className={field}
          />
        </label>

        <label className="block">
          <span className="text-sm font-medium">Color</span>
          <input
            value={form.color}
            onChange={(e) => set("color", e.target.value)}
            className={field}
          />
        </label>

        <label className="block">
          <span className="text-sm font-medium">Nombre del dueño</span>
          <input
            value={form.ownerName}
            onChange={(e) => set("ownerName", e.target.value)}
            className={field}
          />
        </label>

        <label className="block">
          <span className="text-sm font-medium">Documento</span>
          <input
            value={form.documentId}
            onChange={(e) => set("documentId", e.target.value)}
            className={field}
          />
        </label>

        <label className="block">
          <span className="text-sm font-medium">Vínculo</span>
          <select
            value={form.kind}
            onChange={(e) => set("kind", e.target.value as OwnerKind)}
            className={field}
          >
            {Object.entries(OWNER_KIND_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="text-sm font-medium">Teléfono</span>
          <input
            value={form.phone}
            onChange={(e) => set("phone", e.target.value)}
            className={field}
          />
        </label>
      </div>

      {error && (
        <p role="alert" className="mt-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      )}

      <div className="mt-4 flex gap-2">
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-slate-900 px-3 py-2 text-sm font-medium text-white
            hover:bg-slate-800 disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900"
        >
          {busy ? "Guardando…" : "Guardar"}
        </button>
        <button
          type="button"
          onClick={() => {
            setOpen(false);
            setError(null);
          }}
          className="rounded border border-slate-300 px-3 py-2 text-sm hover:bg-slate-100
            dark:border-slate-700 dark:hover:bg-slate-800"
        >
          Cancelar
        </button>
      </div>
    </form>
  );
}
