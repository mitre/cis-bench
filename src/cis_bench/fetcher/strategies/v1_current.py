"""CIS WorkBench scraper strategy for current HTML structure (October 2025).

This strategy extracts ALL fields including:
- HTML content from <div id="..."> elements
- Structured data from custom <wb-...> elements
- Parsed compliance mappings (MITRE, NIST, CIS Controls)
"""

from bs4 import BeautifulSoup

from cis_bench.fetcher.strategies.base import ExtractedRecommendation, ScraperStrategy
from cis_bench.utils.html_parser import attribute_text
from cis_bench.utils.parsers import WorkbenchParser


class WorkbenchV1Strategy(ScraperStrategy):
    """Scraper for current CIS WorkBench HTML (as of October 2025).

    Extracts from TWO sources:
    1. <div id="*-recommendation-data"> elements - HTML content
    2. <wb-recommendation-*> custom elements - Structured JSON
    """

    @property
    def version(self) -> str:
        return "v1_2025_10"

    @property
    def selectors(self) -> dict[str, dict[str, str]]:
        """Element ID selectors for HTML content fields."""
        return {
            "assessment_html": {"id": "automated_scoring-recommendation-data"},
            "description": {"id": "description-recommendation-data"},
            "rationale": {"id": "rationale_statement-recommendation-data"},
            "impact": {"id": "impact_statement-recommendation-data"},
            "audit": {"id": "audit_procedure-recommendation-data"},
            "remediation": {"id": "remediation_procedure-recommendation-data"},
            "default_value": {"id": "default_value-recommendation-data"},
            "artifact_equation": {"id": "artifact_equation-recommendation-data"},
            "mitre_mapping_html": {"id": "mitre_mappings-recommendation-data"},
            "references": {"id": "references-recommendation-data"},
            "additional_info": {"id": "notes-recommendation-data"},
        }

    def extract_recommendation(self, html: str) -> ExtractedRecommendation:
        """Extract ALL recommendation fields from HTML.

        Extracts:
        - HTML content from div elements
        - Structured data from custom wb- elements
        - Parses tables and JSON

        Args:
            html: Raw HTML content from recommendation page

        Returns:
            Every field the page supplies, parsed where the model wants structure
        """
        soup = BeautifulSoup(html, "html.parser")

        # ============ Step 1: Extract HTML content from div elements ============
        content = {
            field: self._element_content(soup, selector)
            for field, selector in self.selectors.items()
        }

        # ============ Step 2: Extract from custom <wb-*> elements ============
        profiles_elem = soup.find("wb-recommendation-profiles")
        profiles_json = attribute_text(profiles_elem, "profiles") if profiles_elem else None

        controls_elem = soup.find("wb-recommendation-feature-controls")
        controls_json = attribute_text(controls_elem, "json-controls") if controls_elem else None

        artifacts_elem = soup.find("wb-recommendation-artifacts")
        artifacts_json = (
            attribute_text(artifacts_elem, "artifacts-json") if artifacts_elem else None
        )

        # ============ Step 3: Parse HTML tables/content to structured data ============
        assessment_html = content["assessment_html"]
        mitre_html = content["mitre_mapping_html"]
        references = content["references"]
        return ExtractedRecommendation(
            assessment_status=(
                WorkbenchParser.extract_assessment_status(assessment_html)
                if assessment_html
                else "Unknown"
            ),
            profiles=WorkbenchParser.parse_profiles_json(profiles_json) if profiles_json else [],
            cis_controls=(
                WorkbenchParser.parse_cis_controls_json(controls_json) if controls_json else []
            ),
            mitre_mapping=WorkbenchParser.parse_mitre_table(mitre_html) if mitre_html else None,
            nist_controls=WorkbenchParser.parse_nist_controls(references) if references else [],
            parent=WorkbenchParser.parse_parent_link(html),
            artifacts=(
                WorkbenchParser.parse_artifacts_json(artifacts_json) if artifacts_json else []
            ),
            description=content["description"],
            rationale=content["rationale"],
            impact=content["impact"],
            audit=content["audit"],
            remediation=content["remediation"],
            additional_info=content["additional_info"],
            default_value=content["default_value"],
            artifact_equation=content["artifact_equation"],
            references=references,
        )

    @staticmethod
    def _element_content(soup: BeautifulSoup, selector: dict[str, str]) -> str | None:
        """The inner HTML of the element the selector names, stripped; None when absent."""
        if "id" not in selector:
            return None
        elem = soup.find(id=selector["id"])
        if elem is None:
            return None
        return elem.decode_contents().strip()

    def is_compatible(self, html: str) -> bool:
        """Check if this strategy works with given HTML.

        Checks for presence of multiple signature elements for robustness.
        """
        soup = BeautifulSoup(html, "html.parser")

        # Check for at least 2 of our expected div elements
        found_divs = 0
        check_fields = ["description", "rationale", "audit"]

        for field in check_fields:
            selector = self.selectors.get(field)
            if selector and "id" in selector:
                if soup.find(id=selector["id"]):
                    found_divs += 1

        # Also check for custom wb- elements (modern benchmarks)
        has_wb_elements = bool(soup.find("wb-recommendation-profiles"))

        # Compatible if we have divs OR wb-elements
        return found_divs >= 2 or has_wb_elements
