"""CUIT (Argentine tax ID) validation.

A CUIT has 11 digits: a 2-digit type prefix, an 8-digit body and a check digit.
The check digit uses weights 5,4,3,2,7,6,5,4,3,2 over the first 10 digits (mod 11).
"""
import re

WEIGHTS = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
VALID_PREFIXES = {"20", "23", "24", "27", "30", "33", "34"}


def normalize(cuit: str) -> str:
    """Strip separators: '30-71234567-1' -> '30712345671'."""
    return re.sub(r"\D", "", str(cuit or ""))


def check_digit(first_ten: str) -> int | None:
    """Return the check digit for the first 10 digits, or None if no valid digit exists."""
    total = sum(int(d) * w for d, w in zip(first_ten, WEIGHTS))
    dv = 11 - (total % 11)
    if dv == 11:
        return 0
    if dv == 10:
        return None  # no valid CUIT with this body and prefix
    return dv


def is_valid(cuit: str) -> bool:
    digits = normalize(cuit)
    if len(digits) != 11 or digits[:2] not in VALID_PREFIXES:
        return False
    dv = check_digit(digits[:10])
    return dv is not None and dv == int(digits[10])


def format_cuit(digits: str) -> str:
    d = normalize(digits)
    return f"{d[:2]}-{d[2:10]}-{d[10:]}" if len(d) == 11 else d
