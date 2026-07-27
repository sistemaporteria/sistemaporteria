"""Download video with legible license plates for testing plate detection and OCR.

Generic traffic footage does not work: it is filmed to *count* vehicles, not to *read*
plates, so plates come out around 10 px wide. ALPR project repositories do commit usable
material, because they need it for their own demos.

Source: https://github.com/BarthPaleologue/ALPR (MIT). Plates are Portuguese and French, so
this material exercises detection and raw character accuracy but cannot validate the
Colombian domain layer. See docs/05-evaluacion.md.

Usage:
  python datasets/scripts/download_alpr_videos.py
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET_DIR = REPO_ROOT / "datasets" / "raw" / "video"
BASE_URL = "https://raw.githubusercontent.com/BarthPaleologue/ALPR/main"

FILES = {
  "alpr_video1.mp4": "warpPerspective/video1.mp4",
  "alpr_test.mp4": "alprLib/testVideos/test.mp4",
  "alpr_video.mp4": "warpPerspective/video.mp4",
}


def main() -> int:
  TARGET_DIR.mkdir(parents=True, exist_ok=True)
  failures = 0

  for name, path in FILES.items():
    destination = TARGET_DIR / name
    if destination.exists():
      print(f"ya existe: {name}")
      continue
    try:
      print(f"descargando {name} ...")
      urllib.request.urlretrieve(f"{BASE_URL}/{path}", destination)
      size_mb = destination.stat().st_size / 1e6
      print(f"  -> {destination.relative_to(REPO_ROOT)} ({size_mb:.1f} MB)")
    except OSError as error:
      print(f"  fallo: {error}", file=sys.stderr)
      failures += 1

  return 1 if failures else 0


if __name__ == "__main__":
  raise SystemExit(main())
