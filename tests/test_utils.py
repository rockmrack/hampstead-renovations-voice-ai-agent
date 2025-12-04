"""
Unit tests for utility functions.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api"))

from utils.helpers import (
    format_phone_number,
    is_valid_uk_phone,
    is_valid_postcode,
    normalize_postcode,
    is_in_service_area,
    get_area_tier,
    extract_name_parts,
    sanitize_for_speech,
    truncate_text,
    mask_phone_number,
    parse_budget_range,
)


class TestPhoneNumberUtils:
    """Tests for phone number utilities."""

    def test_format_phone_number_uk_mobile(self):
        """Test formatting UK mobile numbers."""
        assert format_phone_number("07912345678") == "+447912345678"
        assert format_phone_number("447912345678") == "+447912345678"
        assert format_phone_number("+447912345678") == "+447912345678"

    def test_format_phone_number_uk_landline(self):
        """Test formatting UK landline numbers."""
        result = format_phone_number("02071234567")
        assert result.startswith("+44")

    def test_format_phone_number_with_spaces(self):
        """Test formatting numbers with spaces."""
        result = format_phone_number("079 1234 5678")
        assert " " not in result
        assert result.startswith("+")

    def test_is_valid_uk_phone_valid(self):
        """Test valid UK phone numbers."""
        assert is_valid_uk_phone("+447912345678") is True
        assert is_valid_uk_phone("07912345678") is True

    def test_is_valid_uk_phone_invalid(self):
        """Test invalid UK phone numbers."""
        assert is_valid_uk_phone("+1234567890") is False
        assert is_valid_uk_phone("invalid") is False

    def test_mask_phone_number(self):
        """Test phone number masking."""
        assert mask_phone_number("+447912345678") == "********5678"
        assert mask_phone_number("5678") == "5678"
        assert mask_phone_number("123") == "****"


class TestPostcodeUtils:
    """Tests for postcode utilities."""

    def test_is_valid_postcode_valid(self):
        """Test valid UK postcodes."""
        assert is_valid_postcode("NW3 2AB") is True
        assert is_valid_postcode("NW32AB") is True
        assert is_valid_postcode("W1A 1AA") is True
        assert is_valid_postcode("EC1A 1BB") is True

    def test_is_valid_postcode_invalid(self):
        """Test invalid postcodes."""
        assert is_valid_postcode("ABC 123") is False
        assert is_valid_postcode("12345") is False
        assert is_valid_postcode("INVALID") is False

    def test_normalize_postcode(self):
        """Test postcode normalization."""
        assert normalize_postcode("nw32ab") == "NW3 2AB"
        assert normalize_postcode("NW3  2AB") == "NW3 2AB"
        assert normalize_postcode("  nw3 2ab  ") == "NW3 2AB"

    def test_is_in_service_area_primary(self):
        """Test primary service areas."""
        assert is_in_service_area("NW3 2AB") is True
        assert is_in_service_area("NW6 1XJ") is True
        assert is_in_service_area("N6 5HE") is True
        assert is_in_service_area("NW11 7ES") is True

    def test_is_in_service_area_extended(self):
        """Test extended service areas."""
        assert is_in_service_area("W1A 1AA") is True
        assert is_in_service_area("EC1A 1BB") is True
        assert is_in_service_area("HA3 5AB") is True

    def test_is_in_service_area_outside(self):
        """Test areas outside service region."""
        assert is_in_service_area("SE1 1AA") is False
        assert is_in_service_area("E1 6AN") is False
        assert is_in_service_area("CR0 1AA") is False

    def test_get_area_tier_premium(self):
        """Test premium area tier."""
        assert get_area_tier("NW3 2AB") == "premium"
        assert get_area_tier("NW6 1XJ") == "premium"
        assert get_area_tier("N6 5HE") == "premium"

    def test_get_area_tier_standard(self):
        """Test standard area tier."""
        assert get_area_tier("NW1 1AA") == "standard"
        assert get_area_tier("N1 1AA") == "standard"

    def test_get_area_tier_outside(self):
        """Test outside service area returns None."""
        assert get_area_tier("SE1 1AA") is None


class TestNameUtils:
    """Tests for name utilities."""

    def test_extract_name_parts_full_name(self):
        """Test extracting first and last name."""
        first, last = extract_name_parts("John Smith")
        assert first == "John"
        assert last == "Smith"

    def test_extract_name_parts_single_name(self):
        """Test single name."""
        first, last = extract_name_parts("John")
        assert first == "John"
        assert last == ""

    def test_extract_name_parts_multiple_names(self):
        """Test multiple names."""
        first, last = extract_name_parts("John Robert Smith")
        assert first == "John"
        assert last == "Robert Smith"

    def test_extract_name_parts_with_spaces(self):
        """Test name with extra spaces."""
        first, last = extract_name_parts("  John   Smith  ")
        assert first == "John"
        assert last == "Smith"


class TestTextUtils:
    """Tests for text utilities."""

    def test_sanitize_for_speech_symbols(self):
        """Test symbol replacement for TTS."""
        assert "and" in sanitize_for_speech("Tom & Jerry")
        assert "at" in sanitize_for_speech("email@example.com")
        assert "pounds" in sanitize_for_speech("£50")
        assert "percent" in sanitize_for_speech("50%")

    def test_sanitize_for_speech_multiple_spaces(self):
        """Test multiple space normalization."""
        result = sanitize_for_speech("Hello    world")
        assert "  " not in result

    def test_truncate_text_short(self):
        """Test text shorter than limit."""
        text = "Hello world"
        assert truncate_text(text, 50) == text

    def test_truncate_text_long(self):
        """Test text longer than limit."""
        text = "This is a very long text that needs to be truncated"
        result = truncate_text(text, 30)
        assert len(result) <= 30
        assert result.endswith("...")

    def test_truncate_text_word_boundary(self):
        """Test truncation at word boundary."""
        text = "Hello wonderful world"
        result = truncate_text(text, 15)
        assert not result.endswith(" ...")


class TestBudgetUtils:
    """Tests for budget parsing utilities."""

    def test_parse_budget_range_k_notation(self):
        """Test parsing 'k' notation."""
        result = parse_budget_range("£50k-100k")
        assert result == (50000, 100000)

    def test_parse_budget_range_full_numbers(self):
        """Test parsing full numbers."""
        result = parse_budget_range("50000 to 100000")
        assert result == (50000, 100000)

    def test_parse_budget_range_single_value(self):
        """Test parsing single value with range estimation."""
        result = parse_budget_range("around £75000")
        assert result is not None
        min_val, max_val = result
        assert min_val < 75000 < max_val

    def test_parse_budget_range_invalid(self):
        """Test parsing invalid budget."""
        result = parse_budget_range("no idea")
        assert result is None
