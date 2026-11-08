# api tests
import json

from fastapi.testclient import TestClient

from app.api import app

TRIP = {
    "origin": "Delhi",
    "destination": "Jaipur",
    "start_date": "2026-11-27",
    "end_date": "2026-11-29",
    "budget_inr": 15000,
    "travellers": 2,
}
REQ = {**TRIP, "origin": "Indore", "destination": "Goa", "budget_inr": 20000}


def events(client, auth, body):
    with client.stream("POST", "/plan/stream", json=body, headers=auth) as r:
        return [json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")]


def test_root_opens_docs(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"] == "/docs"


def test_health_and_routes_are_public(client):
    assert client.get("/health").json() == {"ok": True, "llm": False}
    routes = client.get("/routes").json()
    assert {"from": "Delhi", "to": "Jaipur"} in routes and len(routes) == 8


def test_planning_needs_sign_in(client):
    for path in ("/plan", "/plan/stream", "/plan/text", "/plan/pdf"):
        assert client.post(path, json={}).status_code == 401


def test_plan_response_shape(client, auth):
    j = client.post("/plan", json=TRIP, headers=auth).json()
    for key in (
        "summary",
        "budget_plan",
        "outbound",
        "return",
        "stay",
        "days",
        "breakdown",
        "trace",
        "notes",
        "options",
    ):
        assert key in j
    assert j["total_cost"] == sum(j["breakdown"].values())
    opts = j["options"]
    assert opts["outbound"] and opts["return"] and opts["stays"] and opts["places"]
    assert [s["price_per_night_inr"] for s in opts["stays"]] == sorted(s["price_per_night_inr"] for s in opts["stays"])


def test_invalid_request_is_422(client, auth):
    assert client.post("/plan", json={**TRIP, "destination": "Delhi"}, headers=auth).status_code == 422


def test_stream_sends_agents_then_plan(client, auth):
    ev = events(client, auth, TRIP)
    agents = [e["agent"] for e in ev]
    assert agents[0] == "coordinator" and {"transport", "stay", "places", "writer", "critic"} <= set(agents)
    assert ev[-1]["agent"] == "done" and ev[-1]["plan"]["days"]


def test_stream_reports_low_budget(client, auth):
    ev = events(client, auth, {**TRIP, "budget_inr": 500})
    assert ev == [{"agent": "error", "note": "budget Rs 500 is below the minimum Rs 3000 needed just for food"}]


def test_text_without_llm_is_422(client, auth):
    r = client.post("/plan/text", json={"text": "goa next week"}, headers=auth)
    assert r.status_code == 422 and "LLM key" in r.json()["detail"]


def test_regenerate_with_user_changes(client, auth):
    first = client.post("/plan", json=TRIP, headers=auth).json()
    other_stay = next(s for s in first["options"]["stays"] if s["id"] != first["stay"]["id"])
    dropped = first["places"][0]["id"]
    added = next(
        p["id"]
        for p in first["options"]["places"]
        if p["id"] not in {x["id"] for x in first["places"]} and not p["closed_days"]
    )
    out = next(t for t in first["options"]["outbound"] if t["id"] != first["outbound"]["id"])
    second = client.post(
        "/plan",
        headers=auth,
        json={
            **TRIP,
            "stay_id": other_stay["id"],
            "exclude_places": [dropped],
            "include_places": [added],
            "outbound_id": out["id"],
        },
    ).json()
    assert second["stay"]["id"] == other_stay["id"]
    assert second["outbound"]["id"] == out["id"]
    ids = {p["id"] for p in second["places"]}
    assert dropped not in ids and added in ids


def test_pdf_download(client, auth):
    plan = client.post("/plan", json=TRIP, headers=auth).json()
    r = client.post("/plan/pdf", json=plan, headers=auth)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF") and len(r.content) > 2000
    assert 'filename="safarnama-delhi-jaipur-2026-11-27.pdf"' in r.headers["content-disposition"]


def test_pdf_for_day_trip_and_over_budget(client, auth):
    plan = client.post(
        "/plan",
        headers=auth,
        json={
            "origin": "Bengaluru",
            "destination": "Mysuru",
            "start_date": "2026-11-24",
            "end_date": "2026-11-24",
            "budget_inr": 3000,
            "travellers": 1,
        },
    ).json()
    plan["over_budget_by"] = 250
    plan["notes"] = ["a note"]
    plan["days"][0]["items"] = []
    r = client.post("/plan/pdf", json=plan, headers=auth)
    assert r.status_code == 200 and r.content.startswith(b"%PDF")


def test_swagger_has_bearer_auth():
    spec = TestClient(app).get("/openapi.json").json()
    assert "HTTPBearer" in spec["components"]["securitySchemes"]


def test_revise_endpoint_updates_plan_and_memory(client, auth):
    body = {
        "origin": "Indore",
        "destination": "Goa",
        "start_date": "2026-11-18",
        "end_date": "2026-11-22",
        "budget_inr": 25000,
        "travellers": 2,
    }
    plan = client.post("/plan", json=body, headers=auth).json()
    res = client.post(
        "/plan/revise", json={"plan": plan, "message": "remove the flea market and add another beach"}, headers=auth
    ).json()
    assert "Removed Anjuna Flea Market" in res["changes"] and res["plan"]["request"]["exclude_places"] == ["goa-p6"]
    assert res["learned"]["likes"] == ["beach"] and res["understood"][0]["label"] == "Remove a place" and res["turn_id"]
    q = client.post(
        "/plan/revise", json={"plan": res["plan"], "message": "when is the best time to visit?"}, headers=auth
    ).json()
    assert q["plan"] is None and q["sources"]
    mem = client.get("/memory", headers=auth).json()
    assert mem["likes"] == ["beach"] and mem["items"][0]["text"] == "remove the flea market and add another beach"
    assert client.delete("/memory", headers=auth).json() == {"forgot": 1}
    assert client.get("/memory", headers=auth).json()["items"] == []


def test_plan_uses_what_it_learned(client, auth):
    body = {
        "origin": "Indore",
        "destination": "Goa",
        "start_date": "2026-11-18",
        "end_date": "2026-11-22",
        "budget_inr": 25000,
        "travellers": 2,
    }
    plan = client.post("/plan", json=body, headers=auth).json()
    client.post("/plan/revise", json={"plan": plan, "message": "I don't like shopping"}, headers=auth)
    again = client.post("/plan", json=body, headers=auth).json()
    assert "goa-p6" not in [p["id"] for p in again["places"]] and any("left out shopping" in n for n in again["notes"])


def test_revise_checks_input(client, auth):
    assert client.post("/plan/revise", json={"plan": {}, "message": "x"}, headers=auth).status_code == 422
    assert client.post("/plan/revise", json={"message": "x"}).status_code == 401


def test_revise_reports_budget_too_low(client, auth):
    body = {
        "origin": "Indore",
        "destination": "Goa",
        "start_date": "2026-11-18",
        "end_date": "2026-11-22",
        "budget_inr": 25000,
        "travellers": 2,
    }
    plan = client.post("/plan", json=body, headers=auth).json()
    res = client.post("/plan/revise", json={"plan": plan, "message": "set the budget to 500"}, headers=auth)
    assert res.status_code == 422


def test_learn_endpoint(client, auth):
    body = {
        "origin": "Indore",
        "destination": "Goa",
        "start_date": "2026-11-18",
        "end_date": "2026-11-22",
        "budget_inr": 25000,
        "travellers": 2,
    }
    plan = client.post("/plan", json=body, headers=auth).json()
    res = client.post(
        "/plan/revise", json={"plan": plan, "message": "i dont wanna go to fort aguada"}, headers=auth
    ).json()
    out = client.post(
        "/learn", json={"turn_id": res["turn_id"], "good": False, "fixes": {"0": "remove_place"}}, headers=auth
    ).json()
    assert out["learned"] == 1 and client.get("/model", headers=auth).json()["by_source"]["corrected"] == 1
    assert client.get("/model").status_code == 401
    assert client.post("/learn", json={"turn_id": 9999, "good": True}, headers=auth).status_code == 404
    assert client.post("/learn", json={"turn_id": 1, "good": True}).status_code == 401
    again = client.post("/learn", json={"turn_id": res["turn_id"], "good": True}, headers=auth)
    assert again.status_code == 409
    second = client.post("/plan/revise", json={"plan": plan, "message": "remove fort aguada"}, headers=auth).json()
    good = client.post("/learn", json={"turn_id": second["turn_id"], "good": True}, headers=auth).json()
    assert good["model"]["learned"] >= 2


def test_teaching_is_capped_per_day(client, auth, monkeypatch):
    from app.ml import intent

    plan = client.post("/plan", json=REQ, headers=auth).json()
    res = client.post("/plan/revise", json={"plan": plan, "message": "remove fort aguada"}, headers=auth).json()
    monkeypatch.setattr(intent, "PER_USER_PER_DAY", 0)
    assert client.post("/learn", json={"turn_id": res["turn_id"], "good": True}, headers=auth).status_code == 429


def test_revise_rejects_bad_numbers_politely(client, auth):
    plan = client.post("/plan", json=REQ, headers=auth).json()
    for message, words in [
        ("set the budget to 20000 for 15 people", "1 to 10 travellers"),
        ("set budget to 99999999999999999999999", "at most"),
    ]:
        res = client.post("/plan/revise", json={"plan": plan, "message": message}, headers=auth)
        assert res.status_code == 200 and words in res.json()["reply"]


def test_plan_checks_city_dates_and_sizes(client, auth):
    paris = client.post("/plan", json={**REQ, "destination": "Paris"}, headers=auth)
    assert paris.status_code == 422 and "Paris" in paris.json()["detail"]
    past = client.post("/plan", json={**REQ, "start_date": "2026-10-01", "end_date": "2026-10-03"}, headers=auth)
    assert past.status_code == 422 and "past" in past.json()["detail"]
    assert client.post("/plan", json={**REQ, "budget_inr": 10**30}, headers=auth).status_code == 422
    assert client.post("/plan", json={**REQ, "preferences": ["beach"] * 500}, headers=auth).status_code == 422
    stream = client.post("/plan/stream", json={**REQ, "destination": "Paris"}, headers=auth).text
    assert '"agent": "error"' in stream and "Paris" in stream
    huge = client.post("/plan", content=b"x" * 2_000_000, headers={**auth, "content-type": "application/json"})
    assert huge.status_code == 413


def test_security_headers(client):
    res = client.get("/health")
    assert res.headers["x-content-type-options"] == "nosniff" and res.headers["x-frame-options"] == "DENY"


def test_pdf_text_is_not_markup(client, auth):
    import pathlib

    image = str(pathlib.Path(__file__).resolve().parents[1] / "docs" / "images" / "menu.png")
    doc = {"request": {**REQ, "origin": 'In"dore'}, "summary": f'<img src="{image}" width="50" height="50"/> & <b>'}
    res = client.post("/plan/pdf", json=doc, headers=auth)
    assert res.status_code == 200 and len(res.content) < 20000
    assert res.headers["content-disposition"] == 'attachment; filename="safarnama-in-dore-goa-2026-11-27.pdf"'


def test_profile_first_login_and_update(client, auth):
    me = client.get("/profile", headers=auth).json()
    assert me["onboarded"] is False and me["interests"] == [] and len(me["options"]) == 15
    saved = client.put("/profile", json={"interests": ["beaches", "views", "beaches", "made-up"]}, headers=auth).json()
    assert saved == {**saved, "onboarded": True, "interests": ["beaches", "views"]}
    assert client.get("/memory", headers=auth).json()["interests"] == ["beaches", "views"]
    assert client.put("/profile", json={"interests": []}, headers=auth).json()["onboarded"] is True


def test_plan_puts_interests_first(client, auth):
    body = {
        "origin": "Delhi",
        "destination": "Jaipur",
        "start_date": "2026-11-18",
        "end_date": "2026-11-19",
        "budget_inr": 9000,
        "travellers": 1,
    }
    before = client.post("/plan", json=body, headers=auth).json()
    client.put("/profile", json={"interests": ["shopping"]}, headers=auth)
    after = client.post("/plan", json=body, headers=auth).json()
    assert "jai-p7" not in [p["id"] for p in before["places"]] and "jai-p7" in [p["id"] for p in after["places"]]
    assert any("picked first for your interests: shopping and markets" in t["note"] for t in after["trace"])
