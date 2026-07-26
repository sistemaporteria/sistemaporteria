"""Synthetic Colombian license plate renderer.

No public dataset contains Colombian plates with character-level ground truth, so the OCR
and the domain rules are evaluated against plates rendered here. Synthetic data has a
decisive advantage for measurement: the label is exact and the degradation is a controlled
variable, which is what makes it possible to answer "at what plate width does OCR break?"
— the question that determines the camera spec. See docs/05-evaluacion.md.
"""

from __future__ import annotations

import random
import string
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from plate_rules import PlateCategory, PlateColor

# Physical proportions. CALIBRAR: car plates are 330x160 mm per the national standard;
# the motorcycle ratio is an estimate and must be measured on real plates.
CAR_ASPECT = 330 / 160
MOTO_ASPECT = 1.35

RGB = tuple[int, int, int]

BACKGROUND_RGB: dict[PlateColor, RGB] = {
  PlateColor.YELLOW: (247, 200, 20),
  PlateColor.WHITE: (245, 245, 242),
  PlateColor.GREEN: (0, 110, 60),
  PlateColor.RED: (190, 30, 35),
  PlateColor.BLACK: (25, 25, 25),
}

FOREGROUND_RGB: dict[PlateColor, RGB] = {
  PlateColor.YELLOW: (20, 20, 20),
  PlateColor.WHITE: (20, 20, 20),
  PlateColor.GREEN: (250, 250, 250),
  PlateColor.RED: (20, 20, 20),
  PlateColor.BLACK: (240, 200, 40),
}

# Candidate fonts, most plate-like first. Colombian plates use a condensed bold sans.
FONT_CANDIDATES = (
  "C:/Windows/Fonts/arialbd.ttf",
  "C:/Windows/Fonts/seguisb.ttf",
  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


@dataclass(frozen=True)
class PlateSpec:
  """A plate to render: its text, category, colors and geometry."""

  text: str
  category: PlateCategory
  background: PlateColor
  aspect: float
  bottom_label: str = "COLOMBIA"


def _load_font(size: int) -> ImageFont.FreeTypeFont:
  for candidate in FONT_CANDIDATES:
    if Path(candidate).exists():
      return ImageFont.truetype(candidate, size)
  try:
    import matplotlib

    fallback = Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans-Bold.ttf"
    if fallback.exists():
      return ImageFont.truetype(str(fallback), size)
  except ImportError:
    pass
  raise RuntimeError("no usable TrueType font found; install matplotlib or run on Windows")


def _fit_font(
  draw: ImageDraw.ImageDraw, text: str, max_width: int, max_height: int
) -> tuple[ImageFont.FreeTypeFont, tuple[int, int, int, int]]:
  """Largest font whose rendered text fits both bounds.

  Sizing on height alone overflows the plate horizontally, because the character count
  varies between formats and the digit group is separated by a wide gap.
  """
  size = max_height
  while size > 6:
    font = _load_font(size)
    box = draw.textbbox((0, 0), text, font=font)
    if box[2] - box[0] <= max_width and box[3] - box[1] <= max_height:
      return font, box
    size -= 1
  font = _load_font(6)
  return font, draw.textbbox((0, 0), text, font=font)


def random_spec(rng: random.Random, category: PlateCategory | None = None) -> PlateSpec:
  """Draw a random plate that is valid under the national catalog."""
  letters = string.ascii_uppercase
  digits = string.digits

  def pick(pool: str, n: int) -> str:
    return "".join(rng.choice(pool) for _ in range(n))

  category = (
    category
    or rng.choices(
      [
        PlateCategory.PRIVATE_CAR,
        PlateCategory.MOTORCYCLE,
        PlateCategory.PUBLIC_CAR,
        PlateCategory.OFFICIAL_CAR,
      ],
      weights=[0.60, 0.25, 0.12, 0.03],
    )[0]
  )

  if category is PlateCategory.MOTORCYCLE:
    return PlateSpec(
      text=pick(letters, 3) + pick(digits, 2) + pick(letters, 1),
      category=category,
      background=PlateColor.YELLOW,
      aspect=MOTO_ASPECT,
    )

  background = {
    PlateCategory.PRIVATE_CAR: PlateColor.YELLOW,
    PlateCategory.PUBLIC_CAR: PlateColor.WHITE,
    PlateCategory.OFFICIAL_CAR: PlateColor.GREEN,
  }[category]
  prefix = (
    "O" + pick(letters, 2) if category is PlateCategory.OFFICIAL_CAR else pick(letters, 3)
  )
  return PlateSpec(
    text=prefix + pick(digits, 3),
    category=category,
    background=background,
    aspect=CAR_ASPECT,
  )


def render(spec: PlateSpec, width: int = 660) -> Image.Image:
  """Draw a clean, undegraded plate at the requested pixel width."""
  height = int(round(width / spec.aspect))
  bg = BACKGROUND_RGB[spec.background]
  fg = FOREGROUND_RGB[spec.background]

  image = Image.new("RGB", (width, height), bg)
  draw = ImageDraw.Draw(image)

  border = max(2, width // 110)
  draw.rectangle([0, 0, width - 1, height - 1], outline=fg, width=border)

  # The bottom band must stay small relative to the characters. An oversized band makes the
  # OCR read into it and append phantom characters — measured on motorcycle plates, where
  # an earlier 34% band produced readings like DOF38U -> DOF38UG.
  is_moto = spec.aspect < 1.8
  main_area_bottom = int(height * (0.80 if is_moto else 0.76))
  inset = border * 2 + int(width * 0.04)

  # Colombian plates separate the letter group from the digit group with the ministry
  # emblem; a wide space reproduces the layout the OCR actually sees.
  label = f"{spec.text[:3]}  {spec.text[3:]}"
  font, box = _fit_font(
    draw, label, width - inset * 2, int((main_area_bottom - border * 2) * 0.88)
  )
  draw.text(
    (
      (width - (box[2] - box[0])) / 2 - box[0],
      (main_area_bottom - (box[3] - box[1])) / 2 - box[1],
    ),
    label,
    font=font,
    fill=fg,
  )

  band_height = height - main_area_bottom
  small, small_box = _fit_font(
    draw, spec.bottom_label, width - inset * 2, int(band_height * 0.55)
  )
  draw.text(
    (
      (width - (small_box[2] - small_box[0])) / 2 - small_box[0],
      main_area_bottom + (band_height - (small_box[3] - small_box[1])) / 2 - small_box[1],
    ),
    spec.bottom_label,
    font=small,
    fill=fg,
  )

  return image
