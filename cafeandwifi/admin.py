import hmac

from flask import (
    Blueprint,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from . import csrf
from .attributes import SEATING_BANDS, pounds_from_pence
from .catalogue import Cafe, Catalogue, InvalidCafe
from .forms import cafe_details_from
from .google import GoogleGateway, GoogleUnavailable, PlaceCandidate

bp = Blueprint("admin", __name__, url_prefix="/admin")

OPEN_ENDPOINTS = {"admin.sign_in"}

# The glossary rule for each Attribute, shown as help text so every Cafe is
# recorded the same way.
ATTRIBUTE_RULES = {
    "has_wifi": (
        "Wi-Fi",
        "Free for customers, even if it needs a code from the receipt or has a time limit.",
    ),
    "has_sockets": (
        "Sockets",
        "A Visitor could realistically get a seat next to one. A single socket behind one table doesn't count.",
    ),
    "has_toilet": (
        "Toilet",
        "Usable without leaving the building, including a shared one in a museum or hotel.",
    ),
    "calls_permitted": (
        "Calls permitted",
        "Calls are allowed anywhere inside, such as phone booths. This is the Cafe's rule, not how noisy it is.",
    ),
}


@bp.before_request
def require_curator():
    csrf.protect()
    if request.endpoint not in OPEN_ENDPOINTS and not session.get("curator"):
        return redirect(url_for("admin.sign_in"))


def catalogue() -> Catalogue:
    return current_app.extensions["catalogue"]


def password_matches(attempt: str) -> bool:
    expected = current_app.config["ADMIN_PASSWORD"]
    # An unset password must never let anyone in, including an empty attempt.
    return bool(expected) and hmac.compare_digest(
        attempt.encode(), expected.encode()
    )


@bp.route("/sign-in", methods=["GET", "POST"])
def sign_in():
    if request.method == "GET":
        return render_template("admin/sign_in.html")
    if not password_matches(request.form.get("password", "")):
        return render_template("admin/sign_in.html", failed=True), 401
    session.clear()
    session["curator"] = True
    return redirect(url_for("admin.cafe_list"))


@bp.post("/sign-out")
def sign_out():
    session.clear()
    return redirect(url_for("public.map_page"))


@bp.get("")
def cafe_list():
    cafes = catalogue().all()
    return render_template(
        "admin/list.html",
        cafes=cafes,
        unpositioned=sum(not cafe.positioned for cafe in cafes),
        unmatched=sum(not cafe.google_place_id for cafe in cafes),
    )


def form_values(cafe: Cafe) -> dict:
    return {
        "name": cafe.name,
        "neighbourhood": cafe.neighbourhood,
        "latitude": "" if cafe.latitude is None else str(cafe.latitude),
        "longitude": "" if cafe.longitude is None else str(cafe.longitude),
        "google_place_id": cafe.google_place_id or "",
        "has_wifi": "1" if cafe.has_wifi else "",
        "has_sockets": "1" if cafe.has_sockets else "",
        "has_toilet": "1" if cafe.has_toilet else "",
        "calls_permitted": "1" if cafe.calls_permitted else "",
        "seating_capacity": cafe.seating_capacity,
        "coffee_price": pounds_from_pence(cafe.coffee_price_pence),
    }


def same_name(a: str, b: str) -> bool:
    return " ".join(a.split()).casefold() == " ".join(b.split()).casefold()


def render_cafe_form(
    values: dict,
    *,
    cafe: Cafe | None = None,
    google_pin: tuple[str, str] | None = None,
    error=None,
    status=200,
):
    place_id = values.get("google_place_id", "")
    google_name = values.get("google_name", "")
    return (
        render_template(
            "admin/cafe_form.html",
            values=values,
            cafe=cafe,
            error=error,
            google_name=google_name,
            google_pin=google_pin,
            names_differ=bool(google_name) and not same_name(values.get("name", ""), google_name),
            sharing_place=(
                catalogue().sharing_place(place_id, except_id=cafe.id if cafe else None)
                if place_id
                else []
            ),
            seating_bands=SEATING_BANDS,
            attribute_rules=ATTRIBUTE_RULES,
            neighbourhoods=catalogue().neighbourhoods(),
            maps_key=current_app.config["GOOGLE_MAPS_BROWSER_KEY"],
        ),
        status,
    )


def chosen_place() -> dict:
    """The Google place the Curator picked, carried from the candidates page."""
    args = request.args
    if not args.get("place_id"):
        return {}
    return {
        "google_place_id": args["place_id"],
        "google_name": args.get("google_name", ""),
        "latitude": args.get("latitude", ""),
        "longitude": args.get("longitude", ""),
    }


@bp.get("/cafes/new/details")
def new_cafe_details():
    place = chosen_place()
    return render_cafe_form({"name": place.get("google_name", ""), **place})


@bp.post("/cafes")
def create_cafe():
    try:
        catalogue().add(cafe_details_from(request.form))
    except InvalidCafe as error:
        return render_cafe_form(request.form.to_dict(), error=error, status=400)
    return redirect(url_for("admin.cafe_list"))


def google() -> GoogleGateway:
    return current_app.extensions["google"]


def find_places(details_endpoint: str, cafe: Cafe | None = None, **url_values):
    """Step 2 of matching a Cafe to a Google place, shared by add and re-match.

    Candidates link to the details form with the place carried in the query
    string: nothing from Google is kept beyond the Curator's next request.
    """
    link = request.args.get("link", "").strip()
    query = request.args.get("q", "").strip()
    problem = None
    candidates: list[PlaceCandidate] = []

    try:
        if link:
            resolved = google().resolve_link(link)
            if resolved is None or not resolved.name:
                problem = "We could not find a place from that link. Search for it by name instead."
            else:
                query = resolved.name
                candidates = google().search_places(query, near=resolved.coordinates)
        elif query:
            candidates = google().search_places(query)
    except GoogleUnavailable as error:
        problem = str(error)

    if query and not candidates and not problem:
        problem = f"Google has no places matching “{query}”. Try a different name."

    choices = [
        (
            candidate,
            url_for(
                details_endpoint,
                **url_values,
                place_id=candidate.place_id,
                google_name=candidate.name,
                latitude=candidate.coordinates.latitude,
                longitude=candidate.coordinates.longitude,
            ),
        )
        for candidate in candidates
    ]
    return render_template(
        "admin/find_place.html",
        cafe=cafe,
        link=link,
        query=query,
        problem=problem,
        choices=choices,
        searched=bool(link or query),
        search_action=request.path,
    )


@bp.get("/cafes/new")
@bp.get("/cafes/new/places")
def new_cafe():
    return find_places("admin.new_cafe_details")


def existing_cafe(cafe_id: int) -> Cafe:
    cafe = catalogue().get(cafe_id)
    if cafe is None:
        abort(404)
    return cafe


@bp.get("/cafes/<int:cafe_id>/edit")
def edit_cafe(cafe_id: int):
    cafe = existing_cafe(cafe_id)
    values = form_values(cafe)
    place = chosen_place()
    google_pin = None
    if place and cafe.positioned:
        # Keep the pin the Curator already confirmed; offer Google's instead of swapping it in.
        google_pin = (place.pop("latitude"), place.pop("longitude"))
    return render_cafe_form({**values, **place}, cafe=cafe, google_pin=google_pin)


@bp.post("/cafes/<int:cafe_id>")
def update_cafe(cafe_id: int):
    cafe = existing_cafe(cafe_id)
    try:
        catalogue().update(cafe_id, cafe_details_from(request.form))
    except InvalidCafe as error:
        return render_cafe_form(request.form.to_dict(), cafe=cafe, error=error, status=400)
    return redirect(url_for("admin.cafe_list"))


@bp.get("/cafes/<int:cafe_id>/place")
def rematch_cafe(cafe_id: int):
    return find_places("admin.edit_cafe", existing_cafe(cafe_id), cafe_id=cafe_id)


@bp.route("/cafes/<int:cafe_id>/delete", methods=["GET", "POST"])
def delete_cafe(cafe_id: int):
    cafe = existing_cafe(cafe_id)
    if request.method == "GET":
        return render_template("admin/delete.html", cafe=cafe)
    catalogue().delete(cafe_id)
    return redirect(url_for("admin.cafe_list"))
