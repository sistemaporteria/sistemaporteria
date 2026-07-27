from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from porteria_api import Settings, create_app
from porteria_api.supabase import InsertOutcome, SupabaseError

TOKEN = "token-de-prueba"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class FakeSupabase:
  """Stands in for PostgREST so tests need no network and no live database."""

  def __init__(self, vehicle=None, outcome=None, error=None):
    self.vehicle = vehicle
    self.outcome = outcome or InsertOutcome(True, {"id": "evt-uuid-1"})
    self.error = error
    self.inserted: list[dict] = []
    self.looked_up: list[str] = []

  def ping(self):
    return True

  def find_vehicle_by_plate(self, plate):
    self.looked_up.append(plate)
    if self.error:
      raise self.error
    return self.vehicle

  def insert_access_event(self, payload):
    self.inserted.append(payload)
    if self.error:
      raise self.error
    return self.outcome

  def close(self):
    pass


def build(fake: FakeSupabase) -> TestClient:
  settings = Settings(
    supabase_url="https://example.supabase.co",
    supabase_secret_key="secreto",
    ingest_token=TOKEN,
  )
  return TestClient(create_app(settings=settings, supabase=fake))


def event(**overrides):
  payload = {
    "occurred_at": datetime(2026, 7, 26, 8, 0, tzinfo=UTC).isoformat(),
    "camera_id": "porteria_entrada",
    "direction": "in",
    "frigate_event_id": "1785000100.11-aaa",
    "plate_read": "KEM018",
    "raw_read": "KEM018",
    "ocr_confidence": 0.94,
    "verdict": "confirmed",
    "detected_class": "car",
    "plate_class": "car",
    "frames_agreed": 4,
    "frames_total": 4,
    "needs_review": False,
  }
  payload.update(overrides)
  return payload


class TestAuth:
  def test_rejects_missing_token(self):
    response = build(FakeSupabase()).post("/events", json=event())
    assert response.status_code == 401

  def test_rejects_wrong_token(self):
    client = build(FakeSupabase())
    response = client.post("/events", json=event(), headers={"Authorization": "Bearer otro"})
    assert response.status_code == 401

  def test_accepts_valid_token(self):
    response = build(FakeSupabase()).post("/events", json=event(), headers=AUTH)
    assert response.status_code == 201

  def test_refuses_to_run_without_a_configured_token(self):
    settings = Settings(
      supabase_url="https://example.supabase.co", supabase_secret_key="s", ingest_token=""
    )
    client = TestClient(create_app(settings=settings, supabase=FakeSupabase()))
    assert client.post("/events", json=event(), headers=AUTH).status_code == 503


class TestValidation:
  def test_rejects_naive_timestamp(self):
    # Without a timezone the value would be read as UTC and shift every report by five hours.
    payload = event(occurred_at="2026-07-26T08:00:00")
    assert build(FakeSupabase()).post("/events", json=payload, headers=AUTH).status_code == 422

  def test_rejects_invalid_direction(self):
    payload = event(direction="sideways")
    assert build(FakeSupabase()).post("/events", json=payload, headers=AUTH).status_code == 422

  def test_rejects_confidence_out_of_range(self):
    payload = event(ocr_confidence=1.5)
    assert build(FakeSupabase()).post("/events", json=payload, headers=AUTH).status_code == 422

  def test_requires_frigate_event_id(self):
    payload = event()
    del payload["frigate_event_id"]
    assert build(FakeSupabase()).post("/events", json=payload, headers=AUTH).status_code == 422


class TestPlateRevalidation:
  def test_uppercases_the_plate(self):
    fake = FakeSupabase()
    build(fake).post("/events", json=event(plate_read="kem018"), headers=AUTH)
    assert fake.looked_up == ["KEM018"]

  def test_foreign_plate_is_stored_as_raw_read_only(self):
    # The server owns what enters the database: a plate the domain rejects never becomes one.
    fake = FakeSupabase()
    response = build(fake).post(
      "/events", json=event(plate_read="29UM92", raw_read="29UM92"), headers=AUTH
    )
    assert response.status_code == 201
    row = fake.inserted[0]
    assert row["plate_read"] is None
    assert row["raw_read"] == "29UM92"
    assert row["review_status"] == "pending"

  def test_repairs_a_correctable_reading(self):
    fake = FakeSupabase()
    build(fake).post("/events", json=event(plate_read="KEM0I8"), headers=AUTH)
    assert fake.inserted[0]["plate_read"] == "KEM018"

  def test_event_without_plate_is_still_recorded(self):
    fake = FakeSupabase()
    response = build(fake).post(
      "/events", json=event(plate_read=None, raw_read=None), headers=AUTH
    )
    assert response.status_code == 201
    assert fake.inserted[0]["plate_read"] is None
    assert fake.inserted[0]["review_status"] == "pending"
    assert fake.looked_up == []


