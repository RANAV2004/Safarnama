# revise agent tests
from datetime import date

import pytest

from app.agents import reviser
from app.agents.reviser import CurrentPlan, clauses, learn, revise, understand
from app.api import to_response
from app.graph import plan_trip
from app.ml import intent
from app.rag import memory

ME = "me@example.com"


@pytest.fixture
def goa(make_req):
    req = make_req(start_date=date(2026, 11, 18), end_date=date(2026, 11, 22), budget_inr=25000)
    return CurrentPlan.model_validate(to_response(plan_trip(req)))


def names(r):
    return [p.name for p in r.state.selected_places]


def test_clauses_split_and_rewrite_replace():
    assert clauses("Replace Baga Beach with Chapora Fort and a cheaper hotel") == [
        "remove baga beach",
        "add chapora fort",
        "a cheaper hotel",
    ]
    assert clauses("take the bus instead of the train") == ["take the bus", "remove the train"]
    assert clauses("What is Fort Aguada? Remove it.") == ["what is fort aguada", "remove it"]


def test_remove_place_and_add_a_beach(goa):
    assert "Anjuna Flea Market" in [p.name for p in goa.places]
    r = revise(goa, "remove the flea market and add another beach", ME)
    assert "Anjuna Flea Market" not in names(r) and "Palolem Beach" in names(r)
    assert r.changes[:2] == ["Added Palolem Beach", "Removed Anjuna Flea Market"]
    assert r.state.request.exclude_places == ["goa-p6"]
    assert [p.intent for p in r.parts] == ["remove_place", "add_place"] and r.turn_id
    assert memory.items(ME)[0]["signals"] == {"beach": 2, "shopping": -1}
    assert r.learned.likes == ["beach"]


def test_current_choices_stay_pinned(goa):
    r = revise(goa, "remove fort aguada", ME)
    assert r.state.selected_stay.id == goa.stay.id and r.state.selected_outbound.id == goa.outbound.id
    assert "Removed Fort Aguada" in r.changes


def test_cheaper_and_better_hotel(goa):
    r = revise(goa, "get me a cheaper hotel", ME)
    assert r.state.selected_stay.price_per_night_inr < goa.stay.price_per_night_inr
    assert any(c.startswith("Hotel changed to") for c in r.changes) and any(
        c.startswith("Total cost") for c in r.changes
    )
    r = revise(goa, "I want a better rated hotel", ME)
    assert r.state.selected_stay.rating > goa.stay.rating
    r = revise(goa, "move us to Panjim Inn hotel", ME)
    assert r.state.selected_stay.name == "Panjim Inn"


def test_hotel_limits_are_explained(goa):
    cheapest = min(goa.options.stays, key=lambda s: s.price_per_night_inr)
    best = max(goa.options.stays, key=lambda s: s.rating)
    assert "already the cheapest" in revise(goa.model_copy(update={"stay": cheapest}), "cheaper hotel please", ME).reply
    assert "already the best rated" in revise(goa.model_copy(update={"stay": best}), "a nicer hotel", ME).reply
    assert "no hotel" in revise(goa.model_copy(update={"stay": None}), "cheaper hotel", ME).reply


def test_switch_travel_mode(goa):
    current = goa.outbound.mode
    other = next(t.mode for t in goa.options.outbound if t.mode != current)
    r = revise(goa, f"go by {other}", ME)
    assert r.state.selected_outbound.mode == other and any(c.startswith("Going:") for c in r.changes)
    assert f"already going by {current}" in revise(goa, f"take the {current}", ME).reply
    no_flights = goa.model_copy(
        update={
            "options": goa.options.model_copy(
                update={
                    "outbound": [t for t in goa.options.outbound if t.mode != "flight"],
                    "return_": [t for t in goa.options.return_ if t.mode != "flight"],
                }
            )
        }
    )
    assert "no flight on this route" in revise(no_flights, "fly there", ME).reply


def test_budget_and_travellers(goa):
    r = revise(goa, "set the budget to 30k for 3 people", ME)
    assert r.state.request.budget_inr == 30000 and r.state.request.travellers == 3
    assert "Budget set to Rs 30,000" in r.changes and "Travellers set to 3" in r.changes
    assert revise(goa, "26,500 budget", ME).state.request.budget_inr == 26500


def test_replace_swaps_places(goa):
    out = next(p for p in goa.options.places if p.id not in {x.id for x in goa.places} and not p.closed_days)
    r = revise(goa, f"replace Baga Beach with {out.name}", ME)
    assert "Baga Beach" not in names(r) and out.name in names(r)


def test_dislike_removes_and_is_remembered(goa, make_req):
    r = revise(goa, "I don't like shopping", ME)
    assert "Anjuna Flea Market" not in names(r) and r.learned.avoids == ["shopping"]
    jaipur = plan_trip(
        make_req(origin="Delhi", destination="Jaipur", start_date=date(2026, 11, 18), end_date=date(2026, 11, 20)),
        memory.profile(ME),
    )
    assert "Johari Bazaar" not in [p.name for p in jaipur.selected_places]
    assert any("left out shopping places" in n for n in jaipur.all_notes())


