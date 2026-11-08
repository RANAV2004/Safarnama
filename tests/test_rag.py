# rag tests
from app.rag import guide, memory
from app.rag.vectors import VectorIndex, stem, tokens


def test_tokens_drop_stop_words_and_join_plurals():
    assert tokens("The beaches and churches for my kids") == ["beach", "church", "kid"]
    assert tokens("a calm seaside at dusk") == ["quiet", "beach", "sunset"]
    assert stem("stories") == "story" and stem("glass") == "glass"


def test_index_ranks_closest_doc_first():
    idx = VectorIndex([("a", "old fort with a sunset view"), ("b", "busy market for shopping"), ("c", "quiet beach")])
    assert idx.search("sunset at the fort")[0][0] == "a"
    assert idx.search("shopping", allow={"a", "c"}) == []
    assert idx.search("") == []


def test_guide_covers_every_place():
    from app.providers.fixture import load

    ids = {p["id"] for ps in load("places").values() for p in ps}
    assert ids <= set(guide.docs())
    assert all(guide.get(f"city-{c.lower()}") for c in load("places"))


def test_guide_search_stays_in_the_city():
    hits = guide.search("history of fort aguada", "Goa")
    assert hits[0]["id"] == "goa-p2" and all(h["city"] == "Goa" for h in hits)
    assert [h["id"] for h in guide.search("best time for the monsoon", "Goa", only={"goa-p1"})] == ["city-goa"]
    assert "Tip:" in guide.snippet(hits[0])


def test_memory_learns_likes_and_avoids():
    memory.remember("a@x.com", "Goa", "more beaches please", {"beach": 2})
    memory.remember("a@x.com", "Goa", "remove the flea market", {"shopping": -1})
    p = memory.profile("a@x.com")
    assert p.likes == ["beach"] and p.avoids == [] and p.memories[0] == "remove the flea market"
    memory.remember("a@x.com", "Jaipur", "no markets", {"shopping": -2})
    assert memory.profile("a@x.com").avoids == ["shopping"]
    assert memory.profile("b@x.com").likes == []


def test_recall_finds_similar_feedback():
    memory.remember("a@x.com", "Goa", "I want quiet beaches", {"beach": 2})
    memory.remember("a@x.com", "Goa", "cheaper hotel", {})
    assert memory.recall("a@x.com", "a quiet beach") == ["I want quiet beaches"]
    assert memory.recall("a@x.com", " ") == [] and memory.recall("z@x.com", "beach") == []


def test_forget_wipes_only_that_user():
    memory.remember("a@x.com", "Goa", "x", {"beach": 1})
    memory.remember("b@x.com", "Goa", "y", {"beach": 1})
    assert memory.forget("a@x.com") == 1
    assert memory.items("a@x.com") == [] and len(memory.items("b@x.com")) == 1


def test_memory_keeps_the_latest_items(monkeypatch):
    monkeypatch.setattr(memory, "KEEP", 3)
    for i in range(5):
        memory.remember("a@x.com", "Goa", f"note {i}", {})
    assert [i["text"] for i in memory.items("a@x.com")] == ["note 4", "note 3", "note 2"]


def test_model_is_saved_and_reloaded():
    from app.ml import intent

    intent.train()
    assert intent.model_path().exists()
    intent._cache.clear()
    assert intent.predict("remove _place_")[0] == "remove_place"
    intent.model_path().write_bytes(b"broken")
    intent._cache.clear()
    assert intent.predict("cheaper hotel")[0] == "cheaper_hotel"
    assert intent.add_examples([(" ", "add_place"), ("x", "not-an-intent")], "confirmed") == 0


def test_self_training_waits_for_ten_examples():
    from app.ml import intent

    first = intent.stamp(intent.examples())
    intent.add_examples([("remove _place_", "remove_place")] * 9, "auto", retrain=False)
    assert intent.stamp(intent.examples()) == first
    intent.add_examples([("remove _place_", "remove_place")], "auto", retrain=False)
    assert intent.stamp(intent.examples()) != first