class TestVehicleResolution:
  def test_links_a_known_vehicle(self):
    fake = FakeSupabase(vehicle={"id": "veh-1", "plate": "KEM018", "owner_id": "own-1"})
    response = build(fake).post("/events", json=event(), headers=AUTH)
    body = response.json()
    assert body["vehicle_known"] is True
    assert body["vehicle_id"] == "veh-1"
    assert fake.inserted[0]["review_status"] == "auto"

  def test_unknown_vehicle_goes_to_the_review_queue(self):
    # Not an error: this queue is what feeds vehicle registration.
    fake = FakeSupabase(vehicle=None)
    response = build(fake).post("/events", json=event(), headers=AUTH)
    assert response.json()["vehicle_known"] is False
    assert response.json()["needs_review"] is True
    assert fake.inserted[0]["review_status"] == "pending"

  def test_conflicting_verdict_forces_review_even_when_known(self):
    fake = FakeSupabase(vehicle={"id": "veh-1"})
    payload = event(verdict="conflict", needs_review=True)
    build(fake).post("/events", json=payload, headers=AUTH)
    assert fake.inserted[0]["review_status"] == "pending"


class TestIdempotency:
  def test_resend_after_outage_is_not_an_error(self):
    # The agent retries from its outbox; the passage is already recorded.
    fake = FakeSupabase(outcome=InsertOutcome(False, None, "already_recorded"))
    response = build(fake).post("/events", json=event(), headers=AUTH)
    assert response.status_code == 200
    assert response.json()["status"] == "already_recorded"

  def test_duplicate_passage_within_the_window_is_not_an_error(self):
    fake = FakeSupabase(outcome=InsertOutcome(False, None, "duplicate"))
    response = build(fake).post("/events", json=event(), headers=AUTH)
    assert response.status_code == 200
    assert response.json()["status"] == "duplicate"


class TestFailures:
  def test_database_failure_returns_502_so_the_agent_retries(self):
    # 502, not 500: the event must stay queued at the edge.
    fake = FakeSupabase(error=SupabaseError("red caida"))
    response = build(fake).post("/events", json=event(), headers=AUTH)
    assert response.status_code == 502

  def test_health_reports_ok(self):
    assert build(FakeSupabase()).get("/health").json()["status"] == "ok"

  def test_health_reports_degraded_without_configuration(self):
    settings = Settings(supabase_url="", supabase_secret_key="", ingest_token=TOKEN)
    client = TestClient(create_app(settings=settings, supabase=None))
    body = client.get("/health").json()
    assert body["status"] == "degraded"
    assert body["configured"] is False


class TestSupabaseErrorMapping:
  @pytest.mark.parametrize(
    ("code", "expected"),
    [("23505", "already_recorded"), ("23P01", "duplicate")],
  )
  def test_constraint_codes_map_to_benign_outcomes(self, code, expected, monkeypatch):
    import httpx

    from porteria_api.supabase import SupabaseClient

    def handler(request):
      return httpx.Response(409, json={"code": code, "message": "conflict"})

    client = SupabaseClient("https://example.co/rest/v1", "k")
    client._client = httpx.Client(transport=httpx.MockTransport(handler))
    outcome = client.insert_access_event({})
    assert not outcome.created
    assert outcome.reason == expected

  def test_unknown_error_raises(self):
    import httpx

    from porteria_api.supabase import SupabaseClient

    def handler(request):
      return httpx.Response(500, json={"code": "XX000", "message": "boom"})

    client = SupabaseClient("https://example.co/rest/v1", "k")
    client._client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(SupabaseError):
      client.insert_access_event({})
