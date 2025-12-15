"""CIS WorkBench scraper strategy for current HTML structure (October 2025).

This strategy extracts ALL fields including:
- HTML content from <div id="..."> elements
- Structured data from custom <wb-...> elements
- Parsed compliance mappings (MITRE, NIST, CIS Controls)
"""

from typing import Any

from bs4 import BeautifulSoup

from cis_bench.utils.parsers import WorkbenchParser

from .base import ScraperStrategy


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

    def extract_recommendation(self, html: str) -> dict[str, Any]:
        """Extract ALL recommendation fields from HTML.

        Extracts:
        - HTML content from div elements
        - Structured data from custom wb- elements
        - Parses tables and JSON

        Args:
            html: Raw HTML content from recommendation page

        Returns:
            Dictionary with all extracted and parsed fields
        """
        soup = BeautifulSoup(html, "html.parser")
        data = {}

        # ============ Step 1: Extract HTML content from div elements ============
        for field, selector in self.selectors.items():
            elem = None

            if "id" in selector:
                elem = soup.find(id=selector["id"])

            if elem is not None:
                data[field] = elem.decode_contents().strip()
            else:
                data[field] = None

        # ============ Step 2: Extract from custom <wb-*> elements ============

        # Profiles
        profiles_elem = soup.find("wb-recommendation-profiles")
        if profiles_elem and profiles_elem.get("profiles"):
            data["profiles"] = WorkbenchParser.parse_profiles_json(profiles_elem.get("profiles"))
        else:
            data["profiles"] = []

        # CIS Controls
        controls_elem = soup.find("wb-recommendation-feature-controls")
        if controls_elem and controls_elem.get("json-controls"):
            data["cis_controls"] = WorkbenchParser.parse_cis_controls_json(
                controls_elem.get("json-controls")
            )
        else:
            data["cis_controls"] = []

        # Artifacts
        artifacts_elem = soup.find("wb-recommendation-artifacts")
        if artifacts_elem and artifacts_elem.get("artifacts-json"):
            data["artifacts"] = WorkbenchParser.parse_artifacts_json(
                artifacts_elem.get("artifacts-json")
            )
        else:
            data["artifacts"] = []

        # ============ Step 3: Parse HTML tables/content to structured data ============

        # Parse MITRE mapping table
        if data.get("mitre_mapping_html"):
            data["mitre_mapping"] = WorkbenchParser.parse_mitre_table(data["mitre_mapping_html"])
        else:
            data["mitre_mapping"] = None

        # Parse NIST controls from references
        if data.get("references"):
            data["nist_controls"] = WorkbenchParser.parse_nist_controls(data["references"])
        else:
            data["nist_controls"] = []

        # Parse assessment status
        if data.get("assessment_html"):
            data["assessment_status"] = WorkbenchParser.extract_assessment_status(
                data["assessment_html"]
            )
        else:
            data["assessment_status"] = "Unknown"

        # Parse parent reference (from full HTML)
        data["parent"] = WorkbenchParser.parse_parent_link(html)

        # ============ Step 4: Clean up temporary fields ============
        # Remove temporary HTML fields we only needed for parsing
        data.pop("assessment_html", None)
        data.pop("mitre_mapping_html", None)

        return data

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
