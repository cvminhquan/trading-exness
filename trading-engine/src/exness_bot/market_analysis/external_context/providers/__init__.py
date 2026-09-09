"""Free external data providers package."""

from exness_bot.market_analysis.external_context.providers.bls import BlsProvider
from exness_bot.market_analysis.external_context.providers.composite import (
    FreeSourcesCompositeProvider,
)
from exness_bot.market_analysis.external_context.providers.federal_reserve import (
    FederalReserveProvider,
)
from exness_bot.market_analysis.external_context.providers.fred import FredProvider
from exness_bot.market_analysis.external_context.providers.rss import RssProvider

__all__ = [
    "BlsProvider",
    "FederalReserveProvider",
    "FredProvider",
    "FreeSourcesCompositeProvider",
    "RssProvider",
]
