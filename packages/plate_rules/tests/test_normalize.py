import pytest

from plate_rules import clean, coerce_to_mask, normalize


class TestClean:
  def test_uppercases_and_strips_separators(self):
    assert clean("abc-123") == "ABC123"

  def test_removes_spaces_and_dots(self):
    assert clean(" ABC . 123 ") == "ABC123"

  def test_removes_country_token(self):
    assert clean("ABC123 COLOMBIA") == "ABC123"

  def test_empty_input(self):
    assert clean("---") == ""


class TestCoerceToMask:
  def test_no_corrections_when_already_valid(self):
    assert coerce_to_mask("ABC123", "LLLNNN") == ("ABC123", 0)

  def test_digit_to_letter(self):
    assert coerce_to_mask("A8C123", "LLLNNN") == ("ABC123", 1)

  def test_letter_to_digit(self):
    assert coerce_to_mask("ABC1Z3", "LLLNNN") == ("ABC123", 1)

  def test_documented_example_two_corrections(self):
    assert coerce_to_mask("A8C1Z3", "LLLNNN") == ("ABC123", 2)

  def test_returns_none_on_length_mismatch(self):
    assert coerce_to_mask("ABC12", "LLLNNN") is None

  def test_returns_none_when_char_has_no_mapping(self):
    # 'X' has no digit lookalike, so it cannot fill a digit slot.
    assert coerce_to_mask("ABCX23", "LLLNNN") is None

  def test_rejects_unknown_mask_slot(self):
    with pytest.raises(ValueError):
      coerce_to_mask("ABC123", "LLLXXX")


class TestNormalize:
  @pytest.mark.parametrize(
    ("raw", "expected", "mask"),
    [
      ("ABC123", "ABC123", "LLLNNN"),
      ("abc-123", "ABC123", "LLLNNN"),
      ("ABC12D", "ABC12D", "LLLNNL"),
      ("ABC12", "ABC12", "LLLNN"),
      ("123ABC", "123ABC", "NNNLLL"),
      ("R12345", "R12345", "LNNNNN"),
      ("T1234", "T1234", "LNNNN"),
      ("FAC123456", "FAC123456", "LLLNNNNNN"),
    ],
  )
  def test_valid_catalog_plates(self, raw, expected, mask):
    result = normalize(raw)
    assert result.is_valid
    assert result.text == expected
    assert result.mask == mask
    assert result.corrections == 0

  def test_corrects_ocr_confusion(self):
    result = normalize("A8C1Z3")
    assert result.is_valid
    assert result.text == "ABC123"
    assert result.corrections == 2

  def test_rejects_when_over_correction_limit(self):
    result = normalize("48C1Z3")
    assert not result.is_valid
    assert result.rejection_reason is not None
    assert result.rejection_reason.startswith("too_many_corrections")

  def test_correction_limit_is_configurable(self):
    result = normalize("48C1Z3", max_corrections=3)
    assert result.is_valid
    assert result.text == "ABC123"
    assert result.corrections == 3

  def test_rejects_unsupported_length(self):
    result = normalize("AB12")
    assert not result.is_valid
    assert result.rejection_reason == "unsupported_length_4"

  def test_rejects_empty(self):
    result = normalize("///")
    assert not result.is_valid
    assert result.rejection_reason == "empty_after_cleanup"

  def test_keeps_raw_for_audit(self):
    result = normalize("a8c-1z3")
    assert result.raw == "a8c-1z3"

  def test_prefers_fewest_corrections_across_masks(self):
    # 6 chars match LLLNNN, NNNLLL, LNNNNN and NNNNNN; the zero-correction one must win.
    result = normalize("123ABC")
    assert result.text == "123ABC"
    assert result.corrections == 0
