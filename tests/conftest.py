# test setup
import os
from datetime import date
from uuid import uuid4

import pytest

os.environ["LLM_MODE"] = "off"
os.environ["PROVIDER_MODE"] = "fixture"
os.environ["PASSWORD_ROUNDS"] = "1000"
os.environ["SAFARNAMA_ENV"] = "test"
os.environ["WIKI_MODE"] = "off"
from app.state import TripRequest


@pytest.fixture(autouse=True)
def memory_db(tmp_path, monkeypatch):
    from app.limits import LIMITS

    monkeypatch.setenv("SAFARNAMA_DB", str(tmp_path / "memory.db"))
    LIMITS.clear()


@pytest.fixture
def make_req():
    def make(**kw):
        base = dict(
            origin="Indore",
            destination="Goa",
            start_date=date(2026, 11, 20),
            end_date=date(2026, 11, 23),
            budget_inr=20000,
            travellers=2,
        )
        return TripRequest(**{**base, **kw})

    return make


def sign_in(client, email: str | None = None, name: str = "Test User") -> dict:
    email = email or f"t{uuid4().hex[:8]}@example.com"
    res = client.post(
        "/auth/signup", json={"email": email, "name": name, "birth_date": "2000-05-17", "password": "travel123"}
    )
    client.cookies.clear()
    return {"Authorization": f"Bearer {res.json()['token']}"}


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app import api

    api.today = lambda: date(2026, 11, 1)
    return TestClient(api.app)


@pytest.fixture
def auth(client):
    return sign_in(client)
