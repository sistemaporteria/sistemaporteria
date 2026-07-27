"""OCR text cleanup and pattern-guided correction.

OCR engines confuse characters that look alike. Because the mask each position must satisfy
is known in advance, the confusion can be resolved deterministically instead of guessed.
See docs/02-placas-colombia.md section 5.
"""

from __future__ import annotations

import re

from .patterns import DIGIT, LETTER, candidate_masks, find_pattern, strict_masks
from .types import NormalizedPlate

# Upper bound on how many characters may be coerced. Beyond this the reading is too
# corrupted to trust: inventing a plausible-but-wrong plate is far worse than not reading.
MAX_CORRECTIONS = 2

# Confidence penalty applied per coerced character, consumed by the temporal aggregator.
CONFIDENCE_PENALTY_PER_CORRECTION = 0.15

LETTER_TO_DIGIT: dict[str, str] = {
  "O": "0",
  "D": "0",
  "Q": "0",
  "I": "1",
  "L": "1",
  "Z": "2",
  "E": "3",
  "A": "4",
  "S": "5",
  "G": "6",
  "T": "7",
  "B": "8",
}

DIGIT_TO_LETTER: dict[str, str] = {
  "0": "O",
  "1": "I",
  "2": "Z",
  "4": "A",
  "5": "S",
  "6": "G",
  "8": "B",
}

# Tokens some OCR engines emit alongside the plate code.
NOISE_TOKENS = ("COLOMBIA", "MINTRANSPORTE", "MERCOSUR")

_NON_ALNUM = re.compile(r"[^A-Z0-9]")


def clean(raw: str) -> str:
  """Strip everything that cannot be part of a plate code."""
  text = raw.upper()
  for token in NOISE_TOKENS:
    text = text.replace(token, "")
  return _NON_ALNUM.sub("", text)


def coerce_to_mask(text: str, mask: str) -> tuple[str, int] | None:
  """Force each character to satisfy its mask slot.

  Returns the coerced text and how many characters had to change, or None when some
  character has no known correction for its slot.
  """
  if len(text) != len(mask):
    return None

  out: list[str] = []
  corrections = 0

  for char, slot in zip(text, mask, strict=True):
    if slot == LETTER:
      if char.isalpha():
        out.append(char)
        continue
      replacement = DIGIT_TO_LETTER.get(char)
    elif slot == DIGIT:
      if char.isdigit():
        out.append(char)
        continue
      replacement = LETTER_TO_DIGIT.get(char)
    else:
      raise ValueError(f"unknown mask slot: {slot!r}")

    if replacement is None:
      return None
    out.append(replacement)
    corrections += 1

  return "".join(out), corrections


def _exact_strict_match(text: str) -> str | None:
  """Mask of the strict pattern the text already satisfies, if any.

  Strict patterns accept only exact matches; nothing is ever coerced into them.
  """
  if find_pattern(text) is None:
    return None
  for mask in strict_masks(len(text)):
    result = coerce_to_mask(text, mask)
    if result is not None and result[1] == 0:
      return mask
  return None


def _best_coercion(text: str, masks: tuple[str, ...]) -> tuple[str, str, int] | None:
  """Coercion needing the fewest changes that still lands on a catalog pattern."""
  best: tuple[str, str, int] | None = None
  for mask in masks:
    result = coerce_to_mask(text, mask)
    if result is None:
      continue
    coerced, corrections = result
    if find_pattern(coerced) is None:
      continue
    if best is None or corrections < best[2]:
      best = (coerced, mask, corrections)
    if corrections == 0:
      break
  return best


def normalize(raw: str, max_corrections: int = MAX_CORRECTIONS) -> NormalizedPlate:
  """Clean an OCR reading and coerce it onto the closest valid Colombian plate pattern.

  Every catalog mask of the same length is attempted; the one needing the fewest coercions
  and yielding a catalog-valid plate wins.
  """
  text = clean(raw)

  if not text:
    return NormalizedPlate(raw, "", None, 0, False, "empty_after_cleanup")

  strict_mask = _exact_strict_match(text)
  if strict_mask is not None:
    return NormalizedPlate(raw, text, strict_mask, 0, True)

  masks = candidate_masks(len(text))
  if not masks:
    return NormalizedPlate(raw, text, None, 0, False, f"unsupported_length_{len(text)}")

  best = _best_coercion(text, masks)
  if best is None:
    return NormalizedPlate(raw, text, None, 0, False, "no_matching_pattern")

  coerced, mask, corrections = best
  if corrections > max_corrections:
    return NormalizedPlate(
      raw, coerced, mask, corrections, False, f"too_many_corrections_{corrections}"
    )

  return NormalizedPlate(raw, coerced, mask, corrections, True)


def adjust_confidence(ocr_confidence: float, corrections: int) -> float:
  """Discount OCR confidence by how much the reading had to be repaired."""
  adjusted = ocr_confidence - corrections * CONFIDENCE_PENALTY_PER_CORRECTION
  return max(0.0, min(1.0, adjusted))
