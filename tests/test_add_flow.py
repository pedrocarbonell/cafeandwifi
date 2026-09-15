from urllib.parse import urlencode

import pytest

from cafeandwifi.google import Coordinates, PlaceCandidate, ResolvedLink
from conftest import add_cafe

FORA_LINK = "https://www.google.com/maps/place/FORA+Borough/@51.50,-0.09,17z"
SHORT_LINK = "https://maps.app.goo.gl/abc123"

FORA_BOROUGH = PlaceCandidate(
    place_id="ChIJ-fora-borough",
    name="FORA - Borough",
    address="180 Borough High St, London SE1 1LB, UK",
    coordinates=Coordinates(51.5003, -0.0921),
)
FORA_CLERKENWELL = PlaceCandidate(
    place_id="ChIJ-fora-clerkenwell",
    name="FORA - Clerkenwell",
    address="9 Dallington St, London EC1V 0LN, UK",
    coordinates=Coordinates(51.5245, -0.1010),
)


def places_page(client, **params):
    return client.get("/admin/cafes/new/places?" + urlencode(params))


@pytest.mark.parametrize(
    "path",
    ["/admin/cafes/new", "/admin/cafes/new/places?q=fora", "/admin/cafes/new/details"],
)
def test_the_add_flow_needs_the_curator_signed_in(client, google, path):
    response = client.get(path)

    assert response.status_code == 302
    assert google.searches == []


def test_the_add_flow_starts_by_asking_for_a_google_maps_link(curator):
    html = curator.get("/admin/cafes/new").text

    assert 'name="link"' in html
    assert 'name="q"' in html


def test_pasting_a_link_shows_googles_top_matching_places(curator, google):
    google.links[FORA_LINK] = ResolvedLink("FORA Borough", Coordinates(51.50, -0.09))
    google.places["FORA Borough"] = [FORA_BOROUGH, FORA_CLERKENWELL]

    html = places_page(curator, link=FORA_LINK).text

    assert google.searches == ["FORA Borough"]
    assert "FORA - Borough" in html and "180 Borough High St" in html
    assert "FORA - Clerkenwell" in html and "9 Dallington St" in html


def test_a_short_link_works_like_a_full_one(curator, google):
    google.links[SHORT_LINK] = ResolvedLink("FORA Borough", None)
    google.places["FORA Borough"] = [FORA_BOROUGH]

    html = places_page(curator, link=f"  {SHORT_LINK} ").text

    assert "FORA - Borough" in html


def test_a_link_that_leads_nowhere_offers_a_search_by_name(curator, google):
    html = places_page(curator, link="https://goo.gl/maps/dead").text

    assert "could not find a place from that link" in html
    assert 'name="q"' in html
    assert google.searches == []


def test_a_link_with_no_matching_places_offers_a_search_by_name(curator, google):
    google.links[FORA_LINK] = ResolvedLink("FORA Borough", None)

    html = places_page(curator, link=FORA_LINK).text

    assert "Google has no places matching" in html
    assert 'name="q"' in html


def test_the_curator_can_search_by_name(curator, google):
    google.places["Forage Cafe Clerkenwell"] = [FORA_CLERKENWELL]

    html = places_page(curator, q="Forage Cafe Clerkenwell").text

    assert "FORA - Clerkenwell" in html


def test_when_google_is_unavailable_the_curator_is_told_why(curator, google):
    from cafeandwifi.google import GoogleUnavailable

    def unavailable(text, near=None):
        raise GoogleUnavailable("Set GOOGLE_MAPS_SERVER_KEY to search Google places.")

    google.search_places = unavailable

    response = places_page(curator, q="FORA Borough")

    assert response.status_code == 200
    assert "Set GOOGLE_MAPS_SERVER_KEY to search Google places." in response.text


def choose(curator, candidate):
    """Follow the candidate's Choose link, as the Curator would click it."""
    import re

    html = places_page(curator, q="search").text
    links = re.findall(r'href="(/admin/cafes/new/details\?[^"]+)"', html)
    link = next(l for l in links if candidate.place_id in l)
    return curator.get(link.replace("&amp;", "&"))


def test_choosing_a_place_prefills_name_place_and_position(curator, google):
    google.places["search"] = [FORA_BOROUGH, FORA_CLERKENWELL]

    html = choose(curator, FORA_CLERKENWELL).text

    assert 'name="name" id="name" required value="FORA - Clerkenwell"' in html
    assert 'name="google_place_id" value="ChIJ-fora-clerkenwell"' in html
    assert 'value="51.5245"' in html and 'value="-0.101"' in html
    assert "Google calls this place" in html
    assert "names differ" not in html


def test_choosing_a_place_then_saving_puts_the_cafe_where_the_curator_confirmed(
    client, curator, google
):
    google.places["search"] = [FORA_CLERKENWELL]
    choose(curator, FORA_CLERKENWELL)

    add_cafe(
        curator, name="Forage Cafe", google_name="FORA - Clerkenwell",
        google_place_id="ChIJ-fora-clerkenwell", latitude="51.52461", longitude="-0.10093",
    )

    cafe = client.get("/api/cafes").json["cafes"][0]
    assert (cafe["name"], cafe["google_place_id"]) == ("Forage Cafe", "ChIJ-fora-clerkenwell")
    assert (cafe["latitude"], cafe["longitude"]) == (51.52461, -0.10093)


def test_names_that_differ_from_googles_are_flagged_but_still_saved(client, curator):
    response = add_cafe(
        curator, name="Forage Cafe", google_name="FORA - Clerkenwell", coffee_price="oops"
    )

    assert "Google calls this place" in response.text
    assert "FORA - Clerkenwell" in response.text
    assert "names differ — same business?" in response.text

    response = add_cafe(curator, name="Forage Cafe", google_name="FORA - Clerkenwell")
    assert response.status_code == 302


def test_a_place_already_matched_to_another_cafe_is_warned_about_not_blocked(
    client, curator, google
):
    add_cafe(curator, name="Barbican Kitchen", google_place_id=FORA_BOROUGH.place_id)
    google.places["search"] = [FORA_BOROUGH]

    html = choose(curator, FORA_BOROUGH).text

    assert "already matched to" in html
    assert "Barbican Kitchen" in html

    response = add_cafe(curator, name="Barbican Foyer", google_place_id=FORA_BOROUGH.place_id)
    assert response.status_code == 302
    assert client.get("/api/cafes").json["count"] == 2
