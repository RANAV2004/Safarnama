# providers
import os

from app.providers.base import PlacesProvider, ProviderError, StayProvider, TransportProvider
from app.providers.fixture import FixturePlaces, FixtureStays, FixtureTransport


class WithFallback:
    def __init__(self, primary, backup):
        self.primary, self.backup = primary, backup
        self.last_error: str | None = None

    def search(self, *args, **kwargs):
        self.last_error = None
        try:
            return self.primary.search(*args, **kwargs)
        except ProviderError as e:
            self.last_error = f"{type(self.primary).__name__} failed ({e}), used fixtures"
            return self.backup.search(*args, **kwargs)


class Providers:
    def __init__(self, transport, stays, places):
        self.transport, self.stays, self.places = transport, stays, places


def get_providers() -> Providers:
    mode = os.getenv("PROVIDER_MODE", "fixture")
    if mode == "live":
        from app.providers.serpapi import SerpApiFlights, SerpApiHotels

        return Providers(
            WithFallback(SerpApiFlights(), FixtureTransport()),
            WithFallback(SerpApiHotels(), FixtureStays()),
            FixturePlaces(),
        )
    return Providers(FixtureTransport(), FixtureStays(), FixturePlaces())


__all__ = [
    "get_providers",
    "Providers",
    "WithFallback",
    "ProviderError",
    "TransportProvider",
    "StayProvider",
    "PlacesProvider",
]
