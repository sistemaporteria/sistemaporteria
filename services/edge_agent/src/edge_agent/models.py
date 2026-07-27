"""What the agent produces: one access event per vehicle passage."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from plate_rules import CrossCheckVerdict, PlateColor, VehicleClass


class Direction(StrEnum):
  IN = "in"
  OUT = "out"


@dataclass(frozen=True)
class PlateReading:
  """A single OCR observation published by Frigate for a tracked object."""

  text: str
  confidence: float
  at: datetime


@dataclass
class TrackedObject:
  """State accumulated for one Frigate object while it is still in frame.

  Frigate refines the plate as the vehicle moves and keeps its own best result, but it does
  not expose the individual readings in the final event. Collecting the `lpr` updates lets
  the agent run its own confidence-weighted vote, which also survives Frigate changing its
  internal strategy.
  """

  object_id: str
  camera: str
  label: str | None = None
  readings: list[PlateReading] = field(default_factory=list)
  final_plate: str | None = None
  final_confidence: float | None = None
  started_at: datetime | None = None
  ended_at: datetime | None = None
  entered_zones: tuple[str, ...] = ()

  def add_reading(self, text: str, confidence: float, at: datetime) -> None:
    if text:
      self.readings.append(PlateReading(text, confidence, at))


@dataclass(frozen=True)
class AccessEvent:
  """A vehicle passage, ready to be persisted. Mirrors the access_events table."""

  occurred_at: datetime
  camera_id: str
  direction: Direction
  raw_read: str | None
  plate_read: str | None
  ocr_confidence: float | None
  verdict: CrossCheckVerdict
  detected_class: VehicleClass | None
  plate_class: VehicleClass | None
  frames_agreed: int | None
  frames_total: int | None
  frigate_event_id: str
  track_id: str | None = None
  image_url: str | None = None
  plate_color: PlateColor = PlateColor.UNKNOWN
  category: str | None = None
  service_type: str | None = None
  needs_review: bool = False
  notes: tuple[str, ...] = ()

  def to_payload(self) -> dict[str, Any]:
    """Serialize for the ingest API. Enums become their string values."""
    data = asdict(self)
    data["occurred_at"] = self.occurred_at.astimezone(UTC).isoformat()
    data["direction"] = self.direction.value
    data["verdict"] = self.verdict.value
    data["detected_class"] = self.detected_class.value if self.detected_class else None
    data["plate_class"] = self.plate_class.value if self.plate_class else None
    data["plate_color"] = self.plate_color.value
    data["notes"] = list(self.notes)
    return data
