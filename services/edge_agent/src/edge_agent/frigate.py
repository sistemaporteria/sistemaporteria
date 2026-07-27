"""Parse Frigate MQTT payloads into the agent's own vocabulary.

Two topics carry what the agent needs:

  frigate/events                 type: new | update | end, with before/after snapshots of the
                                 tracked object. `after.label` is the independent car vs
                                 motorcycle signal the cross-check depends on.
  frigate/tracked_object_update  type: lpr, one incremental plate reading per refinement.

Frigate runs its own aggregation and keeps its most confident result, but does not expose the
individual readings in the final event. Collecting the `lpr` updates lets the agent run its
own confidence-weighted vote, and keeps it working if Frigate changes that strategy.

Reference: https://docs.frigate.video/integrations/mqtt/
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

VEHICLE_LABELS = frozenset({"car", "motorcycle", "motorbike", "truck", "bus"})


@dataclass(frozen=True)
class EventMessage:
  """A frigate/events message, reduced to what matters here."""

  type: str
  object_id: str
  camera: str
  label: str
  plate: str | None
  plate_score: float | None
  start_time: datetime | None
  end_time: datetime | None
  entered_zones: tuple[str, ...]

  @property
  def is_end(self) -> bool:
    return self.type == "end"

  @property
  def is_vehicle(self) -> bool:
    return self.label in VEHICLE_LABELS


@dataclass(frozen=True)
class LprMessage:
  """A frigate/tracked_object_update message of type `lpr`."""

  object_id: str
  camera: str | None
  plate: str
  at: datetime


def _timestamp(value: Any) -> datetime | None:
  if value is None:
    return None
  try:
    return datetime.fromtimestamp(float(value), tz=UTC)
  except (TypeError, ValueError, OSError):
    return None


def parse_event(payload: str | bytes) -> EventMessage | None:
  """Parse a frigate/events payload. Returns None when it is not usable.

  Malformed payloads are swallowed rather than raised: a broker can deliver anything, and one
  bad message must not take down the agent in the middle of a shift.
  """
  try:
    data = json.loads(payload)
  except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
    return None
  if not isinstance(data, dict):
    return None

  # `after` carries the current state; `before` is only the previous snapshot.
  state = data.get("after") or data.get("before")
  if not isinstance(state, dict):
    return None
  object_id = state.get("id")
  camera = state.get("camera")
  if not object_id or not camera:
    return None

  score = state.get("recognized_license_plate_score")
  zones = state.get("entered_zones") or []

  return EventMessage(
    type=str(data.get("type", "")),
    object_id=str(object_id),
    camera=str(camera),
    label=str(state.get("label") or ""),
    plate=(state.get("recognized_license_plate") or None),
    plate_score=float(score) if isinstance(score, int | float) else None,
    start_time=_timestamp(state.get("start_time")),
    end_time=_timestamp(state.get("end_time")),
    entered_zones=tuple(str(z) for z in zones if z),
  )


def parse_tracked_object_update(payload: str | bytes) -> LprMessage | None:
  """Parse a frigate/tracked_object_update payload, keeping only `lpr` messages."""
  try:
    data = json.loads(payload)
  except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
    return None
  if not isinstance(data, dict) or data.get("type") != "lpr":
    return None

  object_id, plate = data.get("id"), data.get("plate")
  if not object_id or not plate:
    return None

  at = _timestamp(data.get("timestamp")) or datetime.now(tz=UTC)
  camera = data.get("camera")
  return LprMessage(
    object_id=str(object_id),
    camera=str(camera) if camera else None,
    plate=str(plate),
    at=at,
  )
