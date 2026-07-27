"""Turn Frigate messages into access events.

This is the only place that knows both Frigate's vocabulary and the domain's. It holds the
per-object state while a vehicle is in frame, and on the `end` event it aggregates, classifies
and cross-checks before emitting.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from plate_rules import CrossCheckVerdict, PlateColor, Reading, VehicleClass, aggregate
from plate_rules.classify import DETECTOR_LABEL_TO_CLASS

from .config import Config
from .frigate import EventMessage, LprMessage
from .models import AccessEvent, Direction, TrackedObject

logger = logging.getLogger(__name__)

# A tracked object that never produced an `end` event is dropped after this long, so a
# crashed or restarted Frigate cannot leak memory here.
STALE_OBJECT_TTL = timedelta(minutes=15)


class Pipeline:
  """Accumulates readings per tracked object and emits one event per passage."""

  def __init__(self, config: Config, emit: Callable[[AccessEvent], None]) -> None:
    self.config = config
    self.emit = emit
    self._objects: dict[str, TrackedObject] = {}
    self._last_emitted: dict[tuple[str, str], datetime] = {}

  # --- ingest -------------------------------------------------------------------------

  def handle_event(self, message: EventMessage) -> None:
    if message.camera not in self.config.camera_directions:
      return
    if not message.is_vehicle:
      return

    tracked = self._objects.setdefault(
      message.object_id, TrackedObject(message.object_id, message.camera)
    )
    tracked.label = message.label or tracked.label
    tracked.entered_zones = message.entered_zones or tracked.entered_zones
    tracked.started_at = tracked.started_at or message.start_time

    # Frigate refines the plate across updates; keep its latest best as a fallback for the
    # case where no individual `lpr` update arrived.
    if message.plate:
      tracked.final_plate = message.plate
      tracked.final_confidence = message.plate_score

    if message.is_end:
      tracked.ended_at = message.end_time or datetime.now(tz=UTC)
      self._finish(tracked)

  def handle_lpr(self, message: LprMessage) -> None:
    tracked = self._objects.get(message.object_id)
    if tracked is None:
      # An `lpr` update can arrive before the first `events` message. Keep it: discarding it
      # would throw away a reading that the vote may need.
      tracked = TrackedObject(message.object_id, message.camera or "")
      self._objects[message.object_id] = tracked
    tracked.add_reading(message.plate, 1.0, message.at)

  def prune(self, now: datetime | None = None) -> int:
    """Drop objects that never ended. Returns how many were removed."""
    now = now or datetime.now(tz=UTC)
    stale = [
      key
      for key, tracked in self._objects.items()
      if (tracked.started_at or now) < now - STALE_OBJECT_TTL
    ]
    for key in stale:
      del self._objects[key]
    return len(stale)

  # --- emit ---------------------------------------------------------------------------

  def _finish(self, tracked: TrackedObject) -> None:
    self._objects.pop(tracked.object_id, None)

    direction = self.config.camera_directions.get(tracked.camera)
    if direction is None:
      return

    event = self._build_event(tracked, direction)
    if event is None:
      return

    if self._is_duplicate(event):
      logger.info("descartado por deduplicacion: %s en %s", event.plate_read, event.camera_id)
      return

    if event.plate_read:
      self._last_emitted[(event.camera_id, event.plate_read)] = event.occurred_at
    self.emit(event)

  def _build_event(self, tracked: TrackedObject, direction: Direction) -> AccessEvent | None:
    occurred_at = tracked.ended_at or tracked.started_at or datetime.now(tz=UTC)
    detected_class = DETECTOR_LABEL_TO_CLASS.get((tracked.label or "").lower())

    readings = [
      Reading(r.text, r.confidence, PlateColor.UNKNOWN, tracked.label) for r in tracked.readings
    ]
    if not readings and tracked.final_plate:
      readings = [
        Reading(
          tracked.final_plate,
          tracked.final_confidence if tracked.final_confidence is not None else 1.0,
          PlateColor.UNKNOWN,
          tracked.label,
        )
      ]

    if not readings:
      # A vehicle passed but no plate was ever read. The event is still recorded: an
      # unreadable passage is information, and dropping it would hide a failing camera.
      return AccessEvent(
        occurred_at=occurred_at,
        camera_id=tracked.camera,
        direction=direction,
        raw_read=None,
        plate_read=None,
        ocr_confidence=None,
        verdict=CrossCheckVerdict.UNRECOGNIZED_PATTERN,
        detected_class=detected_class,
        plate_class=None,
        frames_agreed=0,
        frames_total=0,
        frigate_event_id=tracked.object_id,
        track_id=tracked.object_id,
        needs_review=True,
        notes=("sin_lectura_de_placa",),
      )

    consensus = aggregate(readings)
    if consensus is None:
      return None

    identification = consensus.identification
    raw_read = readings[0].text if len(readings) == 1 else identification.plate.raw

    return AccessEvent(
      occurred_at=occurred_at,
      camera_id=tracked.camera,
      direction=direction,
      raw_read=raw_read,
      plate_read=identification.plate.text if identification.plate.is_valid else None,
      ocr_confidence=round(identification.confidence, 4),
      verdict=identification.verdict,
      detected_class=detected_class,
      plate_class=identification.vehicle_class
      if identification.vehicle_class is not VehicleClass.UNKNOWN
      else None,
      frames_agreed=consensus.votes,
      frames_total=consensus.total_readings,
      frigate_event_id=tracked.object_id,
      track_id=tracked.object_id,
      category=identification.category.value,
      service_type=identification.service_type.value,
      needs_review=(
        identification.needs_review
        or consensus.is_contested
        or identification.confidence < self.config.min_confidence
      ),
      notes=identification.notes,
    )

  def _is_duplicate(self, event: AccessEvent) -> bool:
    if not event.plate_read:
      return False
    previous = self._last_emitted.get((event.camera_id, event.plate_read))
    if previous is None:
      return False
    delta = abs((event.occurred_at - previous).total_seconds())
    return delta < self.config.dedup_window_seconds
