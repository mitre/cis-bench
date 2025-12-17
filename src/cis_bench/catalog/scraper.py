"""Catalog scraper for CIS WorkBench.

Scrapes benchmark listing pages and populates the catalog database.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn

from cis_bench import __version__
from cis_bench.catalog.database import CatalogDatabase
from cis_bench.catalog.parser import WorkBenchCatalogParser

logger = logging.getLogger(__name__)


class CatalogScraper:
    """Scrape CIS WorkBench catalog and populate database."""

    BASE_URL = "https://workbench.cisecurity.org/benchmarks"

    def __init__(self, database: CatalogDatabase, session: requests.Session):
        """Initialize scraper.

        Args:
            database: CatalogDatabase instance
            session: Authenticated requests session (from AuthManager)
        """
        self.db = database
        self.session = session
        self.session.verify = False  # TODO: Add config for SSL verification

    def scrape_full_catalog(
        self, max_pages: int | None = None, rate_limit_seconds: float = 2.0
    ) -> dict:
        """Scrape all catalog pages from CIS WorkBench.

        Args:
            max_pages: Maximum pages to scrape (None = all pages)
            rate_limit_seconds: Delay between requests (default: 2 seconds)

        Returns:
            Dictionary with scrape statistics

        Example:
            scraper = CatalogScraper(db, session)
            stats = scraper.scrape_full_catalog(max_pages=5)
            print(f"Scraped {stats['total_benchmarks']} benchmarks")
        """
        logger.info(
            f"Starting full catalog scrape (max_pages={max_pages}, rate_limit={rate_limit_seconds}s)"
        )

        # Detect total pages by scraping page 1 first
        first_page_html = self._fetch_page(1)
        first_page_benchmarks = WorkBenchCatalogParser.parse_catalog_page(first_page_html)

        pagination = WorkBenchCatalogParser.extract_pagination_info(first_page_html)
        total_pages = pagination.get("total_pages")

        if total_pages is None:
            logger.warning(
                "Could not detect total pages from pagination, will scrape conservatively"
            )
            total_pages = 70  # Conservative estimate - will stop when no more results

        if max_pages:
            total_pages = min(total_pages, max_pages)

        logger.info(f"Will scrape {total_pages} pages (detected from pagination)")

        # Save first page
        for bench in first_page_benchmarks:
            self.db.insert_benchmark(bench)

        total_benchmarks = len(first_page_benchmarks)
        failed_pages = []

        # Progress bar with additional info
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total} pages)"),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task(
                f"Scraping catalog | {total_benchmarks} benchmarks found", total=total_pages
            )
            progress.update(task, advance=1)  # First page done

            # Scrape remaining pages in batches
            batch_size = 10
            threads_per_batch = 5
            remaining_pages = list(range(2, total_pages + 1))

            for batch_start in range(0, len(remaining_pages), batch_size):
                batch_pages = remaining_pages[batch_start : batch_start + batch_size]

                # Fetch batch concurrently
                with ThreadPoolExecutor(max_workers=threads_per_batch) as executor:
                    future_to_page = {
                        executor.submit(self._fetch_and_parse_page, page_num): page_num
                        for page_num in batch_pages
                    }

                    for future in as_completed(future_to_page):
                        page_num = future_to_page[future]
                        try:
                            benchmarks = future.result()

                            if benchmarks:
                                # Save to database
                                for bench in benchmarks:
                                    self.db.insert_benchmark(bench)

                                total_benchmarks += len(benchmarks)
                                logger.debug(f"Page {page_num}: {len(benchmarks)} benchmarks")
                            else:
                                logger.warning(f"Page {page_num} returned no benchmarks")

                            # Update progress
                            progress.update(
                                task,
                                advance=1,
                                description=f"Scraping catalog | {total_benchmarks} benchmarks found",
                            )

                        except Exception as e:
                            logger.error(f"Failed to scrape page {page_num}: {e}")
                            failed_pages.append(page_num)
                            progress.update(task, advance=1)

                # Check failure threshold (stop if >10% of pages have failed)
                failure_rate = len(failed_pages) / (batch_start + len(batch_pages))
                if failure_rate > 0.10:
                    logger.error(
                        f"Failure rate too high: {len(failed_pages)}/{batch_start + len(batch_pages)} pages failed ({failure_rate:.1%})"
                    )
                    progress.stop()
                    raise Exception(
                        f"Scraping aborted: {len(failed_pages)} pages failed. "
                        f"This may indicate authentication issues or WorkBench problems."
                    )

                # Rate limit between batches (not between pages in batch)
                if batch_start + batch_size < len(remaining_pages):
                    time.sleep(rate_limit_seconds)

        # Mark latest versions
        self.db.mark_latest_versions()

        # Save metadata
        from datetime import UTC, datetime

        self.db.set_metadata("last_full_scrape", datetime.now(UTC).isoformat())
        self.db.set_metadata("total_pages_scraped", str(total_pages))

        stats = {
            "total_benchmarks": total_benchmarks,
            "pages_scraped": total_pages,
            "failed_pages": failed_pages,
            "success_rate": (
                (total_pages - len(failed_pages)) / total_pages if total_pages > 0 else 0
            ),
        }

        logger.info(f"Scrape complete: {total_benchmarks} benchmarks from {total_pages} pages")

        if failed_pages:
            logger.warning(f"Failed pages: {failed_pages}")

        return stats

    def scrape_page_one_update(self, rate_limit_seconds: float = 2.0) -> dict:
        """Quick update by scraping only page 1 (newest benchmarks).

        Args:
            rate_limit_seconds: Delay before request

        Returns:
            Dictionary with new_count and updated_count
        """
        logger.info("Starting quick catalog update (page 1 only)")

        time.sleep(rate_limit_seconds)

        html = self._fetch_page(1)
        benchmarks = WorkBenchCatalogParser.parse_catalog_page(html)

        new_count = 0
        updated_count = 0

        for bench in benchmarks:
            existing = self.db.get_benchmark(bench["benchmark_id"])

            if not existing:
                # New benchmark
                self.db.insert_benchmark(bench)
                new_count += 1
                logger.debug(f"New: {bench['benchmark_id']} - {bench['title']}")

            elif existing.get("last_revision_date") != bench.get("last_revision_date"):
                # Updated (if we had revision dates - for now just update)
                self.db.insert_benchmark(bench)
                updated_count += 1
                logger.debug(f"Updated: {bench['benchmark_id']}")

        # Update metadata
        from datetime import UTC, datetime

        self.db.set_metadata("last_update_scrape", datetime.now(UTC).isoformat())

        stats = {"new_count": new_count, "updated_count": updated_count}

        logger.info(f"Update complete: {new_count} new, {updated_count} updated")

        return stats

    def _fetch_page(self, page_num: int) -> str:
        """Fetch single catalog page.

        Args:
            page_num: Page number (1-based)

        Returns:
            HTML content

        Raises:
            requests.RequestException: If request fails
        """
        url = f"{self.BASE_URL}?page={page_num}"

        logger.debug(f"Fetching page {page_num}: {url}")

        headers = {"User-Agent": f"cis-bench-cli/{__version__} (github.com/mitre/cis-bench)"}

        response = self.session.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        logger.debug(f"Fetched {len(response.text)} bytes from page {page_num}")

        return response.text

    def _fetch_and_parse_page(self, page_num: int, max_retries: int = 3) -> list:
        """Fetch and parse a single page with retry logic (for concurrent execution).

        Args:
            page_num: Page number to fetch
            max_retries: Maximum retry attempts

        Returns:
            List of benchmark dictionaries

        Raises:
            Exception: If fetch or parse fails after all retries
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                html = self._fetch_page(page_num)
                benchmarks = WorkBenchCatalogParser.parse_catalog_page(html)

                if attempt > 0:
                    logger.info(f"Page {page_num} succeeded on retry {attempt + 1}")

                return benchmarks

            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2  # Exponential backoff: 2s, 4s, 6s
                    logger.warning(
                        f"Page {page_num} failed (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s: {e}"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(f"Page {page_num} failed after {max_retries} attempts: {e}")

        raise last_error

    def test_connection(self) -> bool:
        """Test if we can connect and are authenticated.

        Returns:
            True if connection successful and authenticated

        Raises:
            Exception with helpful message if connection fails
        """
        try:
            html = self._fetch_page(1)

            # Check if we got a real page (not login redirect)
            if "login" in html.lower() and len(html) < 5000:
                raise Exception(
                    "Not authenticated. Page redirected to login.\n"
                    "Please log into https://workbench.cisecurity.org in your browser first."
                )

            benchmarks = WorkBenchCatalogParser.parse_catalog_page(html)

            if len(benchmarks) == 0:
                raise Exception(
                    "Connected but no benchmarks found. HTML structure may have changed."
                )

            logger.info(f"Connection test passed: Found {len(benchmarks)} benchmarks on page 1")
            return True

        except requests.RequestException as e:
            raise Exception(f"Connection failed: {e}") from e
