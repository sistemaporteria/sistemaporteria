"""Run the full plate pipeline over a video and report what it actually reads.

Used to decide whether a candidate video is usable as test material: it reports how often a
plate is detected, how wide those plates are in pixels, and what text comes out. The pixel
width is the number that matters — docs/05-evaluacion.md measured the OCR cliff at 60 px.

Usage:
  python scripts/probe_video_alpr.py datasets/raw/video/alpr_video1.mp4 --every 10
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "plate_rules" / "src"))

import cv2
from plate_rules import normalize


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("video", type=Path)
  parser.add_argument("--every", type=int, default=10, help="process one frame every N")
  parser.add_argument("--max-frames", type=int, default=120)
  parser.add_argument("--detector", default="yolo-v9-t-640-license-plate-end2end")
  parser.add_argument("--ocr", default="cct-xs-v2-global-model")
  parser.add_argument("--save-crops", type=Path, default=None)
  args = parser.parse_args()

  from fast_alpr import ALPR

  alpr = ALPR(detector_model=args.detector, ocr_model=args.ocr, ocr_device="cpu")

  capture = cv2.VideoCapture(str(args.video))
  if not capture.isOpened():
    print(f"no se pudo abrir {args.video}", file=sys.stderr)
    return 1

  total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
  widths: list[int] = []
  texts: Counter[str] = Counter()
  frames_with_plate = 0
  processed = 0

  if args.save_crops:
    args.save_crops.mkdir(parents=True, exist_ok=True)

  index = 0
  while processed < args.max_frames:
    ok, frame = capture.read()
    if not ok:
      break
    if index % args.every:
      index += 1
      continue
    index += 1
    processed += 1

    results = alpr.predict(frame)
    if results:
      frames_with_plate += 1
    for order, result in enumerate(results):
      box = result.detection.bounding_box
      width = box.x2 - box.x1
      widths.append(width)
      text = (result.ocr.text if result.ocr else "") or ""
      texts[text.strip().upper()] += 1
      if args.save_crops:
        crop = frame[max(box.y1, 0) : box.y2, max(box.x1, 0) : box.x2]
        if crop.size:
          cv2.imwrite(str(args.save_crops / f"{index:05d}_{order}_{width}px.png"), crop)

  capture.release()

  print(f"\nvideo         : {args.video.name} ({total} frames)")
  print(f"analizados    : {processed} (1 de cada {args.every})")
  print(
    f"con placa     : {frames_with_plate} ({100 * frames_with_plate / max(processed, 1):.0f}%)"
  )
  if widths:
    print(
      f"ancho de placa: min {min(widths)} / mediana {statistics.median(widths):.0f} / "
      f"max {max(widths)} px"
    )
    below = sum(1 for w in widths if w < 60)
    print(f"bajo 60 px    : {below}/{len(widths)} ({100 * below / len(widths):.0f}%)")

  print("\nlecturas mas frecuentes:")
  for text, count in texts.most_common(10):
    result = normalize(text)
    status = "valida-CO" if result.is_valid else (result.rejection_reason or "invalida")
    print(f"  {count:3d}x  {text:12} -> {status}")

  return 0


if __name__ == "__main__":
  raise SystemExit(main())
