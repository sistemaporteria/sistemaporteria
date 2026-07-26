import random

import pytest
from plate_rules import PlateCategory, PlateColor, identify, normalize

from plate_synth import Degradation, apply, random_spec, render


class TestRandomSpec:
  @pytest.mark.parametrize(
    ("category", "expected_color"),
    [
      (PlateCategory.PRIVATE_CAR, PlateColor.YELLOW),
      (PlateCategory.PUBLIC_CAR, PlateColor.WHITE),
      (PlateCategory.OFFICIAL_CAR, PlateColor.GREEN),
      (PlateCategory.MOTORCYCLE, PlateColor.YELLOW),
    ],
  )
  def test_background_matches_the_catalog(self, category, expected_color):
    spec = random_spec(random.Random(1), category)
    assert spec.background is expected_color

  def test_official_plates_start_with_o(self):
    spec = random_spec(random.Random(1), PlateCategory.OFFICIAL_CAR)
    assert spec.text.startswith("O")

  def test_motorcycle_plates_are_narrower(self):
    car = random_spec(random.Random(1), PlateCategory.PRIVATE_CAR)
    moto = random_spec(random.Random(1), PlateCategory.MOTORCYCLE)
    assert moto.aspect < car.aspect

  def test_every_generated_plate_is_domain_valid(self):
    rng = random.Random(99)
    for _ in range(200):
      spec = random_spec(rng)
      result = normalize(spec.text)
      assert result.is_valid, spec.text
      assert result.corrections == 0

  def test_generated_class_agrees_with_the_domain(self):
    rng = random.Random(5)
    for _ in range(100):
      spec = random_spec(rng)
      identified = identify(spec.text, plate_color=spec.background)
      assert identified.category is spec.category


class TestRender:
  def test_respects_requested_width_and_aspect(self):
    spec = random_spec(random.Random(1), PlateCategory.PRIVATE_CAR)
    image = render(spec, width=660)
    assert image.width == 660
    assert image.height == pytest.approx(660 / spec.aspect, abs=1)

  def test_text_stays_inside_the_plate(self):
    # A font sized on height alone overflows horizontally; guard against the regression by
    # checking the border pixels still hold the background color.
    spec = random_spec(random.Random(2), PlateCategory.PRIVATE_CAR)
    image = render(spec, width=660)
    mid_y = image.height // 2
    inside = max(2, image.width // 110) + 4  # just past the drawn border
    assert image.getpixel((inside, mid_y))[0] > 100
    assert image.getpixel((image.width - inside, mid_y))[0] > 100


class TestDegrade:
  def test_default_degradation_only_resizes(self):
    spec = random_spec(random.Random(1), PlateCategory.PRIVATE_CAR)
    out = apply(render(spec), Degradation(target_width=200))
    assert out.width == 200

  def test_preserves_aspect_ratio(self):
    spec = random_spec(random.Random(1), PlateCategory.PRIVATE_CAR)
    source = render(spec)
    out = apply(source, Degradation(target_width=150))
    assert out.height == pytest.approx(150 * source.height / source.width, abs=1)

  @pytest.mark.parametrize(
    "degradation",
    [
      Degradation(motion_blur=9),
      Degradation(defocus_blur=2.0),
      Degradation(yaw_deg=30),
      Degradation(pitch_deg=-30),
      Degradation(brightness=1.7, contrast=0.5),
      Degradation(noise_sigma=20),
      Degradation(jpeg_quality=25),
    ],
  )
  def test_every_degradation_produces_a_usable_image(self, degradation):
    spec = random_spec(random.Random(1), PlateCategory.PRIVATE_CAR)
    out = apply(render(spec), degradation)
    assert out.size == (degradation.target_width, out.height)
    assert out.mode == "RGB"

  def test_perspective_does_not_translate_the_plate(self):
    # A yaw warp must foreshorten, keeping the plate centered. An earlier version shifted it
    # sideways instead, which is not what a rotated plate looks like.
    spec = random_spec(random.Random(1), PlateCategory.PRIVATE_CAR)
    warped = apply(render(spec), Degradation(target_width=200, yaw_deg=30))
    center_column = warped.width // 2
    column = [warped.getpixel((center_column, y)) for y in range(warped.height)]
    assert any(px[0] > 150 and px[2] < 120 for px in column)

  def test_labels_are_unique_per_variant(self):
    labels = {Degradation(target_width=w).label() for w in (40, 60, 80)}
    assert len(labels) == 3
