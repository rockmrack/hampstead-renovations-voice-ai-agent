"""
Utility helper functions.
Common utilities used across the application.
"""

import re
from typing import Optional

import phonenumbers
from phonenumbers import NumberParseException


def format_phone_number(phone: str, default_region: str = "GB") -> str:
    """
    Format phone number to E.164 format.
    
    Args:
        phone: Raw phone number string
        default_region: Default region code (GB for UK)
        
    Returns:
        Phone number in E.164 format (+447912345678)
    """
    # Remove common formatting characters
    cleaned = re.sub(r"[\s\-\(\)\.]+", "", phone)
    
    try:
        parsed = phonenumbers.parse(cleaned, default_region)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(
                parsed, phonenumbers.PhoneNumberFormat.E164
            )
    except NumberParseException:
        pass
    
    # Fallback: ensure starts with +
    if not cleaned.startswith("+"):
        if cleaned.startswith("0"):
            cleaned = "44" + cleaned[1:]
        cleaned = "+" + cleaned
    
    return cleaned


def is_valid_uk_phone(phone: str) -> bool:
    """Check if phone number is a valid UK number."""
    try:
        parsed = phonenumbers.parse(phone, "GB")
        return (
            phonenumbers.is_valid_number(parsed) and
            phonenumbers.region_code_for_number(parsed) == "GB"
        )
    except NumberParseException:
        return False


def is_valid_postcode(postcode: str) -> bool:
    """
    Validate UK postcode format.
    
    Args:
        postcode: Postcode to validate
        
    Returns:
        True if valid UK postcode format
    """
    # UK postcode regex pattern
    pattern = r"^[A-Z]{1,2}[0-9][0-9A-Z]?\s?[0-9][A-Z]{2}$"
    return bool(re.match(pattern, postcode.upper().strip()))


def normalize_postcode(postcode: str) -> str:
    """
    Normalize postcode to standard format (XX## #XX).
    
    Args:
        postcode: Raw postcode string
        
    Returns:
        Normalized postcode with space
    """
    cleaned = re.sub(r"\s+", "", postcode.upper().strip())
    
    if len(cleaned) >= 5:
        # Insert space before last 3 characters
        return f"{cleaned[:-3]} {cleaned[-3:]}"
    
    return cleaned


def is_in_service_area(postcode: str) -> bool:
    """
    Check if postcode is within Hampstead Renovations service area.
    
    Service areas: NW, N (parts), W (parts), WC, EC (parts)
    Focus on North/Northwest London
    
    Args:
        postcode: UK postcode
        
    Returns:
        True if in service area
    """
    if not is_valid_postcode(postcode):
        return False
    
    normalized = normalize_postcode(postcode).upper()
    outcode = normalized.split()[0] if " " in normalized else normalized[:-3]
    
    # Primary service areas (Hampstead and surrounding)
    primary_areas = [
        "NW1", "NW2", "NW3", "NW4", "NW5", "NW6", "NW7", "NW8", "NW9", "NW10", "NW11",
        "N1", "N2", "N3", "N4", "N5", "N6", "N7", "N8", "N10", "N11", "N12",
        "N14", "N19", "N20",
    ]
    
    # Extended service areas
    extended_areas = [
        "W1", "W2", "W3", "W4", "W5", "W9", "W10", "W11", "W12",
        "WC1", "WC2",
        "EC1", "EC2", "EC3", "EC4",
        "EN4", "EN5",
        "HA0", "HA1", "HA2", "HA3", "HA8", "HA9",
        "WD6", "WD23",
    ]
    
    return outcode in primary_areas or outcode in extended_areas


def get_area_tier(postcode: str) -> Optional[str]:
    """
    Get service tier for postcode area.
    
    Returns:
        'premium' for Hampstead core, 'standard' for extended area, None if outside
    """
    if not is_in_service_area(postcode):
        return None
    
    normalized = normalize_postcode(postcode).upper()
    outcode = normalized.split()[0] if " " in normalized else normalized[:-3]
    
    premium_areas = ["NW3", "NW6", "NW8", "N6", "NW11", "N2"]
    
    if outcode in premium_areas:
        return "premium"
    
    return "standard"


def extract_name_parts(full_name: str) -> tuple[str, str]:
    """
    Split full name into first and last name.
    
    Args:
        full_name: Full name string
        
    Returns:
        Tuple of (first_name, last_name)
    """
    parts = full_name.strip().split(None, 1)
    first_name = parts[0] if parts else ""
    last_name = parts[1] if len(parts) > 1 else ""
    return first_name, last_name


def sanitize_for_speech(text: str) -> str:
    """
    Sanitize text for TTS output.
    
    Removes/replaces characters that don't work well with TTS.
    
    Args:
        text: Raw text
        
    Returns:
        Cleaned text suitable for TTS
    """
    # Replace common symbols with spoken equivalents
    replacements = {
        "&": " and ",
        "@": " at ",
        "#": " number ",
        "%": " percent ",
        "£": " pounds ",
        "$": " dollars ",
        "€": " euros ",
        "+": " plus ",
        "=": " equals ",
        "/": " or ",
    }
    
    result = text
    for symbol, replacement in replacements.items():
        result = result.replace(symbol, replacement)
    
    # Remove multiple spaces
    result = re.sub(r"\s+", " ", result)
    
    return result.strip()


def truncate_text(text: str, max_length: int = 160, suffix: str = "...") -> str:
    """
    Truncate text to maximum length with suffix.
    
    Args:
        text: Text to truncate
        max_length: Maximum length including suffix
        suffix: Suffix to add when truncating
        
    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text
    
    return text[: max_length - len(suffix)].rsplit(" ", 1)[0] + suffix


def mask_phone_number(phone: str) -> str:
    """
    Mask phone number for logging (show only last 4 digits).
    
    Args:
        phone: Full phone number
        
    Returns:
        Masked phone number
    """
    if len(phone) < 4:
        return "****"
    return "*" * (len(phone) - 4) + phone[-4:]


def parse_budget_range(budget_text: str) -> Optional[tuple[int, int]]:
    """
    Parse budget text into numeric range.
    
    Args:
        budget_text: Budget description (e.g., "£50k-100k", "around 75000")
        
    Returns:
        Tuple of (min, max) in pounds, or None if unparseable
    """
    # Remove currency symbols and normalize
    text = budget_text.lower().replace("£", "").replace(",", "").strip()
    
    # Handle 'k' suffix
    text = re.sub(r"(\d+)k", lambda m: str(int(m.group(1)) * 1000), text)
    
    # Look for range pattern
    range_match = re.search(r"(\d+)\s*[-–to]+\s*(\d+)", text)
    if range_match:
        return int(range_match.group(1)), int(range_match.group(2))
    
    # Look for single number with "around" or similar
    single_match = re.search(r"(\d+)", text)
    if single_match:
        value = int(single_match.group(1))
        # Assume +/- 20% range
        return int(value * 0.8), int(value * 1.2)
    
    return None
