"""Parsing utilities for extracting structured data from CIS WorkBench HTML."""

import json
import re

from bs4 import BeautifulSoup

from cis_bench.models.benchmark import Artifact, CISControl, MITREMapping, ParentReference


class WorkbenchParser:
    """Utilities for parsing CIS WorkBench HTML into structured data."""

    @staticmethod
    def parse_mitre_table(html: str | None) -> MITREMapping | None:
        """Parse MITRE ATT&CK mapping from HTML table.

        Args:
            html: HTML containing MITRE mapping table

        Returns:
            MITREMapping object or None if no data
        """
        if not html or html == "null" or not html.strip():
            return None

        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")

        if not table:
            return None

        result = {"techniques": [], "tactics": [], "mitigations": []}

        rows = table.find_all("tr")
        current_section = None

        for row in rows:
            cells = row.find_all(["th", "td"])
            if not cells:
                continue

            # Header row - determines which section
            if cells[0].name == "th":
                header_text = cells[0].get_text(strip=True).lower()
                if "technique" in header_text:
                    current_section = "techniques"
                elif "tactic" in header_text:
                    current_section = "tactics"
                elif "mitigation" in header_text:
                    current_section = "mitigations"

            # Data row - contains comma-separated IDs
            elif cells[0].name == "td" and current_section:
                text = cells[0].get_text(strip=True)
                if text:
                    # Split by comma and clean
                    items = [item.strip() for item in text.split(",") if item.strip()]
                    result[current_section].extend(items)

        # Return None if no data found
        if not any(result.values()):
            return None

        return MITREMapping(**result)

    @staticmethod
    def parse_nist_controls(html: str | None) -> list[str]:
        """Parse NIST SP 800-53 control references from HTML.

        Args:
            html: HTML containing NIST references

        Returns:
            List of NIST control IDs
        """
        if not html:
            return []

        # Pattern: "NIST SP 800-53 Rev. X: CONTROL-ID, CONTROL-ID"
        # Or: "NIST SP 800-53 Revision X :: CONTROL-ID (ENHANCEMENT)"
        patterns = [
            r"NIST SP 800-53[^:]*:\s*([A-Z]{2}-\d+(?:\s*\([^)]+\))?(?:\s*,\s*[A-Z]{2}-\d+(?:\s*\([^)]+\))?)*)",
            r"NIST SP 800-53[^:]*::\s*([A-Z]{2}-\d+(?:\s*\([^)]+\))?)",
        ]

        controls = []
        for pattern in patterns:
            matches = re.findall(pattern, html)
            for match in matches:
                # Split by comma
                items = [item.strip() for item in match.split(",")]
                controls.extend(items)

        return sorted(set(controls))  # Deduplicate and sort

    @staticmethod
    def parse_profiles_json(profiles_json: str) -> list[str]:
        """Parse profiles from JSON string.

        Args:
            profiles_json: JSON string from wb-recommendation-profiles element

        Returns:
            List of profile titles
        """
        try:
            profiles_data = json.loads(profiles_json)
            return [p["title"] for p in profiles_data if "title" in p]
        except (json.JSONDecodeError, KeyError, TypeError):
            return []

    @staticmethod
    def parse_cis_controls_json(controls_json: str) -> list[CISControl]:
        """Parse CIS Controls from JSON string.

        Args:
            controls_json: JSON string from wb-recommendation-feature-controls element

        Returns:
            List of CISControl objects
        """
        try:
            controls_data = json.loads(controls_json)
            controls = []

            for c in controls_data:
                # Handle None/missing IG values - default to False
                control = CISControl(
                    version=c["version"],
                    control=c["control"],
                    title=c.get("title", ""),
                    ig1=c.get("ig1") if c.get("ig1") is not None else False,
                    ig2=c.get("ig2") if c.get("ig2") is not None else False,
                    ig3=c.get("ig3") if c.get("ig3") is not None else False,
                )
                controls.append(control)

            return controls

        except (json.JSONDecodeError, KeyError, TypeError):
            return []

    @staticmethod
    def parse_artifacts_json(artifacts_json: str) -> list[Artifact]:
        """Parse artifacts from JSON string.

        Args:
            artifacts_json: JSON string from wb-recommendation-artifacts element

        Returns:
            List of Artifact objects
        """
        try:
            artifacts_data = json.loads(artifacts_json)
            artifacts = []

            for a in artifacts_data:
                artifact = Artifact(
                    id=a["id"],
                    view_level=a.get("view_level", ""),
                    title=a.get("title", ""),
                    status=a.get("status", "unknown"),
                    artifact_type=a.get("artifact_type", {}),
                )
                artifacts.append(artifact)

            return artifacts

        except (json.JSONDecodeError, KeyError, TypeError):
            return []

    @staticmethod
    def parse_parent_link(html: str) -> ParentReference | None:
        """Parse parent recommendation link from HTML.

        Args:
            html: Full page HTML

        Returns:
            ParentReference or None
        """
        soup = BeautifulSoup(html, "html.parser")

        # Find link with "PARENT" text
        parent_link = soup.find("a", string=re.compile(r"PARENT\s*:", re.IGNORECASE))

        if not parent_link:
            # Try finding by icon class
            icon = soup.find("i", class_="fa-level-up")
            if icon and icon.parent and icon.parent.name == "a":
                parent_link = icon.parent

        if parent_link and parent_link.get("href"):
            title_text = parent_link.get_text(strip=True)
            # Remove "PARENT :" prefix
            title = re.sub(r"^.*PARENT\s*:\s*", "", title_text, flags=re.IGNORECASE)

            return ParentReference(url=parent_link["href"], title=title)

        return None

    @staticmethod
    def extract_assessment_status(html: str | None) -> str:
        """Extract assessment status from HTML.

        Args:
            html: HTML from assessment field

        Returns:
            'Automated' or 'Manual'
        """
        if not html:
            return "Unknown"

        text = BeautifulSoup(html, "html.parser").get_text(strip=True)

        if "automated" in text.lower():
            return "Automated"
        elif "manual" in text.lower():
            return "Manual"
        else:
            return text if text else "Unknown"
