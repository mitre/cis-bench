"""Download benchmarks using catalog with smart caching.

Integrates catalog database with WorkbenchScraper for efficient downloads.
"""

import logging

from cis_bench.catalog.database import (
    CatalogDatabase,
    deserialize_benchmark_json,
    serialize_benchmark_json,
)
from cis_bench.catalog.parser import WorkBenchCatalogParser
from cis_bench.catalog.search import CatalogSearch
from cis_bench.fetcher.workbench import WorkbenchScraper
from cis_bench.models.benchmark import Benchmark

logger = logging.getLogger(__name__)


class CatalogDownloader:
    """Download benchmarks using catalog with change detection."""

    def __init__(self, database: CatalogDatabase, scraper: WorkbenchScraper):
        """Initialize downloader.

        Args:
            database: CatalogDatabase instance
            scraper: WorkbenchScraper instance (authenticated)
        """
        self.db = database
        self.scraper = scraper
        self.search = CatalogSearch(database)

    def download_by_id(self, benchmark_id: str, force: bool = False) -> dict:
        """Download benchmark by catalog ID.

        Args:
            benchmark_id: Benchmark ID from catalog
            force: Force re-download even if up-to-date

        Returns:
            Dictionary with download info

        Raises:
            ValueError: If benchmark not in catalog
        """
        logger.info(f"Downloading benchmark: {benchmark_id}")

        # Get catalog entry
        catalog_entry = self.db.get_benchmark(benchmark_id)

        if not catalog_entry:
            raise ValueError(
                f"Benchmark {benchmark_id} not in catalog.\n"
                f"Run 'cis-bench catalog refresh' to populate catalog."
            )

        # Check if already downloaded
        existing = self.db.get_downloaded(benchmark_id)

        if existing and not force:
            logger.debug("Benchmark already downloaded, checking if up-to-date")

            # Compare revision dates if available
            if (
                catalog_entry.get("last_revision_date")
                and existing.get("workbench_last_modified")
                and catalog_entry["last_revision_date"] == existing["workbench_last_modified"]
            ):
                logger.info("Benchmark is up-to-date (matching revision date)")
                return {
                    "benchmark_id": benchmark_id,
                    "status": "already_current",
                    "downloaded_at": existing["downloaded_at"],
                    "recommendation_count": existing["recommendation_count"],
                    "message": "Already up-to-date. Use --force to re-download.",
                }

        # Validate and canonicalize benchmark URL against configured WorkBench origin
        _, benchmark_url = WorkBenchCatalogParser.normalize_benchmark_url(
            catalog_entry["url"],
            expected_benchmark_id=str(benchmark_id),
        )

        # Download from WorkBench
        logger.info(f"Fetching from WorkBench: {benchmark_url}")

        benchmark = self.scraper.download_benchmark(benchmark_url)

        content_json, content_hash = serialize_benchmark_json(benchmark)

        # Check if content actually changed
        is_unchanged = bool(existing and existing.get("content_hash") == content_hash and not force)
        if is_unchanged:
            logger.info("Content unchanged (same hash), updating timestamp only")

        self.db.save_downloaded(
            benchmark_id=benchmark_id,
            content_json=content_json,
            content_hash=content_hash,
            recommendation_count=len(benchmark.recommendations),
            workbench_last_modified=catalog_entry.get("last_revision_date"),
        )

        if is_unchanged:
            return {
                "benchmark_id": benchmark_id,
                "status": "unchanged",
                "content_hash": content_hash,
                "recommendation_count": len(benchmark.recommendations),
                "message": "Content unchanged (verified by hash).",
            }

        status = "updated" if existing else "downloaded"

        logger.info(
            f"Benchmark {status}: {len(benchmark.recommendations)} recommendations, {len(content_json)} bytes"
        )

        return {
            "benchmark_id": benchmark_id,
            "status": status,
            "content_hash": content_hash,
            "recommendation_count": len(benchmark.recommendations),
            "file_size": len(content_json),
            "benchmark": benchmark,  # Return Benchmark object
        }

    def download_by_name(
        self,
        name_query: str,
        latest: bool = True,
        interactive: bool = False,
        force: bool = False,
    ) -> dict:
        """Download benchmark by name (fuzzy search).

        Args:
            name_query: Search query (fuzzy matched)
            latest: Only search latest versions
            interactive: If multiple matches, prompt user to select
            force: Force re-download even if up-to-date

        Returns:
            Download result dict

        Raises:
            ValueError: If no matches or multiple matches without interactive
        """
        logger.info(f"Searching catalog for: {name_query}")

        results = self.search.find_by_name(name_query, latest_only=latest)

        if len(results) == 0:
            raise ValueError(f"No benchmarks found matching: {name_query}")

        if len(results) == 1:
            # Single match - download it
            benchmark_id = results[0]["benchmark_id"]
            logger.info(f"Found single match: {results[0]['title']}")
            return self.download_by_id(benchmark_id, force=force)

        # Multiple matches
        if not interactive:
            # Show matches and ask user to be more specific
            matches = "\n".join([f"  [{r['benchmark_id']}] {r['title']}" for r in results])
            raise ValueError(
                f"Multiple benchmarks match '{name_query}':\n{matches}\n\n"
                f"Use a more specific query or download by ID."
            )

        # Interactive selection (requires questionary)
        logger.info(f"Found {len(results)} matches, prompting for selection")
        benchmark_id = self._interactive_select(results)

        return self.download_by_id(benchmark_id, force=force)

    def _interactive_select(self, results: list[dict]) -> str:
        """Interactive selection from multiple results.

        Args:
            results: List of matching benchmarks

        Returns:
            Selected benchmark ID
        """
        import questionary

        choices = []
        for r in results:
            version = r.get("version")
            version_suffix = f" {version}" if version else ""
            choices.append(
                questionary.Choice(
                    title=f"[{r['benchmark_id']}] {r['title']}{version_suffix}",
                    value=str(r["benchmark_id"]),
                )
            )

        selection = questionary.select("Select benchmark:", choices=choices).ask()
        if not isinstance(selection, str) or not selection:
            raise ValueError("Benchmark selection cancelled")

        return selection

    def get_downloaded_benchmark(self, benchmark_id: str) -> Benchmark | None:
        """Get downloaded benchmark from database.

        Args:
            benchmark_id: Benchmark ID

        Returns:
            Benchmark object or None if not downloaded
        """
        downloaded = self.db.get_downloaded(benchmark_id)

        if not downloaded:
            return None

        return deserialize_benchmark_json(downloaded["content_json"])
