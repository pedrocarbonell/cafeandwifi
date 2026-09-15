from conftest import add_cafe


def test_a_cafe_the_curator_adds_appears_with_all_its_details(client, curator):
    add_cafe(
        curator,
        name="Old Spike",
        neighbourhood="Peckham",
        latitude="51.4651552",
        longitude="-0.0666088",
        google_place_id="ChIJ-old-spike",
        has_wifi="1",
        has_sockets=None,
        has_toilet="1",
        calls_permitted=None,
        seating_capacity="0-10",
        coffee_price="2.80",
    )

    body = client.get("/api/cafes").json

    assert body["count"] == 1
    cafe = body["cafes"][0]
    assert cafe == {
        "id": cafe["id"],
        "name": "Old Spike",
        "neighbourhood": "Peckham",
        "latitude": 51.4651552,
        "longitude": -0.0666088,
        "google_place_id": "ChIJ-old-spike",
        "has_wifi": True,
        "has_sockets": False,
        "has_toilet": True,
        "calls_permitted": False,
        "seating_capacity": "0-10",
        "coffee_price_pence": 280,
        "google_maps_url": "https://www.google.com/maps/search/?api=1&query=Old%20Spike&query_place_id=ChIJ-old-spike",
        "waze_url": "https://waze.com/ul?ll=51.4651552,-0.0666088&navigate=yes",
        "share_url": f"https://cafeandwifi.example/cafes/{cafe['id']}",
    }


def test_the_map_is_empty_before_any_cafe_is_added(client):
    assert client.get("/api/cafes").json == {"cafes": [], "count": 0}


def test_a_cafe_without_a_position_is_not_on_the_map(client, curator):
    add_cafe(curator, name="Somewhere", latitude="", longitude="")
    add_cafe(curator, name="Placed")

    names = [c["name"] for c in client.get("/api/cafes").json["cafes"]]

    assert names == ["Placed"]


def test_a_cafe_without_a_google_place_has_no_google_maps_link(client, curator):
    add_cafe(curator, google_place_id="")

    cafe = client.get("/api/cafes").json["cafes"][0]

    assert cafe["google_place_id"] is None
    assert cafe["google_maps_url"] is None
    assert cafe["waze_url"].startswith("https://waze.com/ul?ll=")


def test_share_links_fall_back_to_the_address_the_site_was_reached_on(
    make_app, google
):
    from conftest import sign_in

    client = make_app(SITE_URL="").test_client()
    sign_in(client)
    add_cafe(client)

    cafe = client.get("/api/cafes").json["cafes"][0]

    assert cafe["share_url"] == f"http://localhost/cafes/{cafe['id']}"


def test_cafes_are_listed_in_name_order(client, curator):
    for name in ["Whitechapel Grind", "Ace Hotel Shoreditch", "Goswell Road Coffee"]:
        add_cafe(curator, name=name)

    names = [c["name"] for c in client.get("/api/cafes").json["cafes"]]

    assert names == ["Ace Hotel Shoreditch", "Goswell Road Coffee", "Whitechapel Grind"]
