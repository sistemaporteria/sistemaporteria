import pytest

from plate_rules import (
  CrossCheckVerdict,
  PlateCategory,
  PlateColor,
  ServiceType,
  VehicleClass,
  categories_for,
  cross_check,
  identify,
)


class TestCategoriesForPattern:
  def test_car_mask_is_ambiguous(self):
    categories = categories_for("ABC123")
    assert PlateCategory.PRIVATE_CAR in categories
    assert PlateCategory.PUBLIC_CAR in categories
    assert len(categories) > 1

  def test_motorcycle_mask_is_unambiguous(self):
    assert categories_for("ABC12D") == (PlateCategory.MOTORCYCLE,)

  def test_trailer_requires_r_prefix(self):
    assert categories_for("R12345") == (PlateCategory.TRAILER,)
    assert categories_for("X12345") == ()

  def test_unknown_text(self):
    assert categories_for("ZZ") == ()


class TestColorDisambiguation:
  def test_yellow_means_private_car(self):
    result = identify("ABC123", plate_color=PlateColor.YELLOW)
    assert result.category is PlateCategory.PRIVATE_CAR
    assert result.service_type is ServiceType.PRIVATE

  def test_white_means_public_car(self):
    result = identify("ABC123", plate_color=PlateColor.WHITE)
    assert result.category is PlateCategory.PUBLIC_CAR
    assert result.service_type is ServiceType.PUBLIC

  def test_green_means_official_car(self):
    result = identify("OAB123", plate_color=PlateColor.GREEN)
    assert result.category is PlateCategory.OFFICIAL_CAR
    assert result.service_type is ServiceType.OFFICIAL

  def test_unknown_color_falls_back_to_priority_and_flags_it(self):
    result = identify("ABC123", plate_color=PlateColor.UNKNOWN)
    assert result.category is PlateCategory.PRIVATE_CAR
    assert "ambiguous_without_color" in result.notes

  def test_bad_color_does_not_destroy_a_good_pattern_match(self):
    # Motorcycle plates are yellow; a red estimate must not erase the match.
    result = identify("ABC12D", plate_color=PlateColor.RED)
    assert result.category is PlateCategory.MOTORCYCLE
    assert result.vehicle_class is VehicleClass.MOTORCYCLE

  def test_d_prefix_is_not_treated_as_diplomatic(self):
    result = identify("DAB123", plate_color=PlateColor.YELLOW)
    assert result.category is PlateCategory.PRIVATE_CAR


class TestCrossCheck:
  def test_motorcycle_agreement(self):
    verdict, _ = cross_check(VehicleClass.MOTORCYCLE, "motorcycle")
    assert verdict is CrossCheckVerdict.CONFIRMED

  def test_truck_counts_as_car(self):
    verdict, _ = cross_check(VehicleClass.CAR, "truck")
    assert verdict is CrossCheckVerdict.CONFIRMED

  def test_disagreement_is_a_conflict(self):
    verdict, note = cross_check(VehicleClass.MOTORCYCLE, "car")
    assert verdict is CrossCheckVerdict.CONFLICT
    assert note is not None

  def test_missing_label_is_unverified(self):
    verdict, _ = cross_check(VehicleClass.CAR, None)
    assert verdict is CrossCheckVerdict.UNVERIFIED

  def test_unmapped_label_is_unverified(self):
    verdict, note = cross_check(VehicleClass.CAR, "person")
    assert verdict is CrossCheckVerdict.UNVERIFIED
    assert note is not None and "unmapped" in note

  def test_trailer_is_not_verifiable(self):
    verdict, _ = cross_check(VehicleClass.TRAILER, "car")
    assert verdict is CrossCheckVerdict.UNVERIFIED


class TestIdentify:
  def test_confirmed_reading_gets_a_confidence_bonus(self):
    result = identify(
      "ABC12D", ocr_confidence=0.90, plate_color=PlateColor.YELLOW, detector_label="motorcycle"
    )
    assert result.verdict is CrossCheckVerdict.CONFIRMED
    assert result.confidence > 0.90
    assert not result.needs_review

  def test_ocr_error_surfaces_as_a_conflict(self):
    # Real failure mode: motorcycle ABC12D misread as ABC120 (D -> 0).
    result = identify("ABC120", plate_color=PlateColor.YELLOW, detector_label="motorcycle")
    assert result.vehicle_class is VehicleClass.CAR
    assert result.verdict is CrossCheckVerdict.CONFLICT
    assert result.needs_review

  def test_conflict_penalizes_confidence(self):
    result = identify("ABC120", ocr_confidence=0.95, detector_label="motorcycle")
    assert result.confidence < 0.95

  def test_invalid_plate_needs_review(self):
    result = identify("XX", detector_label="car")
    assert result.verdict is CrossCheckVerdict.UNRECOGNIZED_PATTERN
    assert result.needs_review
    assert not result.plate.is_valid

  def test_corrections_reduce_confidence(self):
    clean_read = identify("ABC123", ocr_confidence=0.90)
    fixed_read = identify("A8C123", ocr_confidence=0.90)
    assert fixed_read.plate.text == "ABC123"
    assert fixed_read.confidence < clean_read.confidence

  @pytest.mark.parametrize(
    ("text", "expected_class"),
    [
      ("ABC123", VehicleClass.CAR),
      ("ABC12D", VehicleClass.MOTORCYCLE),
      ("ABC12", VehicleClass.MOTORCYCLE),
      ("123ABC", VehicleClass.MOTORCYCLE),
      ("R12345", VehicleClass.TRAILER),
      ("T1234", VehicleClass.CAR),
    ],
  )
  def test_vehicle_class_per_pattern(self, text, expected_class):
    assert identify(text).vehicle_class is expected_class
