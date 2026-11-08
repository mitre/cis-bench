"""HTML parsing and cleaning utilities for CIS benchmark data."""

import logging
import re
import warnings
from typing import Any

from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning, Tag

# strip_html: block elements are set apart by a blank line; line elements end a line
_BLOCK_TAGS = [
    "p",
    "div",
    "pre",
    "ul",
    "ol",
    "dl",
    "table",
    "blockquote",
    "section",
    "article",
    "header",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
]
_LIST_TAGS = ["ul", "ol", "dl"]
_LINE_TAGS = ["li", "tr", "dt", "dd"]
_CELL_TAGS = ["td", "th"]
# Where a tag breaks the text, strip_html leaves a mark (private-use characters, removed from
# the input first). Each run of marks with the whitespace around them becomes one line
# break, or a blank line when a block starts or ends in it, so the source's indentation
# between tags adds nothing while the text's own line breaks away from tags are kept.
_LINE_MARK = ""
_BLOCK_MARK = ""
_NO_MARKS = {ord(_LINE_MARK): None, ord(_BLOCK_MARK): None}
_MARK_RUN_RE = re.compile(
    rf"[ \t\n]*[{_LINE_MARK}{_BLOCK_MARK}](?:[ \t\n]*[{_LINE_MARK}{_BLOCK_MARK}])*[ \t]*\n?"
)
_TRAILING_SPACE_RE = re.compile(r"[ \t]+$", re.MULTILINE)
_BLANK_LINES_RE = re.compile(r"\n{3,}")

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
    """Utilities for cleaning and parsing HTML content from CIS benchmarks."""

    @staticmethod
    def strip_html(html: str | None) -> str:
        """The text of HTML or HTML-bearing text as plain text a reader can follow.

        WorkBench's fields are Markdown-like text whose own line breaks and spacing carry
        its structure (commands, lists, paragraphs), so line breaks and spacing away from
        tags are kept as written (Windows line breaks become \\n). Tags change the text
        where they stand: inline markup (b, code, a, ...) leaves its text in the sentence
        with no added space; paragraphs, headings, tables and lists other than a list
        inside a list item are set apart by a blank line; list items, table rows and <br>
        are lines of their own; table cells are separated by a tab. Whitespace between
        tags adds nothing. Trailing spaces are dropped and three or more line breaks
        become one blank line.

        The text is parsed as HTML, so anything in angle brackets is read as a tag and
        removed with it: a placeholder such as <user> in a command does not survive.

        Args:
            html: HTML content or None

        Returns:
            Plain text, entities decoded; "" for no content
        """
        if not html:
            return ""

        logger.debug(f"Stripping HTML tags from content (length: {len(html)})")
        html = html.replace("\r\n", "\n").replace("\r", "\n").translate(_NO_MARKS)
        # Text with no tags still goes through the parser so its entities are decoded; a
        # field that is only a URL or a path makes bs4 warn that the input looks like a
        # locator, and here it is content, so that one warning is not wanted.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", MarkupResemblesLocatorWarning)
            soup = BeautifulSoup(html, "html.parser")

        for tag in soup.find_all(_BLOCK_TAGS):
            nested_list = tag.name in _LIST_TAGS and tag.find_parent(_LINE_TAGS) is not None
            mark = _LINE_MARK if nested_list else _BLOCK_MARK
            tag.insert_before(mark)
            tag.insert_after(mark)
        for tag in soup.find_all(_LINE_TAGS):
            tag.insert_before(_LINE_MARK)
            tag.insert_after(_LINE_MARK)
        for cell in soup.find_all(_CELL_TAGS):
            if cell.find_previous_sibling(_CELL_TAGS) is not None:
                cell.insert_before("\t")
        for br in soup.find_all("br"):
            br.replace_with("\n")

        text = _MARK_RUN_RE.sub(
            lambda run: "\n\n" if _BLOCK_MARK in run.group() else "\n", soup.get_text()
        )
        text = _TRAILING_SPACE_RE.sub("", text)
        result = _BLANK_LINES_RE.sub("\n\n", text).strip("\n").rstrip()
        logger.debug(f"Stripped result length: {len(result)}")
        return result

    @staticmethod
    def html_to_markdown(html: str | None) -> str:
        """Convert HTML to Markdown format.

        Args:
            html: HTML content

        Returns:
            Markdown formatted text
        """
        if not html:
            return ""

        # Simple HTML → Markdown conversion
        # For production, consider using html2text library
        text = html
        text = re.sub(r"<p>(.*?)</p>", r"\1\n\n", text)
        text = re.sub(r"<code>(.*?)</code>", r"`\1`", text)
        text = re.sub(r"<pre>(.*?)</pre>", r"```\n\1\n```", text, flags=re.DOTALL)
        text = re.sub(r"<li>(.*?)</li>", r"- \1", text)
        text = re.sub(r"<ul>(.*?)</ul>", r"\1", text, flags=re.DOTALL)
        text = re.sub(r"<strong>(.*?)</strong>", r"**\1**", text)
        text = re.sub(r"<em>(.*?)</em>", r"*\1*", text)

        # Remove remaining tags. A field that is only a URL makes bs4 warn that the input
        # looks like a locator; here it is content, so that one warning is not wanted.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", MarkupResemblesLocatorWarning)
            soup = BeautifulSoup(text, "html.parser")
        return soup.get_text(separator="\n", strip=True)

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
                f"Parsed MITRE data: {len(result['techniques'])} techniques, {len(result['tactics'])} tactics, {len(result['mitigations'])} mitigations"
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
