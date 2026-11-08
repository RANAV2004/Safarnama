# provider interfaces
from abc import ABC, abstractmethod
from datetime import date
from typing import Literal

from app.state import PlaceOption, StayOption, TransportOption


class ProviderError(Exception):
    pass


class TransportProvider(ABC):
    @abstractmethod
    def search(
        self,
        origin: str,
        destination: str,
        travel_date: date,
        travellers: int,
        direction: Literal["arrive_on", "depart_on"],
    ) -> list[TransportOption]: ...


class StayProvider(ABC):
    @abstractmethod
    def search(self, city: str, check_in: date, check_out: date, travellers: int) -> list[StayOption]: ...


class PlacesProvider(ABC):
    @abstractmethod
    def search(self, city: str) -> list[PlaceOption]: ...
