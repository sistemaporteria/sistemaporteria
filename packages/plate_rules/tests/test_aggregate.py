from plate_rules import PlateColor, Reading, aggregate


def readings(*pairs: tuple[str, float], detector_label: str | None = None) -> list[Reading]:
  return [
    Reading(text, confidence, PlateColor.YELLOW, detector_label) for text, confidence in pairs
  ]


class TestAggregate:
  def test_empty_track_returns_none(self):
    assert aggregate([]) is None

  def test_majority_wins_over_a_noisy_frame(self):
    result = aggregate(
      readings(("ABC123", 0.91), ("ABC128", 0.62), ("ABC123", 0.88), ("ABC123", 0.94))
    )
    assert result is not None
    assert result.identification.plate.text == "ABC123"
    assert result.votes == 3
    assert result.total_readings == 4

  def test_confidence_outweighs_raw_count(self):
    # Two weak agreeing frames must not beat one very confident reading.
    result = aggregate(readings(("ABC123", 0.99), ("XYZ789", 0.20), ("XYZ789", 0.25)))
    assert result is not None
    assert result.identification.plate.text == "ABC123"

  def test_corrected_readings_merge_into_the_consensus(self):
    result = aggregate(readings(("ABC123", 0.90), ("A8C123", 0.85), ("ABC1Z3", 0.80)))
    assert result is not None
    assert result.identification.plate.text == "ABC123"
    assert result.votes == 3
    assert result.agreement == 1.0

  def test_invalid_readings_are_dropped_before_voting(self):
    result = aggregate(readings(("ABC123", 0.70), ("XX", 0.99), ("!!", 0.99)))
    assert result is not None
    assert result.identification.plate.text == "ABC123"
    assert result.total_readings == 1

  def test_all_invalid_still_returns_something_for_review(self):
    result = aggregate(readings(("XX", 0.9), ("YY", 0.8)))
    assert result is not None
    assert result.identification.needs_review

  def test_contested_track_is_flagged(self):
    result = aggregate(readings(("ABC123", 0.50), ("XYZ789", 0.49), ("QRS456", 0.48)))
    assert result is not None
    assert result.is_contested
    assert result.runner_up is not None

  def test_clear_track_is_not_contested(self):
    result = aggregate(readings(("ABC123", 0.9), ("ABC123", 0.9), ("ABC123", 0.9)))
    assert result is not None
    assert not result.is_contested
    assert result.runner_up is None

  def test_cross_check_survives_aggregation(self):
    result = aggregate(readings(("ABC12D", 0.9), ("ABC12D", 0.9), detector_label="motorcycle"))
    assert result is not None
    assert not result.identification.needs_review
