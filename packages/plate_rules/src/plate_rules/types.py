"""Domain vocabulary for Colombian license plates.

Pure data definitions: no I/O, no third-party dependencies. See docs/02-placas-colombia.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class VehicleClass(StrEnum):
  """Coarse physical class, comparable against an object detector label."""

  CAR = "car"
  MOTORCYCLE = "motorcycle"
  TRAILER = "trailer"
  UNKNOWN = "unknown"


class ServiceType(StrEnum):
  """Legal service category encoded by the plate."""

  PRIVATE = "private"
  PUBLIC = "public"
  OFFICIAL = "official"
  DIPLOMATIC = "diplomatic"
  ANTIQUE = "antique"
  TEMPORARY = "temporary"
  POLICE = "police"
  MILITARY = "military"
  UNKNOWN = "unknown"


class PlateColor(StrEnum):
  """Background color of the plate, estimated from the cropped image."""

  YELLOW = "yellow"
  WHITE = "white"
  GREEN = "green"
  RED = "red"
  BLACK = "black"
  UNKNOWN = "unknown"


class PlateCategory(StrEnum):
  """A concrete plate type from the national catalog."""

  PRIVATE_CAR = "private_car"
  PUBLIC_CAR = "public_car"
  OFFICIAL_CAR = "official_car"
  ANTIQUE_CAR = "antique_car"
  DIPLOMATIC_CAR = "diplomatic_car"
  MOTORCYCLE = "motorcycle"
  MOTORCYCLE_LEGACY = "motorcycle_legacy"
  MOTOCARRO_PRIVATE = "motocarro_private"
  MOTOCARRO_PUBLIC = "motocarro_public"
  TRAILER = "trailer"
  TEMPORARY = "temporary"
  POLICE = "police"
  AIR_FORCE = "air_force"
  UNKNOWN = "unknown"


class CrossCheckVerdict(StrEnum):
  """Result of contrasting the plate-derived class against what the camera saw."""

  CONFIRMED = "confirmed"
  CONFLICT = "conflict"
  UNVERIFIED = "unverified"
  UNRECOGNIZED_PATTERN = "unrecognized_pattern"


@dataclass(frozen=True)
class NormalizedPlate:
  """Outcome of cleaning and pattern-coercing a raw OCR string."""

  raw: str
  text: str
  mask: str | None
  corrections: int
  is_valid: bool
  rejection_reason: str | None = None


@dataclass(frozen=True)
class PlateIdentification:
  """Full classification of a plate reading."""

  plate: NormalizedPlate
  categories: tuple[PlateCategory, ...] = ()
  category: PlateCategory = PlateCategory.UNKNOWN
  vehicle_class: VehicleClass = VehicleClass.UNKNOWN
  service_type: ServiceType = ServiceType.UNKNOWN
  verdict: CrossCheckVerdict = CrossCheckVerdict.UNVERIFIED
  confidence: float = 0.0
  notes: tuple[str, ...] = field(default_factory=tuple)

  @property
  def needs_review(self) -> bool:
    return self.verdict in (
      CrossCheckVerdict.CONFLICT,
      CrossCheckVerdict.UNRECOGNIZED_PATTERN,
    )
