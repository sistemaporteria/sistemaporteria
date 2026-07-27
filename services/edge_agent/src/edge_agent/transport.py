"""Delivery of queued events to the ingest API.

The sink is an interface so the outbox can be drained against the real API, against a log
during development, or against a fake in tests, without the pipeline knowing which.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Protocol

from .config import Config
from .outbox import Outbox

logger = logging.getLogger(__name__)

# Retry with backoff; past this an event stays queued and is reported as stuck rather than
# retried forever, so a permanent failure (bad token, schema drift) becomes visible.
MAX_ATTEMPTS = 8


class Sink(Protocol):
  """Where a delivered event ends up."""

  def send(self, payload: dict[str, Any]) -> None:
    """Deliver one event. Raise on failure so the row stays queued."""
    ...


class LoggingSink:
  """Prints instead of sending. Default while no API exists yet."""

  def send(self, payload: dict[str, Any]) -> None:
    logger.info(
      "EVENTO %s %s placa=%s conf=%s veredicto=%s revision=%s",
      payload.get("camera_id"),
      payload.get("direction"),
      payload.get("plate_read"),
      payload.get("ocr_confidence"),
      payload.get("verdict"),
      payload.get("needs_review"),
    )


class HttpSink:
  """POSTs to services/api."""

  def __init__(self, base_url: str, token: str = "", timeout: int = 20) -> None:
    self.url = f"{base_url.rstrip('/')}/events"
    self.token = token
    self.timeout = timeout

  def send(self, payload: dict[str, Any]) -> None:
    headers = {"Content-Type": "application/json", "User-Agent": "porteria-edge-agent/1.0"}
    if self.token:
      headers["Authorization"] = f"Bearer {self.token}"
    request = urllib.request.Request(
      self.url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
    )
    with urllib.request.urlopen(request, timeout=self.timeout) as response:
      if response.status >= 300:
        raise RuntimeError(f"HTTP {response.status}")


class Synchronizer:
  """Drains the outbox into a sink."""

  def __init__(self, outbox: Outbox, sink: Sink) -> None:
    self.outbox = outbox
    self.sink = sink

  def drain(self, limit: int = 50) -> tuple[int, int]:
    """Try to deliver pending events. Returns (delivered, failed)."""
    delivered = failed = 0
    for row in self.outbox.pending(limit):
      if row.attempts >= MAX_ATTEMPTS:
        continue
      try:
        self.sink.send(row.payload)
      except (urllib.error.URLError, OSError, RuntimeError) as error:
        self.outbox.mark_failed(row.id, str(error))
        failed += 1
        continue
      self.outbox.mark_sent(row.id)
      delivered += 1
    return delivered, failed

  def stuck(self) -> list[int]:
    """Rows that exhausted their retries and need a human to look."""
    return [row.id for row in self.outbox.pending(500) if row.attempts >= MAX_ATTEMPTS]


def build_sink(config: Config) -> Sink:
  """Pick a sink: the API when configured, otherwise log only."""
  if config.api_ingest_token:
    return HttpSink(config.api_base_url, config.api_ingest_token)
  logger.warning("sin API_INGEST_TOKEN: los eventos solo se registran en el log")
  return LoggingSink()
