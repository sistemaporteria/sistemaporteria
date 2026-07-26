"""Build labelled synthetic plate test sets on disk."""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path

from plate_rules import PlateCategory

from .degrade import SWEEPS, Degradation, apply
from .render import PlateSpec, random_spec, render


@dataclass(frozen=True)
class Sample:
  """One generated image and everything needed to score a prediction against it."""

  filename: str
  text: str
  category: str
  background: str
  sweep: str
  variant: str
  target_width: int


def build(
  out_dir: Path,
  *,
  samples_per_variant: int = 25,
  sweeps: tuple[str, ...] | None = None,
  seed: int = 20260725,
) -> list[Sample]:
  """Generate the sweeps and write images plus a ground-truth manifest.

  The same plate texts are reused across every variant of a sweep, so differences in the
  results come from the degradation and not from having drawn easier plates.
  """
  rng = random.Random(seed)
  out_dir.mkdir(parents=True, exist_ok=True)
  images_dir = out_dir / "images"
  images_dir.mkdir(exist_ok=True)

  specs: list[PlateSpec] = [random_spec(rng) for _ in range(samples_per_variant)]
  selected = sweeps or tuple(SWEEPS)
  manifest: list[Sample] = []

  for sweep_name in selected:
    for degradation in SWEEPS[sweep_name]:
      for index, spec in enumerate(specs):
        image = apply(render(spec), degradation)
        filename = f"{sweep_name}/{degradation.label()}/{index:03d}_{spec.text}.png"
        path = images_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
        manifest.append(
          Sample(
            filename=filename,
            text=spec.text,
            category=spec.category.value,
            background=spec.background.value,
            sweep=sweep_name,
            variant=degradation.label(),
            target_width=degradation.target_width,
          )
        )

  (out_dir / "manifest.json").write_text(
    json.dumps([asdict(s) for s in manifest], indent=2), encoding="utf-8"
  )
  return manifest


def build_flat(out_dir: Path, *, count: int = 200, seed: int = 20260725) -> list[Sample]:
  """Generate a realistic mixed set: no sweep, random degradations within sane ranges.

  This is the set that stands in for a day at the gate, as opposed to the sweeps, which
  isolate one variable each.
  """
  rng = random.Random(seed)
  out_dir.mkdir(parents=True, exist_ok=True)
  images_dir = out_dir / "images"
  images_dir.mkdir(exist_ok=True)

  manifest: list[Sample] = []
  for index in range(count):
    spec = random_spec(rng)
    degradation = Degradation(
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
    image = apply(render(spec), degradation)
    filename = f"{index:04d}_{spec.text}.png"
    image.save(images_dir / filename)
    manifest.append(
      Sample(
        filename=filename,
        text=spec.text,
        category=spec.category.value,
        background=spec.background.value,
        sweep="mixed",
        variant=degradation.label(),
        target_width=degradation.target_width,
      )
    )

  (out_dir / "manifest.json").write_text(
    json.dumps([asdict(s) for s in manifest], indent=2), encoding="utf-8"
  )
  return manifest


__all__ = ["Sample", "build", "build_flat", "PlateCategory"]