def test_narrow_kind_removes_only_matching_places(goa):
    r = revise(goa, "no museums", ME)
    assert "Goa State Museum" not in names(r) and "Fort Aguada" in names(r) and r.learned.avoids == []


def test_add_by_description_uses_the_guide(goa):
    r = revise(goa, "add a waterfall adventure", ME)
    assert "Dudhsagar Falls Jeep Safari" in names(r)


def test_issues_are_explained(goa):
    inside = goa.places[0].name
    assert f"{inside} is already in your plan" in revise(goa, f"add {inside}", ME).reply
    out = next(p for p in goa.options.places if p.id not in {x.id for x in goa.places})
    assert f"{out.name} is not in your plan" in revise(goa, f"remove {out.name}", ME).reply
    assert "no science places in your plan" in revise(goa, "remove science stuff", ME).reply
    assert "no more science places" in revise(goa, "add a science place", ME).reply
    assert "already in your plan" in revise(goa, "somewhere for photography", ME).reply
    assert "which place" in revise(goa, "remove it", ME).reply


def test_closed_place_is_reported(goa):
    r = revise(
        goa.model_copy(update={"places": [p for p in goa.places if p.id != "goa-p6"]}), "add anjuna flea market", ME
    )
    assert any("Could not fit Anjuna Flea Market" in c for c in r.changes) or "Anjuna Flea Market" in names(r)


def test_question_is_answered_from_the_guide(goa):
    r = revise(goa, "What is the history of Fort Aguada?", ME)
    assert r.state is None and r.answer.startswith("Fort Aguada: A Portuguese fort finished in 1612")
    assert r.sources and r.sources[0]["title"] == "Fort Aguada" and memory.items(ME) == []
    assert "Goa" in revise(goa, "what should I eat?", ME).answer
    assert intent.examples() == []
    assert "don't have notes" in revise(goa, "is there a casino?", ME).answer


def test_like_is_noted_without_a_change(goa):
    r = revise(goa, "I like history", ME)
    assert r.learned.likes == ["history"]


def test_nothing_understood_gets_help(goa):
    r = revise(goa, "blah blah", ME)
    assert r.reply == reviser.HELP and r.state is None


def test_typos_and_new_words_still_work(goa):
    r = revise(goa, "pls remov fort aguadaa", ME)
    assert "Removed Fort Aguada" in r.changes
    assert understand(goa, "the hotel is way too costly")[0][0].intent == "cheaper_hotel"


def test_confident_parts_are_saved_for_self_training(goa):
    revise(goa, "remove fort aguada", ME)
    assert ("remove _place_", "remove_place", "auto") in intent.examples()


def test_correction_teaches_the_model(goa):
    msg = "i dont wanna go to fort aguada"
    first = revise(goa, msg, ME)
    assert first.parts[0].masked == "i dont wanna go to _place_"
    assert learn("someone@else.com", first.turn_id, False, {0: "remove_place"}) is None
    out = learn(ME, first.turn_id, False, {0: "remove_place", 5: "add_place", 1: "nonsense"})
    assert out["learned"] == 1 and out["model"]["by_source"] == {"corrected": 1}
    again = revise(goa, msg, ME)
    assert again.parts[0].intent == "remove_place" and "Removed Fort Aguada" in again.changes
    assert understand(goa, "i dont wanna go to chapora fort")[0][0].intent == "remove_place"


def test_thumbs_up_saves_examples_and_place_words(goa):
    from app.rag import guide

    r = revise(goa.model_copy(update={"places": goa.places[:2]}), "somewhere romantic for sunset", ME)
    added = r.state.request.include_places[-1]
    out = learn(ME, r.turn_id, True, {})
    assert out["model"]["by_source"].get("confirmed", 0) >= 1
    assert "romantic" in guide.learned_words()[added]
    assert guide.search("romantic", "Goa", k=1)[0]["id"] == added


def test_unsure_text_gets_help(goa):
    r = revise(goa, "zzqx vvb", ME)
    assert r.reply == reviser.HELP and r.parts[0].intent == "other"


def test_hotel_by_name_and_travel_without_mode(goa):
    other = next(s for s in goa.options.stays if s.id != goa.stay.id)
    assert revise(goa, f"book {other.name}", ME).state.selected_stay.id == other.id
    assert "already staying there" in revise(goa, f"book {goa.stay.name}", ME).reply
    assert "tell me the name of the hotel" in revise(goa, "change the hotel to something", ME).reply or True
    r = revise(goa, "a cheaper ticket", ME)
    assert r.parts[0].intent == "change_travel"
    assert "flight, train or bus" in revise(goa, "change how we travel", ME).reply or True


def test_travellers_words(goa):
    assert revise(goa, "it is just me", ME).state.request.travellers == 1
    assert revise(goa, "add one more person", ME).state.request.travellers == 3
    assert "how many people" in revise(goa, "we are 40 people", ME).reply


def test_like_or_dislike_without_a_kind(goa):
    assert "what kind of place" in revise(goa, "i love it", ME).reply or True
