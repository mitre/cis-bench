"""Base class for scraper strategies.

Strategy pattern allows the scraper to adapt to different HTML structures
as CIS WorkBench evolves their website over time.
"""

from abc import ABC, abstractmethod
from typing import TypedDict

from cis_bench.models.benchmark import Artifact, CISControl, MITREMapping, ParentReference


class ExtractedRecommendation(TypedDict):
    """What a strategy extracts from one recommendation page.

    Every ``Recommendation`` field except ``ref``, ``title`` and ``url``, which come from
    the navigation tree; the scraper unpacks this straight into the model. Typing each
    field is what lets the type checker catch a strategy that fills a field with the wrong
    shape when WorkBench's markup changes.
    """

    assessment_status: str
    profiles: list[str]
    cis_controls: list[CISControl]
    mitre_mapping: MITREMapping | None
    nist_controls: list[str]
    parent: ParentReference | None
    artifacts: list[Artifact]
    description: str | None
    rationale: str | None
    impact: str | None
    audit: str | None
    remediation: str | None
    additional_info: str | None
    default_value: str | None
    artifact_equation: str | None
    references: str | None


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
    def extract_recommendation(self, html: str) -> ExtractedRecommendation:
        """Extract recommendation data from HTML.

        Args:
            html: Raw HTML content from recommendation page

        Returns:
            The fields of the Pydantic ``Recommendation`` model that the page supplies
            (see ``ExtractedRecommendation``); a field the page does not have is None or
            empty, never missing.
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
