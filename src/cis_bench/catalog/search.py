"""Search and filtering for CIS benchmark catalog.

Provides high-level search operations with filtering, ranking, and formatting.
"""

import logging

from cis_bench.catalog.database import CatalogDatabase

logger = logging.getLogger(__name__)


class CatalogSearch:
    """Search and filter catalog benchmarks."""

    def __init__(self, database: CatalogDatabase):
        """Initialize search.

        Args:
            database: CatalogDatabase instance
        """
        self.db = database

    def search(
        self,
        query: str = "",
        platform: str | None = None,
        platform_type: str | None = None,
        status: str | None = "Published",
        latest_only: bool = False,
        *,
        limit: int | None,
        named_releases: bool = False,
    ) -> list[dict]:
        """Search catalog with filters.

        Args:
            query: Search query (fuzzy matching)
            platform: Filter by platform name
            platform_type: Filter by platform category (cloud, os, database, container, application)
            status: Filter by status (default: Published; None or 'all' returns all statuses)
            latest_only: Only latest versions
            limit: Max results; None returns every match
            named_releases: With latest_only, also keep the releases the query names by
                their version, latest or not

        Returns:
            List of matching benchmarks with all metadata

        Example:
            search = CatalogSearch(db)
            results = search.search(
                "ubuntu", platform="Operating System", latest_only=True, limit=20
            )
        """
        logger.debug(
            f"Search: query='{query}', platform={platform}, platform_type={platform_type}, status={status!r}, latest={latest_only}"
        )

        # The database normalizes the status filter (None, blank, 'all' -> unfiltered).
        results = self.db.search(
            query=query,
            platform=platform,
            platform_type=platform_type,
            status=status,
            latest_only=latest_only,
            limit=limit,
            named_releases=named_releases,
        )

        logger.info(f"Search returned {len(results)} results")
        return results

    def count(
        self,
        query: str = "",
        platform: str | None = None,
        platform_type: str | None = None,
        status: str | None = "Published",
        latest_only: bool = False,
        *,
        named_releases: bool = False,
    ) -> int:
        """Count every benchmark search() would return for these filters, ignoring any limit."""
        return self.db.count_search(
            query=query,
            platform=platform,
            platform_type=platform_type,
            status=status,
            latest_only=latest_only,
            named_releases=named_releases,
        )

    def find_by_id(self, benchmark_id: str) -> dict | None:
        """Find benchmark by exact ID.

        Args:
            benchmark_id: Benchmark ID

        Returns:
            Benchmark dict or None
        """
        return self.db.get_benchmark(benchmark_id)

    def find_by_name(self, name: str, latest_only: bool = True) -> list[dict]:
        """Find benchmarks by name (fuzzy matching).

        Args:
            name: Part of benchmark name
            latest_only: Only latest versions

        Returns:
            List of matching benchmarks
        """
        return self.search(query=name, latest_only=latest_only, limit=20)

    def get_platforms(self) -> list[dict]:
        """Get all platforms with benchmark counts.

        Returns:
            List of platforms with counts
        """
        return self.db.list_platforms()

    def get_communities(self) -> list[dict]:
        """Get all communities with benchmark counts.

        Returns:
            List of communities
        """
        return self.db.list_communities()

    def format_result_for_display(self, result: dict) -> str:
        """Format search result for CLI display.

        Args:
            result: Benchmark result dict

        Returns:
            Formatted string for display

        Example:
            [23598] CIS Ubuntu Linux 20.04 LTS Benchmark v2.0.1
                    Platform: Operating System | Published: 2024-08-01 | Latest
        """
        # First line: [ID] Title Version
        line1 = f"[{result['benchmark_id']}] {result['title']}"
        if result.get("version"):
            line1 += f" {result['version']}"

        # Second line: metadata
        meta_parts = []

        if result.get("platform"):
            meta_parts.append(f"Platform: {result['platform']}")

        if result.get("published_date"):
            meta_parts.append(f"Published: {result['published_date']}")

        if result.get("is_latest"):
            meta_parts.append("Latest")

        line2 = " | ".join(meta_parts) if meta_parts else ""

        return f"{line1}\n        {line2}" if line2 else line1

    def format_results_table(self, results: list[dict], show_description: bool = False) -> str:
        """Format multiple results as a table.

        Args:
            results: List of benchmark results
            show_description: Include description snippets

        Returns:
            Formatted table string
        """
        if not results:
            return "No benchmarks found."

        lines = []

        for result in results:
            lines.append(self.format_result_for_display(result))

            if show_description and result.get("description"):
                desc = result["description"][:100]
                if len(result["description"]) > 100:
                    desc += "..."
                lines.append(f"        {desc}")

            lines.append("")  # Blank line between results

        return "\n".join(lines)
