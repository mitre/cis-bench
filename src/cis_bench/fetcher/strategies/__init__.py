"""Scraper strategies for different HTML versions.

Strategies are auto-registered when imported.
"""

from .base import ScraperStrategy
from .detector import StrategyDetector
from .v1_current import WorkbenchV1Strategy

# Auto-register current strategy
StrategyDetector.register_strategy(WorkbenchV1Strategy())

__all__ = [
    "ScraperStrategy",
    "StrategyDetector",
    "WorkbenchV1Strategy",
]
