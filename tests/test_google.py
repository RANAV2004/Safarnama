# Google Places live mode, with fake Google responses
import httpx
import pytest

from app import explore
from app import google_places as google


class Reply:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def json(self):
        return self.data


def place(pid, name, rating, count, **kw):
    return {
        "id": pid,
        "displayName": {"text": name},
        "shortFormattedAddress": "Old Manali",
        "location": {"latitude": 32.25, "longitude": 77.18},
        "rating": rating,
        "userRatingCount": count,
        "googleMapsUri": f"https://maps.google.com/?cid={pid}",
        **kw,
    }


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-key")
    google._memory.clear()
    google.photos.clear()
    calls = []

    def post(url, json, headers, timeout):
        calls.append(json)
        assert headers["X-Goog-Api-Key"] == "test-key" and "places.displayName" in headers["X-Goog-FieldMask"]
        if "searchAlongRouteParameters" in json:
            return Reply({"places": [place("r1", "Jogini Falls", 4.6, 900)]})
        return Reply(
            {
                "places": [
                    place("a", "Busy Cafe", 4.2, 5000, priceLevel="PRICE_LEVEL_MODERATE"),
                    place(
                        "b",
                        "Small Gem",
                        4.9,
                        12,
                        editorialSummary={"text": "Cosy spot by the river."},
                        regularOpeningHours={"weekdayDescriptions": ["Monday: 9 AM to 9 PM"]},
                        photos=[{"name": "places/b/photos/p1", "authorAttributions": [{"displayName": "Asha"}]}],
                    ),
                ]
            }
        )

    monkeypatch.setattr(google.httpx, "post", post)
    yield calls
    google._memory.clear()
    google.photos.clear()


def test_off_without_a_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    assert not google.enabled()
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "k")
    monkeypatch.setenv("PLACES_MODE", "off")
    assert not google.enabled()


def test_city_comes_from_google_and_is_kept_for_an_hour(live, client):
    manali = client.get("/explore/Manali").json()
    assert manali["places_from"] == "Google Maps" and "Manali" in manali["info"]["intro"]
    cafes = manali["sections"]["cafe"]
    assert [c["name"] for c in cafes] == ["Busy Cafe", "Small Gem"]
    busy, gem = cafes
    assert busy["price"] == "₹₹" and busy["text"] == "Rated 4.2 by 5,000 people on Google."
    assert (
        gem["text"] == "Cosy spot by the river."
        and gem["hours"] == "Monday: 9 AM to 9 PM"
        and gem["photo_by"] == "Asha"
    )
    assert gem["maps_url"] == "https://maps.google.com/?cid=b" and gem["id"] == "g-b"
    assert (
        live[0]["locationBias"]["circle"]["radius"] == 20000.0
        and live[0]["textQuery"] == "top tourist attractions in Manali"
    )
    client.get("/explore/Manali")
    assert len(live) == 4


def test_any_city_works_with_google(live, client):
    spiti = client.get("/explore/Spiti").json()
    assert spiti["places_from"] == "Google Maps" and spiti["info"] == {} and spiti["top"]


def test_google_failure_falls_back_to_wikivoyage(monkeypatch, client):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "bad")
    google._memory.clear()
    monkeypatch.setattr(google.httpx, "post", lambda *a, **k: Reply({"error": {}}, 403))
    assert client.get("/explore/Manali").json()["places_from"] == "Wikivoyage"

    def down(*a, **k):
        raise httpx.ConnectTimeout("slow")

    google._memory.clear()
    monkeypatch.setattr(google.httpx, "post", down)
    assert client.get("/explore/Manali").json()["places_from"] == "Wikivoyage"
    assert client.get("/explore/Spiti").status_code == 404
    google._memory.clear()


def test_google_photos(live, client, monkeypatch):
    client.get("/explore/Manali")
    seen = []

    def get(url, headers, timeout):
        seen.append(url)
        return Reply({"photoUri": "https://lh3.googleusercontent.com/abc"})

    monkeypatch.setattr(google.httpx, "get", get)
    shot = client.get("/media/g-b").json()
    assert shot["image"] == "https://lh3.googleusercontent.com/abc" and "skipHttpRedirect=true" in seen[0]
    assert client.get("/media/g-a").json()["image"] is None
    assert client.get("/media/g-b").json()["image"] == shot["image"] and len(seen) == 1


def test_stops_along_the_real_road(live, monkeypatch):
    monkeypatch.setattr(google.httpx, "get", lambda url, timeout: Reply({"routes": [{"geometry": "abc"}]}))
    out = explore.stops("Mumbai", "Goa")
    assert out["source"].startswith("Google Maps") and [s["name"] for s in out["stops"]] == ["Jogini Falls"]
    along = [c for c in live if "searchAlongRouteParameters" in c]
    assert along and along[0]["searchAlongRouteParameters"]["polyline"]["encodedPolyline"] == "abc"


def test_no_road_means_stored_stops(live, monkeypatch):
    def down(*a, **k):
        raise httpx.ConnectTimeout("slow")

    monkeypatch.setattr(google.httpx, "get", down)
    out = explore.stops("Mumbai", "Goa")
    assert not out["source"].startswith("Google Maps")


def test_meals_use_google_food(live):
    days = [{"date": "2026-11-27", "items": []}]
    out = explore.meals("Manali", days, (32.25, 77.18))
    assert out and {p["source"] for p in out[0]["picks"]} == {"Google Maps"}


def test_memory_is_trimmed(monkeypatch):
    google._memory.clear()
    for i in range(510):
        google.remembered(f"k{i}", lambda i=i: i, now=1000 + i)
    assert len(google._memory) <= 500
    assert google.remembered("k509", lambda: "new", now=1509) == 509
    assert google.remembered("k509", lambda: "new", now=1509 + google.KEEP_SECONDS + 1) == "new"
    google._memory.clear()
