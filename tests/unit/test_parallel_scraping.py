"""Unit tests for parallel catalog scraping."""

import re
import threading
import time
from unittest.mock import patch

import pytest
import requests

from cis_bench.catalog.scraper import CatalogScraper
from cis_bench.exceptions import AuthenticationError
from tests.conftest import StubReply

BASE = "https://workbench.cisecurity.org"
TIMEOUT = (10.0, 30.0)
WORKERS = 5
BATCH = 10


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary test database."""
    from cis_bench.catalog.database import CatalogDatabase

    db_path = tmp_path / "test_catalog.db"
    db = CatalogDatabase(db_path)
    db.initialize_schema()
    return db


def get_sample_html(max_page=100):
    """Generate sample HTML with pagination."""
    return f"""
    <table>
        <tr>
            <th>Title</th>
            <th>Version</th>
            <th>Status</th>
            <th>Community</th>
            <th>Collections</th>
            <th>Owner</th>
        </tr>
        <tr>
            <td><a href="/benchmarks/12345">CIS Test Benchmark</a></td>
            <td>v1.0.0</td>
            <td>Published</td>
            <td>Test Community</td>
            <td>Test Collection</td>
            <td>testuser</td>
        </tr>
    </table>
    <nav>
        <a>1</a><a>2</a><a>3</a><a>{max_page}</a>
    </nav>
    """


@pytest.fixture
def sample_html():
    """Sample HTML for parsing."""
    return get_sample_html(100)


# ============================================================================
# Tests: Parallel Scraping
# ============================================================================


class TestWorkersAndBatchSizeComeFromTheCaller:
    def test_the_page_fetch_runs_with_the_given_workers_and_batch_size(
        self, temp_db, sample_html, stub_session
    ):
        from cis_bench.catalog import scraper as scraper_module

        session, _ = stub_session(lambda url: sample_html)
        scraper = CatalogScraper(
            temp_db, session, base_url=BASE, timeout=TIMEOUT, max_workers=2, batch_size=3
        )
        with patch.object(scraper_module, "iter_batches", wraps=scraper_module.iter_batches) as run:
            scraper.scrape_full_catalog(max_pages=5)

        assert run.call_args.kwargs["max_workers"] == 2
        assert run.call_args.kwargs["batch_size"] == 3


class TestMultiPageScraping:
    """Test scraping behavior with multiple pages."""

    def test_scrape_multiple_pages_successfully(self, temp_db, sample_html, stub_session):
        """Scraping successfully processes all requested pages."""
        session, _ = stub_session(lambda url: sample_html)

        scraper = CatalogScraper(
            temp_db, session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        # Scrape multiple pages - should complete successfully
        stats = scraper.scrape_full_catalog(max_pages=5)

        # Behavior: completes scraping
        assert "pages_scraped" in stats
        assert "total_benchmarks" in stats
        assert stats["pages_scraped"] > 0
        assert stats["total_benchmarks"] >= 0

    def test_scrape_large_catalog_completes(self, temp_db, sample_html, stub_session):
        """Scraping can handle large catalogs."""
        session, _ = stub_session(lambda url: sample_html)

        scraper = CatalogScraper(
            temp_db, session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        # Behavior: handles large number of pages without crashing
        stats = scraper.scrape_full_catalog(max_pages=20)

        assert stats["pages_scraped"] > 0
        assert "failed_pages" in stats


# ============================================================================
# Tests: Failure Threshold
# ============================================================================


class TestFailureThreshold:
    """Test failure threshold abort logic."""

    def test_scraping_aborts_when_failure_rate_exceeds_10_percent(
        self, temp_db, sample_html, monkeypatch, stub_session
    ):
        """Scraping aborts when >10% of pages fail."""

        def handler(url):
            page_num = _page_number(url)
            # Fail every even page (pages 2, 4, 6, 8, 10 -> 5/11 > 10%)
            if page_num % 2 == 0:
                raise requests.ConnectionError(f"Network error on page {page_num}")
            return sample_html

        session, _ = stub_session(handler)

        scraper = CatalogScraper(
            temp_db, session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        # Should abort due to high failure rate
        with pytest.raises(Exception) as exc_info:
            scraper.scrape_full_catalog(max_pages=20)

        assert "Scraping aborted" in str(exc_info.value)
        assert "pages failed" in str(exc_info.value)


class TestScrapingBehavior:
    """Test overall scraping behavior (not implementation details)."""

    def test_scraping_respects_max_pages_limit(self, temp_db, sample_html, stub_session):
        """Scraping stops at max_pages limit."""
        session, _ = stub_session(lambda url: sample_html)

        scraper = CatalogScraper(
            temp_db, session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        # Behavior: respects the max_pages parameter
        stats = scraper.scrape_full_catalog(max_pages=10)

        # Should not exceed requested pages
        assert stats["pages_scraped"] <= 10
        assert stats["pages_scraped"] > 0

    def test_scraping_returns_statistics(self, temp_db, sample_html, stub_session):
        """Scraping returns useful statistics."""
        session, _ = stub_session(lambda url: sample_html)

        scraper = CatalogScraper(
            temp_db, session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        stats = scraper.scrape_full_catalog(max_pages=5)

        # Behavior: returns complete statistics
        assert "pages_scraped" in stats
        assert "total_benchmarks" in stats
        assert "failed_pages" in stats
        assert isinstance(stats["pages_scraped"], int)
        assert isinstance(stats["total_benchmarks"], int)
        assert isinstance(stats["failed_pages"], list)


# ============================================================================
# Tests: Shared fetch, per-thread sessions and request policy
# ============================================================================

_LOGIN_PAGE = (
    '<html><body><div class="index-signin-wrapper"><form action="/login">'
    '<input name="login"><input name="password"></form></div></body></html>'
)


def _catalog_page(page: int, total_pages: int) -> str:
    """A listing page whose one row is a benchmark unique to that page."""
    return f"""
    <table>
        <tr><th>Title</th><th>Version</th><th>Status</th><th>Community</th>
            <th>Collections</th><th>Owner</th></tr>
        <tr>
            <td><a href="/benchmarks/{10000 + page}">CIS Page {page} Benchmark</a></td>
            <td>v1.0.0</td><td>Published</td><td>Test Community</td>
            <td>Test Collection</td><td>testuser</td>
        </tr>
    </table>
    <nav><a>1</a><a>2</a><a>3</a><a>{total_pages}</a></nav>
    """


def _page_number(url: str) -> int:
    match = re.search(r"[?&]page=(\d+)", url)
    assert match, url
    return int(match.group(1))


class TestCatalogRefreshSharedFetch:
    """Catalog refresh uses the shared paced fetch, per-thread sessions and request policy."""

    PAGES = 25

    def _rotating_pages(self, overrides=None, delay=0.01):
        """Handler for a PAGES-page catalog that rotates the session cookie on every response."""
        counter = iter(range(1, 10_000))
        lock = threading.Lock()
        overrides = overrides or {}

        def handler(url):
            page = _page_number(url)
            if page in overrides:
                return overrides[page](page)
            time.sleep(delay)
            with lock:
                rotation = next(counter)
            return StubReply(
                body=_catalog_page(page, self.PAGES),
                set_cookies=(
                    f"workbench_session=rotated-{rotation}; Path=/",
                    f"XSRF-TOKEN=xsrf-{rotation}; Path=/",
                ),
            )

        return handler

    @staticmethod
    def _logged_in(session):
        session.verify = "/etc/ssl/corporate-ca.pem"
        for name, value in (("auth0", "saved-auth"), ("workbench_session", "saved-session")):
            session.cookies.set(name, value, domain="workbench.cisecurity.org", path="/")
        return session

    def test_catalog_pages_are_fetched_with_per_thread_sessions(self, temp_db, stub_session):
        session, transport = stub_session(self._rotating_pages())
        self._logged_in(session)
        scraper = CatalogScraper(
            temp_db, session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        stats = scraper.scrape_full_catalog(max_pages=self.PAGES)

        assert stats["failed_pages"] == []
        assert sorted(_page_number(u) for u in transport.urls) == list(range(1, self.PAGES + 1))
        for headers in transport.headers:
            assert "auth0=saved-auth" in headers.get("Cookie", "")
        assert {s["verify"] for s in transport.settings} == {session.verify}
        assert 2 <= transport.peak_in_flight <= 5
        # Page one ran on the caller's session; the 24 worker responses rotated only the
        # workers' own copies.
        assert session.cookies.get("workbench_session") == "rotated-1"

    def test_every_catalog_request_uses_the_timeout_the_scraper_is_given(
        self, temp_db, stub_session
    ):
        temp_db.insert_benchmark(
            {
                "benchmark_id": "401",
                "title": "CIS Benchmark 401",
                "version": "v1.0.0",
                "url": "https://workbench.cisecurity.org/benchmarks/401",
                "status": "Published",
            }
        )
        temp_db.save_downloaded("401", "{}", "h", 1, version="v1.0.0")
        detail = "<html><body><span>Published 2 months ago on Aug 28th 2025</span></body></html>"
        listing = self._rotating_pages(delay=0)

        def handler(url):
            return detail if "/benchmarks/401" in url else listing(url)

        session, transport = stub_session(handler)
        scraper = CatalogScraper(
            temp_db,
            session,
            base_url=BASE,
            timeout=(10.0, 45.0),
            max_workers=WORKERS,
            batch_size=BATCH,
        )

        scraper.scrape_full_catalog(max_pages=3)
        scraper.scrape_page_one_update()
        scraper.refresh_downloaded_revision_dates()

        assert len(transport.settings) == 5
        assert {s["timeout"] for s in transport.settings} == {(10.0, 45.0)}

    def test_a_page_that_keeps_timing_out_is_counted_failed(self, temp_db, stub_session):
        def stalled(page):
            raise requests.Timeout("Read timed out")

        session, transport = stub_session(self._rotating_pages(overrides={3: stalled}, delay=0))
        scraper = CatalogScraper(
            temp_db, session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        stats = scraper.scrape_full_catalog(max_pages=self.PAGES)

        assert stats["failed_pages"] == [3]

    def test_a_missing_page_is_counted_failed(self, temp_db, stub_session):
        session, transport = stub_session(
            self._rotating_pages(overrides={4: lambda page: StubReply("gone", status=404)}, delay=0)
        )
        scraper = CatalogScraper(
            temp_db, session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        stats = scraper.scrape_full_catalog(max_pages=self.PAGES)

        assert stats["failed_pages"] == [4]

    def test_a_login_page_stops_the_refresh_after_its_batch(self, temp_db, stub_session):
        session, transport = stub_session(
            self._rotating_pages(overrides={3: lambda page: _LOGIN_PAGE}, delay=0)
        )
        scraper = CatalogScraper(
            temp_db, session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        with pytest.raises(AuthenticationError):
            scraper.scrape_full_catalog(max_pages=self.PAGES)

        fetched = {_page_number(u) for u in transport.urls}
        assert fetched.isdisjoint(range(12, self.PAGES + 1))  # nothing from a later batch

    def test_every_page_is_saved_and_counted_in_the_progress_bar(self, temp_db, stub_session):
        session, _ = stub_session(self._rotating_pages())
        scraper = CatalogScraper(
            temp_db, session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        with (
            patch("cis_bench.catalog.scraper.Progress") as progress_class,
        ):
            stats = scraper.scrape_full_catalog(max_pages=self.PAGES)

        assert stats["total_benchmarks"] == self.PAGES
        for page in range(1, self.PAGES + 1):
            assert temp_db.get_benchmark(str(10000 + page)) is not None, page
        bar = progress_class.return_value.__enter__.return_value
        advanced = sum(c.kwargs.get("advance", 0) for c in bar.update.call_args_list)
        assert advanced == self.PAGES
        last_description = [
            c.kwargs["description"] for c in bar.update.call_args_list if "description" in c.kwargs
        ][-1]
        assert f"{self.PAGES} benchmarks found" in last_description
