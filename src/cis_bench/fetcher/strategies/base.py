"""Base class for scraper strategies.

Strategy pattern allows the scraper to adapt to different HTML structures
as CIS WorkBench evolves their website over time.
"""

from abc import ABC, abstractmethod
from typing import Any


class ScraperStrategy(ABC):
    """Abstract base for scraper strategies.

    Each strategy knows how to extract data from a specific HTML structure.
    When CIS WorkBench changes their HTML, create a new strategy class.

    Example:
        class WorkbenchV2Strategy(ScraperStrategy):
            version = "v2_2026_01"

            selectors = {
                "description": {"class": "new-description-class"}
            }

            def extract_recommendation(self, html):
                # Extract using new structure
                ...
    """

    @property
    @abstractmethod
    def version(self) -> str:
        """Strategy version identifier.

        Returns:
            Version string (e.g., 'v1_2025_10')

        Note:
            Use format: v{major}_{YYYY}_{MM} for tracking
        """
        pass

    @property
    @abstractmethod
    def selectors(self) -> dict[str, dict[str, str]]:
        """CSS/XPath selectors for this HTML version.

        Returns:
            Dict mapping field names to selector configs

        Example:
            {
                "assessment": {"id": "automated_scoring-recommendation-data"},
                "description": {"class": "recommendation-desc"},
                "audit": {"xpath": "//div[@data-field='audit']"}
            }
        """
        pass

    @abstractmethod
    def extract_recommendation(self, html: str) -> dict[str, Any]:
        """Extract recommendation data from HTML.

        Args:
            html: Raw HTML content from recommendation page

        Returns:
            Dictionary with extracted fields matching our Pydantic model:
            {
                'assessment': str | None,
                'description': str | None,
                'rationale': str | None,
                'impact': str | None,
                'audit': str | None,
                'remediation': str | None,
                'default_value': str | None,
                'artifact_eq': str | None,
                'mitre_mapping': str | None,
                'references': str | None
            }

        Raises:
            ValueError: If HTML cannot be parsed

        Note:
            Should return None for fields not found (don't raise exceptions)
        """
        pass

    def is_compatible(self, html: str) -> bool:
        """Check if this strategy can parse the given HTML.

        Args:
            html: Raw HTML content

        Returns:
            True if this strategy can handle the HTML, False otherwise

        Note:
            Default implementation checks for presence of first selector.
            Override for more sophisticated detection logic.
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        # Check if first selector exists
        if not self.selectors:
            return False

        first_field = list(self.selectors.keys())[0]
        first_selector = self.selectors[first_field]

        if "id" in first_selector:
            return soup.find(id=first_selector["id"]) is not None
        elif "class" in first_selector:
            return soup.find(class_=first_selector["class"]) is not None

        return False

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} version={self.version}>"
