import html as html_lib
import json
import re

import pytest

from conftest import add_cafe, cafe_id_named, csrf_token


def meta(html, prop):
    match = re.search(rf'<meta property="{prop}" content="([^"]*)">', html)
    assert match, f"no {prop} meta tag"
    return html_lib.unescape(match.group(1))


@pytest.fixture
def science_gallery(client, curator):
    add_cafe(
        curator, name="Science Gallery London", neighbourhood="London Bridge",
        has_wifi="1", has_sockets="1", has_toilet="1", calls_permitted="1",
        seating_capacity="50+", coffee_price="2.40",
    )
    return cafe_id_named(client, "Science Gallery London")


def test_a_share_link_opens_the_map_with_that_cafes_card(client, science_gallery):
    response = client.get(f"/cafes/{science_gallery}")

    assert response.status_code == 200
    assert 'id="filter-form"' in response.text
    shared = re.search(r'data-shared-cafe="([^"]+)"', response.text).group(1)
    cafe = json.loads(html_lib.unescape(shared))
    assert cafe == client.get("/api/cafes").json["cafes"][0]
    assert "Shared with you" in response.text


def test_a_share_link_previews_the_cafes_name_and_neighbourhood(client, science_gallery):
    html = client.get(f"/cafes/{science_gallery}").text

    assert meta(html, "og:title") == "Science Gallery London"
    assert meta(html, "og:description") == (
        "London Bridge · Wi-Fi · Sockets · Toilet · Calls permitted · Seating 50+ · Coffee £2.40"
    )
    assert meta(html, "og:url") == f"https://cafeandwifi.example/cafes/{science_gallery}"
    assert "<title>Science Gallery London · Cafe &amp; Wifi</title>" in html


def test_the_preview_only_mentions_attributes_the_cafe_has(client, curator):
    add_cafe(
        curator, name="Quiet Corner", neighbourhood="Peckham", has_wifi="1",
        has_sockets=None, has_toilet=None, calls_permitted=None,
        seating_capacity="0-10", coffee_price="1.80",
    )
    cafe_id = cafe_id_named(client, "Quiet Corner")

    description = meta(client.get(f"/cafes/{cafe_id}").text, "og:description")

    assert description == "Peckham · Wi-Fi · Calls forbidden · Seating 0-10 · Coffee £1.80"


def test_the_preview_image_is_the_generic_site_image_not_a_google_photo(
    client, science_gallery
):
    image = meta(client.get(f"/cafes/{science_gallery}").text, "og:image")

    assert image.startswith("https://cafeandwifi.example/static/")
    assert "google" not in image
    assert client.get(image.removeprefix("https://cafeandwifi.example")).status_code == 200


def test_the_map_page_previews_the_site_too(client):
    html = client.get("/").text

    assert meta(html, "og:title") == "Cafe & Wifi · London"


def test_a_link_to_a_removed_cafe_shows_the_london_map_with_a_note(
    client, curator, science_gallery
):
    token = csrf_token(curator, f"/admin/cafes/{science_gallery}/delete")
    curator.post(f"/admin/cafes/{science_gallery}/delete", data={"csrf_token": token})

    response = client.get(f"/cafes/{science_gallery}")

    assert response.status_code == 404
    assert "This cafe is no longer listed" in response.text
    assert 'id="filter-form"' in response.text
    assert "data-shared-cafe" not in response.text


def test_a_link_to_a_cafe_that_never_existed_is_not_found(client):
    response = client.get("/cafes/12345")

    assert response.status_code == 404
    assert "This cafe is no longer listed" in response.text


def test_a_link_to_a_cafe_without_a_position_is_treated_as_not_listed(client, curator):
    add_cafe(curator, name="Nowhere Yet", latitude="", longitude="")
    cafe_id = re.search(
        r'<tr data-cafe="Nowhere Yet">.*?/admin/cafes/(\d+)/edit', curator.get("/admin").text, re.S
    ).group(1)

    assert client.get(f"/cafes/{cafe_id}").status_code == 404
