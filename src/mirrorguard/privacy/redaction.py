"""Masks personal details in text before it is stored.

This is a pattern-based redactor. It catches details that have a recognisable
shape (emails, phone numbers, card and ID numbers, web addresses). It does not
catch names or street addresses. A deployment that needs those can plug in a
stronger redactor, such as Microsoft Presidio, behind the same `Redactor` interface.
"""

import re
from typing import Protocol


class Redactor(Protocol):
    def redact(self, text: str) -> str: ...


def _luhn_ok(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2:
            value = value * 2 - 9 if value > 4 else value * 2
        total += value
    return total % 10 == 0


def _card(match: re.Match) -> str:
    digits = re.sub(r"\D", "", match.group())
    return "[CARD]" if 13 <= len(digits) <= 19 and _luhn_ok(digits) else match.group()


# Order matters: longer and more specific shapes are masked first.
_RULES: list[tuple[re.Pattern, object]] = [
    (re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"), "[EMAIL]"),
    (re.compile(r"\bhttps?://\S+", re.IGNORECASE), "[LINK]"),
    (re.compile(r"\b\d(?:[ -]?\d){12,18}\b"), _card),
    (re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}\b"), "[ID NUMBER]"),  # Aadhaar-style
    (re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), "[ID NUMBER]"),  # PAN-style
    (re.compile(r"(?<![\w.])\+?\d[\d ()-]{8,14}\d(?![\w.])"), "[PHONE]"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[IP ADDRESS]"),
]


class PatternRedactor:
    def redact(self, text: str) -> str:
        for pattern, replacement in _RULES:
            text = pattern.sub(replacement, text)
        return text


class NoRedactor:
    def redact(self, text: str) -> str:
        return text
