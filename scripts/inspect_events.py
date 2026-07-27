"""Read back what actually landed in the database.

Uses the server-side secret key from .env.local, which bypasses RLS, so it shows the real
rows rather than what an anonymous client would see. The key is never printed.

Usage:
  python scripts/inspect_events.py
  python scripts/inspect_events.py --purge-demo   # delete the demo rows again
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "plate_rules" / "src"))
sys.path.insert(0, str(REPO_ROOT / "services" / "api" / "src"))

import httpx  # noqa: E402

from porteria_api.config import Settings  # noqa: E402

DEMO_PLATES = ("KEM018", "HCR605")


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--purge-demo", action="store_true")
  args = parser.parse_args()

  settings = Settings.from_env()
  if not settings.is_configured():
    print("falta SUPABASE_URL o SUPABASE_SECRET_KEY en .env.local", file=sys.stderr)
    return 1

  headers = {
    "apikey": settings.supabase_secret_key,
    "Authorization": f"Bearer {settings.supabase_secret_key}",
    "User-Agent": "porteria-inspect/1.0",
  }

  with httpx.Client(base_url=settings.rest_url, headers=headers, timeout=30) as client:
    if args.purge_demo:
      response = client.delete("/access_events", params={"frigate_event_id": "like.1785*"})
      print(f"borrado HTTP {response.status_code}")
      return 0

    print("=== access_events ===")
    response = client.get(
      "/access_events",
      params={
        "select": "occurred_at,camera_id,direction,plate_read,raw_read,verdict,"
        "detected_class,plate_class,review_status,frames_agreed,frames_total",
        "order": "occurred_at.asc",
      },
    )
    rows = response.json()
    for row in rows:
      print(
        f"  {row['occurred_at'][:19]}  {row['camera_id']:17} {row['direction']:3} "
        f"placa={str(row['plate_read'] or '-'):8} crudo={str(row['raw_read'] or '-'):8} "
        f"{row['verdict']:20} {row['review_status']}"
      )
    print(f"  total: {len(rows)}")

    print("\n=== parking_sessions ===")
    response = client.get(
      "/parking_sessions",
      params={
        "select": "plate,entered_at,exited_at,duration,is_open",
        "order": "entered_at.asc",
      },
    )
    for row in response.json():
      estado = "ABIERTA" if row["is_open"] else f"cerrada ({row['duration']})"
      print(f"  {row['plate']:8} entro={row['entered_at'][:19]}  {estado}")

  return 0


if __name__ == "__main__":
  raise SystemExit(main())
