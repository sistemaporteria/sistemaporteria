"""Temporal aggregation of the many readings produced by one vehicle.

A vehicle is visible for 20-40 frames, each yielding a reading. Keeping the last one wastes
most of the evidence. Confidence-weighted voting over the whole track raises a ~90%
per-frame accuracy to ~98-99%. See docs/02-placas-colombia.md section 6.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .classify import identify
from .types import PlateColor, PlateIdentification


@dataclass(frozen=True)
class Reading:
  """One OCR observation of a plate within a track."""

  text: str
  confidence: float = 1.0
  plate_color: PlateColor = PlateColor.UNKNOWN
  detector_label: str | None = None


@dataclass(frozen=True)
class AggregatedPlate:
  """Consensus over every reading collected for a single track."""

  identification: PlateIdentification
  votes: int
  total_readings: int
  score: float
  runner_up: str | None

  @property
  def agreement(self) -> float:
    return self.votes / self.total_readings if self.total_readings else 0.0

  @property
  def is_contested(self) -> bool:
    """True when the winner did not clearly dominate, so a human should confirm."""
    return self.agreement < 0.5 or self.runner_up is not None and self.votes <= 1


def aggregate(readings: list[Reading]) -> AggregatedPlate | None:
  """Pick the consensus plate for a track by confidence-weighted voting.

  Invalid readings are dropped before voting; if every reading is invalid, the best-scoring
  one is still returned so the event reaches the review queue instead of vanishing.
  """
  if not readings:
    return None

  identifications = [
    identify(
      r.text,
      ocr_confidence=r.confidence,
      plate_color=r.plate_color,
      detector_label=r.detector_label,
    )
    for r in readings
  ]

  valid = [i for i in identifications if i.plate.is_valid]
  pool = valid or identifications

  scores: dict[str, float] = defaultdict(float)
  counts: dict[str, int] = defaultdict(int)
  best_by_text: dict[str, PlateIdentification] = {}

  for ident in pool:
    key = ident.plate.text
    scores[key] += ident.confidence
    counts[key] += 1
    current = best_by_text.get(key)
    if current is None or ident.confidence > current.confidence:
      best_by_text[key] = ident

  ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
  winner_text, winner_score = ranked[0]
  runner_up = ranked[1][0] if len(ranked) > 1 else None

  return AggregatedPlate(
    identification=best_by_text[winner_text],
    votes=counts[winner_text],
    total_readings=len(pool),
    score=winner_score,
    runner_up=runner_up,
  )
