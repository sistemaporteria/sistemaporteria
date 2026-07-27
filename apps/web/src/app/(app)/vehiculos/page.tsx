import { RegisterVehicle } from "@/components/register-vehicle";
import { createClient } from "@/lib/supabase/server";
import { OWNER_KIND_LABEL, VEHICLE_CLASS_LABEL, type Owner, type Vehicle } from "@/lib/types";

export const dynamic = "force-dynamic";

type VehicleWithOwner = Vehicle & { owners: Pick<Owner, "full_name" | "kind"> | null };

export default async function VehiculosPage() {
  const supabase = await createClient();

  const { data: vehicles, error } = await supabase
    .from("vehicles")
    .select(
      "id, plate, class, category, service_type, brand, model, color, owner_id, active, " +
        "owners(full_name, kind)",
    )
    .order("plate")
    .limit(200)
    .returns<VehicleWithOwner[]>();

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold">Vehículos registrados</h1>
        <p className="mt-1 text-sm text-slate-500">
          Un vehículo registrado deja de aparecer en la cola de revisión: sus pasos se asocian
          solos con su dueño.
        </p>
      </header>

      <RegisterVehicle />

      {error && (
        <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          {error.message}
        </p>
      )}

      <div className="overflow-x-auto">
        <table className="w-full min-w-[42rem] text-sm">
          <thead className="border-b border-slate-200 text-left text-slate-500
            dark:border-slate-800">
            <tr>
              <th className="py-2 pr-3 font-medium">Placa</th>
              <th className="py-2 pr-3 font-medium">Tipo</th>
              <th className="py-2 pr-3 font-medium">Dueño</th>
              <th className="py-2 pr-3 font-medium">Vínculo</th>
              <th className="py-2 font-medium">Marca / color</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {(vehicles ?? []).map((vehicle) => (
              <tr key={vehicle.id}>
                <td className="py-2 pr-3 font-mono font-medium">{vehicle.plate}</td>
                <td className="py-2 pr-3">{VEHICLE_CLASS_LABEL[vehicle.class]}</td>
                <td className="py-2 pr-3">{vehicle.owners?.full_name ?? "—"}</td>
                <td className="py-2 pr-3 text-slate-500">
                  {vehicle.owners ? OWNER_KIND_LABEL[vehicle.owners.kind] : "—"}
                </td>
                <td className="py-2 text-slate-500">
                  {[vehicle.brand, vehicle.color].filter(Boolean).join(" · ") || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {(vehicles ?? []).length === 0 && (
          <p className="py-6 text-center text-sm text-slate-500">
            Todavía no hay vehículos registrados.
          </p>
        )}
      </div>
    </div>
  );
}
