"""Transactional outbox: never lose an access event to a network outage.

The agent never calls the API from the thread that processes MQTT messages. It writes to a
local SQLite file first — an operation that cannot fail for network reasons — and a separate
worker drains it.

Without this, a ten-minute internet outage at peak hour silently loses around thirty
passages. In a gate that today runs on a paper notebook, losing records is worse than the
system it replaces, and it would destroy trust in it.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = """
create table if not exists outbox (
  id             integer primary key autoincrement,
  frigate_id     text not null unique,
  payload        text not null,
  created_at     text not null,
  sent_at        text,
  attempts       integer not null default 0,
  last_error     text
);
create index if not exists outbox_pending_idx on outbox (sent_at, id) where sent_at is null;
"""


@dataclass(frozen=True)
class OutboxRow:
  id: int
  frigate_id: str
  payload: dict[str, Any]
  attempts: int


class Outbox:
  """SQLite-backed queue of events waiting to reach the API."""

  def __init__(self, path: Path) -> None:
    self.path = path
    self.path.parent.mkdir(parents=True, exist_ok=True)
    with self._connect() as connection:
      connection.executescript(SCHEMA)

  @contextmanager
  def _connect(self) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(self.path, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
      # WAL lets the sync worker read while the MQTT thread writes.
      connection.execute("pragma journal_mode=WAL")
      yield connection
      connection.commit()
    finally:
      connection.close()

  def enqueue(self, frigate_id: str, payload: dict[str, Any]) -> bool:
    """Queue an event. Returns False when it was already queued.

    The unique constraint on frigate_id makes re-delivery from the broker harmless: MQTT at
    least-once semantics mean the same event can arrive twice.
    """
    with self._connect() as connection:
      try:
        connection.execute(
          "insert into outbox (frigate_id, payload, created_at) values (?, ?, ?)",
          (frigate_id, json.dumps(payload), datetime.now(tz=UTC).isoformat()),
        )
        return True
      except sqlite3.IntegrityError:
        return False

  def pending(self, limit: int = 50) -> list[OutboxRow]:
    with self._connect() as connection:
      rows = connection.execute(
        "select id, frigate_id, payload, attempts from outbox "
        "where sent_at is null order by id limit ?",
        (limit,),
      ).fetchall()
    return [
      OutboxRow(r["id"], r["frigate_id"], json.loads(r["payload"]), r["attempts"]) for r in rows
    ]

  def mark_sent(self, row_id: int) -> None:
    with self._connect() as connection:
      connection.execute(
        "update outbox set sent_at = ?, last_error = null where id = ?",
        (datetime.now(tz=UTC).isoformat(), row_id),
      )

  def mark_failed(self, row_id: int, error: str) -> None:
    with self._connect() as connection:
      connection.execute(
        "update outbox set attempts = attempts + 1, last_error = ? where id = ?",
        (error[:500], row_id),
      )

  def counts(self) -> dict[str, int]:
    with self._connect() as connection:
      row = connection.execute(
        "select count(*) filter (where sent_at is null) as pendientes, "
        "count(*) filter (where sent_at is not null) as enviados, "
        "count(*) as total from outbox"
      ).fetchone()
    return {"pendientes": row["pendientes"], "enviados": row["enviados"], "total": row["total"]}

  def purge_sent(self, keep_days: int = 7) -> int:
    """Drop delivered rows older than keep_days so the file does not grow forever."""
    cutoff = datetime.now(tz=UTC).timestamp() - keep_days * 86400
    cutoff_iso = datetime.fromtimestamp(cutoff, tz=UTC).isoformat()
    with self._connect() as connection:
      cursor = connection.execute(
        "delete from outbox where sent_at is not null and sent_at < ?", (cutoff_iso,)
      )
      return cursor.rowcount
