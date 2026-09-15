"""Turning the Curator's Cafe form into CafeDetails, with messages for mistakes."""

from .attributes import pence_from_pounds
from .catalogue import CafeDetails, InvalidCafe

BOOLEAN_ATTRIBUTES = ("has_wifi", "has_sockets", "has_toilet", "calls_permitted")


def _coordinate(form, field: str) -> float | None:
    text = form.get(field, "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        raise InvalidCafe("position", "Latitude and longitude must be numbers.")


def cafe_details_from(form) -> CafeDetails:
    """Raises InvalidCafe for anything the form can't express as a Cafe."""
    price = pence_from_pounds(form.get("coffee_price", ""))
    if price is None:
        raise InvalidCafe("coffee_price", "Enter the Coffee price in pounds, like 2.80.")
    return CafeDetails(
        name=form.get("name", ""),
        neighbourhood=form.get("neighbourhood", ""),
        latitude=_coordinate(form, "latitude"),
        longitude=_coordinate(form, "longitude"),
        google_place_id=form.get("google_place_id") or None,
        seating_capacity=form.get("seating_capacity", ""),
        coffee_price_pence=price,
        **{name: form.get(name) == "1" for name in BOOLEAN_ATTRIBUTES},
    )
