"""Catalog scraper for CIS WorkBench.

Scrapes benchmark listing pages and populates the catalog database.
"""

import logging

import requests
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn
from sqlalchemy.exc import IntegrityError, OperationalError

from cis_bench.catalog.database import CatalogDatabase
from cis_bench.catalog.parser import WorkBenchCatalogParser
from cis_bench.config import WORKBENCH_BATCH_SIZE, WORKBENCH_MAX_CONCURRENT_REQUESTS
from cis_bench.exceptions import AuthenticationError, FetchError
from cis_bench.fetcher.auth import is_workbench_login_page
from cis_bench.fetcher.http import ThreadSessions, get_with_retry
from cis_bench.utils.parallel import iter_batches
from cis_bench.utils.workbench_urls import catalog_listing_url, resolve_benchmark_reference

logger = logging.getLogger(__name__)


class CatalogScraper:
    """Scrape CIS WorkBench catalog and populate database.

    Listing pages after the first are fetched from worker threads in batches; each worker
    thread uses its own copy of the session, whose adapter paces and retries every request
    (see cis_bench.fetcher.http). Database writes stay on the calling thread.
    """

    _CATALOG_COMPARISON_FIELDS = (
        "title",
        "version",
        "status",
        "url",
        "platform",
        "platform_type",
        "community",
        "owner",
    )

    def __init__(
        self,
        database: CatalogDatabase,
        session: requests.Session,
        *,
        base_url: str,
        timeout: tuple[float, float],
    ):
        """Initialize scraper.

        Args:
            database: CatalogDatabase instance
            session: Authenticated requests session (from AuthManager)
            base_url: The WorkBench origin (already validated) every URL is built on
            timeout: (connect, read) seconds for every request
        """
        self.db = database
        self.session = session
        self.base_url = base_url
        self.timeout = timeout
        self._sessions = ThreadSessions(session)

    def scrape_full_catalog(
        self,
        max_pages: int | None = None,
    ) -> dict:
        """Scrape all catalog pages from CIS WorkBench.

        Args:
            max_pages: Maximum pages to scrape (None = all pages)

        Returns:
            Dictionary with scrape statistics

        Example:
            scraper = CatalogScraper(db, session, base_url=origin, timeout=(10.0, 30.0))
            stats = scraper.scrape_full_catalog(max_pages=5)
            print(f"Scraped {stats['total_benchmarks']} benchmarks")
        """
        logger.info(f"Starting full catalog scrape (max_pages={max_pages})")

        # Detect total pages by scraping page 1 first
        first_page_html = self._fetch_page(1)
        first_page_benchmarks = WorkBenchCatalogParser.parse_catalog_page(
            first_page_html, base_url=self.base_url
        )
        if not first_page_benchmarks:
            raise ValueError(
                "No benchmarks found on catalog page 1; HTML structure may have changed."
            )

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
        total_benchmarks = self._insert_page_benchmarks(first_page_benchmarks, page_num=1)
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

            # Scrape remaining pages in batches; each batch is saved here, on the calling
            # thread, before the next one starts.
            def fetch_page(page_num: int) -> tuple[int, list[dict]]:
                return page_num, self._fetch_and_parse_page(page_num)

            def page_finished(_completed: int, _total: int, _page_num: int) -> None:
                progress.update(task, advance=1)

            pages_processed = 1
            for batch in iter_batches(
                range(2, total_pages + 1),
                fetch_page,
                batch_size=WORKBENCH_BATCH_SIZE,
                max_workers=WORKBENCH_MAX_CONCURRENT_REQUESTS,
                progress_callback=page_finished,
            ):
                for _, error in batch.failed:
                    if isinstance(error, AuthenticationError):
                        progress.stop()
                        raise error
                for page_num, error in batch.failed:
                    logger.error(f"Failed to scrape page {page_num}: {error}")
                    failed_pages.append(page_num)
                for page_num, benchmarks in batch.results:
                    if not benchmarks:
                        logger.warning(f"Page {page_num} returned no benchmarks")
                        continue
                    try:
                        inserted_count = self._insert_page_benchmarks(benchmarks, page_num)
                    except OperationalError:
                        raise
                    except Exception as e:
                        logger.error(f"Failed to scrape page {page_num}: {e}")
                        failed_pages.append(page_num)
                        continue
                    total_benchmarks += inserted_count
                    logger.debug(f"Page {page_num}: {inserted_count} benchmarks")
                progress.update(
                    task, description=f"Scraping catalog | {total_benchmarks} benchmarks found"
                )

                # Stop if >10% of pages have failed, including page 1
                pages_processed += batch.total
                failure_rate = len(failed_pages) / pages_processed
                if failure_rate > 0.10:
                    logger.error(
                        f"Failure rate too high: {len(failed_pages)}/{pages_processed} pages failed ({failure_rate:.1%})"
                    )
                    progress.stop()
                    raise Exception(
                        f"Scraping aborted: {len(failed_pages)} pages failed. "
                        f"This may indicate authentication issues or WorkBench problems."
                    )

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

    def scrape_page_one_update(self) -> dict:
        """Quick update by scraping only page 1 (newest benchmarks).

        Returns:
            Dictionary with new_count and updated_count
        """
        logger.info("Starting quick catalog update (page 1 only)")

        html = self._fetch_page(1)
        benchmarks = WorkBenchCatalogParser.parse_catalog_page(html, base_url=self.base_url)

        new_count = 0
        updated_count = 0
        unchanged_count = 0

        for bench in benchmarks:
            benchmark_id = bench.get("benchmark_id") if isinstance(bench, dict) else None
            if not benchmark_id:
                self._try_insert_benchmark(bench, page_num=1)
                continue

            existing = self.db.get_benchmark(benchmark_id)

            if not existing:
                # New benchmark
                if self._try_insert_benchmark(bench, page_num=1):
                    new_count += 1
                    logger.debug(f"New: {benchmark_id} - {bench.get('title', '')}")

            elif self._has_catalog_changes(existing, bench):
                if self._try_insert_benchmark(bench, page_num=1):
                    updated_count += 1
                    logger.debug(f"Updated: {benchmark_id}")
            else:
                unchanged_count += 1

        if benchmarks and (new_count + updated_count + unchanged_count) == 0:
            raise ValueError(f"All {len(benchmarks)} benchmarks on page 1 failed validation")

        if new_count > 0 or updated_count > 0:
            self.db.mark_latest_versions()

        # Update metadata
        from datetime import UTC, datetime

        self.db.set_metadata("last_update_scrape", datetime.now(UTC).isoformat())

        stats = {"new_count": new_count, "updated_count": updated_count}

        logger.info(f"Update complete: {new_count} new, {updated_count} updated")

        return stats

    @classmethod
    def _has_catalog_changes(cls, existing: dict, incoming: dict) -> bool:
        """Return True when any scraped catalog field, collection set, or revision date changed."""
        for field in cls._CATALOG_COMPARISON_FIELDS:
            inc_val = incoming.get(field)
            if isinstance(inc_val, str):
                inc_val = inc_val.strip() or None
            if existing.get(field) != inc_val:
                return True

        existing_collections = {
            c.strip()
            for c in (existing.get("collections") or [])
            if isinstance(c, str) and c.strip()
        }
        incoming_collections = {
            c.strip()
            for c in (incoming.get("collections") or [])
            if isinstance(c, str) and c.strip()
        }
        if existing_collections != incoming_collections:
            return True

        inc_rev = incoming.get("last_revision_date")
        return inc_rev is not None and existing.get("last_revision_date") != inc_rev

    def _try_insert_benchmark(self, bench: dict, page_num: int) -> bool:
        """Insert a single parsed benchmark row, isolating row-level data errors."""
        try:
            self.db.insert_benchmark(bench)
            return True
        except (ValueError, KeyError, TypeError, IntegrityError) as exc:
            bench_id = (
                bench.get("benchmark_id", "<unknown>") if isinstance(bench, dict) else "<unknown>"
            )
            logger.warning(f"Skipping invalid benchmark {bench_id} on page {page_num}: {exc}")
            return False

    def _insert_page_benchmarks(self, benchmarks: list[dict], page_num: int) -> int:
        """Insert all parsed benchmarks for a catalog page.

        Returns the count of successfully inserted rows. Raises ValueError when a
        non-empty page has zero valid rows so the caller records the page as failed.
        """
        if not benchmarks:
            return 0

        inserted_count = sum(
            1 for bench in benchmarks if self._try_insert_benchmark(bench, page_num)
        )
        if inserted_count == 0:
            raise ValueError(
                f"All {len(benchmarks)} benchmarks on page {page_num} failed validation"
            )
        return inserted_count

    def refresh_downloaded_revision_dates(self) -> int:
        """Fetch each downloaded benchmark's detail page and record its publication date.

        Only downloaded benchmarks are visited (a handful of requests, never the
        whole catalog). A page without a recognisable date leaves the row as it
        was. A login page means the session is gone and raises immediately.

        Returns:
            Number of benchmarks whose date was recorded
        """
        refreshed = 0
        for benchmark_id in self.db.list_downloaded_benchmark_ids():
            try:
                _, url = resolve_benchmark_reference(str(benchmark_id), base_url=self.base_url)
            except ValueError as e:
                logger.warning(
                    f"Skipping downloaded benchmark with invalid id {benchmark_id!r}: {e}"
                )
                continue
            logger.debug(f"Fetching detail page for downloaded benchmark {benchmark_id}: {url}")
            response = get_with_retry(self._sessions.current(), url, timeout=self.timeout)
            if is_workbench_login_page(response.text):
                raise AuthenticationError(
                    "WorkBench returned the login page; the saved session has expired"
                )
            metadata = WorkBenchCatalogParser.parse_benchmark_detail_page(response.text)
            iso_date = WorkBenchCatalogParser.published_date_to_iso(metadata.get("published_date"))
            if iso_date is not None:
                self.db.set_downloaded_revision_date(benchmark_id, iso_date)
                refreshed += 1
            else:
                logger.debug(f"No publication date found on detail page for {benchmark_id}")
        return refreshed

    def _fetch_page(self, page_num: int) -> str:
        """Fetch single catalog page.

        Args:
            page_num: Page number (1-based)

        Returns:
            HTML content

        Raises:
            FetchError: If the request still fails after every retry
            requests.HTTPError: For a non-retryable HTTP status
        """
        url = f"{catalog_listing_url(base_url=self.base_url)}?page={page_num}"

        logger.debug(f"Fetching page {page_num}: {url}")

        response = get_with_retry(self._sessions.current(), url, timeout=self.timeout)

        logger.debug(f"Fetched {len(response.text)} bytes from page {page_num}")

        return response.text

    def _fetch_and_parse_page(self, page_num: int) -> list[dict]:
        """Fetch and parse one listing page (run on a worker thread during a full refresh).

        Retries happen inside the shared GET; a login page raises AuthenticationError from the
        parser, which the full refresh treats as the end of the run.
        """
        return WorkBenchCatalogParser.parse_catalog_page(
            self._fetch_page(page_num), base_url=self.base_url
        )

    def test_connection(self) -> bool:
        """Test if we can connect and are authenticated.

        Returns:
            True if connection successful and authenticated

        Raises:
            AuthenticationError: If response is a login page or redirect
            ValueError: If page 1 parses zero benchmarks
            Exception: If HTTP connection fails
        """
        try:
            html = self._fetch_page(1)
            benchmarks = WorkBenchCatalogParser.parse_catalog_page(html, base_url=self.base_url)

            # Catch minimal login redirect pages without full WorkBench form markup
            if not benchmarks and "login" in html.lower() and len(html) < 5000:
                raise AuthenticationError(
                    "Not authenticated. Page redirected to login.\n"
                    f"Please log into {self.base_url} in your browser first."
                )

            if len(benchmarks) == 0:
                raise ValueError(
                    "Connected but no benchmarks found. HTML structure may have changed."
                )

            logger.info(f"Connection test passed: Found {len(benchmarks)} benchmarks on page 1")
            return True

        except (requests.RequestException, FetchError) as e:
            raise Exception(f"Connection failed: {e}") from e
