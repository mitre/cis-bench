"""Scraper strategies for different HTML versions.

Strategies are auto-registered when imported.
"""

from .base import ScraperStrategy
from .detector import StrategyDetector
from .v1_current import WorkbenchV1Strategy
from .v2_2026 import WorkbenchV2Strategy

# Register newest strategy first so the detector prefers it while keeping
# V1 available as a fallback for older cached HTML.
StrategyDetector.register_strategy(WorkbenchV1Strategy(), position=0)
StrategyDetector.register_strategy(WorkbenchV2Strategy(), position=0)

__all__ = [
    "ScraperStrategy",
    "StrategyDetector",
    "WorkbenchV1Strategy",
    "WorkbenchV2Strategy",
]
