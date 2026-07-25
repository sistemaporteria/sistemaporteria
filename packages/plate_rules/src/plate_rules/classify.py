"""Vehicle type inference and cross-checking.

Three independent signals are combined:
  1. the text pattern      -> a set of candidate categories (often ambiguous)
  2. the plate background color -> narrows the set (private vs public, mainly)
  3. the object detector label  -> confirms or contradicts the physical class

Signal 3 is what turns this module into a free OCR error detector: a plate whose pattern
says "motorcycle" attached to something the camera calls a car almost always means the OCR
misread a character. See docs/02-placas-colombia.md section 4.
"""

from __future__ import annotations

from .normalize import adjust_confidence, normalize
from .patterns import (
  CATEGORY_COLOR,
  CATEGORY_PRIORITY,
  CATEGORY_SERVICE_TYPE,
  CATEGORY_VEHICLE_CLASS,
  find_pattern,
)
from .types import (
  CrossCheckVerdict,
  NormalizedPlate,
  PlateCategory,
  PlateColor,
  PlateIdentification,
  ServiceType,
  VehicleClass,
)

# COCO labels emitted by the object detector, mapped to our coarse physical classes.
DETECTOR_LABEL_TO_CLASS: dict[str, VehicleClass] = {
  "car": VehicleClass.CAR,
  "truck": VehicleClass.CAR,
  "bus": VehicleClass.CAR,
  "motorcycle": VehicleClass.MOTORCYCLE,
  "motorbike": VehicleClass.MOTORCYCLE,
}

CONFIDENCE_BONUS_CONFIRMED = 0.05
CONFIDENCE_PENALTY_CONFLICT = 0.40


def categories_for(text: str) -> tuple[PlateCategory, ...]:
  """Every catalog category compatible with the plate text."""
  pattern = find_pattern(text)
  return pattern.categories if pattern else ()


def narrow_by_color(
  categories: tuple[PlateCategory, ...], color: PlateColor
) -> tuple[PlateCategory, ...]:
  """Keep only the categories whose official background color matches the observation.

  An unknown or non-matching color leaves the candidate set untouched rather than emptying
  it: a bad color estimate must not destroy a good pattern match.
  """
  if color is PlateColor.UNKNOWN:
    return categories
  narrowed = tuple(c for c in categories if CATEGORY_COLOR.get(c) is color)
  return narrowed or categories


def pick_category(categories: tuple[PlateCategory, ...]) -> PlateCategory:
  """Resolve a still-ambiguous candidate set using the gate's real-world frequencies."""
  if not categories:
    return PlateCategory.UNKNOWN
  if len(categories) == 1:
    return categories[0]
  for candidate in CATEGORY_PRIORITY:
    if candidate in categories:
      return candidate
  return categories[0]


def cross_check(
  expected: VehicleClass, detector_label: str | None
) -> tuple[CrossCheckVerdict, str | None]:
  """Contrast the plate-derived class against what the object detector saw."""
  if detector_label is None:
    return CrossCheckVerdict.UNVERIFIED, None

  observed = DETECTOR_LABEL_TO_CLASS.get(detector_label.lower())
  if observed is None:
    return CrossCheckVerdict.UNVERIFIED, f"unmapped_detector_label:{detector_label}"

  if expected is VehicleClass.UNKNOWN:
    return CrossCheckVerdict.UNVERIFIED, None

  # A trailer is towed by a car, so the detector legitimately reports a car for it.
  if expected is VehicleClass.TRAILER:
    return CrossCheckVerdict.UNVERIFIED, "trailer_not_verifiable"

  if expected is observed:
    return CrossCheckVerdict.CONFIRMED, None

  return (
    CrossCheckVerdict.CONFLICT,
    f"plate_suggests:{expected.value}|detector_saw:{observed.value}",
  )


def identify(
  raw_text: str,
  *,
  ocr_confidence: float = 1.0,
  plate_color: PlateColor = PlateColor.UNKNOWN,
  detector_label: str | None = None,
) -> PlateIdentification:
  """Full classification of a single plate reading."""
  plate: NormalizedPlate = normalize(raw_text)
  confidence = adjust_confidence(ocr_confidence, plate.corrections)
  notes: list[str] = []

  if not plate.is_valid:
    if plate.rejection_reason:
      notes.append(plate.rejection_reason)
    return PlateIdentification(
      plate=plate,
      verdict=CrossCheckVerdict.UNRECOGNIZED_PATTERN,
      confidence=confidence * 0.5,
      notes=tuple(notes),
    )

  categories = categories_for(plate.text)
  narrowed = narrow_by_color(categories, plate_color)
  if plate_color is PlateColor.UNKNOWN and len(categories) > 1:
    notes.append("ambiguous_without_color")
  elif len(narrowed) == len(categories) > 1:
    notes.append(f"color_did_not_narrow:{plate_color.value}")

  category = pick_category(narrowed)
  vehicle_class = CATEGORY_VEHICLE_CLASS.get(category, VehicleClass.UNKNOWN)
  service_type = CATEGORY_SERVICE_TYPE.get(category, ServiceType.UNKNOWN)

  verdict, note = cross_check(vehicle_class, detector_label)
  if note:
    notes.append(note)

  if verdict is CrossCheckVerdict.CONFIRMED:
    confidence = min(1.0, confidence + CONFIDENCE_BONUS_CONFIRMED)
  elif verdict is CrossCheckVerdict.CONFLICT:
    confidence = max(0.0, confidence - CONFIDENCE_PENALTY_CONFLICT)

  return PlateIdentification(
    plate=plate,
    categories=narrowed,
    category=category,
    vehicle_class=vehicle_class,
    service_type=service_type,
    verdict=verdict,
    confidence=confidence,
    notes=tuple(notes),
  )
