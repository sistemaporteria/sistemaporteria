"""Configuration for the ingest API."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

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


@dataclass
class Settings:
  supabase_url: str
  supabase_secret_key: str
  ingest_token: str
  request_timeout: int = 20

  @property
  def rest_url(self) -> str:
    return f"{self.supabase_url.rstrip('/')}/rest/v1"

  def is_configured(self) -> bool:
    return bool(self.supabase_url and self.supabase_secret_key)

  @classmethod
  def from_env(cls) -> Settings:
    return cls(
      supabase_url=_get("SUPABASE_URL"),
      # The secret key bypasses RLS entirely. It lives only here, server-side: the browser
      # and the edge agent never see it.
      supabase_secret_key=_get("SUPABASE_SECRET_KEY"),
      ingest_token=_get("API_INGEST_TOKEN"),
      request_timeout=int(_get("API_REQUEST_TIMEOUT", "20")),
    )


def generate_ingest_token() -> str:
  """A shared secret for the edge agent. Not a user credential: one machine, one token."""
  return secrets.token_urlsafe(32)
