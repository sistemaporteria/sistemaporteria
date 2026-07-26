"""Controlled degradations that reproduce how a plate actually reaches the camera.

Each degradation is an independent, measurable variable. That is the point: sweeping one at
a time answers questions the real installation depends on — how many pixels wide must a
plate be, how much motion blur is tolerable, at what angle recognition collapses. Those
answers become the camera specification in docs/02-placas-colombia.md section 7.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose

import cv2
import numpy as np
from PIL import Image


@dataclass(frozen=True)
class Degradation:
  """How a rendered plate is degraded before being handed to the OCR.

  Defaults are a no-op, so any sweep varies exactly one factor.
  """

  target_width: int = 200
  motion_blur: int = 0
  defocus_blur: float = 0.0
  yaw_deg: float = 0.0
  pitch_deg: float = 0.0
  brightness: float = 1.0
  contrast: float = 1.0
  noise_sigma: float = 0.0
  jpeg_quality: int = 100

  def label(self) -> str:
    return (
      f"w{self.target_width}_mb{self.motion_blur}_df{self.defocus_blur:g}"
      f"_yaw{self.yaw_deg:g}_pit{self.pitch_deg:g}_br{self.brightness:g}"
      f"_ct{self.contrast:g}_ns{self.noise_sigma:g}_q{self.jpeg_quality}"
    )


def _to_cv(image: Image.Image) -> np.ndarray:
  return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def _to_pil(array: np.ndarray) -> Image.Image:
  return Image.fromarray(cv2.cvtColor(array, cv2.COLOR_BGR2RGB))


# Camera distance expressed in plate widths. A gate camera reading a plate ~2 m away sees a
# 33 cm plate, so roughly 6. CALIBRAR against the real mounting distance.
VIEW_DISTANCE_RATIO = 6.0


def _edge_scales(angle_deg: float, extent: float) -> tuple[float, float]:
  """Relative size of the far and near edges under a pinhole projection.

  A naive "shrink the far edge by tan(angle)" model collapses the plate long before a real
  camera would, which would yield an unjustifiably strict angle requirement in the camera
  spec. This uses actual perspective division instead.
  """
  depth = VIEW_DISTANCE_RATIO * extent
  offset = (extent / 2) * np.sin(np.radians(abs(angle_deg)))
  far = depth / (depth + offset)
  near = depth / max(depth - offset, 1e-6)
  norm = max(far, near)
  return far / norm, near / norm


def _warp_perspective(img: np.ndarray, yaw_deg: float, pitch_deg: float) -> np.ndarray:
  """Foreshorten the plate as if seen off-axis.

  Perspective compresses the plate along the rotation axis and shortens its far edge; it
  does not translate the plate. Yaw rotates about the vertical axis, pitch about the
  horizontal one.
  """
  h, w = img.shape[:2]
  half_w, half_h = w / 2, h / 2
  # Corners as offsets from the center: top-left, top-right, bottom-right, bottom-left.
  corners = np.array(
    [[-half_w, -half_h], [half_w, -half_h], [half_w, half_h], [-half_w, half_h]],
    dtype=np.float64,
  )

  if yaw_deg:
    far, near = _edge_scales(yaw_deg, w)
    corners[:, 0] *= np.cos(np.radians(abs(yaw_deg)))
    left, right = (far, near) if yaw_deg > 0 else (near, far)
    corners[0][1] *= left
    corners[3][1] *= left
    corners[1][1] *= right
    corners[2][1] *= right

  if pitch_deg:
    far, near = _edge_scales(pitch_deg, h)
    corners[:, 1] *= np.cos(np.radians(abs(pitch_deg)))
    top, bottom = (far, near) if pitch_deg > 0 else (near, far)
    corners[0][0] *= top
    corners[1][0] *= top
    corners[2][0] *= bottom
    corners[3][0] *= bottom

  src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
  dst = np.float32(corners + [half_w, half_h])
  matrix = cv2.getPerspectiveTransform(src, dst)
  return cv2.warpPerspective(img, matrix, (w, h), borderMode=cv2.BORDER_REPLICATE)


def _motion_blur(img: np.ndarray, kernel_size: int) -> np.ndarray:
  """Horizontal smear, the shape a vehicle crossing the frame actually produces."""
  kernel = np.zeros((kernel_size, kernel_size), dtype=np.float32)
  kernel[kernel_size // 2, :] = 1.0 / kernel_size
  return cv2.filter2D(img, -1, kernel)


def apply(plate: Image.Image, degradation: Degradation) -> Image.Image:
  """Run the full degradation chain in the order it happens physically."""
  img = _to_cv(plate)

  if degradation.yaw_deg or degradation.pitch_deg:
    img = _warp_perspective(img, degradation.yaw_deg, degradation.pitch_deg)

  # Resize before blur and noise: the sensor samples the scene, then everything downstream
  # acts on the sampled pixels. Blurring first would overstate quality.
  height = max(1, int(round(degradation.target_width * img.shape[0] / img.shape[1])))
  img = cv2.resize(img, (degradation.target_width, height), interpolation=cv2.INTER_AREA)

  if degradation.motion_blur > 1:
    img = _motion_blur(img, degradation.motion_blur)

  if degradation.defocus_blur > 0:
    img = cv2.GaussianBlur(img, (0, 0), degradation.defocus_blur)

  if not (isclose(degradation.brightness, 1.0) and isclose(degradation.contrast, 1.0)):
    mean = 128.0
    img = np.clip(
      (img.astype(np.float32) - mean) * degradation.contrast * degradation.brightness
      + mean * degradation.brightness,
      0,
      255,
    ).astype(np.uint8)

  if degradation.noise_sigma > 0:
    rng = np.random.default_rng(abs(hash(degradation.label())) % (2**32))
    noise = rng.normal(0, degradation.noise_sigma, img.shape)
    img = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)

  if degradation.jpeg_quality < 100:
    ok, buffer = cv2.imencode(
      ".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), degradation.jpeg_quality]
    )
    if ok:
      img = cv2.imdecode(buffer, cv2.IMREAD_COLOR)

  return _to_pil(img)


# Sweeps used by the evaluation harness. One variable moves per sweep, everything else stays
# at its default, so the resulting curve is interpretable.
WIDTH_SWEEP = tuple(Degradation(target_width=w) for w in (40, 60, 80, 100, 130, 160, 200, 280))
MOTION_BLUR_SWEEP = tuple(Degradation(motion_blur=k) for k in (0, 3, 5, 7, 9, 13, 17))
DEFOCUS_SWEEP = tuple(Degradation(defocus_blur=s) for s in (0, 0.5, 1.0, 1.5, 2.0, 3.0))
YAW_SWEEP = tuple(Degradation(yaw_deg=a) for a in (0, 10, 20, 30, 40, 50, 60))
PITCH_SWEEP = tuple(Degradation(pitch_deg=a) for a in (0, 10, 20, 30, 40, 50))
LIGHTING_SWEEP = tuple(
  Degradation(brightness=b, contrast=c)
  for b, c in ((1.0, 1.0), (1.6, 0.6), (0.45, 1.0), (0.25, 0.8), (1.9, 0.4))
)
NOISE_SWEEP = tuple(Degradation(noise_sigma=s) for s in (0, 5, 10, 20, 35))
JPEG_SWEEP = tuple(Degradation(jpeg_quality=q) for q in (100, 80, 60, 40, 25, 15))

SWEEPS: dict[str, tuple[Degradation, ...]] = {
  "width": WIDTH_SWEEP,
  "motion_blur": MOTION_BLUR_SWEEP,
  "defocus": DEFOCUS_SWEEP,
  "yaw": YAW_SWEEP,
  "pitch": PITCH_SWEEP,
  "lighting": LIGHTING_SWEEP,
  "noise": NOISE_SWEEP,
  "jpeg": JPEG_SWEEP,
}
