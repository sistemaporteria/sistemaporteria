"""Thin PostgREST client.

Only the few calls the ingest path needs, so the API keeps no ORM and no schema duplication.
Postgres constraint violations are translated into named outcomes here, because the whole
idempotency story depends on telling them apart.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Postgres SQLSTATEs the ingest path expects and must not treat as failures.
UNIQUE_VIOLATION = "23505"
EXCLUSION_VIOLATION = "23P01"


class SupabaseError(RuntimeError):
  """A call failed for a reason the caller cannot resolve."""


@dataclass(frozen=True)
class InsertOutcome:
  """Why an insert did or did not create a row."""

  created: bool
  row: dict[str, Any] | None
  reason: str | None = None


class SupabaseClient:
  def __init__(self, rest_url: str, secret_key: str, timeout: int = 20) -> None:
    self.rest_url = rest_url.rstrip("/")
    self._headers = {
      "apikey": secret_key,
      "Authorization": f"Bearer {secret_key}",
      "Content-Type": "application/json",
      "User-Agent": "porteria-api/1.0",
    }
    self._client = httpx.Client(timeout=timeout)

  def close(self) -> None:
    self._client.close()

  def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
    try:
      return self._client.request(
        method,
        f"{self.rest_url}/{path}",
        headers={**self._headers, **kwargs.pop("headers", {})},
        **kwargs,
      )
    except httpx.HTTPError as error:
      raise SupabaseError(f"fallo de red hacia Supabase: {error}") from error

  def ping(self) -> bool:
    """Cheap liveness check that does not depend on any row existing."""
    try:
      response = self._request("GET", "cameras", params={"select": "id", "limit": "1"})
    except SupabaseError:
      return False
    return response.status_code < 400

  def find_vehicle_by_plate(self, plate: str) -> dict[str, Any] | None:
    response = self._request(
      "GET",
      "vehicles",
      params={"select": "id,plate,owner_id,class,active", "plate": f"eq.{plate}", "limit": "1"},
    )
    if response.status_code >= 400:
      raise SupabaseError(f"consulta de vehiculo fallo: {response.status_code} {response.text}")
    rows = response.json()
    return rows[0] if rows else None

  def insert_access_event(self, payload: dict[str, Any]) -> InsertOutcome:
    """Insert one event, distinguishing the two benign conflicts from real errors.

    - unique violation on frigate_event_id: the agent re-sent after a network outage, so the
      passage is already recorded. Benign, and the agent must stop retrying.
    - exclusion violation: the same plate on the same camera within 90 s. A vehicle that
      stops or reverses at the barrier produces several tracks; only one is a real passage.
    """
    response = self._request(
      "POST",
      "access_events",
      json=payload,
      headers={"Prefer": "return=representation"},
    )

    if response.status_code < 300:
      rows = response.json()
      return InsertOutcome(created=True, row=rows[0] if rows else None)

    code = _error_code(response)
    if code == UNIQUE_VIOLATION:
      return InsertOutcome(False, None, "already_recorded")
    if code == EXCLUSION_VIOLATION:
      return InsertOutcome(False, None, "duplicate")

    raise SupabaseError(f"insercion fallo: {response.status_code} {response.text[:400]}")


def _error_code(response: httpx.Response) -> str | None:
  try:
    return response.json().get("code")
  except ValueError:
    return None
