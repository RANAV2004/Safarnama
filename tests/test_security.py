# security helper tests
import httpx
import pytest
from pydantic import ValidationError

from app import api, mailer
from app.graph import check_supported
from app.providers import ProviderError, serpapi
from app.state import TripRequest


class FakeSMTP:
    sent = []

    def __init__(self, host, port, timeout):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        self.user = user

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


def test_mail_goes_to_the_log_without_smtp(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    assert mailer.send("a@x.com", "hi", "code 123456") is False


def test_mail_uses_smtp_when_set(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "me")
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    assert mailer.send("a@x.com", "Your code", "code 123456") is True
    assert FakeSMTP.sent[-1]["To"] == "a@x.com" and FakeSMTP.sent[-1]["Subject"] == "Your code"


def test_client_ip_trusts_proxy_only_when_told(monkeypatch):
    class Req:
        headers = {"x-forwarded-for": "9.9.9.9, 10.0.0.1"}
        client = type("C", (), {"host": "10.0.0.1"})()

    assert api.client_ip(Req()) == "10.0.0.1"
    monkeypatch.setenv("TRUST_PROXY", "1")
    assert api.client_ip(Req()) == "9.9.9.9"


def test_stream_hides_unexpected_errors(client, auth, monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("database password is hunter2")

    monkeypatch.setattr(api, "stream_trip", broken)
    body = {
        "origin": "Indore",
        "destination": "Goa",
        "start_date": "2026-11-27",
        "end_date": "2026-11-29",
        "budget_inr": 20000,
    }
    text = client.post("/plan/stream", json=body, headers=auth).text
    assert "planning failed, please try again" in text and "hunter2" not in text


def test_live_mode_skips_the_route_check(monkeypatch, make_req):
    monkeypatch.setenv("PROVIDER_MODE", "live")
    check_supported(make_req(origin="Pune"))


def test_serpapi_network_and_json_errors(monkeypatch):
    monkeypatch.setenv("SERPAPI_KEY", "k")

    def timeout(*a, **k):
        raise httpx.ConnectTimeout("slow")

    monkeypatch.setattr(serpapi.httpx, "get", timeout)
    with pytest.raises(ProviderError, match="ConnectTimeout"):
        serpapi.call({})

    class NotJson:
        def raise_for_status(self):
            pass

        def json(self):
            raise ValueError("no")

    monkeypatch.setattr(serpapi.httpx, "get", lambda *a, **k: NotJson())
    with pytest.raises(ProviderError, match="not JSON"):
        serpapi.call({})


def test_revise_explains_changes_it_cannot_make(monkeypatch, make_req):
    from app.agents import reviser
    from app.graph import plan_trip

    s = plan_trip(make_req())
    plan = reviser.CurrentPlan(
        request=s.request,
        outbound=s.selected_outbound,
        stay=s.selected_stay,
        places=s.selected_places,
        options=reviser.PlanOptions(stays=s.stay_options, places=s.place_options),
    )

    def bad(*a, **k):
        try:
            TripRequest.model_validate({})
        except ValidationError as e:
            raise e

    monkeypatch.setattr(reviser, "apply", bad)
    r = reviser.revise(plan, "set the budget to 30000", "me@x.com")
    assert r.reply.startswith("I could not make that change") and r.state is None
