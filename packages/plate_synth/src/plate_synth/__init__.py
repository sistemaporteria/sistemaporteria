"""Synthetic Colombian license plate generation for evaluation.

Renders catalog-valid plates and degrades them under controlled, measurable variables.
See docs/05-evaluacion.md.
"""

from .dataset import Sample, build, build_flat
from .degrade import SWEEPS, Degradation, apply
from .render import PlateSpec, random_spec, render

__all__ = [
  "SWEEPS",
  "Degradation",
  "PlateSpec",
  "Sample",
  "apply",
  "build",
  "build_flat",
  "random_spec",
  "render",
]

__version__ = "0.1.0"
