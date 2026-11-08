# intent model
import hashlib
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline

from app.db import connect, db_path, now_iso
from app.ml.seed import LABELS, seed_examples

SURE = 0.45
AUTO_SAVE = 0.85
AUTO_EVERY = 10
PER_USER_PER_DAY = 100
WEIGHT = {"seed": 1.0, "auto": 0.5, "confirmed": 2.0, "corrected": 3.0}
_cache: dict[str, Pipeline] = {}


def model_path() -> Path:
    return Path(os.getenv("SAFARNAMA_MODEL", str(db_path().parent / "intent_model.joblib")))


def build() -> Pipeline:
    feats = FeatureUnion(
        [
            ("words", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, token_pattern=r"[a-z_]+")),
            ("chars", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True)),
        ]
    )
    return Pipeline([("features", feats), ("clf", LogisticRegression(C=10, max_iter=3000))])


def examples() -> list[tuple[str, str, str]]:
    with connect() as con:
        return con.execute("select text, intent, source from examples order by id").fetchall()


def stamp(rows: list[tuple[str, str, str]]) -> str:
    firm = [r for r in rows if r[2] != "auto"]
    h = hashlib.sha1(repr(firm).encode()).hexdigest()[:12]
    return f"v1-{len(firm)}-{(len(rows) - len(firm)) // AUTO_EVERY}-{h}"


def train() -> Pipeline:
    rows = examples()
    key = stamp(rows)
    data = [(t, i, "seed") for t, i in seed_examples()] + rows
    model = build()
    model.fit(
        [t for t, _, _ in data], [i for _, i, _ in data], clf__sample_weight=[WEIGHT.get(s, 1.0) for _, _, s in data]
    )
    path = model_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"stamp": key, "model": model}, path)
    if len(_cache) > 6:
        _cache.clear()
    _cache[key] = model
    return model


def model() -> Pipeline:
    key = stamp(examples())
    if key in _cache:
        return _cache[key]
    path = model_path()
    if path.exists():
        try:
            saved = joblib.load(path)
            if saved.get("stamp") == key:
                _cache[key] = saved["model"]
                return saved["model"]
        except Exception:
            pass
    return train()


def predict(masked: str) -> tuple[str, float]:
    m = model()
    probs = m.predict_proba([masked])[0]
    best = int(probs.argmax())
    intent, conf = m.classes_[best], float(probs[best])
    return (intent if conf >= SURE else "other"), round(conf, 3)


def room_left(user: str) -> int:
    since = (datetime.now(UTC) - timedelta(days=1)).isoformat(timespec="seconds")
    with connect() as con:
        used = con.execute("select count(*) from examples where user = ? and created >= ?", (user, since)).fetchone()[0]
    return max(0, PER_USER_PER_DAY - used)


def add_examples(rows: list[tuple[str, str]], source: str, retrain: bool = True, user: str | None = None) -> int:
    good = [(t.strip()[:300], i) for t, i in rows if t.strip() and i in LABELS]
    if not good:
        return 0
    now = now_iso()
    with connect() as con:
        con.executemany(
            "insert into examples (text, intent, source, created, user) values (?, ?, ?, ?, ?)",
            [(t, i, source, now, user) for t, i in good],
        )
    if retrain:
        train()
    return len(good)


def stats() -> dict:
    rows = examples()
    counts: dict[str, int] = {}
    for _, _, s in rows:
        counts[s] = counts.get(s, 0) + 1
    return {"seed": len(seed_examples()), "learned": len(rows), "by_source": counts, "intents": LABELS}
