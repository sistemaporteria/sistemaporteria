"""Colombian plate pattern catalog.

A pattern maps a character mask to the set of plate categories compatible with it. Most
masks are ambiguous on purpose: `LLLNNN` alone cannot tell a private car from a taxi. The
ambiguity is resolved later by `classify`, using plate color. See docs/02-placas-colombia.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .types import PlateCategory, PlateColor, ServiceType, VehicleClass

LETTER = "L"
DIGIT = "N"


@dataclass(frozen=True)
class PlatePattern:
  """A recognizable plate shape.

  `mask` uses L for letter and N for digit, and drives OCR coercion in `normalize`.
  `prefix` restricts the pattern to plates starting with a specific character; it never
  identifies a category on its own, since ordinary plates may share those prefixes.
  `strict` forbids OCR coercion into this pattern.

  Why `strict` exists: a pattern's false-positive risk grows with how many strings can be
  coerced into it. `NNNNNN` is the worst case — nearly every letter has a digit lookalike, so
  almost any six-character reading collapses into it. Measured on real (Portuguese) footage,
  the reading `66TE67` was coerced into `667367` and accepted as a police plate. Patterns
  that permissive must match exactly or not at all.
  """

  name: str
  mask: str
  categories: tuple[PlateCategory, ...]
  prefix: str | None = None
  strict: bool = False

  @property
  def length(self) -> int:
    return len(self.mask)

  @property
  def regex(self) -> re.Pattern[str]:
    body = "".join("[A-Z]" if slot == LETTER else "[0-9]" for slot in self.mask)
    return re.compile(f"^{body}$")

  def matches(self, text: str) -> bool:
    if self.prefix and not text.startswith(self.prefix):
      return False
    return bool(self.regex.match(text))


# Ordered from most specific to most generic: the first match wins when lengths collide.
PATTERNS: tuple[PlatePattern, ...] = (
  PlatePattern(
    name="air_force",
    mask="LLLNNNNNN",
    categories=(PlateCategory.AIR_FORCE,),
    prefix="FAC",
  ),
  PlatePattern(
    name="trailer",
    mask="LNNNNN",
    categories=(PlateCategory.TRAILER,),
    prefix="R",
  ),
  PlatePattern(
    name="temporary",
    mask="LNNNN",
    categories=(PlateCategory.TEMPORARY,),
    prefix="T",
  ),
  PlatePattern(
    name="motorcycle",
    mask="LLLNNL",
    categories=(PlateCategory.MOTORCYCLE,),
  ),
  PlatePattern(
    name="motocarro",
    mask="NNNLLL",
    categories=(
      PlateCategory.MOTOCARRO_PRIVATE,
      PlateCategory.MOTOCARRO_PUBLIC,
    ),
    # Digit-leading and therefore easy to coerce into from foreign formats; measured on real
    # footage, the Portuguese plate 0961RF became 096IRF. Require an exact match.
    strict=True,
  ),
  PlatePattern(
    name="police",
    mask="NNNNNN",
    categories=(PlateCategory.POLICE,),
    strict=True,
  ),
  PlatePattern(
    name="car",
    mask="LLLNNN",
    categories=(
      PlateCategory.PRIVATE_CAR,
      PlateCategory.PUBLIC_CAR,
      PlateCategory.OFFICIAL_CAR,
      PlateCategory.ANTIQUE_CAR,
      PlateCategory.DIPLOMATIC_CAR,
    ),
  ),
  PlatePattern(
    name="motorcycle_legacy",
    mask="LLLNN",
    categories=(PlateCategory.MOTORCYCLE_LEGACY,),
  ),
)

CATEGORY_VEHICLE_CLASS: dict[PlateCategory, VehicleClass] = {
  PlateCategory.PRIVATE_CAR: VehicleClass.CAR,
  PlateCategory.PUBLIC_CAR: VehicleClass.CAR,
  PlateCategory.OFFICIAL_CAR: VehicleClass.CAR,
  PlateCategory.ANTIQUE_CAR: VehicleClass.CAR,
  PlateCategory.DIPLOMATIC_CAR: VehicleClass.CAR,
  PlateCategory.TEMPORARY: VehicleClass.CAR,
  PlateCategory.POLICE: VehicleClass.CAR,
  PlateCategory.AIR_FORCE: VehicleClass.CAR,
  PlateCategory.MOTORCYCLE: VehicleClass.MOTORCYCLE,
  PlateCategory.MOTORCYCLE_LEGACY: VehicleClass.MOTORCYCLE,
  PlateCategory.MOTOCARRO_PRIVATE: VehicleClass.MOTORCYCLE,
  PlateCategory.MOTOCARRO_PUBLIC: VehicleClass.MOTORCYCLE,
  PlateCategory.TRAILER: VehicleClass.TRAILER,
  PlateCategory.UNKNOWN: VehicleClass.UNKNOWN,
}

CATEGORY_SERVICE_TYPE: dict[PlateCategory, ServiceType] = {
  PlateCategory.PRIVATE_CAR: ServiceType.PRIVATE,
  PlateCategory.PUBLIC_CAR: ServiceType.PUBLIC,
  PlateCategory.OFFICIAL_CAR: ServiceType.OFFICIAL,
  PlateCategory.ANTIQUE_CAR: ServiceType.ANTIQUE,
  PlateCategory.DIPLOMATIC_CAR: ServiceType.DIPLOMATIC,
  PlateCategory.MOTORCYCLE: ServiceType.PRIVATE,
  PlateCategory.MOTORCYCLE_LEGACY: ServiceType.PRIVATE,
  PlateCategory.MOTOCARRO_PRIVATE: ServiceType.PRIVATE,
  PlateCategory.MOTOCARRO_PUBLIC: ServiceType.PUBLIC,
  PlateCategory.TRAILER: ServiceType.OFFICIAL,
  PlateCategory.TEMPORARY: ServiceType.TEMPORARY,
  PlateCategory.POLICE: ServiceType.POLICE,
  PlateCategory.AIR_FORCE: ServiceType.MILITARY,
  PlateCategory.UNKNOWN: ServiceType.UNKNOWN,
}

# Background color of each category, per the national catalog. Used to disambiguate the
# categories that share a mask.
CATEGORY_COLOR: dict[PlateCategory, PlateColor] = {
  PlateCategory.PRIVATE_CAR: PlateColor.YELLOW,
  PlateCategory.PUBLIC_CAR: PlateColor.WHITE,
  PlateCategory.OFFICIAL_CAR: PlateColor.GREEN,
  # Antique and diplomatic plates are white with a blue stripe the color estimator does not
  # detect; they collapse onto WHITE and are therefore reported as PUBLIC_CAR.
  PlateCategory.ANTIQUE_CAR: PlateColor.WHITE,
  PlateCategory.DIPLOMATIC_CAR: PlateColor.WHITE,
  PlateCategory.MOTORCYCLE: PlateColor.YELLOW,
  PlateCategory.MOTORCYCLE_LEGACY: PlateColor.YELLOW,
  PlateCategory.MOTOCARRO_PRIVATE: PlateColor.YELLOW,
  PlateCategory.MOTOCARRO_PUBLIC: PlateColor.WHITE,
  PlateCategory.TRAILER: PlateColor.GREEN,
  PlateCategory.TEMPORARY: PlateColor.RED,
  PlateCategory.POLICE: PlateColor.WHITE,
  PlateCategory.AIR_FORCE: PlateColor.BLACK,
}

# Preference order when color cannot break a tie. Private cars dominate a university gate by
# a wide margin, so it is the safest default.
CATEGORY_PRIORITY: tuple[PlateCategory, ...] = (
  PlateCategory.PRIVATE_CAR,
  PlateCategory.MOTORCYCLE,
  PlateCategory.MOTORCYCLE_LEGACY,
  PlateCategory.PUBLIC_CAR,
  PlateCategory.MOTOCARRO_PRIVATE,
  PlateCategory.MOTOCARRO_PUBLIC,
  PlateCategory.OFFICIAL_CAR,
  PlateCategory.TRAILER,
  PlateCategory.TEMPORARY,
  PlateCategory.ANTIQUE_CAR,
  PlateCategory.DIPLOMATIC_CAR,
  PlateCategory.POLICE,
  PlateCategory.AIR_FORCE,
)


def find_pattern(text: str) -> PlatePattern | None:
  """Return the first catalog pattern the text satisfies, or None."""
  for pattern in PATTERNS:
    if pattern.matches(text):
      return pattern
  return None


def candidate_masks(length: int) -> tuple[str, ...]:
  """Masks worth attempting OCR coercion against, for a reading of a given length.

  Strict patterns are excluded: they are still recognized when the text matches them exactly,
  but nothing is ever bent into them.
  """
  seen: list[str] = []
  for pattern in PATTERNS:
    if pattern.strict:
      continue
    if pattern.length == length and pattern.mask not in seen:
      seen.append(pattern.mask)
  return tuple(seen)


def strict_masks(length: int) -> tuple[str, ...]:
  """Masks of strict patterns, usable only for a zero-correction match."""
  return tuple(dict.fromkeys(p.mask for p in PATTERNS if p.strict and p.length == length))
