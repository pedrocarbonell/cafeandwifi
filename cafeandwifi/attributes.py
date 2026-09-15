"""Attribute vocabulary shared by the catalogue, Filters and forms."""

import re

# Seating capacity bands, smallest first. The order is what "minimum" means.
SEATING_BANDS = ("0-10", "10-20", "20-30", "30-40", "40-50", "50+")

_POUNDS = re.compile(r"^£?\s*(\d{1,3})(?:\.(\d{1,2}))?$")
_BAND_SPACING = re.compile(r"\s*-\s*")


def pence_from_pounds(text: str) -> int | None:
    """"2.40", "£2.4" or "3" to pence; None when it isn't a price in pounds."""
    match = _POUNDS.match(text.strip())
    if not match:
        return None
    pounds, pence = match.groups()
    return int(pounds) * 100 + int((pence or "0").ljust(2, "0"))


def pounds_from_pence(pence: int) -> str:
    return f"{pence // 100}.{pence % 100:02d}"


def seating_band(text: str) -> str | None:
    """Normalise a free-text seating value ("0 - 10") to a band, if it is one."""
    band = _BAND_SPACING.sub("-", text.strip())
    return band if band in SEATING_BANDS else None
