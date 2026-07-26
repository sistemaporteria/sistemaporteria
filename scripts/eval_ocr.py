"""Measure OCR accuracy against synthetic Colombian plates.

Answers the two questions the installation depends on:
  1. How degraded can a plate get before the OCR fails? (each sweep isolates one variable)
  2. How much does the domain layer add on top of the raw model? (raw vs normalized columns)

Usage:
  python scripts/eval_ocr.py                       # every sweep, 20 plates each
  python scripts/eval_ocr.py --sweep width yaw     # only these
  python scripts/eval_ocr.py --mixed --samples 200 # realistic mixed set, no sweep
"""

from __future__ import annotations

import argparse
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "plate_rules" / "src"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "plate_synth" / "src"))

import random

import numpy as np
from PIL import Image
from plate_rules import normalize
from plate_synth import SWEEPS, Degradation, apply, random_spec, render

DEFAULT_MODEL = "cct-xs-v2-global-model"


@dataclass
class Score:
  """Accuracy of one variant, before and after the domain layer."""

  variant: str
  total: int
  raw_exact: int
  normalized_exact: int
  char_accuracy: float
  rejected: int

  @property
  def raw_pct(self) -> float:
    return 100 * self.raw_exact / self.total if self.total else 0.0

  @property
  def normalized_pct(self) -> float:
    return 100 * self.normalized_exact / self.total if self.total else 0.0


def character_accuracy(truth: str, prediction: str) -> float:
  """Fraction of correct characters, penalizing length mismatch."""
  if not truth:
    return 0.0
  matched = sum(1 for a, b in zip(truth, prediction, strict=False) if a == b)
  return matched / max(len(truth), len(prediction))


def evaluate(recognizer, specs, degradations, label: str) -> list[Score]:
  scores: list[Score] = []
  for degradation in degradations:
    # The v2 global models are RGB; passing grayscale arrays makes the batch collapse into a
    # single multi-channel image and the ONNX shape check fails.
    images = [np.array(apply(render(spec), degradation).convert("RGB")) for spec in specs]
    predictions = recognizer.run(images)

    raw_exact = normalized_exact = rejected = 0
    char_scores: list[float] = []

    for spec, prediction in zip(specs, predictions, strict=True):
      predicted = (prediction.plate or "").upper().strip()
      truth = spec.text
      if predicted == truth:
        raw_exact += 1
      char_scores.append(character_accuracy(truth, predicted))

      result = normalize(predicted)
      if not result.is_valid:
        rejected += 1
      elif result.text == truth:
        normalized_exact += 1

    scores.append(
      Score(
        variant=degradation.label() if label == "mixed" else _short(degradation, label),
        total=len(specs),
        raw_exact=raw_exact,
        normalized_exact=normalized_exact,
        char_accuracy=statistics.fmean(char_scores) if char_scores else 0.0,
        rejected=rejected,
      )
    )
  return scores


def _short(degradation, sweep: str) -> str:
  field = {
    "width": ("target_width", "px"),
    "motion_blur": ("motion_blur", "k"),
    "defocus": ("defocus_blur", "sigma"),
    "yaw": ("yaw_deg", "deg"),
    "pitch": ("pitch_deg", "deg"),
    "noise": ("noise_sigma", "sigma"),
    "jpeg": ("jpeg_quality", "q"),
  }.get(sweep)
  if field is None:
    return f"br{degradation.brightness:g}/ct{degradation.contrast:g}"
  value = getattr(degradation, field[0])
  return f"{value:g} {field[1]}"


def print_table(sweep: str, scores: list[Score], baseline: Score | None = None) -> None:
  """Print a sweep, expressed relative to the undegraded baseline when available.

  The synthetic renderer has a known systematic error floor (Arial Bold draws `I` as a bare
  bar, confusable with T/1/J, where the real plate typeface disambiguates). Reporting the
  delta against the same plates undegraded cancels that constant offset, so the curve shows
  the effect of the degradation rather than the artifact.
  """
  print(f"\n=== {sweep} ===")
  header = (
    f"{'variante':>14} | {'OCR crudo':>10} | {'+ dominio':>10} | {'car acc':>8} | {'rechaz':>7}"
  )
  if baseline is not None:
    header += f" | {'vs base':>8}"
  print(header)
  print("-" * (len(header) + 2))
  for score in scores:
    row = (
      f"{score.variant:>14} | {score.raw_pct:9.1f}% | {score.normalized_pct:9.1f}% "
      f"| {100 * score.char_accuracy:7.1f}% | {score.rejected:4d}/{score.total}"
    )
    if baseline is not None:
      row += f" | {score.normalized_pct - baseline.normalized_pct:+7.1f}%"
    print(row)


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--model", default=DEFAULT_MODEL)
  parser.add_argument("--samples", type=int, default=20)
  parser.add_argument("--sweep", nargs="*", default=None, help="sweeps to run")
  parser.add_argument("--mixed", action="store_true", help="realistic mixed set instead")
  parser.add_argument("--seed", type=int, default=20260725)
  parser.add_argument("--save-samples", type=Path, default=None)
  args = parser.parse_args()

  from fast_plate_ocr import LicensePlateRecognizer

  rng = random.Random(args.seed)
  specs = [random_spec(rng) for _ in range(args.samples)]

  print(f"modelo: {args.model}")
  print(f"placas: {len(specs)} (mismas en todas las variantes)")
  recognizer = LicensePlateRecognizer(args.model, device="cpu")

  if args.mixed:
    degradations = [
      Degradation(
        target_width=rng.choice([90, 110, 130, 160, 200]),
        motion_blur=rng.choice([0, 0, 3, 5, 7]),
        defocus_blur=rng.choice([0.0, 0.0, 0.5, 1.0, 1.5]),
        yaw_deg=rng.uniform(-25, 25),
        pitch_deg=rng.uniform(0, 20),
        brightness=rng.uniform(0.5, 1.5),
        contrast=rng.uniform(0.6, 1.1),
        noise_sigma=rng.uniform(0, 12),
        jpeg_quality=rng.choice([90, 75, 60, 45]),
      )
    ]
    print_table("mixed", evaluate(recognizer, specs, degradations, "mixed"))
    return 0

  selected = args.sweep or list(SWEEPS)

  baseline = evaluate(recognizer, specs, [Degradation(target_width=280)], "baseline")[0]
  print(
    f"baseline sin degradar (280 px): crudo {baseline.raw_pct:.1f}% | "
    f"+dominio {baseline.normalized_pct:.1f}% | car {100 * baseline.char_accuracy:.1f}%"
  )

  for sweep in selected:
    if sweep not in SWEEPS:
      print(f"sweep desconocido: {sweep}", file=sys.stderr)
      return 1
    print_table(sweep, evaluate(recognizer, specs, SWEEPS[sweep], sweep), baseline)

  if args.save_samples:
    args.save_samples.mkdir(parents=True, exist_ok=True)
    for sweep in selected:
      for degradation in SWEEPS[sweep]:
        image: Image.Image = apply(render(specs[0]), degradation)
        image.save(args.save_samples / f"{sweep}_{degradation.label()}.png")

  return 0


if __name__ == "__main__":
  raise SystemExit(main())
