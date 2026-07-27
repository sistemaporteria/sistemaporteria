import json

from edge_agent.frigate import parse_event, parse_tracked_object_update


def event_payload(**overrides):
  state = {
    "id": "1607123955.475377-mxklsc",
    "camera": "porteria_entrada",
    "label": "car",
    "sub_label": None,
    "score": 0.87,
    "box": [432, 496, 544, 854],
    "current_zones": ["carril"],
    "entered_zones": ["carril"],
    "start_time": 1607123955.475377,
    "end_time": None,
    "recognized_license_plate": "ABC123",
    "recognized_license_plate_score": 0.93,
  }
  state.update(overrides.pop("state", {}))
  payload = {"type": overrides.pop("type", "update"), "before": state, "after": state}
  payload.update(overrides)
  return json.dumps(payload)


class TestParseEvent:
  def test_reads_the_after_state(self):
    message = parse_event(event_payload())
    assert message is not None
    assert message.object_id == "1607123955.475377-mxklsc"
    assert message.camera == "porteria_entrada"
    assert message.label == "car"
    assert message.plate == "ABC123"
    assert message.plate_score == 0.93

  def test_prefers_after_over_before(self):
    payload = json.loads(event_payload())
    payload["before"]["recognized_license_plate"] = "OLD999"
    payload["after"]["recognized_license_plate"] = "NEW111"
    message = parse_event(json.dumps(payload))
    assert message is not None and message.plate == "NEW111"

  def test_falls_back_to_before_when_after_missing(self):
    payload = json.loads(event_payload())
    payload.pop("after")
    message = parse_event(json.dumps(payload))
    assert message is not None and message.plate == "ABC123"

  def test_detects_end_type(self):
    assert parse_event(event_payload(type="end")).is_end
    assert not parse_event(event_payload(type="update")).is_end

  def test_recognizes_vehicle_labels(self):
    for label in ("car", "motorcycle", "truck", "bus"):
      assert parse_event(event_payload(state={"label": label})).is_vehicle
    assert not parse_event(event_payload(state={"label": "person"})).is_vehicle

  def test_parses_unix_timestamps(self):
    message = parse_event(event_payload())
    assert message.start_time is not None
    assert message.start_time.year == 2020

  def test_missing_plate_is_none_not_empty(self):
    message = parse_event(event_payload(state={"recognized_license_plate": None}))
    assert message is not None and message.plate is None

  def test_entered_zones_preserved(self):
    message = parse_event(event_payload())
    assert message.entered_zones == ("carril",)

  # A broker can deliver anything; one bad message must not take the agent down.
  def test_survives_malformed_json(self):
    assert parse_event("{no es json") is None

  def test_survives_non_object_payload(self):
    assert parse_event("[1, 2, 3]") is None

  def test_rejects_payload_without_id_or_camera(self):
    assert parse_event(json.dumps({"type": "end", "after": {"label": "car"}})) is None

  def test_survives_bad_timestamp(self):
    message = parse_event(event_payload(state={"start_time": "no-es-fecha"}))
    assert message is not None and message.start_time is None


class TestParseTrackedObjectUpdate:
  def test_parses_lpr_message(self):
    payload = json.dumps(
      {
        "type": "lpr",
        "id": "1607123955.475377-mxklsc",
        "camera": "porteria_entrada",
        "plate": "ABC123",
        "timestamp": 1607123958.748393,
      }
    )
    message = parse_tracked_object_update(payload)
    assert message is not None
    assert message.plate == "ABC123"
    assert message.object_id == "1607123955.475377-mxklsc"

  def test_ignores_other_update_types(self):
    for kind in ("description", "face", "classification"):
      payload = json.dumps({"type": kind, "id": "x", "plate": "ABC123"})
      assert parse_tracked_object_update(payload) is None

  def test_requires_id_and_plate(self):
    assert parse_tracked_object_update(json.dumps({"type": "lpr", "id": "x"})) is None
    assert parse_tracked_object_update(json.dumps({"type": "lpr", "plate": "A"})) is None

  def test_defaults_timestamp_when_absent(self):
    payload = json.dumps({"type": "lpr", "id": "x", "plate": "ABC123"})
    message = parse_tracked_object_update(payload)
    assert message is not None and message.at is not None

  def test_survives_malformed_json(self):
    assert parse_tracked_object_update("<html>") is None
