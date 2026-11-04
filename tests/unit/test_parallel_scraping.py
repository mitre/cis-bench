"""Unit tests for parallel catalog scraping with retry logic."""

import re
import threading
import time
from unittest.mock import patch

import pytest
import requests

from cis_bench.catalog.scraper import CatalogScraper
from cis_bench.exceptions import AuthenticationError
from tests.conftest import StubReply


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
# Tests: Retry Logic
# ============================================================================


# ============================================================================
# Tests: Parallel Scraping
# ============================================================================


class TestMultiPageScraping:
    """Test scraping behavior with multiple pages."""

    def test_scrape_multiple_pages_successfully(self, temp_db, sample_html, stub_session):
        """Scraping successfully processes all requested pages."""
        session, _ = stub_session(lambda url: sample_html)

        scraper = CatalogScraper(temp_db, session)

        # Scrape multiple pages - should complete successfully
        stats = scraper.scrape_full_catalog(max_pages=5, rate_limit_seconds=0)

        # Behavior: completes scraping
        assert "pages_scraped" in stats
        assert "total_benchmarks" in stats
        assert stats["pages_scraped"] > 0
        assert stats["total_benchmarks"] >= 0

    def test_scrape_large_catalog_completes(self, temp_db, sample_html, stub_session):
        """Scraping can handle large catalogs."""
        session, _ = stub_session(lambda url: sample_html)

        scraper = CatalogScraper(temp_db, session)

        # Behavior: handles large number of pages without crashing
        stats = scraper.scrape_full_catalog(max_pages=20, rate_limit_seconds=0)

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
        import cis_bench.catalog.scraper as scraper_module

        monkeypatch.setattr(scraper_module.time, "sleep", lambda _secs: None)

        def handler(url):
            page_num = _page_number(url)
            # Fail 50% of pages deterministically across retries (pages 2, 4, 6, 8, 10 -> 5/11 > 10%)
            if page_num % 2 == 0:
                raise requests.ConnectionError(f"Network error on page {page_num}")
            return sample_html

        session, _ = stub_session(handler)

        scraper = CatalogScraper(temp_db, session)

        # Should abort due to high failure rate
        with pytest.raises(Exception) as exc_info:
            scraper.scrape_full_catalog(max_pages=20, rate_limit_seconds=0)

        assert "Scraping aborted" in str(exc_info.value)
        assert "pages failed" in str(exc_info.value)

    def test_scraping_handles_transient_failures_with_retry(
        self, temp_db, sample_html, monkeypatch, stub_session
    ):
        """Scraping handles transient failures via retry logic."""
        import cis_bench.catalog.scraper as scraper_module

        monkeypatch.setattr(scraper_module.time, "sleep", lambda _secs: None)
        attempts: dict[int, int] = {}
        lock = threading.Lock()

        def handler(url):
            page_num = _page_number(url)
            with lock:
                attempts[page_num] = attempts.get(page_num, 0) + 1
                first_attempt = attempts[page_num] == 1
            # Every fifth page drops its connection once, then answers on the retry.
            if page_num % 5 == 0 and first_attempt:
                raise requests.ConnectionError(f"Transient error on page {page_num}")
            return sample_html

        session, _ = stub_session(handler)

        scraper = CatalogScraper(temp_db, session)

        stats = scraper.scrape_full_catalog(max_pages=10, rate_limit_seconds=0)

        # Retry fixes transient failures: every page was fetched, none counted failed
        assert stats["pages_scraped"] == 10
        assert stats["failed_pages"] == []
        assert attempts[5] == 2 and attempts[10] == 2


# ============================================================================
# Tests: Scraping Behavior
# ============================================================================


