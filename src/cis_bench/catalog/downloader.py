"""Download benchmarks using catalog with smart caching.

Integrates catalog database with WorkbenchScraper for efficient downloads.
"""

import logging
from collections.abc import Callable

from cis_bench.catalog.database import (
    CatalogDatabase,
    deserialize_benchmark_json,
    serialize_benchmark_json,
    update_reason,
)
from cis_bench.catalog.search import CatalogSearch
from cis_bench.fetcher.workbench import WorkbenchScraper
from cis_bench.models.benchmark import Benchmark, BenchmarkPage
from cis_bench.utils.workbench_urls import normalize_benchmark_url

logger = logging.getLogger(__name__)


class CatalogDownloader:
    """Download benchmarks using catalog with change detection."""

    def __init__(
        self, database: CatalogDatabase, connect: Callable[[], WorkbenchScraper] | None = None
    ):
        """Initialize downloader.

        Args:
            database: CatalogDatabase instance
            connect: Returns an authenticated WorkbenchScraper. It is called the first time a
                benchmark must be fetched, and only then: a copy that is up to date, or a
                benchmark the catalog does not list, never opens a WorkBench session. None
                for a downloader that only caches benchmarks fetched elsewhere.
        """
        self.db = database
        self._connect = connect
        self._scraper: WorkbenchScraper | None = None
        self.search = CatalogSearch(database)

    @property
    def scraper(self) -> WorkbenchScraper:
        """The scraper for this downloader, connecting to WorkBench on first use."""
        if self._scraper is None:
            if self._connect is None:
                raise RuntimeError(
                    "This CatalogDownloader was built with no way to connect to WorkBench; "
                    "pass connect to download"
                )
            self._scraper = self._connect()
        return self._scraper

    def cache(self, benchmark_id: str, benchmark: Benchmark) -> tuple[str, str]:
        """Cache a downloaded benchmark: the one place every command caches a download.

        The cached row carries the copy's version and the date WorkBench showed it as
        published. What the benchmark's page said (publish date, description) is recorded on
        the release's catalog row (record_page), which holds what WorkBench shows now;
        check-updates compares the two dates.

        Returns:
            The cached JSON and its content hash, as serialize_benchmark_json gives them
        """
        content_json, content_hash = serialize_benchmark_json(benchmark)
        self.db.save_downloaded(
            version=benchmark.version,
            benchmark_id=benchmark_id,
            content_json=content_json,
            content_hash=content_hash,
            recommendation_count=len(benchmark.recommendations),
            downloaded_at=benchmark.downloaded_at,
            published_date=benchmark.published_date,
            benchmark=benchmark,
        )
        self.db.record_page(
            benchmark_id,
            BenchmarkPage(
                title=benchmark.title,
                published_date=benchmark.published_date,
                description=benchmark.description,
            ),
        )
        logger.debug(f"Cached benchmark {benchmark_id}")
        return content_json, content_hash

    def download_by_id(
        self,
        benchmark_id: str,
        force: bool = False,
        progress_callback: Callable[[str], None] | None = None,
    ) -> dict:
        """Download benchmark by catalog ID.

        Args:
            benchmark_id: Benchmark ID from catalog
            force: Force re-download even if up-to-date
            progress_callback: Receives the scraper's progress messages, for a caller that
                shows its own progress

        Returns:
            Dictionary with download info

        Raises:
            ValueError: If benchmark not in catalog
        """
        logger.debug(f"Downloading benchmark: {benchmark_id}")

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
            reason = update_reason(
                catalog_version=catalog_entry.get("version"),
                catalog_published=catalog_entry.get("published_date"),
                copy_version=existing.get("version"),
                copy_published=existing.get("published_date"),
                downloaded_at=existing["downloaded_at"],
            )
            if reason is None:
                logger.debug(f"Benchmark {benchmark_id} is cached and up to date")
                return {
                    "benchmark_id": benchmark_id,
                    "status": "already_current",
                    "downloaded_at": existing["downloaded_at"],
                    "recommendation_count": existing["recommendation_count"],
                    "message": "Already up to date. Use --force to download it again.",
                }
            logger.debug(f"Downloading benchmark {benchmark_id} again: {reason}")

        # Validate and canonicalize the URL against the origin the scraper fetches from
        _, benchmark_url = normalize_benchmark_url(
            catalog_entry["url"],
            base_url=self.scraper.base_url,
            expected_benchmark_id=str(benchmark_id),
        )

        logger.debug(f"Fetching from WorkBench: {benchmark_url}")
        benchmark = self.scraper.download_benchmark(
            benchmark_url, progress_callback=progress_callback
        )
        content_json, content_hash = self.cache(benchmark_id, benchmark)

        # Check if content actually changed
        is_unchanged = bool(existing and existing.get("content_hash") == content_hash and not force)
        if is_unchanged:
            logger.debug("Content unchanged (same hash), timestamp updated only")

        if is_unchanged:
            return {
                "benchmark_id": benchmark_id,
                "status": "unchanged",
                "content_hash": content_hash,
                "recommendation_count": len(benchmark.recommendations),
                "message": "Content unchanged (verified by hash).",
            }

        status = "updated" if existing else "downloaded"

        logger.debug(
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
        """Download benchmark by name (catalog search).

        Args:
            name_query: Search query (every word matches the start of a word)
            latest: Only search latest versions
            interactive: If multiple matches, prompt user to select
            force: Force re-download even if up-to-date

        Returns:
            Download result dict

        Raises:
            ValueError: If no matches or multiple matches without interactive
        """
        logger.debug(f"Searching catalog for: {name_query}")

        results = self.search.find_by_name(name_query, latest_only=latest)

        if len(results) == 0:
            raise ValueError(f"No benchmarks found matching: {name_query}")

        if len(results) == 1:
            # Single match - download it
            benchmark_id = results[0]["benchmark_id"]
            logger.debug(f"Found single match: {results[0]['title']}")
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
        logger.debug(f"Found {len(results)} matches, prompting for selection")
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
