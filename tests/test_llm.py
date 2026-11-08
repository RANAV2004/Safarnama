# llm tests
import anthropic
import httpx
from pydantic import BaseModel

from app import llm
from app.llm import Usage, extract_json
from tests.fakes import fake_llm


class Pick(BaseModel):
    choice: int
    reason: str


def test_disabled_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert llm.ask_json("s", "p", Pick, Usage()) is None


def test_off_mode_wins_over_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("LLM_MODE", "off")
    assert not llm.enabled()


def test_extract_json_from_chatty_reply():
    assert extract_json('Sure! {"choice": 1, "reason": "ok"} hope it helps') == '{"choice": 1, "reason": "ok"}'


def test_valid_reply_is_parsed_and_usage_counted(monkeypatch):
    fake_llm(monkeypatch, ['{"choice": 2, "reason": "cheapest"}'])
    usage = Usage()
    ans = llm.ask_json("s", "p", Pick, usage)
    assert ans == Pick(choice=2, reason="cheapest")
    assert usage.tokens == 120 and usage.cost_usd > 0


def test_invalid_then_valid_retries_once(monkeypatch):
    client = fake_llm(monkeypatch, ['{"choice": "two"}', '{"choice": 2, "reason": "fixed"}'])
    assert llm.ask_json("s", "p", Pick, Usage()).reason == "fixed"
    assert client.messages.calls == 2


def test_invalid_twice_returns_none(monkeypatch):
    fake_llm(monkeypatch, ["not json", "still not json"])
    assert llm.ask_json("s", "p", Pick, Usage()) is None


def test_api_error_returns_none(monkeypatch):
    err = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    fake_llm(monkeypatch, [err])
    assert llm.ask_json("s", "p", Pick, Usage()) is None
