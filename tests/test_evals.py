# evals tests
import json
from datetime import date

from app.state import TripRequest
from evals import baseline, make_trips, run_evals
from evals.baseline import OneShot, single_llm, single_pass
from tests.fakes import answer


def test_make_trips_is_repeatable(tmp_path, monkeypatch):
    monkeypatch.setattr(make_trips, "OUT", tmp_path / "a.jsonl")
    make_trips.main(10)
    first = (tmp_path / "a.jsonl").read_text()
    make_trips.main(10)
    assert first == (tmp_path / "a.jsonl").read_text()
    assert len(first.splitlines()) == 10


def test_single_pass_has_no_loops(make_req):
    s = single_pass(make_req(budget_inr=20000))
    assert [t.agent for t in s.trace] == ["coordinator", "transport", "stay", "places", "budget_check", "writer"]


def test_single_llm_builds_a_plan(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("LLM_MODE", "auto")
    req = TripRequest(
        origin="Delhi",
        destination="Jaipur",
        start_date=date(2026, 11, 27),
        end_date=date(2026, 11, 28),
        budget_inr=15000,
        travellers=2,
    )
    plan = OneShot(
        outbound_id="del-jai-1",
        return_id="jai-del-1",
        stay_id="jai-h2",
        days=[
            {
                "date": "2026-11-28",
                "items": [
                    {"place_id": "jai-p1", "start": "09:00", "end": "12:00"},
                    {"place_id": "fake", "start": "13:00", "end": "14:00"},
                ],
            }
        ],
    )
    answer(monkeypatch, lambda schema, p: plan)
    s, usage = single_llm(req)
    assert s.selected_stay.id == "jai-h2" and [p.id for p in s.selected_places] == ["jai-p1"]
    assert s.total_cost > 0


def test_single_llm_failure(monkeypatch, make_req):
    answer(monkeypatch, lambda schema, p: None)
    s, _ = single_llm(make_req())
    assert s.errors == ["single llm call failed"]


def test_apply_merges_like_the_graph(make_req):
    s = baseline.apply(single_pass(make_req(budget_inr=20000)), {"notes": ["x"], "floors": {"extra": 1}})
    assert s.notes[-1] == "x" and s.floors["extra"] == 1


def test_run_evals_writes_report(tmp_path, monkeypatch):
    monkeypatch.setattr(run_evals, "HERE", tmp_path)
    monkeypatch.setattr(make_trips, "OUT", tmp_path / "trips.jsonl")
    make_trips.main(6)
    monkeypatch.setattr("sys.argv", ["run_evals", "--limit", "6"])
    run_evals.main()
    report = (tmp_path / "results.md").read_text()
    assert "plans with zero violations" in report and "budget level" in report
    raw = json.loads((tmp_path / "results.json").read_text())
    assert set(raw) == {"multi-agent", "single pass (no negotiation, no critic)"}
    assert len(raw["multi-agent"]) == 6


def test_low_budget_trip_is_skipped(make_req):
    rows = run_evals.run_system(
        "x",
        single_pass,
        [
            {
                "id": "t",
                "factor": 1,
                "origin": "Indore",
                "destination": "Goa",
                "start_date": "2026-11-20",
                "end_date": "2026-11-23",
                "budget_inr": 100,
                "travellers": 2,
            }
        ],
    )
    assert rows == []
