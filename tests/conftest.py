import re

import pytest

from cafeandwifi import create_app
from cafeandwifi.google import PlaceCandidate, ResolvedLink

PASSWORD = "correct horse battery staple"


class FakeGoogle:
    """In-memory stand-in for the Google gateway, so no test touches the network."""

    def __init__(self):
        self.links: dict[str, ResolvedLink] = {}
        self.places: dict[str, list[PlaceCandidate]] = {}
        self.searches: list[str] = []

    def resolve_link(self, url):
        return self.links.get(url)

    def search_places(self, text, near=None):
        self.searches.append(text)
        return self.places.get(text, [])


@pytest.fixture
def google():
    return FakeGoogle()


@pytest.fixture
def make_app(tmp_path, google):
    def make(**config):
        return create_app(
            {
                "TESTING": True,
                "DATABASE": str(tmp_path / "cafes.db"),
                "SECRET_KEY": "test-secret",
                "ADMIN_PASSWORD": PASSWORD,
                "SITE_URL": "https://cafeandwifi.example",
                "GOOGLE_MAPS_BROWSER_KEY": "",
                **config,
            },
            google=google,
        )

    return make


@pytest.fixture
def app(make_app):
    return make_app()


@pytest.fixture
def client(app):
    return app.test_client()


def csrf_token(client, path):
    html = client.get(path).text
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, f"no CSRF token on {path}"
    return match.group(1)


def sign_in(client, password=PASSWORD):
    token = csrf_token(client, "/admin/sign-in")
    return client.post(
        "/admin/sign-in", data={"password": password, "csrf_token": token}
    )


@pytest.fixture
def curator(client):
    sign_in(client)
    return client


CAFE_FORM = {
    "name": "Old Spike",
    "neighbourhood": "Peckham",
    "latitude": "51.4651552",
    "longitude": "-0.0666088",
    "google_place_id": "ChIJjYPdp6MDdkgRzzenMJuzBUE",
    "has_wifi": "1",
    "has_sockets": "1",
    "has_toilet": "1",
    "calls_permitted": "1",
    "seating_capacity": "20-30",
    "coffee_price": "2.80",
}


def add_cafe(curator, **fields):
    """Add a Cafe through the admin form. Unticked checkboxes are passed as None."""
    data = {**CAFE_FORM, **fields}
    data = {k: v for k, v in data.items() if v is not None}
    data["csrf_token"] = csrf_token(curator, "/admin/cafes/new/details")
    return curator.post("/admin/cafes", data=data)


def cafe_id_named(client, name):
    for cafe in client.get("/api/cafes").json["cafes"]:
        if cafe["name"] == name:
            return cafe["id"]
    raise AssertionError(f"{name} is not on the map")
