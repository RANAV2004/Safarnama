# admin and saved trip tests
import pytest

from tests.conftest import sign_in

TRIP = {
    "origin": "Delhi",
    "destination": "Jaipur",
    "start_date": "2026-11-27",
    "end_date": "2026-11-29",
    "budget_inr": 15000,
    "travellers": 2,
}


@pytest.fixture
def boss(client, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "boss@x.com")
    return sign_in(client, "boss@x.com", "Boss")


def me(client, head):
    return client.get("/auth/me", headers=head).json()


def test_plans_are_saved_and_updated(client, auth):
    first = client.post("/plan", json=TRIP, headers=auth).json()
    again = client.post(f"/plan?trip_id={first['trip_id']}", json={**TRIP, "budget_inr": 18000}, headers=auth).json()
    assert again["trip_id"] == first["trip_id"]
    other = client.post("/plan", json={**TRIP, "destination": "Udaipur"}, headers=auth).json()
    mine = client.get("/trips", headers=auth).json()
    assert [t["id"] for t in mine] == [other["trip_id"], first["trip_id"]] and mine[1]["total_cost"] == again[
        "total_cost"
    ]
    full = client.get(f"/trips/{first['trip_id']}", headers=auth).json()
    assert full["plan"]["request"]["budget_inr"] == 18000 and full["plan"]["trip_id"] == first["trip_id"]


def test_trips_are_private(client, auth):
    tid = client.post("/plan", json=TRIP, headers=auth).json()["trip_id"]
    stranger = sign_in(client)
    assert client.get(f"/trips/{tid}", headers=stranger).status_code == 404
    assert client.delete(f"/trips/{tid}", headers=stranger).status_code == 404
    ghost = client.post(f"/plan?trip_id={tid}", json=TRIP, headers=stranger).json()["trip_id"]
    assert ghost != tid
    assert client.delete(f"/trips/{tid}", headers=auth).json() == {"deleted": tid}
    assert client.get(f"/trips/{tid}", headers=auth).status_code == 404


def test_stream_and_revise_save_trips(client, auth):
    import json

    body = client.post("/plan/stream", json=TRIP, headers=auth).text
    done = [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")][-1]
    tid = done["plan"]["trip_id"]
    res = client.post(
        "/plan/revise", json={"plan": done["plan"], "message": "remove hawa mahal", "trip_id": tid}, headers=auth
    ).json()
    assert res["plan"]["trip_id"] == tid and len(client.get("/trips", headers=auth).json()) == 1


def test_only_admins_get_in(client, auth):
    for path in ("/admin/stats", "/admin/users", "/admin/trips", "/admin/users/10000"):
        assert client.get(path, headers=auth).status_code == 403
    assert client.get("/admin/users").status_code == 401


def test_admin_finds_users_and_their_trips(client, auth, boss):
    u = me(client, auth)
    tid = client.post("/plan", json=TRIP, headers=auth).json()["trip_id"]
    assert client.get("/admin/stats", headers=boss).json() == {"users": 2, "banned": 0, "itineraries": 1}
    by_id = client.get(f"/admin/users?q=%23{u['id']}", headers=boss).json()
    assert [x["id"] for x in by_id] == [u["id"]] and by_id[0]["trips"] == 1
    assert [x["name"] for x in client.get("/admin/users?q=boss", headers=boss).json()] == ["Boss"]
    assert len(client.get("/admin/users", headers=boss).json()) == 2
    detail = client.get(f"/admin/users/{u['id']}", headers=boss).json()
    assert detail["itineraries"][0]["id"] == tid and detail["trips"] == 1
    assert client.get(f"/trips/{tid}", headers=boss).json()["destination"] == "Jaipur"
    assert client.get("/admin/users/1", headers=boss).status_code == 404
    trips = client.get("/admin/trips", headers=boss).json()
    assert trips[0]["user_name"] == "Test User" and trips[0]["user_id"] == u["id"] and trips[0]["budget_inr"] == 15000
    assert client.get(f"/admin/trips?q={u['id']}", headers=boss).json()[0]["id"] == tid
    assert client.get("/admin/trips?q=jaipur", headers=boss).json()[0]["id"] == tid
    assert client.get("/admin/trips?q=goa", headers=boss).json() == []


def test_ban_and_unban(client, auth, boss):
    uid = me(client, auth)["id"]
    out = client.post(f"/admin/users/{uid}/ban", json={"banned": True}, headers=boss).json()
    assert out["banned"] is True
    assert client.get("/auth/me", headers=auth).status_code == 401
    email = out["email"]
    res = client.post("/auth/login", json={"email": email, "password": "travel123"})
    assert res.status_code == 403 and "suspended" in res.json()["detail"]
    client.post(f"/admin/users/{uid}/ban", json={"banned": False}, headers=boss)
    assert client.post("/auth/login", json={"email": email, "password": "travel123"}).status_code == 200
    assert (
        client.post(f"/admin/users/{me(client, boss)['id']}/ban", json={"banned": True}, headers=boss).status_code
        == 400
    )
    assert client.post("/admin/users/1/ban", json={"banned": True}, headers=boss).status_code == 404


def test_delete_removes_everything(client, auth, boss):
    u = me(client, auth)
    client.post("/plan", json=TRIP, headers=auth)
    client.put("/profile", json={"interests": ["beaches"]}, headers=auth)
    assert client.delete(f"/admin/users/{u['id']}", headers=boss).json() == {"deleted": u["id"]}
    assert client.get("/admin/stats", headers=boss).json() == {"users": 1, "banned": 0, "itineraries": 0}
    assert client.get("/auth/me", headers=auth).status_code == 401
    assert client.delete(f"/admin/users/{u['id']}", headers=boss).status_code == 404
    assert client.delete(f"/admin/users/{me(client, boss)['id']}", headers=boss).status_code == 400
