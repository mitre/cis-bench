"""Field helpers for Recommendation export.

The text fields are read as stored (Markdown, see cis_bench.models.benchmark); the list,
MITRE, parent and CIS Controls helpers below format the structured fields for exporters.
"""

import logging

from cis_bench.models.benchmark import RECOMMENDATION_TEXT_FIELDS, CISControl, Recommendation

logger = logging.getLogger(__name__)


class RecommendationFieldTransformer:
    """The text fields of a recommendation, for exporters that write every one."""

    # The text fields, in the model's order (Markdown as stored)
    CONTENT_FIELDS = list(RECOMMENDATION_TEXT_FIELDS)

    @classmethod
    def stored_text(cls, rec: Recommendation) -> dict[str, str]:
        """Every text field as stored: the Markdown WorkBench gives, "" for a field with none.

        Nothing is parsed or converted here: a placeholder such as <user> is part of the text.
        """
        return {field: getattr(rec, field) or "" for field in cls.CONTENT_FIELDS}


class SafeFieldAccessor:
    """Safe field access with default values.

    Eliminates 20+ instances of 'field if field else ""' pattern.
    """

    @staticmethod
    def get_text(rec: Recommendation, field: str, default: str = "") -> str:
        """Get field value or default.

        Args:
            rec: Recommendation
            field: Field name
            default: Default value if field is None or empty

        Returns:
            Field value or default

        Example:
            >>> title = SafeFieldAccessor.get_text(rec, 'title', 'Untitled')
        """
        value = getattr(rec, field, None)
        return value if value else default

    @staticmethod
    def get_list_as_csv(items: list[str] | None, separator: str = ", ") -> str:
        """Convert list to separated string or empty string.

        Args:
            items: List of strings (or None)
            separator: Separator string

        Returns:
            Joined string or empty string if None/empty

        Example:
            >>> csv = SafeFieldAccessor.get_list_as_csv(rec.profiles, ', ')
        """
        return separator.join(items) if items else ""

    @staticmethod
    def get_mitre_field(rec: Recommendation, field: str, separator: str = ", ") -> str:
        """Get MITRE mapping field as CSV.

        Args:
            rec: Recommendation
            field: MITRE field name ('techniques', 'tactics', 'mitigations')
            separator: Separator string

        Returns:
            Comma-separated values or empty string

        Example:
            >>> techniques = SafeFieldAccessor.get_mitre_field(rec, 'techniques')
        """
        if not rec.mitre_mapping:
            return ""
        items = getattr(rec.mitre_mapping, field, None)
        return separator.join(items) if items else ""

    @staticmethod
    def get_parent_title(rec: Recommendation) -> str:
        """Get parent title or empty string.

        Args:
            rec: Recommendation

        Returns:
            Parent title or empty string

        Example:
            >>> parent = SafeFieldAccessor.get_parent_title(rec)
        """
        return rec.parent.title if rec.parent else ""

    @staticmethod
    def format_parent_link(rec: Recommendation, format: str = "markdown") -> str:
        """Format parent as link.

        Args:
            rec: Recommendation
            format: Link format ('markdown', 'html', 'plain')

        Returns:
            Formatted parent link or empty string

        Example:
            >>> link = SafeFieldAccessor.format_parent_link(rec, 'markdown')
            >>> # Result: "[Parent Title](https://url)"
        """
        if not rec.parent:
            return ""

        if format == "markdown":
            return f"[{rec.parent.title}]({rec.parent.url})"
        elif format == "html":
            return f'<a href="{rec.parent.url}">{rec.parent.title}</a>'
        else:  # plain
            return rec.parent.title


class CISControlFormatter:
    """Format CIS controls for export.

    Eliminates 3+ instances of CIS control filtering/formatting code.
    """

    @staticmethod
    def filter_by_version(controls: list[CISControl], version: int) -> str:
        """Get controls for specific version as CSV.

        Args:
            controls: List of CIS controls
            version: Version to filter by (7 or 8)

        Returns:
            Comma-separated control IDs

        Example:
            >>> v8 = CISControlFormatter.filter_by_version(rec.cis_controls, 8)
            >>> # Result: "4.1, 4.8, 5.3"
        """
        filtered = [c.control for c in controls if c.version == version]
        return ", ".join(filtered)

    @staticmethod
    def format_all_with_version(controls: list[CISControl]) -> str:
        """Format all controls with version prefix.

        Args:
            controls: List of CIS controls

        Returns:
            Formatted string with version prefixes

        Example:
            >>> formatted = CISControlFormatter.format_all_with_version(rec.cis_controls)
            >>> # Result: "v8:4.1, v8:4.8, v7:9.2"
        """
        return ", ".join([f"v{c.version}:{c.control}" for c in controls])

    @staticmethod
    def group_by_version(controls: list[CISControl]) -> dict[int, list[str]]:
        """Group controls by version.

        Args:
            controls: List of CIS controls

        Returns:
            Dict mapping version to list of control IDs

        Example:
            >>> grouped = CISControlFormatter.group_by_version(rec.cis_controls)
            >>> print(grouped[8])  # ['4.1', '4.8']
            >>> print(grouped[7])  # ['9.2']
        """
        grouped: dict[int, list[str]] = {}
        for c in controls:
            grouped.setdefault(c.version, []).append(c.control)
        return grouped

    @staticmethod
    def format_with_details(controls: list[CISControl], include_igs: bool = True) -> list[str]:
        """Format controls with full details.

        Args:
            controls: List of CIS controls
            include_igs: Include IG levels in output

        Returns:
            List of formatted control strings

        Example:
            >>> details = CISControlFormatter.format_with_details(rec.cis_controls)
            >>> # Result: ["v8:4.8 (IG2, IG3): Disable Unnecessary Services", ...]
        """
        result = []
        for c in controls:
            igs = []
            if include_igs:
                if c.ig1:
                    igs.append("IG1")
                if c.ig2:
                    igs.append("IG2")
                if c.ig3:
                    igs.append("IG3")

            ig_str = f" ({', '.join(igs)})" if igs else ""
            result.append(f"v{c.version}:{c.control}{ig_str}: {c.title}")

        return result
