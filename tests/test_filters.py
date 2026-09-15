from urllib.parse import quote

import pytest

from conftest import add_cafe


def names(client, query):
    response = client.get(f"/api/cafes?{query}")
    assert response.status_code == 200, response.text
    return sorted(c["name"] for c in response.json["cafes"])


@pytest.fixture
def cafes(client, curator):
    add_cafe(
        curator, name="Everything", has_wifi="1", has_sockets="1", has_toilet="1",
        calls_permitted="1", seating_capacity="50+", coffee_price="3.00",
    )
    add_cafe(
        curator, name="Tiny and cheap", has_wifi=None, has_sockets=None, has_toilet=None,
        calls_permitted=None, seating_capacity="0-10", coffee_price="1.80",
    )
    add_cafe(
        curator, name="Wifi and calls", has_wifi="1", has_sockets=None, has_toilet="1",
        calls_permitted="1", seating_capacity="20-30", coffee_price="2.40",
    )
    add_cafe(
        curator, name="Sockets only", has_wifi=None, has_sockets="1", has_toilet=None,
        calls_permitted=None, seating_capacity="30-40", coffee_price="2.41",
    )
    return client


def test_no_filters_match_every_cafe(cafes):
    assert names(cafes, "") == ["Everything", "Sockets only", "Tiny and cheap", "Wifi and calls"]


@pytest.mark.parametrize(
    "query, expected",
    [
        ("wifi=1", ["Everything", "Wifi and calls"]),
        ("sockets=1", ["Everything", "Sockets only"]),
        ("toilet=1", ["Everything", "Wifi and calls"]),
        ("calls=1", ["Everything", "Wifi and calls"]),
    ],
)
def test_requiring_an_attribute_hides_cafes_without_it(cafes, query, expected):
    assert names(cafes, query) == expected


@pytest.mark.parametrize(
    "band, expected",
    [
        ("0-10", ["Everything", "Sockets only", "Tiny and cheap", "Wifi and calls"]),
        ("10-20", ["Everything", "Sockets only", "Wifi and calls"]),
        ("30-40", ["Everything", "Sockets only"]),
        ("40-50", ["Everything"]),
        ("50+", ["Everything"]),
    ],
)
def test_minimum_seating_hides_smaller_cafes(cafes, band, expected):
    assert names(cafes, f"min_seating={quote(band)}") == expected


def test_maximum_coffee_price_includes_cafes_at_exactly_that_price(cafes):
    assert names(cafes, "max_price_pence=240") == ["Tiny and cheap", "Wifi and calls"]


def test_filters_combine_so_only_cafes_satisfying_all_remain(cafes):
    assert names(cafes, "wifi=1&calls=1&max_price_pence=250") == ["Wifi and calls"]
    assert names(cafes, "sockets=1&min_seating=40-50") == ["Everything"]


def test_nothing_matching_gives_an_empty_list_with_a_zero_count(cafes):
    body = cafes.get("/api/cafes?calls=1&max_price_pence=100").json

    assert body == {"cafes": [], "count": 0}


def test_empty_parameters_mean_any(cafes):
    query = "wifi=&sockets=&toilet=&calls=&min_seating=&max_price_pence="

    assert len(names(cafes, query)) == 4


@pytest.mark.parametrize(
    "query",
    [
        "wifi=yes",
        "calls=0",
        "min_seating=huge",
        "min_seating=0 - 10",
        "max_price_pence=-1",
        "max_price_pence=2.40",
        "max_price_pence=cheap",
        "max_price_pence=%C2%B2",
    ],
)
def test_invalid_filter_values_are_rejected(cafes, query):
    response = cafes.get(f"/api/cafes?{query}")

    assert response.status_code == 400
    assert "error" in response.json
