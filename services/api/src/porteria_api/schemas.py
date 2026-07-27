"""Request and response shapes for the ingest API.

The incoming payload mirrors edge_agent.models.AccessEvent, but it is validated again here
rather than trusted. The edge runs on a machine in a shared space at the gate; the server
must not assume anything it sends is well formed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Direction = Literal["in", "out"]
Verdict = Literal["confirmed", "conflict", "unverified", "unrecognized_pattern"]
VehicleClassName = Literal["car", "motorcycle", "trailer", "unknown"]


class AccessEventIn(BaseModel):
  """One vehicle passage reported by the edge agent."""

  occurred_at: datetime
  camera_id: str = Field(min_length=1, max_length=64)
  direction: Direction
  frigate_event_id: str = Field(min_length=1, max_length=128)

  raw_read: str | None = Field(default=None, max_length=64)
  plate_read: str | None = Field(default=None, max_length=16)
  ocr_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
  verdict: Verdict = "unverified"
  detected_class: VehicleClassName | None = None
  plate_class: VehicleClassName | None = None
  frames_agreed: int | None = Field(default=None, ge=0)
  frames_total: int | None = Field(default=None, ge=0)
  track_id: str | None = Field(default=None, max_length=128)
  image_url: str | None = Field(default=None, max_length=1000)
  plate_color: str | None = None
  category: str | None = None
  service_type: str | None = None
  needs_review: bool = False
  notes: list[str] = Field(default_factory=list)

  @field_validator("plate_read")
  @classmethod
  def uppercase_plate(cls, value: str | None) -> str | None:
    return value.upper().strip() if value else None

  @field_validator("occurred_at")
  @classmethod
  def require_timezone(cls, value: datetime) -> datetime:
    # A naive timestamp would be silently read as UTC and shift every report by five hours.
    if value.tzinfo is None:
      raise ValueError("occurred_at debe incluir zona horaria")
    return value


class AccessEventOut(BaseModel):
  """What the agent gets back, so it knows whether to stop retrying."""

  status: Literal["created", "duplicate", "already_recorded"]
  event_id: str | None = None
  plate_read: str | None = None
  vehicle_id: str | None = None
  vehicle_known: bool = False
  needs_review: bool = False
  detail: str | None = None


class HealthOut(BaseModel):
  status: Literal["ok", "degraded"]
  database: bool
  configured: bool
  detail: str | None = None
