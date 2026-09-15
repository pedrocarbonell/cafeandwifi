"""Filters: what a Visitor asks the map to show, parsed from query parameters."""

from collections.abc import Mapping
from dataclasses import dataclass

from .attributes import SEATING_BANDS

REQUIRED_ATTRIBUTES = ("wifi", "sockets", "toilet", "calls")


@dataclass(frozen=True)
class Filters:
    """A set of Filters. The defaults mean "any" for every Attribute."""

    wifi: bool = False
    sockets: bool = False
    toilet: bool = False
    calls: bool = False
    min_seating: str | None = None
    max_price_pence: int | None = None


class InvalidFilter(ValueError):
    pass


def parse_filters(params: Mapping[str, str]) -> Filters:
    """Absent or empty parameters mean "any"; anything unrecognised raises InvalidFilter."""
    required = {}
    for name in REQUIRED_ATTRIBUTES:
        value = params.get(name, "")
        if value not in ("", "1"):
            raise InvalidFilter(f"{name} must be 1 (required) or left out (any).")
        required[name] = value == "1"

    min_seating = params.get("min_seating", "") or None
    if min_seating is not None and min_seating not in SEATING_BANDS:
        raise InvalidFilter(f"min_seating must be one of {', '.join(SEATING_BANDS)}.")

    price_text = params.get("max_price_pence", "")
    if price_text and not (price_text.isascii() and price_text.isdigit()):
        raise InvalidFilter("max_price_pence must be a whole number of pence, 0 or more.")

    return Filters(
        **required,
        min_seating=min_seating,
        max_price_pence=int(price_text) if price_text else None,
    )
