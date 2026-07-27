import pytest

from edge_agent.outbox import Outbox
from edge_agent.transport import MAX_ATTEMPTS, Synchronizer


@pytest.fixture
def outbox(tmp_path):
  return Outbox(tmp_path / "outbox.db")


class FailingSink:
  def __init__(self, fail_times: int = 999):
    self.fail_times = fail_times
    self.calls = 0
    self.delivered: list[dict] = []

  def send(self, payload):
    self.calls += 1
    if self.calls <= self.fail_times:
      raise OSError("red caida")
    self.delivered.append(payload)


class TestOutbox:
  def test_enqueue_and_read_back(self, outbox):
    assert outbox.enqueue("evt-1", {"plate_read": "ABC123"})
    pending = outbox.pending()
    assert len(pending) == 1
    assert pending[0].payload["plate_read"] == "ABC123"

  def test_duplicate_frigate_id_is_rejected(self, outbox):
    # MQTT is at-least-once: the same event can be delivered twice.
    assert outbox.enqueue("evt-1", {"a": 1})
    assert not outbox.enqueue("evt-1", {"a": 2})
    assert len(outbox.pending()) == 1

  def test_mark_sent_removes_from_pending(self, outbox):
    outbox.enqueue("evt-1", {})
    outbox.mark_sent(outbox.pending()[0].id)
    assert outbox.pending() == []
    assert outbox.counts() == {"pendientes": 0, "enviados": 1, "total": 1}

  def test_mark_failed_increments_attempts_and_keeps_it_queued(self, outbox):
    outbox.enqueue("evt-1", {})
    outbox.mark_failed(outbox.pending()[0].id, "timeout")
    pending = outbox.pending()
    assert len(pending) == 1
    assert pending[0].attempts == 1

  def test_pending_is_ordered_and_limited(self, outbox):
    for i in range(5):
      outbox.enqueue(f"evt-{i}", {"i": i})
    pending = outbox.pending(limit=3)
    assert [row.payload["i"] for row in pending] == [0, 1, 2]

  def test_survives_reopening_the_file(self, tmp_path):
    path = tmp_path / "outbox.db"
    Outbox(path).enqueue("evt-1", {"plate_read": "ABC123"})
    assert len(Outbox(path).pending()) == 1

  def test_purge_keeps_recent_sent_rows(self, outbox):
    outbox.enqueue("evt-1", {})
    outbox.mark_sent(outbox.pending()[0].id)
    assert outbox.purge_sent(keep_days=7) == 0
    assert outbox.counts()["total"] == 1


class TestSynchronizer:
  def test_delivers_pending_events(self, outbox):
    outbox.enqueue("evt-1", {"plate_read": "ABC123"})
    sink = FailingSink(fail_times=0)
    assert Synchronizer(outbox, sink).drain() == (1, 0)
    assert sink.delivered[0]["plate_read"] == "ABC123"
    assert outbox.pending() == []

  def test_failure_keeps_the_event_queued(self, outbox):
    # The whole point of the outbox: an outage must not lose a passage.
    outbox.enqueue("evt-1", {})
    synchronizer = Synchronizer(outbox, FailingSink())
    assert synchronizer.drain() == (0, 1)
    assert len(outbox.pending()) == 1

  def test_retries_until_it_succeeds(self, outbox):
    outbox.enqueue("evt-1", {"plate_read": "ABC123"})
    sink = FailingSink(fail_times=2)
    synchronizer = Synchronizer(outbox, sink)
    synchronizer.drain()
    synchronizer.drain()
    assert outbox.pending()[0].attempts == 2
    assert synchronizer.drain() == (1, 0)
    assert outbox.pending() == []

  def test_stops_retrying_and_reports_stuck(self, outbox):
    outbox.enqueue("evt-1", {})
    synchronizer = Synchronizer(outbox, FailingSink())
    for _ in range(MAX_ATTEMPTS):
      synchronizer.drain()
    assert synchronizer.stuck()
    # A permanent failure must become visible instead of retrying forever.
    assert synchronizer.drain() == (0, 0)
