"""Live window showing the plate pipeline as it runs, frame by frame.

Two layers are drawn on top of each other so the difference between them is visible:
the model's raw output (plate box + OCR text, from fast_alpr) and the domain verdict
(`plate_rules`: normalization, mask, category, cross-check). A reading the model is
confident about can still be rejected by the domain — that is the point of the panel.

Usage:
  python scripts/live_view.py datasets/raw/video/alpr_video1.mp4
  python scripts/live_view.py rtsp://localhost:8554/entrada --detector-label car

Keys: q or ESC to quit, space to pause, s to save the current frame. The title bar's X
closes it too.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter, deque
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "plate_rules" / "src"))

import cv2
from plate_rules import identify

PANEL_WIDTH = 380
FONT = cv2.FONT_HERSHEY_SIMPLEX
WHITE = (255, 255, 255)
GREY = (160, 160, 160)
GREEN = (120, 220, 120)
AMBER = (80, 190, 245)
RED = (110, 110, 240)

VERDICT_COLORS = {
  "confirmed": GREEN,
  "consistent": GREEN,
  "conflict": AMBER,
  "unrecognized_pattern": RED,
  "invalid": RED,
}


def verdict_color(verdict: str) -> tuple[int, int, int]:
  return VERDICT_COLORS.get(verdict, GREY)


def plate_confidence(ocr_confidence: float | list[float] | None) -> float:
  """Collapse the OCR's per-character scores into one plate-level number.

  The domain expects a single confidence, but the OCR returns one score per character
  (plus padding tokens that score ~1.0). The minimum is the conservative choice: a plate
  is only as trustworthy as its weakest character, and it ignores the padding.
  """
  if ocr_confidence is None:
    return 0.0
  if isinstance(ocr_confidence, (int, float)):
    return float(ocr_confidence)
  return min(ocr_confidence) if ocr_confidence else 0.0


def draw_panel(
  frame: cv2.typing.MatLike,
  identification: object | None,
  raw_text: str,
  raw_confidence: float,
  stats: dict[str, object],
) -> cv2.typing.MatLike:
  height = frame.shape[0]
  panel = cv2.copyMakeBorder(
    frame, 0, 0, 0, PANEL_WIDTH, cv2.BORDER_CONSTANT, value=(24, 24, 24)
  )
  x = frame.shape[1] + 20
  y = 40

  def line(text: str, color=WHITE, size: float = 0.55, step: int = 26) -> None:
    nonlocal y
    cv2.putText(panel, text, (x, y), FONT, size, color, 1, cv2.LINE_AA)
    y += step

  line("MODELO (YOLOv9 + OCR)", GREY, 0.5)
  line(raw_text or "sin lectura", WHITE if raw_text else GREY, 0.9, 34)
  line(f"confianza min {raw_confidence:.2f}" if raw_text else "", GREY, 0.5, 32)

  y += 6
  cv2.line(panel, (x, y), (x + PANEL_WIDTH - 40, y), (70, 70, 70), 1)
  y += 30

  line("DOMINIO (plate_rules)", GREY, 0.5)
  if identification is None:
    line("--", GREY, 0.9, 40)
  else:
    plate = identification.plate
    color = verdict_color(identification.verdict.value)
    line(plate.text or "-", color, 0.9, 34)
    line(f"mascara     {plate.mask or '-'}", GREY, 0.5)
    line(f"correcciones {plate.corrections}", GREY, 0.5)
    line(f"veredicto   {identification.verdict.value}", color, 0.5)
    line(f"tipo        {identification.vehicle_class.value}", GREY, 0.5)
    line(f"servicio    {identification.service_type.value}", GREY, 0.5)
    if not plate.is_valid and plate.rejection_reason:
      line(f"rechazo     {plate.rejection_reason}", RED, 0.45)

  y = height - 90
  line(f"frames      {stats['frames']}", GREY, 0.5)
  line(f"con placa   {stats['hits']}  ({stats['hit_rate']}%)", GREY, 0.5)
  line(f"fps         {stats['fps']}", GREY, 0.5)
  return panel


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("source", help="video file or RTSP URL")
  parser.add_argument(
    "--detector-label", default=None, help="car / motorcycle, for cross-check"
  )
  parser.add_argument("--every", type=int, default=2, help="run the model every N frames")
  parser.add_argument("--width", type=int, default=960, help="display width")
  parser.add_argument("--detector", default="yolo-v9-t-640-license-plate-end2end")
  parser.add_argument("--ocr", default="cct-xs-v2-global-model")
  args = parser.parse_args()

  from fast_alpr import ALPR

  print("cargando modelos...")
  alpr = ALPR(detector_model=args.detector, ocr_model=args.ocr, ocr_device="cpu")

  capture = cv2.VideoCapture(args.source)
  if not capture.isOpened():
    print(f"no se pudo abrir {args.source}", file=sys.stderr)
    return 1

  window = "Porteria UNAL - deteccion de placa en vivo"
  cv2.namedWindow(window, cv2.WINDOW_NORMAL)
  cv2.resizeWindow(window, args.width + PANEL_WIDTH, int(args.width * 0.62))

  seen: Counter[str] = Counter()
  recent = deque(maxlen=30)
  frames = 0
  hits = 0
  index = 0
  paused = False
  last_annotated = None
  last_identification = None
  last_raw = ""
  last_confidence = 0.0

  while True:
    if not paused:
      ok, frame = capture.read()
      if not ok:
        capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
        continue

      scale = args.width / frame.shape[1]
      frame = cv2.resize(frame, (args.width, int(frame.shape[0] * scale)))

      if index % args.every == 0:
        started = time.perf_counter()
        results = alpr.predict(frame)
        recent.append(time.perf_counter() - started)
        frames += 1

        if results:
          hits += 1
          best = max(
            results, key=lambda r: plate_confidence(r.ocr.confidence if r.ocr else None)
          )
          last_raw = ((best.ocr.text if best.ocr else "") or "").strip().upper()
          last_confidence = plate_confidence(best.ocr.confidence if best.ocr else None)
          last_identification = identify(
            last_raw,
            ocr_confidence=last_confidence,
            detector_label=args.detector_label,
          )
          if last_identification.plate.text:
            seen[last_identification.plate.text] += 1
        else:
          last_raw = ""
          last_confidence = 0.0
          last_identification = None

        last_annotated = alpr.draw_predictions(frame).image
      index += 1

    canvas = last_annotated if last_annotated is not None else frame
    elapsed = sum(recent) / len(recent) if recent else 0.0
    stats = {
      "frames": frames,
      "hits": hits,
      "hit_rate": round(100 * hits / max(frames, 1)),
      "fps": round(1 / elapsed, 1) if elapsed else "-",
    }
    cv2.imshow(
      window, draw_panel(canvas, last_identification, last_raw, last_confidence, stats)
    )

    key = cv2.waitKey(1) & 0xFF
    if key in (ord("q"), 27):
      break
    # The title bar's X is not a key event: HighGUI destroys the window but the loop would
    # keep running and imshow would just recreate it. Ask the window whether it still exists.
    if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
      break
    if key == ord(" "):
      paused = not paused
    if key == ord("s"):
      out = REPO_ROOT / f"frame_{index:05d}.png"
      cv2.imwrite(str(out), canvas)
      print(f"guardado {out}")

  capture.release()
  cv2.destroyAllWindows()

  print(f"\nframes analizados: {frames}, con placa: {hits} ({stats['hit_rate']}%)")
  print("placas validas mas vistas:")
  for text, count in seen.most_common(8):
    print(f"  {count:3d}x  {text}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
