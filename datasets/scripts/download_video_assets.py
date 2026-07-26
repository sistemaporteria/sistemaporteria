"""Download public traffic video for testing the vehicle detector.

Uses Roboflow's supervision asset catalog, the only source of real traffic footage that is
free, versioned and downloadable without an account. Everything lands in datasets/raw/video.

Usage:
  python datasets/scripts/download_video_assets.py
  python datasets/scripts/download_video_assets.py --list
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET_DIR = REPO_ROOT / "datasets" / "raw" / "video"

# Assets with vehicles. The rest of the catalog (people, retail, sports) is irrelevant here.
WANTED = ("VEHICLES", "VEHICLES_2")


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--list", action="store_true", help="show the catalog and exit")
  args = parser.parse_args()

  try:
    from supervision.assets import VideoAssets, download_assets
  except ImportError:
    print(
      "supervision is not installed. Run: pip install supervision",
      file=sys.stderr,
    )
    return 1

  if args.list:
    for asset in VideoAssets:
      print(f"{asset.name:24} {asset.value}")
    return 0

  TARGET_DIR.mkdir(parents=True, exist_ok=True)
  for name in WANTED:
    asset = VideoAssets[name]
    print(f"downloading {asset.value} ...")
    # download_assets writes to the current working directory, so move the result.
    downloaded = Path(download_assets(asset))
    destination = TARGET_DIR / downloaded.name
    if downloaded.resolve() != destination.resolve():
      shutil.move(str(downloaded), destination)
    size_mb = destination.stat().st_size / 1_000_000
    print(f"  -> {destination.relative_to(REPO_ROOT)}  ({size_mb:.1f} MB)")

  return 0


if __name__ == "__main__":
  raise SystemExit(main())
