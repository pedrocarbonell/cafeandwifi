"""Google gateway: the only module that talks to Google over the network.

Per ADR-0001 nothing returned from here is stored except a Place ID; names,
addresses and coordinates are shown to the Curator and then discarded (the
coordinates the Curator confirms become their own data).
"""

import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import parse_qs, unquote_plus, urlsplit


@dataclass(frozen=True)
class Coordinates:
    latitude: float
    longitude: float


@dataclass(frozen=True)
class ResolvedLink:
    """What a pasted Google Maps link says about its place, where it says anything."""

    name: str | None
    coordinates: Coordinates | None


@dataclass(frozen=True)
class PlaceCandidate:
    place_id: str
    name: str
    address: str
    coordinates: Coordinates


class GoogleGateway(Protocol):
    def resolve_link(self, url: str) -> ResolvedLink | None:
        """Follow a (possibly short) Google Maps link; None when it leads nowhere useful."""
        ...

    def search_places(
        self, text: str, near: Coordinates | None = None
    ) -> list[PlaceCandidate]:
        """Google's top matching places for a text query, best first."""
        ...


class GoogleUnavailable(Exception):
    """Google can't be asked right now: no key, quota exhausted, or network trouble."""


TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
# Only the fields the Curator needs to pick a place; they stay within Text Search Pro.
TEXT_SEARCH_FIELDS = "places.id,places.displayName,places.formattedAddress,places.location"
SEARCH_BIAS_METRES = 2000.0
TIMEOUT_SECONDS = 10

# Hosts a pasted link may point at. Nothing else is fetched, so the admin form
# can't be used to make the server request arbitrary addresses.
_LINK_HOST = re.compile(
    r"^((www|maps)\.)?google\.[a-z.]+$|^(maps\.app\.)?goo\.gl$|^g\.page$|^g\.co$"
)
_MAPS_HOST = re.compile(r"^((www|maps)\.)?google\.[a-z.]+$")
_PLACE_NAME = re.compile(r"/maps/place/([^/]+)")
_PIN = re.compile(r"!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)")
_VIEWPORT = re.compile(r"@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)")


def _is_followable(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme in ("http", "https") and bool(
        _LINK_HOST.match(parts.hostname or "")
    )


def parse_maps_url(url: str) -> ResolvedLink | None:
    """Read a Google Maps URL; None when the URL isn't Google Maps at all."""
    parts = urlsplit(url)
    if parts.hostname == "consent.google.com":
        # Visitors from the EU are bounced through a consent page first.
        target = parse_qs(parts.query).get("continue")
        return parse_maps_url(target[0]) if target else None
    if not _MAPS_HOST.match(parts.hostname or "") or not parts.path.startswith("/maps"):
        return None

    name_match = _PLACE_NAME.search(parts.path)
    name = unquote_plus(name_match.group(1)).strip() if name_match else ""
    # The !3d…!4d… pair is the place's pin; @lat,lng is only where the map was centred.
    coordinates = _PIN.search(url) or _VIEWPORT.search(url)
    return ResolvedLink(
        name=name or None,
        coordinates=(
            Coordinates(float(coordinates.group(1)), float(coordinates.group(2)))
            if coordinates
            else None
        ),
    )


def follow_redirects(url: str) -> str | None:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (cafeandwifi)"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.geturl()
    except (OSError, ValueError):
        return None


def post_json(url: str, headers: dict[str, str], body: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        try:
            message = json.load(error)["error"]["message"]
        except (ValueError, KeyError, TypeError):
            message = error.reason
        raise GoogleUnavailable(f"Google refused the place search: {message}") from error
    except OSError as error:
        raise GoogleUnavailable("Could not reach Google. Check the connection.") from error


class GoogleMapsGateway:
    def __init__(
        self,
        server_key: str,
        fetch_final_url: Callable[[str], str | None] = follow_redirects,
        post_json: Callable[[str, dict[str, str], dict], dict] = post_json,
    ):
        self._server_key = server_key
        self._fetch_final_url = fetch_final_url
        self._post_json = post_json

    def resolve_link(self, url: str) -> ResolvedLink | None:
        url = url.strip()
        if not _is_followable(url):
            return None
        direct = parse_maps_url(url)
        if direct is not None and direct.name:
            return direct
        final_url = self._fetch_final_url(url)
        return parse_maps_url(final_url) if final_url else None

    def search_places(
        self, text: str, near: Coordinates | None = None
    ) -> list[PlaceCandidate]:
        if not self._server_key:
            raise GoogleUnavailable("Set GOOGLE_MAPS_SERVER_KEY to search Google places.")
        body: dict = {"textQuery": text, "pageSize": 5, "regionCode": "GB"}
        if near is not None:
            body["locationBias"] = {
                "circle": {
                    "center": {"latitude": near.latitude, "longitude": near.longitude},
                    "radius": SEARCH_BIAS_METRES,
                }
            }
        found = self._post_json(
            TEXT_SEARCH_URL,
            {"X-Goog-Api-Key": self._server_key, "X-Goog-FieldMask": TEXT_SEARCH_FIELDS},
            body,
        )
        return [
            PlaceCandidate(
                place_id=place["id"],
                name=place.get("displayName", {}).get("text", ""),
                address=place.get("formattedAddress", ""),
                coordinates=Coordinates(
                    place["location"]["latitude"], place["location"]["longitude"]
                ),
            )
            for place in found.get("places", [])
            if "id" in place and "location" in place
        ]
