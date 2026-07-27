import json
from datetime import UTC, datetime, timedelta

import pytest
from plate_rules import CrossCheckVerdict, VehicleClass

from edge_agent.config import Config, parse_camera_directions
from edge_agent.frigate import parse_event, parse_tracked_object_update
from edge_agent.models import Direction
from edge_agent.pipeline import Pipeline

BASE_TS = 1785000000.0


@pytest.fixture
def config():
  return Config(
    camera_directions=parse_camera_directions("porteria_entrada:in,porteria_salida:out"),
    dedup_window_seconds=90,
  )


@pytest.fixture
def collected():
  return []


@pytest.fixture
def pipeline(config, collected):
  return Pipeline(config, collected.append)


def event(
  kind,
  object_id="obj-1",
  camera="porteria_entrada",
  label="car",
  plate=None,
  score=None,
  start=BASE_TS,
  end=None,
):
  state = {
    "id": object_id,
    "camera": camera,
    "label": label,
    "start_time": start,
    "end_time": end,
    "entered_zones": ["carril"],
    "recognized_license_plate": plate,
    "recognized_license_plate_score": score,
  }
  return parse_event(json.dumps({"type": kind, "after": state}))


def lpr(plate, object_id="obj-1", camera="porteria_entrada", ts=BASE_TS):
  return parse_tracked_object_update(
    json.dumps(
      {"type": "lpr", "id": object_id, "camera": camera, "plate": plate, "timestamp": ts}
    )
  )


class TestDirection:
  def test_direction_comes_from_the_camera(self, pipeline, collected):
    pipeline.handle_event(event("new", plate="ABC123"))
    pipeline.handle_event(event("end", plate="ABC123", end=BASE_TS + 5))
    assert collected[0].direction is Direction.IN

  def test_exit_camera_yields_out(self, pipeline, collected):
    pipeline.handle_event(
      event("new", object_id="o2", camera="porteria_salida", plate="ABC123")
    )
    pipeline.handle_event(
      event("end", object_id="o2", camera="porteria_salida", plate="ABC123", end=BASE_TS + 5)
    )
    assert collected[0].direction is Direction.OUT

  def test_unknown_camera_is_ignored(self, pipeline, collected):
    pipeline.handle_event(event("new", camera="camara_del_parqueadero", plate="ABC123"))
    pipeline.handle_event(event("end", camera="camara_del_parqueadero", end=BASE_TS + 5))
    assert collected == []

  def test_non_vehicle_objects_are_ignored(self, pipeline, collected):
    pipeline.handle_event(event("new", label="person"))
    pipeline.handle_event(event("end", label="person", end=BASE_TS + 5))
    assert collected == []


class TestEmission:
  def test_emits_only_on_end(self, pipeline, collected):
    pipeline.handle_event(event("new", plate="ABC123"))
    pipeline.handle_event(event("update", plate="ABC123"))
    assert collected == []
    pipeline.handle_event(event("end", plate="ABC123", end=BASE_TS + 5))
    assert len(collected) == 1

  def test_aggregates_lpr_readings(self, pipeline, collected):
    pipeline.handle_event(event("new"))
    for plate in ("ABC123", "ABC128", "ABC123", "ABC123"):
      pipeline.handle_lpr(lpr(plate))
    pipeline.handle_event(event("end", end=BASE_TS + 5))
    assert collected[0].plate_read == "ABC123"
    assert collected[0].frames_agreed == 3
    assert collected[0].frames_total == 4

  def test_falls_back_to_frigate_final_plate(self, pipeline, collected):
    # No individual lpr updates arrived; the event's own field must still be used.
    pipeline.handle_event(event("new", plate="ABC123", score=0.9))
    pipeline.handle_event(event("end", plate="ABC123", score=0.9, end=BASE_TS + 5))
    assert collected[0].plate_read == "ABC123"

  def test_lpr_before_first_event_is_kept(self, pipeline, collected):
    pipeline.handle_lpr(lpr("ABC123"))
    pipeline.handle_event(event("end", end=BASE_TS + 5))
    assert collected[0].plate_read == "ABC123"

  def test_vehicle_without_any_reading_is_still_recorded(self, pipeline, collected):
    # An unreadable passage is information: dropping it would hide a failing camera.
    pipeline.handle_event(event("new"))
    pipeline.handle_event(event("end", end=BASE_TS + 5))
    assert len(collected) == 1
    assert collected[0].plate_read is None
    assert collected[0].needs_review
    assert "sin_lectura_de_placa" in collected[0].notes

  def test_frigate_id_travels_for_idempotency(self, pipeline, collected):
    pipeline.handle_event(event("new", object_id="abc-99", plate="ABC123"))
    pipeline.handle_event(event("end", object_id="abc-99", plate="ABC123", end=BASE_TS + 5))
    assert collected[0].frigate_event_id == "abc-99"


