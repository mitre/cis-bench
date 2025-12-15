"""Strategy detection and management.

Auto-detects which scraper strategy to use based on HTML structure.
"""

import logging

from .base import ScraperStrategy

logger = logging.getLogger(__name__)


class StrategyDetector:
    """Auto-detects and selects the correct scraper strategy.

    Strategies are checked in order (newest first). The first compatible
    strategy is selected. This allows backward compatibility with older
    benchmark HTML while supporting new structures.
    """

    # Strategies ordered newest → oldest (check newest first)
    # Populated by importing strategy modules
    _strategies: list[ScraperStrategy] = []

    @classmethod
    def register_strategy(cls, strategy: ScraperStrategy, position: int = 0):
        """Register a scraper strategy.

        Args:
            strategy: Strategy instance to register
            position: Position in strategy list (0 = highest priority)

        Example:
            StrategyDetector.register_strategy(WorkbenchV1Strategy())
        """
        cls._strategies.insert(position, strategy)
        logger.debug(f"Registered scraper strategy: {strategy.version} at position {position}")

    @classmethod
    def detect_strategy(cls, html: str) -> ScraperStrategy:
        """Auto-detect which strategy to use for given HTML.

        Args:
            html: Raw HTML content from CIS WorkBench

        Returns:
            Compatible scraper strategy

        Raises:
            ValueError: If no compatible strategy found

        Note:
            Strategies are checked in order. First match wins.
        """
        if not cls._strategies:
            raise ValueError(
                "No scraper strategies registered. Import a strategy module to register strategies."
            )

        for strategy in cls._strategies:
            try:
                if strategy.is_compatible(html):
                    logger.debug(f"Selected scraper strategy: {strategy.version}")
                    return strategy
            except Exception as e:
                logger.warning(f"Strategy {strategy.version} compatibility check failed: {e}")
                continue

        raise ValueError(
            "No compatible scraper strategy found for the given HTML. "
            "CIS WorkBench HTML structure may have changed. "
            "Please report this issue with the URL you were trying to scrape."
        )

    @classmethod
    def get_strategy(cls, version: str) -> ScraperStrategy | None:
        """Get specific strategy by version.

        Args:
            version: Strategy version identifier (e.g., 'v1_2025_10')

        Returns:
            Strategy instance if found, None otherwise
        """
        for strategy in cls._strategies:
            if strategy.version == version:
                return strategy
        return None

    @classmethod
    def list_strategies(cls) -> list[str]:
        """Get list of registered strategy versions.

        Returns:
            List of version strings, ordered by priority
        """
        return [s.version for s in cls._strategies]

    @classmethod
    def clear_strategies(cls):
        """Clear all registered strategies (useful for testing)."""
        cls._strategies = []
