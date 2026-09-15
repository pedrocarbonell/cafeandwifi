import pytest


@pytest.fixture
def client_with(make_app):
    return lambda **config: make_app(**config).test_client()


def test_map_page_opens_without_signing_in(client_with):
    response = client_with(GOOGLE_MAPS_BROWSER_KEY="").get("/")

    assert response.status_code == 200
    assert "Cafe &amp; Wifi" in response.text


@pytest.mark.parametrize(
    "control",
    [
        'name="wifi"',
        'name="sockets"',
        'name="toilet"',
        'name="calls"',
        'name="min_seating"',
        'name="max_price_pence"',
    ],
)
def test_map_page_offers_a_filter_for_every_attribute(client_with, control):
    response = client_with(GOOGLE_MAPS_BROWSER_KEY="").get("/")

    assert control in response.text


def test_seating_filter_defaults_to_any(client_with):
    html = client_with(GOOGLE_MAPS_BROWSER_KEY="").get("/").text

    assert 'id="seating-any" value="" checked' in html


def test_without_a_maps_key_the_page_says_so_and_loads_no_map(client_with):
    html = client_with(GOOGLE_MAPS_BROWSER_KEY="").get("/").text

    assert "The map needs a Google Maps key" in html
    assert "maps.googleapis.com" not in html


def test_with_a_maps_key_the_page_loads_the_google_map(client_with):
    html = client_with(GOOGLE_MAPS_BROWSER_KEY="browser-key-123").get("/").text

    assert "maps.googleapis.com/maps/api/js?key=browser-key-123" in html
    assert "The map needs a Google Maps key" not in html
