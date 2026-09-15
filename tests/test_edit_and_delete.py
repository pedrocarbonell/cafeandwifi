import re
from urllib.parse import urlencode

import pytest

from cafeandwifi.google import Coordinates, PlaceCandidate
from conftest import CAFE_FORM, add_cafe, cafe_id_named, csrf_token


@pytest.fixture
def old_spike(client, curator):
    add_cafe(curator, name="Old Spike", neighbourhood="Peckham", coffee_price="2.80")
    return cafe_id_named(client, "Old Spike")


def edit(curator, cafe_id, **fields):
    data = {k: v for k, v in {**CAFE_FORM, **fields}.items() if v is not None}
    data["csrf_token"] = csrf_token(curator, f"/admin/cafes/{cafe_id}/edit")
    return curator.post(f"/admin/cafes/{cafe_id}", data=data)


def test_the_edit_form_shows_the_cafes_current_details(curator, old_spike):
    html = curator.get(f"/admin/cafes/{old_spike}/edit").text

    assert 'name="name" id="name" required value="Old Spike"' in html
    assert 'value="2.80"' in html
    assert re.search(r'value="20-30"\s+checked', html)


def test_the_curator_edits_attributes_and_the_name(client, curator, old_spike):
    response = edit(
        curator, old_spike, name="Old Spike Roastery", has_wifi=None,
        coffee_price="3.10", seating_capacity="10-20",
    )

    assert response.status_code == 302
    cafe = client.get("/api/cafes").json["cafes"][0]
    assert cafe["id"] == old_spike
    assert cafe["name"] == "Old Spike Roastery"
    assert cafe["has_wifi"] is False
    assert (cafe["coffee_price_pence"], cafe["seating_capacity"]) == (310, "10-20")


def test_the_curator_moves_a_cafes_pin(client, curator, old_spike):
    edit(curator, old_spike, latitude="51.4655", longitude="-0.0670")

    cafe = client.get("/api/cafes").json["cafes"][0]
    assert (cafe["latitude"], cafe["longitude"]) == (51.4655, -0.067)


def test_an_edit_keeping_the_same_name_is_not_a_duplicate(curator, old_spike):
    assert edit(curator, old_spike, name="Old Spike").status_code == 302


def test_renaming_to_another_cafes_name_is_refused(client, curator, old_spike):
    add_cafe(curator, name="Whitechapel Grind")

    response = edit(curator, old_spike, name="Whitechapel Grind")

    assert response.status_code == 400
    assert "There is already a Cafe called" in response.text
    assert cafe_id_named(client, "Old Spike") == old_spike


def test_editing_a_cafe_that_does_not_exist_is_not_found(curator):
    assert curator.get("/admin/cafes/999/edit").status_code == 404
    assert edit_missing(curator).status_code == 404


def edit_missing(curator):
    data = {**CAFE_FORM, "csrf_token": csrf_token(curator, "/admin")}
    return curator.post("/admin/cafes/999", data=data)


def test_the_curator_redoes_a_cafes_place_match(client, curator, google, old_spike):
    roastery = PlaceCandidate(
        "ChIJ-old-spike-roastery", "Old Spike Roastery", "54 Peckham Rye, London SE15 4JR",
        Coordinates(51.46516, -0.06661),
    )
    google.places["Old Spike Roastery"] = [roastery]

    html = curator.get(
        f"/admin/cafes/{old_spike}/place?" + urlencode({"q": "Old Spike Roastery"})
    ).text
    choose = re.search(rf'href="(/admin/cafes/{old_spike}/edit\?[^"]+)"', html).group(1)
    form = curator.get(choose.replace("&amp;", "&")).text

    assert 'name="name" id="name" required value="Old Spike"' in form
    assert 'name="google_place_id" value="ChIJ-old-spike-roastery"' in form
    assert "names differ — same business?" in form
    # The Curator's confirmed pin stays; Google's is offered, not swapped in.
    assert 'name="latitude" id="latitude" inputmode="decimal"\n                   value="51.4651552"' in form
    assert 'data-google-pin="51.46516,-0.06661"' in form

    edit(
        curator, old_spike, name="Old Spike", google_place_id="ChIJ-old-spike-roastery",
        latitude="51.46516", longitude="-0.06661",
    )
    cafe = client.get("/api/cafes").json["cafes"][0]
    assert cafe["google_place_id"] == "ChIJ-old-spike-roastery"
    assert cafe["latitude"] == 51.46516


def test_deleting_asks_for_confirmation_first(client, curator, old_spike):
    html = curator.get(f"/admin/cafes/{old_spike}/delete").text

    assert "Delete Old Spike?" in html
    assert "Keep it" in html
    assert client.get("/api/cafes").json["count"] == 1


def test_a_deleted_cafe_disappears_from_the_map_and_the_list(client, curator, old_spike):
    token = csrf_token(curator, f"/admin/cafes/{old_spike}/delete")

    response = curator.post(f"/admin/cafes/{old_spike}/delete", data={"csrf_token": token})

    assert response.status_code == 302
    assert client.get("/api/cafes").json["count"] == 0
    assert "Old Spike" not in curator.get("/admin").text


def test_deleting_without_a_csrf_token_is_rejected(client, curator, old_spike):
    response = curator.post(f"/admin/cafes/{old_spike}/delete")

    assert response.status_code == 400
    assert client.get("/api/cafes").json["count"] == 1


def test_redoing_the_match_of_an_unpositioned_cafe_starts_from_googles_pin(curator, google):
    add_cafe(curator, name="Unplaced", latitude="", longitude="")
    cafe_id = re.search(
        r'<tr data-cafe="Unplaced">.*?/admin/cafes/(\d+)/edit', curator.get("/admin").text, re.S
    ).group(1)

    form = curator.get(
        f"/admin/cafes/{cafe_id}/edit?place_id=ChIJ-x&google_name=Unplaced&latitude=51.5&longitude=-0.1"
    ).text

    assert 'value="51.5"' in form and 'value="-0.1"' in form
