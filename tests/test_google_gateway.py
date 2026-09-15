"""The real Google gateway, with its network edge replaced by recorded responses."""

import pytest

from cafeandwifi.google import (
    Coordinates,
    GoogleMapsGateway,
    GoogleUnavailable,
    PlaceCandidate,
    ResolvedLink,
)


def gateway_following(redirects: dict[str, str | None], **kwargs):
    return GoogleMapsGateway(
        server_key="server-key", fetch_final_url=lambda url: redirects.get(url), **kwargs
    )


# Recorded examples of where pasted links end up.
FULL_PLACE_LINK = (
    "https://www.google.com/maps/place/Old+Spike+Roastery/@51.4651552,-0.0666088,17z/"
    "data=!4m12!1m6!3m5!1s0x487603a3a7dd838d:0x4105b39b30a737cf!2sOld+Spike+Roastery!8m2"
    "!3d51.4651552!4d-0.0666088!3m4!1s0x487603a3a7dd838d:0x4105b39b30a737cf!8m2!3d51.4651552!4d-0.0666088"
)
VIEWPORT_ONLY_LINK = "https://www.google.com/maps/place/Ace+Hotel+London+Shoreditch/@51.5249397,-0.0774381,17z"
PIN_AWAY_FROM_VIEWPORT = (
    "https://www.google.com/maps/place/The+Barbican+Centre/@51.52,-0.09,15z/"
    "data=!4m6!3m5!1s0x48761b56fbc8ac6d:0x1a1b!8m2!3d51.5202239!4d-0.0938387!16s"
)
ENCODED_NAME_LINK = (
    "https://www.google.com/maps/place/One+%26+All+Caf%C3%A9+Peckham/@51.4700,-0.0690,17z"
)
G_PAGE_RESOLVED = (
    "https://www.google.com/maps?cid=7938473984739847&hl=en&_ga=share&g_mp=Cidnb29nbGUubWFwcy"
)
CONSENT_INTERSTITIAL = (
    "https://consent.google.com/m?continue=https://www.google.com/maps/place/Whitechapel%2BGrind/"
    "@51.5195,-0.0610,17z/data%3D!3m1!4b1!4m6!3m5!8m2!3d51.519614!4d-0.0598&gl=GB&hl=en"
)


@pytest.mark.parametrize(
    "final_url, expected",
    [
        (FULL_PLACE_LINK, ResolvedLink("Old Spike Roastery", Coordinates(51.4651552, -0.0666088))),
        (VIEWPORT_ONLY_LINK, ResolvedLink("Ace Hotel London Shoreditch", Coordinates(51.5249397, -0.0774381))),
        (PIN_AWAY_FROM_VIEWPORT, ResolvedLink("The Barbican Centre", Coordinates(51.5202239, -0.0938387))),
        (ENCODED_NAME_LINK, ResolvedLink("One & All Café Peckham", Coordinates(51.47, -0.069))),
        (G_PAGE_RESOLVED, ResolvedLink(None, None)),
        (CONSENT_INTERSTITIAL, ResolvedLink("Whitechapel Grind", Coordinates(51.519614, -0.0598))),
    ],
)
def test_a_link_resolves_to_the_places_name_and_pin(final_url, expected):
    short = "https://maps.app.goo.gl/recorded"
    gateway = gateway_following({short: final_url})

    assert gateway.resolve_link(short) == expected


def test_a_dead_link_resolves_to_nothing():
    gateway = gateway_following({})

    assert gateway.resolve_link("https://goo.gl/maps/D9nXNYK3fa1cxwpK8") is None


def test_a_link_that_leaves_google_maps_resolves_to_nothing():
    gateway = gateway_following({"https://g.page/x": "https://www.example.com/landing"})

    assert gateway.resolve_link("https://g.page/x") is None


@pytest.mark.parametrize(
    "pasted", ["not a link", "ftp://www.google.com/maps/place/x", "http://localhost:5050/admin"]
)
def test_only_web_links_are_followed(pasted):
    followed = []
    gateway = GoogleMapsGateway("key", fetch_final_url=lambda url: followed.append(url))

    assert gateway.resolve_link(pasted) is None
    assert followed == []


RECORDED_TEXT_SEARCH = {
    "places": [
        {
            "id": "ChIJ-fora-borough",
            "displayName": {"text": "FORA - Borough", "languageCode": "en"},
            "formattedAddress": "180 Borough High St, London SE1 1LB, UK",
            "location": {"latitude": 51.5003, "longitude": -0.0921},
        },
        {
            "id": "ChIJ-fora-clerkenwell",
            "displayName": {"text": "FORA - Clerkenwell"},
            "location": {"latitude": 51.5245, "longitude": -0.101},
        },
    ]
}


def test_place_search_asks_places_api_for_five_candidates_near_the_link():
    requests = []

    def post_json(url, headers, body):
        requests.append((url, headers, body))
        return RECORDED_TEXT_SEARCH

    gateway = GoogleMapsGateway("server-key", post_json=post_json)

    candidates = gateway.search_places("FORA Borough", near=Coordinates(51.5, -0.09))

    assert candidates == [
        PlaceCandidate("ChIJ-fora-borough", "FORA - Borough",
                       "180 Borough High St, London SE1 1LB, UK", Coordinates(51.5003, -0.0921)),
        PlaceCandidate("ChIJ-fora-clerkenwell", "FORA - Clerkenwell", "",
                       Coordinates(51.5245, -0.101)),
    ]
    url, headers, body = requests[0]
    assert url == "https://places.googleapis.com/v1/places:searchText"
    assert headers["X-Goog-Api-Key"] == "server-key"
    assert headers["X-Goog-FieldMask"] == (
        "places.id,places.displayName,places.formattedAddress,places.location"
    )
    assert body["textQuery"] == "FORA Borough"
    assert body["pageSize"] == 5
    assert body["locationBias"]["circle"]["center"] == {"latitude": 51.5, "longitude": -0.09}


def test_place_search_with_no_results_is_an_empty_list():
    gateway = GoogleMapsGateway("server-key", post_json=lambda *args: {})

    assert gateway.search_places("nowhere") == []


def test_place_search_without_a_server_key_says_google_is_unavailable():
    gateway = GoogleMapsGateway("", post_json=lambda *args: pytest.fail("called Google"))

    with pytest.raises(GoogleUnavailable, match="GOOGLE_MAPS_SERVER_KEY"):
        gateway.search_places("FORA Borough")
