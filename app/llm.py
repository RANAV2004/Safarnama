# llm
import json
import os
import re
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError


@dataclass
class Usage:
    tokens: int = 0
    cost_usd: float = 0.0


def enabled() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY")) and os.getenv("LLM_MODE", "auto") != "off"


def price_per_m() -> tuple[float, float]:
    return float(os.getenv("LLM_INPUT_USD_PER_M", "1.0")), float(os.getenv("LLM_OUTPUT_USD_PER_M", "5.0"))


def extract_json(text: str) -> str:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return m.group(0) if m else text


def ask_json(system: str, prompt: str, schema: type[BaseModel], usage: Usage, retries: int = 1) -> BaseModel | None:
    if not enabled():
        return None
    import anthropic

    client = anthropic.Anthropic()
    model = os.getenv("LLM_MODEL", "claude-haiku-5-5")
    msg = f"{prompt}\n\nReply with only a JSON object matching this schema:\n{json.dumps(schema.model_json_schema())}"
    pin, pout = price_per_m()
    for _ in range(retries + 1):
        try:
            res = client.messages.create(
                model=model, max_tokens=1500, system=system, messages=[{"role": "user", "content": msg}]
            )
        except anthropic.APIError:
            return None
        usage.tokens += res.usage.input_tokens + res.usage.output_tokens
        usage.cost_usd += res.usage.input_tokens / 1e6 * pin + res.usage.output_tokens / 1e6 * pout
        text = "".join(b.text for b in res.content if b.type == "text")
        try:
            return schema.model_validate_json(extract_json(text))
        except ValidationError as e:
            msg = f"{msg}\n\nYour last reply was invalid: {e.errors()[:3]}. Fix it."
    return None
