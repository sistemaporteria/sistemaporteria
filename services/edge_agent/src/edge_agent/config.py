"""Configuration, read from the environment or .env.local.

Every threshold lives here with the reasoning behind its default, so no magic numbers end up
buried in the pipeline.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .models import Direction

REPO_ROOT = Path(__file__).resolve().parents[4]
ENV_FILE = REPO_ROOT / ".env.local"


def _load_env_file() -> dict[str, str]:
  values: dict[str, str] = {}
  if not ENV_FILE.exists():
    return values
  for line in ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
      continue
    key, _, value = line.partition("=")
    values[key.strip()] = value.strip()
  return values


def _get(key: str, default: str = "") -> str:
  return os.environ.get(key) or _load_env_file().get(key, default)


def parse_camera_directions(raw: str) -> dict[str, Direction]:
  """Parse `camera:in,other:out` into a lookup.

  Direction comes from the camera, not from motion analysis: the two lanes are physically
  separate, so the geometry already answers the question. See docs/00-arquitectura.md.
  """
  mapping: dict[str, Direction] = {}
  for chunk in raw.split(","):
    chunk = chunk.strip()
    if not chunk:
      continue
    name, _, direction = chunk.partition(":")
    name, direction = name.strip(), direction.strip().lower()
    if not name or direction not in ("in", "out"):
      raise ValueError(f"entrada invalida en CAMERA_DIRECTIONS: {chunk!r}")
    mapping[name] = Direction(direction)
  return mapping


@dataclass
class Config:
  mqtt_host: str = "localhost"
  mqtt_port: int = 1883
  mqtt_topic_prefix: str = "frigate"

  camera_directions: dict[str, Direction] = field(default_factory=dict)

  api_base_url: str = "http://localhost:8000"
  api_ingest_token: str = ""
  outbox_path: Path = REPO_ROOT / "services" / "edge_agent" / "outbox.db"

  # Two readings of the same plate on the same camera closer than this are the same passage:
  # a vehicle that stops or reverses at the barrier produces several Frigate tracks.
  # Mirrors the 90 s exclusion constraint in the database.
  dedup_window_seconds: int = 90

  # Below this, the aggregated reading goes to the review queue instead of being trusted.
  # Deliberately permissive: an event is never dropped, only flagged.
  min_confidence: float = 0.55

  # Frigate's own OCR filter is set low on purpose so the domain layer can judge; this is the
  # floor for a reading to even enter the vote.
  min_reading_confidence: float = 0.40

  # Estimating plate color requires fetching the snapshot and re-detecting the plate. Off by
  # default: it costs an HTTP round trip per event and the color thresholds are uncalibrated.
  enable_color_estimation: bool = False
  frigate_api_url: str = "http://localhost:5000"

  @classmethod
  def from_env(cls) -> Config:
    return cls(
      mqtt_host=_get("MQTT_HOST", "localhost"),
      mqtt_port=int(_get("MQTT_PORT", "1883")),
      mqtt_topic_prefix=_get("MQTT_TOPIC_PREFIX", "frigate"),
      camera_directions=parse_camera_directions(
        _get("CAMERA_DIRECTIONS", "porteria_entrada:in,porteria_salida:out")
      ),
      api_base_url=_get("API_BASE_URL", "http://localhost:8000"),
      api_ingest_token=_get("API_INGEST_TOKEN", ""),
      outbox_path=Path(_get("OUTBOX_PATH", str(cls.outbox_path))),
      dedup_window_seconds=int(_get("DEDUP_WINDOW_SECONDS", "90")),
      enable_color_estimation=_get("ENABLE_COLOR_ESTIMATION", "").lower()
      in ("1", "true", "yes"),
      frigate_api_url=_get("FRIGATE_API_URL", "http://localhost:5000"),
    )
