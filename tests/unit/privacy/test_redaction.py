"""Masking personal details."""

import pytest

from mirrorguard.privacy.redaction import PatternRedactor

redact = PatternRedactor().redact


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("mail me at asha.k+work@example.co.in please", "mail me at [EMAIL] please"),
        ("call +91 98765 43210 now", "call [PHONE] now"),
        ("my number is 9876543210", "my number is [PHONE]"),
        ("card 4111 1111 1111 1111 expires soon", "card [CARD] expires soon"),
        ("aadhaar 1234 5678 9012", "aadhaar [ID NUMBER]"),
        ("PAN ABCDE1234F", "PAN [ID NUMBER]"),
        ("see https://example.com/me?id=7 ok", "see [LINK] ok"),
        ("server 192.168.1.20 is down", "server [IP ADDRESS] is down"),
    ],
)
def test_personal_details_are_masked(text, expected):
    assert redact(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "I have not slept for 3 days and it is 2026 already",
        "I saved 150000 rupees over 12 months",
        "version 1.2.3 of the app",
        "I scored 87.5 percent",
    ],
)
def test_ordinary_numbers_are_left_alone(text):
    assert redact(text) == text
