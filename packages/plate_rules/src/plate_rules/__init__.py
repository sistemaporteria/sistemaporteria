"""Colombian license plate domain rules.

Pure Python, zero dependencies, no I/O. Computer vision (color estimation, geometry) lives
in `edge_agent` and feeds already-computed values into this package.
"""

from .aggregate import AggregatedPlate, Reading, aggregate
from .classify import categories_for, cross_check, identify
from .normalize import clean, coerce_to_mask, normalize
from .patterns import PATTERNS, PlatePattern, find_pattern
from .types import (
  CrossCheckVerdict,
  NormalizedPlate,
  PlateCategory,
  PlateColor,
  PlateIdentification,
  ServiceType,
  VehicleClass,
)

__all__ = [
  "PATTERNS",
  "AggregatedPlate",
  "CrossCheckVerdict",
  "NormalizedPlate",
  "PlateCategory",
  "PlateColor",
  "PlateIdentification",
  "PlatePattern",
  "Reading",
  "ServiceType",
  "VehicleClass",
  "aggregate",
  "categories_for",
  "clean",
  "coerce_to_mask",
  "cross_check",
  "find_pattern",
  "identify",
  "normalize",
]

__version__ = "0.1.0"
