"""Parsers for the HTML tables and references WorkBench pages carry, and attribute access.

Benchmark text itself is Markdown and is stored and written as it is; nothing here converts
or strips it."""

import logging
import re
from typing import Any

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)


def attribute_text(tag: Tag, name: str) -> str | None:
    """The value of one attribute of tag as text, or None when the tag does not have it.

    bs4 stores multi-valued attributes such as class as a list of words; those are joined
    with single spaces, the way bs4 writes them back out.
    """
    value = tag.get(name)
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return " ".join(value)


class HTMLCleaner:
    """Parsers for the HTML tables (MITRE ATT&CK, CIS Controls) and references on WorkBench
    pages."""

    @staticmethod
    def parse_mitre_table(html: str | None) -> dict[str, list[str]] | None:
        """Parse MITRE ATT&CK mapping table from HTML.

        Args:
            html: HTML content containing MITRE mapping table

        Returns:
            Dictionary with techniques, tactics, mitigations lists or None
        """
        if not html or html == "null":
            return None

        logger.debug("Parsing MITRE ATT&CK mapping table")
        soup = BeautifulSoup(html, "html.parser")

        # Find the MITRE mapping table
        table = soup.find("table")
        if not table:
            logger.debug("No MITRE table found in HTML")
            return None

        result: dict[str, list[str]] = {"techniques": [], "tactics": [], "mitigations": []}

        # Parse table rows
        rows = table.find_all("tr")
        current_section = None

        for row in rows:
            cells = row.find_all(["th", "td"])
            if not cells:
                continue

            # Header row
            if cells[0].name == "th":
                header_text = cells[0].get_text(strip=True).lower()
                if "technique" in header_text:
                    current_section = "techniques"
                elif "tactic" in header_text:
                    current_section = "tactics"
                elif "mitigation" in header_text:
                    current_section = "mitigations"

            # Data row
            elif cells[0].name == "td" and current_section:
                # Parse comma-separated values
                text = cells[0].get_text(strip=True)
                if text:
                    items = [item.strip() for item in text.split(",")]
                    result[current_section].extend(items)

        has_data = any(result.values())
        if has_data:
            logger.debug(
                f"Parsed MITRE data: techniques={len(result['techniques'])}, "
                f"tactics={len(result['tactics'])}, mitigations={len(result['mitigations'])}"
            )
        return result if has_data else None

    @staticmethod
    def parse_cis_controls_table(html: str | None) -> list[dict[str, Any]]:
        """Parse CIS Controls table from HTML.

        Expected structure:
        Control    IG1    IG2    IG3
        Version 8
        10.3       ✓      ✓      ✓
        Version 7
        8.5        ✓      ✓

        Args:
            html: HTML content containing CIS Controls table

        Returns:
            List of CIS Control mappings
        """
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")

        # Find CIS Controls section (might be in references or separate field)
        # This is a placeholder - need to see actual HTML structure
        controls = []

        # Look for "Version 8" and "Version 7" patterns
        text = soup.get_text()

        # Parse Version 8 controls
        v8_match = re.search(r"Version 8\s+([\d.]+)", text)
        if v8_match:
            controls.append(
                {
                    "version": "8",
                    "control_id": v8_match.group(1),
                    "ig1": "IG1" in text,  # Simplified - needs table parsing
                    "ig2": "IG2" in text,
                    "ig3": "IG3" in text,
                }
            )

        # Parse Version 7 controls
        v7_match = re.search(r"Version 7\s+([\d.]+)", text)
        if v7_match:
            controls.append(
                {
                    "version": "7",
                    "control_id": v7_match.group(1),
                    "ig1": "IG1" in text,
                    "ig2": "IG2" in text,
                    "ig3": "IG3" in text,
                }
            )

        return controls

    @staticmethod
    def parse_nist_references(html: str | None) -> list[str]:
        """Parse NIST 800-53 control references from HTML.

        Args:
            html: HTML content containing NIST references

        Returns:
            List of NIST control IDs
        """
        if not html:
            return []

        # Look for patterns like "NIST SP 800-53 Rev. 5: SI-3, MP-7"
        nist_pattern = r"NIST SP 800-53[^:]*:\s*([A-Z]{2}-\d+(?:\s*\([^)]+\))?(?:\s*,\s*[A-Z]{2}-\d+(?:\s*\([^)]+\))?)*)"

        matches = re.findall(nist_pattern, html)
        controls = []

        for match in matches:
            # Split by comma and clean
            items = [item.strip() for item in match.split(",")]
            controls.extend(items)

        return list(set(controls))  # Deduplicate

    @staticmethod
    def extract_profiles_from_title(title: str) -> list[str]:
        """Extract profile/level indicators from title.

        Args:
            title: Recommendation title

        Returns:
            List of profiles (e.g., ['L1', 'Server'] or ['L2', 'Workstation'])
        """
        profiles = []

        # Extract level (L1 or L2)
        if "(L1)" in title:
            profiles.append("Level 1")
        elif "(L2)" in title:
            profiles.append("Level 2")

        # Could also look for Server/Workstation in title or elsewhere
        # This would require seeing the actual data

        return profiles


class HTMLValidator:
    """Validate HTML content structure."""

    @staticmethod
    def has_table(html: str | None) -> bool:
        """Check if HTML contains a table."""
        if not html:
            return False
        return "<table" in html.lower()

    @staticmethod
    def extract_all_ids(html: str) -> list[str]:
        """Extract all element IDs from HTML (for debugging).

        Args:
            html: HTML content

        Returns:
            List of element IDs found
        """
        soup = BeautifulSoup(html, "html.parser")
        return [attribute_text(elem, "id") or "" for elem in soup.find_all(id=True)]
