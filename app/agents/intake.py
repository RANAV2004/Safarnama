# intake agent
from datetime import date

from pydantic import BaseModel, ValidationError

from app import llm
from app.llm import Usage
from app.state import TripRequest


class ParsedTrip(BaseModel):
    origin: str
    destination: str
    start_date: date
    end_date: date
    budget_inr: int
    travellers: int = 1
    preferences: list[str] = []


class IntakeError(ValueError):
    pass


def parse_text(text: str, today: date | None = None) -> TripRequest:
    if not llm.enabled():
        raise IntakeError("free text needs an LLM key, send the structured form instead")
    today = today or date.today()
    ans = llm.ask_json(
        "You extract trip details. Use Indian city names. Budget in rupees as an integer, 15k means 15000.",
        f"Today is {today:%A %d %B %Y}.\nRequest: {text}",
        ParsedTrip,
        Usage(),
    )
    if not ans:
        raise IntakeError("could not understand the request, please use the form")
    try:
        return TripRequest(**ans.model_dump())
    except ValidationError as e:
        raise IntakeError(str(e)) from e
