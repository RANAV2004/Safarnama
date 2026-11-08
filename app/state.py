# state
from datetime import date, datetime, time, timedelta
from operator import add
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MAX_BUDGET = 10_000_000
Short = Annotated[str, Field(max_length=100)]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def merge(a: dict, b: dict) -> dict:
    return {**a, **b}


class MyJourney(BaseModel):
    mode: Literal["flight", "train", "bus"] = "flight"
    provider: str = Field(default="", max_length=60)
    number: str = Field(default="", max_length=20)
    depart_at: datetime
    arrive_at: datetime
    price_inr: int = Field(default=0, ge=0, le=1_000_000)

    @model_validator(mode="after")
    def check_times(self):
        if self.arrive_at <= self.depart_at:
            raise ValueError("arrival must be after departure")
        if self.arrive_at - self.depart_at > timedelta(days=3):
            raise ValueError("a journey cannot take more than three days")
        return self

    def option(self, direction: str) -> "TransportOption":
        label = " ".join(x for x in (self.provider, self.number) if x) or self.mode.title()
        return TransportOption(
            id=f"mine-{direction}",
            mode=self.mode,
            provider=label,
            depart_at=self.depart_at,
            arrive_at=self.arrive_at,
            price_inr=self.price_inr,
            overnight=self.arrive_at.date() > self.depart_at.date(),
            source="you",
        )


class TripRequest(BaseModel):
    origin: str = Field(max_length=60)
    destination: str = Field(max_length=60)
    start_date: date
    end_date: date
    budget_inr: int = Field(gt=0, le=MAX_BUDGET)
    travellers: int = Field(default=1, ge=1, le=10)
    preferences: list[Short] = Field(default_factory=list, max_length=15)
    outbound_id: Short | None = None
    return_id: Short | None = None
    stay_id: Short | None = None
    include_places: list[Short] = Field(default_factory=list, max_length=50)
    exclude_places: list[Short] = Field(default_factory=list, max_length=50)
    note: str = Field(default="", max_length=300)
    my_outbound: MyJourney | None = None
    my_return: MyJourney | None = None

    @field_validator("origin", "destination")
    @classmethod
    def clean_city(cls, v: str) -> str:
        v = v.strip().title()
        if not v:
            raise ValueError("city cannot be empty")
        return v

    @model_validator(mode="after")
    def check_trip(self):
        if self.my_outbound:
            nights = max(0, (self.end_date - self.start_date).days)
            self.start_date = self.my_outbound.arrive_at.date()
            if not self.my_return and self.end_date < self.start_date + timedelta(days=nights):
                self.end_date = self.start_date + timedelta(days=nights)
        if self.my_return:
            self.end_date = self.my_return.depart_at.date()
        if self.my_outbound and self.my_return and self.my_return.depart_at <= self.my_outbound.arrive_at:
            raise ValueError("your return leaves before your outbound journey arrives")
        if self.origin == self.destination:
            raise ValueError("origin and destination must be different")
        if self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        if self.nights > 14:
            raise ValueError("trips longer than 14 nights are not supported")
        return self

    @property
    def nights(self) -> int:
        return (self.end_date - self.start_date).days

    @property
    def days(self) -> int:
        return self.nights + 1

    def trip_dates(self) -> list[date]:
        return [self.start_date + timedelta(days=i) for i in range(self.days)]


class BudgetPlan(BaseModel):
    transport: int
    stay: int
    food: int
    activities: int
    buffer: int

    @property
    def total(self) -> int:
        return self.transport + self.stay + self.food + self.activities + self.buffer


class TransportOption(BaseModel):
    id: str
    mode: Literal["flight", "train", "bus"]
    provider: str
    depart_at: datetime
    arrive_at: datetime
    price_inr: int
    overnight: bool = False
    source: str
    link: str | None = None

    @property
    def hours(self) -> float:
        return (self.arrive_at - self.depart_at).total_seconds() / 3600


class StayOption(BaseModel):
    id: str
    name: str
    area: str = ""
    price_per_night_inr: int
    rating: float | None = None
    checkin_from: time = time(12, 0)
    checkin_until: time = time(22, 0)
    late_checkin: bool = False
    lat: float
    lng: float
    source: str
    link: str | None = None


class PlaceOption(BaseModel):
    id: str
    name: str
    category: str = "sightseeing"
    entry_fee_inr: int = 0
    est_hours: float = 2.0
    opens: time = time(9, 0)
    closes: time = time(18, 0)
    closed_days: list[str] = Field(default_factory=list)
    lat: float
    lng: float
    rating: float = 4.0
    source: str


class PlanItem(BaseModel):
    start: str
    end: str
    title: str
    kind: Literal["travel", "checkin", "place", "free"]
    place_id: str | None = None
    cost_inr: int = 0


class DayPlan(BaseModel):
    date: date
    weekday: str
    items: list[PlanItem] = Field(default_factory=list)
    km: float = 0.0


class CriticIssue(BaseModel):
    type: str
    day: date | None = None
    description: str
    responsible_agent: Literal["transport", "stay", "places", "writer"]


class TraceEvent(BaseModel):
    agent: str
    started_at: datetime
    duration_ms: int
    tokens: int = 0
    cost_usd: float = 0.0
    note: str = ""


class Learned(BaseModel):
    likes: list[str] = Field(default_factory=list)
    avoids: list[str] = Field(default_factory=list)
    memories: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)


class TripState(BaseModel):
    request: TripRequest
    learned: Learned = Field(default_factory=Learned)
    budget_plan: BudgetPlan | None = None
    round: int = 0
    rerun: list[str] = Field(default_factory=list)
    instructions: dict[str, list[str]] = Field(default_factory=dict)
    floors: Annotated[dict[str, int], merge] = Field(default_factory=dict)
    outbound_options: list[TransportOption] = Field(default_factory=list)
    return_options: list[TransportOption] = Field(default_factory=list)
    stay_options: list[StayOption] = Field(default_factory=list)
    place_options: list[PlaceOption] = Field(default_factory=list)
    selected_outbound: TransportOption | None = None
    selected_return: TransportOption | None = None
    selected_stay: StayOption | None = None
    selected_places: list[PlaceOption] = Field(default_factory=list)
    breakdown: dict[str, int] = Field(default_factory=dict)
    total_cost: int = 0
    over_budget_by: int = 0
    days: list[DayPlan] = Field(default_factory=list)
    critic_issues: list[CriticIssue] = Field(default_factory=list)
    critic_round: int = 0
    summary: str = ""
    trace: Annotated[list[TraceEvent], add] = Field(default_factory=list)
    errors: Annotated[list[str], add] = Field(default_factory=list)
    notes: Annotated[list[str], add] = Field(default_factory=list)
    writer_notes: list[str] = Field(default_factory=list)
    critic_notes: list[str] = Field(default_factory=list)

    def all_notes(self) -> list[str]:
        return list(dict.fromkeys(self.notes + self.writer_notes + self.critic_notes))
