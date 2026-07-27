"""End-to-end test over a recorded Frigate session.

Covers the whole chain without a broker, a camera or Frigate: recorded MQTT messages ->
parsing -> temporal aggregation -> classification -> cross-check -> outbox.
"""

import json
from pathlib import Path

import pytest
from plate_rules import CrossCheckVerdict

from edge_agent.config import Config, parse_camera_directions
from edge_agent.main import _dispatch
from edge_agent.outbox import Outbox
from edge_agent.pipeline import Pipeline

FIXTURE = Path(__file__).parent / "fixtures" / "porteria_demo.jsonl"


@pytest.fixture
def events():
  config = Config(
    camera_directions=parse_camera_directions("porteria_entrada:in,porteria_salida:out")
  )
  collected = []
  pipeline = Pipeline(config, collected.append)
  for line in FIXTURE.read_text(encoding="utf-8").splitlines():
    if not line.strip():
      continue
    record = json.loads(line)
    _dispatch(pipeline, config, record["topic"], json.dumps(record["payload"]))
  return collected


def test_emits_one_event_per_vehicle_passage(events):
  # Six vehicles in the recording; the person must not produce an event.
  assert len(events) == 6


def test_mask_coercion_recovers_a_bad_frame_before_the_vote(events):
  # Readings were KEM018, KEM0I8, KEM018, KEM018. The odd one out is not outvoted, it is
  # repaired: against the LLLNNN mask the I in a digit slot coerces to 1, so all four
  # readings agree. This is the coercion working inside the full pipeline, not just in
  # plate_rules unit tests.
  first = events[0]
  assert first.plate_read == "KEM018"
  assert first.frames_agreed == 4
  assert first.frames_total == 4
  assert first.verdict is CrossCheckVerdict.CONFIRMED
  assert not first.needs_review


def test_motorcycle_ocr_error_is_caught_by_cross_check(events):
  # HCR60S misread as HCR605: the pattern says car, the camera saw a motorcycle.
  moto = events[1]
  assert moto.plate_read == "HCR605"
  assert moto.verdict is CrossCheckVerdict.CONFLICT
  assert moto.needs_review


def test_foreign_plate_is_rejected_not_invented(events):
  foreign = events[2]
  assert foreign.plate_read is None
  assert foreign.needs_review


def test_unreadable_passage_is_still_recorded(events):
  unreadable = events[3]
  assert unreadable.plate_read is None
  assert "sin_lectura_de_placa" in unreadable.notes


def test_direction_follows_the_camera(events):
  assert [e.direction.value for e in events] == ["in", "in", "in", "in", "in", "out"]
  assert events[5].camera_id == "porteria_salida"
  assert events[5].plate_read == "KEM018"


def test_person_is_ignored(events):
  assert all(e.detected_class is None or e.detected_class.value != "person" for e in events)


def test_every_event_reaches_the_outbox(tmp_path, events):
  outbox = Outbox(tmp_path / "outbox.db")
  for event in events:
    outbox.enqueue(event.frigate_event_id, event.to_payload())
  assert outbox.counts()["pendientes"] == len(events)


def test_replaying_twice_does_not_duplicate(tmp_path, events):
  # MQTT redelivery and agent restarts must not create phantom passages.
  outbox = Outbox(tmp_path / "outbox.db")
  for _ in range(2):
    for event in events:
      outbox.enqueue(event.frigate_event_id, event.to_payload())
  assert outbox.counts()["total"] == len(events)