class TestScrapingBehavior:
    """Test overall scraping behavior (not implementation details)."""

    def test_scraping_respects_max_pages_limit(self, temp_db, sample_html, stub_session):
        """Scraping stops at max_pages limit."""
        session, _ = stub_session(lambda url: sample_html)

        scraper = CatalogScraper(temp_db, session)

        # Behavior: respects the max_pages parameter
        stats = scraper.scrape_full_catalog(max_pages=10, rate_limit_seconds=0)

        # Should not exceed requested pages
        assert stats["pages_scraped"] <= 10
        assert stats["pages_scraped"] > 0

    def test_scraping_returns_statistics(self, temp_db, sample_html, stub_session):
        """Scraping returns useful statistics."""
        session, _ = stub_session(lambda url: sample_html)

        scraper = CatalogScraper(temp_db, session)

        stats = scraper.scrape_full_catalog(max_pages=5, rate_limit_seconds=0)

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
        scraper = CatalogScraper(temp_db, session)

        with patch("cis_bench.utils.parallel.time"):
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

    def test_refresh_paces_batches_with_the_shared_utility(self, temp_db, stub_session):
        session, _ = stub_session(self._rotating_pages(delay=0))
        scraper = CatalogScraper(temp_db, session)

        with patch("cis_bench.utils.parallel.time") as clock:
            scraper.scrape_full_catalog(max_pages=self.PAGES, rate_limit_seconds=2.0)

        # Pages 2..25 in batches of ten: three batches, two pauses.
        assert clock.sleep.call_args_list == [((2.0,),), ((2.0,),)]

    def test_every_catalog_request_uses_the_configured_timeout(
        self, temp_db, stub_session, monkeypatch
    ):
        monkeypatch.setenv("CIS_BENCH_REQUEST_TIMEOUT", "45")
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
        scraper = CatalogScraper(temp_db, session)

        with patch("cis_bench.utils.parallel.time"), patch("cis_bench.catalog.scraper.time"):
            scraper.scrape_full_catalog(max_pages=3)
            scraper.scrape_page_one_update()
            scraper.refresh_downloaded_revision_dates()

        assert len(transport.settings) == 5
        assert {s["timeout"] for s in transport.settings} == {(10.0, 45.0)}

    def test_a_page_that_keeps_timing_out_is_tried_three_times_then_counted_failed(
        self, temp_db, stub_session
    ):
        def stalled(page):
            raise requests.Timeout("Read timed out")

        session, transport = stub_session(self._rotating_pages(overrides={3: stalled}, delay=0))
        scraper = CatalogScraper(temp_db, session)

        with patch("cis_bench.utils.parallel.time"), patch("cis_bench.fetcher.http.time"):
            stats = scraper.scrape_full_catalog(max_pages=self.PAGES)

        assert [_page_number(u) for u in transport.urls].count(3) == 3
        assert stats["failed_pages"] == [3]

    def test_a_missing_page_is_not_retried(self, temp_db, stub_session):
        session, transport = stub_session(
            self._rotating_pages(overrides={4: lambda page: StubReply("gone", status=404)}, delay=0)
        )
        scraper = CatalogScraper(temp_db, session)

        with patch("cis_bench.utils.parallel.time"), patch("cis_bench.fetcher.http.time") as clock:
            stats = scraper.scrape_full_catalog(max_pages=self.PAGES)

        assert [_page_number(u) for u in transport.urls].count(4) == 1
        assert stats["failed_pages"] == [4]
        clock.sleep.assert_not_called()

    def test_a_login_page_stops_the_refresh_after_its_batch(self, temp_db, stub_session):
        session, transport = stub_session(
            self._rotating_pages(overrides={3: lambda page: _LOGIN_PAGE}, delay=0)
        )
        scraper = CatalogScraper(temp_db, session)

        with patch("cis_bench.utils.parallel.time"), pytest.raises(AuthenticationError):
            scraper.scrape_full_catalog(max_pages=self.PAGES)

        fetched = {_page_number(u) for u in transport.urls}
        assert fetched.isdisjoint(range(12, self.PAGES + 1))  # nothing from a later batch

    def test_every_page_is_saved_and_counted_in_the_progress_bar(self, temp_db, stub_session):
        session, _ = stub_session(self._rotating_pages())
        scraper = CatalogScraper(temp_db, session)

        with (
            patch("cis_bench.utils.parallel.time"),
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

    def test_check_updates_retries_a_detail_page_that_timed_out_once(self, temp_db, stub_session):
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
        attempts = []

        def handler(url):
            attempts.append(url)
            if len(attempts) == 1:
                raise requests.ConnectionError("connection reset")
            return "<html><body><span>Published 2 months ago on Aug 28th 2025</span></body></html>"

        session, _ = stub_session(handler)
        scraper = CatalogScraper(temp_db, session)

        with patch("cis_bench.catalog.scraper.time"), patch("cis_bench.fetcher.http.time"):
            refreshed = scraper.refresh_downloaded_revision_dates()

        assert refreshed == 1
        assert len(attempts) == 2
        assert temp_db.get_downloaded("401")["workbench_last_modified"] == "2025-08-28"
