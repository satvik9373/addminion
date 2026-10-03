"""
Phone number normalization (E.164).

The scrapers capture phone numbers in arbitrary formats:
    (415) 555-1234 | 415-555-1234 | 4155551234 | 1 415 555 1234
We normalize to the E.164 form preferred for storage:

    +14155551234

normalize_phone() returns None when it cannot normalize CONFIDENTLY (e.g. a
bare 7-digit local number with no area code). Callers must then preserve the
original value in a raw field rather than corrupting it.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Anything that is not a digit or a leading '+' is a separator / decoration.
_STRIP = re.compile(r'[^\d+]')


def normalize_phone(raw) -> Optional[str]:
    """Normalize a US phone number to E.164 ('+14155551234').

    Returns None when the value cannot be normalized confidently so the caller
    can keep the original raw string.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None

    clean = _STRIP.sub('', s)
    if not clean:
        return None

    if clean.startswith('+'):
        digits = clean[1:]
        if digits.isdigit() and 8 <= len(digits) <= 15:
            return '+' + digits
        return None  # '+' present but not a plausible E.164 -> not confident

    if not clean.isdigit():
        return None

    if len(clean) == 10 and clean[0] in '23456789':
        return '+1' + clean          # (415) 555-1234 -> +14155551234
    if len(clean) == 11 and clean[0] == '1':
        return '+1' + clean[1:]      # 1-415-555-1234 -> +14155551234
    # 7-digit local numbers, extensions, non-US lengths without a '+' ->
    # not confident; preserve the raw value instead.
    return None


def is_valid_phone(phone) -> bool:
    """True if the value normalizes to a plausible E.164 number."""
    return normalize_phone(phone) is not None
