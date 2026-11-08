# fake llm
from types import SimpleNamespace


class FakeMessages:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(
            usage=SimpleNamespace(input_tokens=100, output_tokens=20), content=[SimpleNamespace(type="text", text=r)]
        )


class FakeClient:
    def __init__(self, replies):
        self.messages = FakeMessages(replies)


def fake_llm(monkeypatch, replies):
    import anthropic

    client = FakeClient(replies)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODE", "auto")
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: client)
    return client


def answer(monkeypatch, fn):
    from app import llm

    monkeypatch.setattr(llm, "ask_json", lambda system, prompt, schema, usage, retries=1: fn(schema, prompt))
