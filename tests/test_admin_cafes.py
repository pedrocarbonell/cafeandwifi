import re

import pytest

from conftest import add_cafe, cafe_id_named, csrf_token


def test_saving_a_new_cafe_returns_to_the_list_and_puts_it_on_the_map(client, curator):
    response = add_cafe(curator, name="Goswell Road Coffee")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin")
    assert "Goswell Road Coffee" in curator.get("/admin").text
    assert cafe_id_named(client, "Goswell Road Coffee")


def test_adding_a_cafe_without_a_csrf_token_is_rejected(client, curator):
    from conftest import CAFE_FORM

    response = curator.post("/admin/cafes", data=CAFE_FORM)

    assert response.status_code == 400
    assert client.get("/api/cafes").json["count"] == 0


def test_a_visitor_cannot_add_a_cafe(client):
    from conftest import CAFE_FORM

    token = csrf_token(client, "/admin/sign-in")
    response = client.post("/admin/cafes", data={**CAFE_FORM, "csrf_token": token})

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/sign-in")
    assert client.get("/api/cafes").json["count"] == 0


def test_cafe_names_are_unique(client, curator):
    add_cafe(curator, name="Old Spike")

    response = add_cafe(curator, name="old spike ")

    assert response.status_code == 400
    assert "There is already a Cafe called" in response.text
    assert client.get("/api/cafes").json["count"] == 1


def test_several_cafes_may_share_a_google_place(client, curator):
    add_cafe(curator, name="Barbican Kitchen", google_place_id="ChIJ-barbican")
    add_cafe(curator, name="Barbican Foyer", google_place_id="ChIJ-barbican")

    assert client.get("/api/cafes").json["count"] == 2


@pytest.mark.parametrize(
    "fields, message",
    [
        ({"name": "  "}, "Give the Cafe a name"),
        ({"neighbourhood": ""}, "Choose a Neighbourhood"),
        ({"seating_capacity": "100+"}, "Choose a Seating capacity band"),
        ({"seating_capacity": None}, "Choose a Seating capacity band"),
        ({"coffee_price": "cheap"}, "Coffee price in pounds"),
        ({"coffee_price": "-2.00"}, "Coffee price in pounds"),
        ({"latitude": "51.5", "longitude": ""}, "both latitude and longitude"),
        ({"latitude": "north"}, "must be numbers"),
    ],
)
def test_invalid_cafes_are_not_saved_and_the_form_says_why(client, curator, fields, message):
    response = add_cafe(curator, **{"neighbourhood": "Keep my typing", **fields})

    assert response.status_code == 400
    assert message in response.text
    if "neighbourhood" not in fields:
        assert 'value="Keep my typing"' in response.text
    assert client.get("/api/cafes").json["count"] == 0


@pytest.mark.parametrize(
    "typed, pence",
    [("2.40", 240), ("£2.40", 240), ("2.4", 240), ("3", 300), ("0.95", 95)],
)
def test_coffee_price_is_entered_in_pounds_and_pence(client, curator, typed, pence):
    add_cafe(curator, coffee_price=typed)

    assert client.get("/api/cafes").json["cafes"][0]["coffee_price_pence"] == pence


def test_the_form_states_each_attributes_rule(curator):
    html = curator.get("/admin/cafes/new/details").text

    assert "Free for customers, even if it needs a code" in html
    assert "A Visitor could realistically get a seat next to one" in html
    assert "Usable without leaving the building" in html
    assert "Calls are allowed anywhere inside" in html


def test_seating_capacity_is_chosen_from_the_fixed_bands(curator):
    html = curator.get("/admin/cafes/new/details").text

    bands = re.findall(r'name="seating_capacity"[^>]*value="([^"]+)"', html)
    assert bands == ["0-10", "10-20", "20-30", "30-40", "40-50", "50+"]


def test_neighbourhoods_already_in_use_are_suggested(curator):
    add_cafe(curator, name="One", neighbourhood="Peckham")
    add_cafe(curator, name="Two", neighbourhood="Shoreditch")
    add_cafe(curator, name="Three", neighbourhood="Peckham")

    html = curator.get("/admin/cafes/new/details").text

    suggestions = re.findall(r'<option value="([^"]+)">', html)
    assert suggestions == ["Peckham", "Shoreditch"]


def test_the_cafe_list_shows_every_cafe_and_flags_what_needs_fixing(curator):
    add_cafe(curator, name="Complete")
    add_cafe(curator, name="Unplaced", latitude="", longitude="")
    add_cafe(curator, name="Unmatched", google_place_id="")
    add_cafe(curator, name="Neither", latitude="", longitude="", google_place_id="")

    html = curator.get("/admin").text

    assert "4 Cafes" in html
    assert "2 need a position · 2 need a Google place" in html
    rows = dict(re.findall(r'<tr data-cafe="([^"]+)">(.*?)</tr>', html, re.S))
    assert set(rows) == {"Complete", "Unplaced", "Unmatched", "Neither"}
    assert "no position" not in rows["Complete"] and "no Google place" not in rows["Complete"]
    assert "no position" in rows["Unplaced"] and "no Google place" not in rows["Unplaced"]
    assert "no Google place" in rows["Unmatched"] and "no position" not in rows["Unmatched"]
    assert "no position" in rows["Neither"] and "no Google place" in rows["Neither"]
