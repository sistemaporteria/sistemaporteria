/** Mirrors the database enums. Kept in sync by hand with services/api/migrations. */

export type Direction = "in" | "out";
export type AppRole = "guard" | "admin";
export type ReviewStatus = "auto" | "pending" | "confirmed" | "corrected" | "discarded";
export type Verdict = "confirmed" | "conflict" | "unverified" | "unrecognized_pattern";
export type VehicleClass = "car" | "motorcycle" | "trailer" | "unknown";
export type OwnerKind = "student" | "professor" | "staff" | "contractor" | "visitor";

export interface Profile {
  id: string;
  full_name: string;
  role: AppRole;
  active: boolean;
}

export interface AccessEvent {
  id: string;
  occurred_at: string;
  camera_id: string;
  direction: Direction;
  raw_read: string | null;
  plate_read: string | null;
  corrected_plate: string | null;
  vehicle_id: string | null;
  ocr_confidence: number | null;
  verdict: Verdict;
  detected_class: VehicleClass | null;
  plate_class: VehicleClass | null;
  frames_agreed: number | null;
  frames_total: number | null;
  image_url: string | null;
  review_status: ReviewStatus;
}

export interface Vehicle {
  id: string;
  plate: string;
  class: VehicleClass;
  category: string | null;
  service_type: string | null;
  brand: string | null;
  model: string | null;
  color: string | null;
  owner_id: string | null;
  active: boolean;
}

export interface Owner {
  id: string;
  full_name: string;
  document_id: string | null;
  kind: OwnerKind;
  phone: string | null;
  email: string | null;
  active: boolean;
}

export interface ParkingSession {
  entry_event_id: string;
  exit_event_id: string | null;
  plate: string;
  vehicle_id: string | null;
  entered_at: string;
  exited_at: string | null;
  duration: string | null;
  is_open: boolean;
}

export const VERDICT_LABEL: Record<Verdict, string> = {
  confirmed: "Confirmado",
  conflict: "Conflicto",
  unverified: "Sin verificar",
  unrecognized_pattern: "Placa no reconocida",
};

export const OWNER_KIND_LABEL: Record<OwnerKind, string> = {
  student: "Estudiante",
  professor: "Docente",
  staff: "Administrativo",
  contractor: "Contratista",
  visitor: "Visitante",
};

export const VEHICLE_CLASS_LABEL: Record<VehicleClass, string> = {
  car: "Carro",
  motorcycle: "Moto",
  trailer: "Remolque",
  unknown: "Desconocido",
};
