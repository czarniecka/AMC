"""Masking of contact details in collected free text."""

import re

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Polish numbers: 600 100 200, +48 600-100-200, (22) 123 45 67.
PHONE = re.compile(
    r"(\+48[\s-]?)?\b\d{3}[\s-]\d{3}[\s-]\d{3}\b|\(\d{2}\)\s?\d{2,3}[\s-]?\d{2}[\s-]?\d{2,3}"
)


def mask_contacts(text: str) -> str:
    """Replace e-mail addresses with [EMAIL] and phone numbers with [TEL]."""
    return PHONE.sub("[TEL]", EMAIL.sub("[EMAIL]", text))