class TestCrossCheck:
  def test_agreement_is_confirmed(self, pipeline, collected):
    pipeline.handle_event(event("new", label="car", plate="ABC123"))
    pipeline.handle_event(event("end", label="car", plate="ABC123", end=BASE_TS + 5))
    assert collected[0].verdict is CrossCheckVerdict.CONFIRMED
    assert not collected[0].needs_review

  def test_ocr_error_on_a_motorcycle_becomes_a_conflict(self, pipeline, collected):
    # Real failure mode: motorcycle ABC12D misread as ABC120.
    pipeline.handle_event(event("new", label="motorcycle", plate="ABC120"))
    pipeline.handle_event(event("end", label="motorcycle", plate="ABC120", end=BASE_TS + 5))
    assert collected[0].verdict is CrossCheckVerdict.CONFLICT
    assert collected[0].needs_review
    assert collected[0].detected_class is VehicleClass.MOTORCYCLE
    assert collected[0].plate_class is VehicleClass.CAR

  def test_foreign_plate_is_flagged_not_invented(self, pipeline, collected):
    pipeline.handle_event(event("new", plate="29UM92"))
    pipeline.handle_event(event("end", plate="29UM92", end=BASE_TS + 5))
    assert collected[0].plate_read is None
    assert collected[0].needs_review


class TestDeduplication:
  def test_same_plate_within_window_is_dropped(self, pipeline, collected):
    for object_id, end in (("o1", BASE_TS + 5), ("o2", BASE_TS + 45)):
      pipeline.handle_event(event("new", object_id=object_id, plate="ABC123"))
      pipeline.handle_event(event("end", object_id=object_id, plate="ABC123", end=end))
    assert len(collected) == 1

  def test_same_plate_after_window_is_kept(self, pipeline, collected):
    for object_id, end in (("o1", BASE_TS + 5), ("o2", BASE_TS + 200)):
      pipeline.handle_event(event("new", object_id=object_id, plate="ABC123"))
      pipeline.handle_event(event("end", object_id=object_id, plate="ABC123", end=end))
    assert len(collected) == 2

  def test_different_cameras_are_independent(self, pipeline, collected):
    pipeline.handle_event(event("new", object_id="o1", plate="ABC123"))
    pipeline.handle_event(event("end", object_id="o1", plate="ABC123", end=BASE_TS + 5))
    pipeline.handle_event(
      event("new", object_id="o2", camera="porteria_salida", plate="ABC123")
    )
    pipeline.handle_event(
      event("end", object_id="o2", camera="porteria_salida", plate="ABC123", end=BASE_TS + 10)
    )
    assert len(collected) == 2


class TestHousekeeping:
  def test_prune_drops_objects_that_never_ended(self, pipeline):
    pipeline.handle_event(event("new", plate="ABC123"))
    future = datetime.fromtimestamp(BASE_TS, tz=UTC) + timedelta(hours=1)
    assert pipeline.prune(now=future) == 1
    assert pipeline.prune(now=future) == 0

  def test_payload_is_json_serializable(self, pipeline, collected):
    pipeline.handle_event(event("new", plate="ABC123"))
    pipeline.handle_event(event("end", plate="ABC123", end=BASE_TS + 5))
    payload = collected[0].to_payload()
    assert json.loads(json.dumps(payload))["plate_read"] == "ABC123"
    assert payload["direction"] == "in"


class TestConfig:
  def test_parses_camera_directions(self):
    assert parse_camera_directions("a:in,b:out") == {"a": Direction.IN, "b": Direction.OUT}

  def test_tolerates_whitespace_and_trailing_comma(self):
    assert parse_camera_directions(" a : in , ") == {"a": Direction.IN}

  @pytest.mark.parametrize("bad", ["a:sideways", "a", ":in"])
  def test_rejects_invalid_entries(self, bad):
    with pytest.raises(ValueError):
      parse_camera_directions(bad)
