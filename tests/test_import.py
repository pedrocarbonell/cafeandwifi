import re
import sqlite3

import pytest

from cafeandwifi.google import Coordinates, ResolvedLink
from conftest import sign_in

ORIGINAL_SCHEMA = """
CREATE TABLE cafe (id INTEGER PRIMARY KEY, name VARCHAR (250) NOT NULL UNIQUE,
  map_url VARCHAR (500) NOT NULL, img_url VARCHAR (500) NOT NULL, location VARCHAR (250) NOT NULL,
  has_sockets BOOLEAN NOT NULL, has_toilet BOOLEAN NOT NULL, has_wifi BOOLEAN NOT NULL,
  can_take_calls BOOLEAN NOT NULL, seats VARCHAR (250), coffee_price VARCHAR (250));
"""

OLD_SPIKE_URL = (
    "https://www.google.com/maps/place/Old+Spike+Roastery/@51.4651552,-0.0666088,17z/"
    "data=!4m12!1m6!3m5!1s0x487603a3a7dd838d:0x4105b39b30a737cf!2sOld+Spike+Roastery!8m2"
    "!3d51.4651552!4d-0.0666088"
)

# Copies of rows from the original database.
ORIGINAL_ROWS = [
    (1, "Science Gallery London", "https://g.page/scigallerylon?share",
     "https://atlondonbridge.com/Science_Gallery.jpg", "London Bridge", 1, 1, 0, 1, "50+", "£2.40"),
    (4, "Old Spike", OLD_SPIKE_URL,
     "https://lh3.googleusercontent.com/p/AF1Qip=s0", "Peckham", 1, 0, 1, 0, "0-10", "£2.80"),
    (8, "Goswell Road Coffee", "https://goo.gl/maps/D9nXNYK3fa1cxwpK8",
     "https://lh3.googleusercontent.com/p/AF1Qip=s0", "Clerkenwell", 1, 1, 1, 0, "10-20", "£2.10"),
    (18, "The Peckham Pelican", "https://goo.gl/maps/qpcpX7MWhFSS1qxH9",
     "https://lh3.googleusercontent.com/p/AF1Qip=s0", "Peckham", 1, 0, 1, 1, "0 - 10", "£2.60"),
]


@pytest.fixture
def original_database(tmp_path):
    with sqlite3.connect(tmp_path / "cafes.db") as conn:
        conn.executescript(ORIGINAL_SCHEMA)
        conn.executemany("INSERT INTO cafe VALUES (?,?,?,?,?,?,?,?,?,?,?)", ORIGINAL_ROWS)
    conn.close()


@pytest.fixture
def imported(original_database, make_app, google):
    google.links[OLD_SPIKE_URL] = ResolvedLink(
        "Old Spike Roastery", Coordinates(51.4651552, -0.0666088)
    )
    google.links["https://goo.gl/maps/D9nXNYK3fa1cxwpK8"] = ResolvedLink(
        "Goswell Road Coffee", Coordinates(51.5271, -0.1028)
    )
    google.links["https://g.page/scigallerylon?share"] = ResolvedLink(
        "Science Gallery London", None
    )
    # The Peckham Pelican's link is dead: the fake doesn't know it.
    app = make_app()
    result = app.test_cli_runner().invoke(args=["import-existing"])
    return app, result


def by_name(client):
    return {c["name"]: c for c in client.get("/api/cafes").json["cafes"]}


def test_cafes_whose_links_carry_coordinates_get_a_position(imported):
    app, result = imported

    cafes = by_name(app.test_client())

    assert result.exit_code == 0, result.output
    assert set(cafes) == {"Old Spike", "Goswell Road Coffee"}
    assert (cafes["Old Spike"]["latitude"], cafes["Old Spike"]["longitude"]) == (
        51.4651552, -0.0666088,
    )
    assert cafes["Old Spike"]["id"] == 4


def test_attributes_are_normalised(imported):
    app, _ = imported

    cafe = by_name(app.test_client())["Old Spike"]

    assert cafe["neighbourhood"] == "Peckham"
    assert (cafe["has_sockets"], cafe["has_toilet"], cafe["has_wifi"]) == (True, False, True)
    assert cafe["calls_permitted"] is False
    assert cafe["seating_capacity"] == "0-10"
    assert cafe["coffee_price_pence"] == 280
    assert cafe["google_place_id"] is None


def test_every_cafe_is_carried_over_and_unpositioned_ones_are_flagged(imported):
    app, result = imported
    client = app.test_client()
    sign_in(client)

    html = client.get("/admin").text

    assert "4 Cafes" in html
    assert "2 need a position · 4 need a Google place" in html
    assert "Imported 4 Cafes; 2 got a Position" in result.output


def test_calls_and_spaced_seat_values_carry_over(imported):
    app, _ = imported
    client = app.test_client()
    sign_in(client)

    pelican_id = re.search(
        r'<tr data-cafe="The Peckham Pelican">.*?/admin/cafes/(\d+)/edit',
        client.get("/admin").text, re.S,
    ).group(1)
    form = client.get(f"/admin/cafes/{pelican_id}/edit").text

    assert re.search(r'value="0-10"\s+checked', form)
    assert re.search(r'name="calls_permitted" id="calls_permitted" value="1"\s+checked', form)
    assert 'value="2.60"' in form


def test_importing_twice_changes_nothing(imported):
    app, _ = imported

    again = app.test_cli_runner().invoke(args=["import-existing"])

    assert again.exit_code != 0
    assert "already been imported" in again.output
    assert app.test_client().get("/api/cafes").json["count"] == 2


def test_unrecognisable_values_stop_the_import_before_anything_changes(
    tmp_path, make_app
):
    with sqlite3.connect(tmp_path / "cafes.db") as conn:
        conn.executescript(ORIGINAL_SCHEMA)
        conn.execute(
            "INSERT INTO cafe VALUES (1,'Odd','u','i','Soho',1,1,1,1,'loads','£2.40')"
        )
    conn.close()
    app = make_app()

    result = app.test_cli_runner().invoke(args=["import-existing"])

    assert result.exit_code != 0
    assert "Odd" in result.output and "loads" in result.output
    again = app.test_cli_runner().invoke(args=["import-existing"])
    assert "loads" in again.output
    assert "already been imported" not in again.output
