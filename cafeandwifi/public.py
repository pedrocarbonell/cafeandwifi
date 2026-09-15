from urllib.parse import quote, urlencode

from flask import Blueprint, current_app, jsonify, render_template, request, url_for

from .attributes import pounds_from_pence
from .catalogue import Cafe, Catalogue
from .filters import InvalidFilter, parse_filters

bp = Blueprint("public", __name__)

# Minimum-seating choices a Visitor can filter on. "0-10" is left out because
# every Cafe seats at least that many, so it would mean the same as "any".
SEATING_FILTER_BANDS = [
    ("10-20", "10–20"),
    ("20-30", "20–30"),
    ("30-40", "30–40"),
    ("40-50", "40–50"),
    ("50+", "50+"),
]

# Coffee price slider, in pence. The top of the range means "any price".
PRICE_SLIDER = {"min": 150, "max": 600, "step": 10}


def catalogue() -> Catalogue:
    return current_app.extensions["catalogue"]


def site_url(path: str) -> str:
    base = current_app.config["SITE_URL"] or request.host_url
    return base.rstrip("/") + path


def google_maps_url(cafe: Cafe) -> str | None:
    if not cafe.google_place_id:
        return None
    query = urlencode(
        {"api": 1, "query": cafe.name, "query_place_id": cafe.google_place_id},
        quote_via=quote,
    )
    return f"https://www.google.com/maps/search/?{query}"


def waze_url(cafe: Cafe) -> str:
    return f"https://waze.com/ul?ll={cafe.latitude},{cafe.longitude}&navigate=yes"


def cafe_json(cafe: Cafe) -> dict:
    return {
        "id": cafe.id,
        "name": cafe.name,
        "neighbourhood": cafe.neighbourhood,
        "latitude": cafe.latitude,
        "longitude": cafe.longitude,
        "google_place_id": cafe.google_place_id,
        "has_wifi": cafe.has_wifi,
        "has_sockets": cafe.has_sockets,
        "has_toilet": cafe.has_toilet,
        "calls_permitted": cafe.calls_permitted,
        "seating_capacity": cafe.seating_capacity,
        "coffee_price_pence": cafe.coffee_price_pence,
        "google_maps_url": google_maps_url(cafe),
        "waze_url": waze_url(cafe),
        "share_url": site_url(url_for("public.share_page", cafe_id=cafe.id)),
    }


def share_description(cafe: Cafe) -> str:
    """The Open Graph description: Neighbourhood plus the Attributes that matter most."""
    parts = [cafe.neighbourhood]
    parts += [
        label
        for label, present in [
            ("Wi-Fi", cafe.has_wifi),
            ("Sockets", cafe.has_sockets),
            ("Toilet", cafe.has_toilet),
        ]
        if present
    ]
    parts.append("Calls permitted" if cafe.calls_permitted else "Calls forbidden")
    parts.append(f"Seating {cafe.seating_capacity}")
    parts.append(f"Coffee £{pounds_from_pence(cafe.coffee_price_pence)}")
    return " · ".join(parts)


def render_map(*, shared: Cafe | None = None, missing: bool = False, status: int = 200):
    preview = {
        "title": shared.name if shared else "Cafe & Wifi · London",
        "description": (
            share_description(shared)
            if shared
            else "London cafes to work from, filtered by Wi-Fi, sockets, calls and coffee price."
        ),
        "url": site_url(request.path),
        "image": site_url(url_for("static", filename="img/og-image.png")),
    }
    return (
        render_template(
            "map.html",
            seating_bands=SEATING_FILTER_BANDS,
            price_slider=PRICE_SLIDER,
            maps_key=current_app.config["GOOGLE_MAPS_BROWSER_KEY"],
            preview=preview,
            shared_cafe=cafe_json(shared) if shared else None,
            missing=missing,
        ),
        status,
    )


@bp.get("/")
def map_page():
    return render_map()


@bp.get("/api/cafes")
def cafe_list():
    try:
        filters = parse_filters(request.args)
    except InvalidFilter as error:
        return jsonify(error=str(error)), 400
    cafes = catalogue().find(filters)
    return jsonify(cafes=[cafe_json(cafe) for cafe in cafes], count=len(cafes))


@bp.get("/cafes/<int:cafe_id>")
def share_page(cafe_id: int):
    cafe = catalogue().get(cafe_id)
    if cafe is None or not cafe.positioned:
        return render_map(missing=True, status=404)
    return render_map(shared=cafe)
