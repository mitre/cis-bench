"""Unit tests for catalog scraper."""

from datetime import date
from pathlib import Path
from unittest.mock import Mock

import pytest

from cis_bench.catalog.database import CatalogDatabase
from cis_bench.catalog.scraper import CatalogScraper
from cis_bench.exceptions import AuthenticationError

BASE = "https://workbench.cisecurity.org"
TIMEOUT = (10.0, 30.0)
WORKERS = 5
BATCH = 10


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary database."""
    db = CatalogDatabase(tmp_path / "test.db")
    db.initialize_schema()
    yield db
    db.close()


@pytest.fixture
def sample_html():
    """Load sample catalog HTML."""
    fixture_path = (
        Path(__file__).parent.parent / "fixtures" / "html" / "workbench_catalog_page1_sample.html"
    )
    return fixture_path.read_text()


@pytest.fixture
def mock_session(sample_html):
    """Mock authenticated session."""
    session = Mock()
    response = Mock()
    response.text = sample_html
    response.status_code = 200
    response.raise_for_status = Mock()
    session.get = Mock(return_value=response)
    session.verify = False
    return session


class TestScraperInitialization:
    """Test scraper initialization."""

    def test_scraper_creation(self, temp_db, mock_session):
        """Test scraper can be created."""
        scraper = CatalogScraper(
            temp_db,
            mock_session,
            base_url=BASE,
            timeout=TIMEOUT,
            max_workers=WORKERS,
            batch_size=BATCH,
        )

        assert scraper.db == temp_db
        assert scraper.session == mock_session

    @pytest.mark.parametrize(
        "verify_setting",
        [True, False, "/etc/ssl/certs/custom-ca.pem"],
    )
    def test_scraper_preserves_session_verify_setting(self, temp_db, verify_setting):
        """CatalogScraper.__init__ must preserve the caller-configured session.verify value."""
        import requests

        session = requests.Session()
        session.verify = verify_setting

        scraper = CatalogScraper(
            temp_db, session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        assert scraper.session.verify == verify_setting

    def test_scraper_does_not_expose_unused_base_url_constant(self):
        """CatalogScraper builds WorkBench URLs from the base_url it is given; there is no BASE_URL class constant."""
        assert not hasattr(CatalogScraper, "BASE_URL")


class TestPageOneShowsWhetherTheSessionAndTheHtmlAreUsable:
    """A refresh checks its first page: an expired session and an unreadable page stop it."""

    @staticmethod
    def _scraper(temp_db, session):
        return CatalogScraper(
            temp_db, session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

    @staticmethod
    def _answering(text):
        session = Mock()
        response = Mock()
        response.text = text
        response.status_code = 200
        response.raise_for_status = Mock()
        session.get = Mock(return_value=response)
        return session

    def test_a_bare_login_redirect_page_is_an_authentication_error(self, temp_db):
        """A redirect stub without WorkBench's login form still means: not logged in."""
        session = self._answering("<html><body>Login required</body></html>")

        with pytest.raises(AuthenticationError, match="Not authenticated"):
            self._scraper(temp_db, session).scrape_full_catalog(max_pages=1)

    def test_a_page_one_without_benchmarks_is_an_error_not_an_empty_catalog(self, temp_db):
        session = self._answering(
            "<html><body><table><tr><th>Title</th></tr></table></body></html>"
        )

        with pytest.raises(ValueError, match="Connected but no benchmarks found"):
            self._scraper(temp_db, session).scrape_full_catalog(max_pages=1)

    def test_the_quick_update_makes_the_same_two_checks(self, temp_db):
        """catalog update reads page 1 too; it must not report success on an unusable page."""
        bare_login = self._answering("<html><body>Login required</body></html>")
        with pytest.raises(AuthenticationError, match="Not authenticated"):
            self._scraper(temp_db, bare_login).scrape_page_one_update()

        empty = self._answering("<html><body><table><tr><th>Title</th></tr></table></body></html>")
        with pytest.raises(ValueError, match="Connected but no benchmarks found"):
            self._scraper(temp_db, empty).scrape_page_one_update()

    def test_a_network_failure_at_page_one_is_a_fetch_error(self, temp_db):
        import requests

        from cis_bench.exceptions import FetchError

        session = Mock()
        session.get = Mock(side_effect=requests.ConnectionError("Network error"))

        with pytest.raises(FetchError, match="Network error"):
            self._scraper(temp_db, session).scrape_full_catalog(max_pages=1)


class TestPageFetching:
    """Test individual page fetching."""

    def test_fetch_page(self, temp_db, mock_session, sample_html):
        """Test fetching single page."""
        scraper = CatalogScraper(
            temp_db,
            mock_session,
            base_url=BASE,
            timeout=TIMEOUT,
            max_workers=WORKERS,
            batch_size=BATCH,
        )

        html = scraper._fetch_page(1)

        assert html == sample_html
        mock_session.get.assert_called_once()

    def test_a_listing_page_has_its_addresses_decoded(self, temp_db, mock_session):
        cf_info = "9df4f3fbf2ddf8e5fcf0edf1f8b3fef2f0"  # info@example.com
        mock_session.get.return_value.text = (
            f'<td><span class="__cf_email__" data-cfemail="{cf_info}">[email protected]</span></td>'
        )
        scraper = CatalogScraper(
            temp_db,
            mock_session,
            base_url=BASE,
            timeout=TIMEOUT,
            max_workers=WORKERS,
            batch_size=BATCH,
        )

        assert scraper._fetch_page(1) == "<td>info@example.com</td>"

    def test_fetch_page_url_format(self, temp_db, mock_session):
        """Test page URL is formatted correctly."""
        scraper = CatalogScraper(
            temp_db,
            mock_session,
            base_url=BASE,
            timeout=TIMEOUT,
            max_workers=WORKERS,
            batch_size=BATCH,
        )

        scraper._fetch_page(5)

        # Check URL includes page parameter
        call_args = mock_session.get.call_args
        url = call_args[0][0]
        assert "?page=5" in url

    def test_fetch_page_uses_the_given_origin(self, temp_db, mock_session):
        """_fetch_page builds the listing URL on the origin the scraper is given."""
        scraper = CatalogScraper(
            temp_db,
            mock_session,
            base_url="https://workbench-staging.cisecurity.org",
            timeout=TIMEOUT,
            max_workers=WORKERS,
            batch_size=BATCH,
        )

        scraper._fetch_page(2)

        assert (
            mock_session.get.call_args[0][0]
            == "https://workbench-staging.cisecurity.org/benchmarks?page=2"
        )


class TestFullCatalogScrape:
    """Test full catalog scraping."""

    def test_scrape_full_catalog(self, temp_db, sample_html, stub_session):
        """Test scraping multiple pages."""
        session, _ = stub_session(lambda url: sample_html)
        scraper = CatalogScraper(
            temp_db, session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        stats = scraper.scrape_full_catalog(max_pages=2)

        assert stats["total_benchmarks"] > 0
        assert stats["pages_scraped"] >= 1
        assert isinstance(stats["failed_pages"], list)

    def test_scrape_respects_max_pages(self, temp_db, sample_html, stub_session):
        """Test max_pages parameter limits scraping."""
        session, _ = stub_session(lambda url: sample_html)
        scraper = CatalogScraper(
            temp_db, session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        stats = scraper.scrape_full_catalog(max_pages=3)

        # Should not scrape more than max_pages
        assert stats["pages_scraped"] <= 3

    def test_scrape_saves_to_database(self, temp_db, mock_session):
        """Test scraped benchmarks are saved to database across all status types."""
        scraper = CatalogScraper(
            temp_db,
            mock_session,
            base_url=BASE,
            timeout=TIMEOUT,
            max_workers=WORKERS,
            batch_size=BATCH,
        )

        stats = scraper.scrape_full_catalog(max_pages=1)

        assert stats["total_benchmarks"] == 6
        db_stats = temp_db.get_catalog_stats()
        assert db_stats["total_benchmarks"] == 6
        assert db_stats["published_benchmarks"] == 2
        stored_statuses = {
            temp_db.get_benchmark(bid)["status"]
            for bid in ("90101", "90102", "90103", "90104", "90105", "90106")
        }
        assert stored_statuses == {
            "Published",
            "Draft",
            "Archived",
            "Rejected",
            "Accepted",
        }

    def test_scrape_marks_latest_versions(self, temp_db, mock_session):
        """Test scraper marks latest versions."""
        scraper = CatalogScraper(
            temp_db,
            mock_session,
            base_url=BASE,
            timeout=TIMEOUT,
            max_workers=WORKERS,
            batch_size=BATCH,
        )

        scraper.scrape_full_catalog(max_pages=1)

        # Verify mark_latest_versions was called (check metadata exists)
        # This is indirect - checking the method was executed
        db_stats = temp_db.get_catalog_stats()
        assert db_stats["total_benchmarks"] > 0  # Scrape completed

    def test_scrape_saves_metadata(self, temp_db, mock_session):
        """Test scraper saves scrape metadata."""
        scraper = CatalogScraper(
            temp_db,
            mock_session,
            base_url=BASE,
            timeout=TIMEOUT,
            max_workers=WORKERS,
            batch_size=BATCH,
        )

        scraper.scrape_full_catalog(max_pages=1)

        # Check metadata was saved
        last_scrape = temp_db.get_metadata("last_full_scrape")
        assert last_scrape is not None


class TestQuickUpdate:
    """Test quick update functionality."""

    def test_page_one_update(self, temp_db, mock_session):
        """Test quick update scrapes page 1 only."""
        scraper = CatalogScraper(
            temp_db,
            mock_session,
            base_url=BASE,
            timeout=TIMEOUT,
            max_workers=WORKERS,
            batch_size=BATCH,
        )

        stats = scraper.scrape_page_one_update()

        assert "new_count" in stats
        assert "updated_count" in stats
        assert isinstance(stats["new_count"], int)

    def test_update_detects_new_benchmarks(self, temp_db, mock_session):
        """Test update detects new benchmarks."""
        scraper = CatalogScraper(
            temp_db,
            mock_session,
            base_url=BASE,
            timeout=TIMEOUT,
            max_workers=WORKERS,
            batch_size=BATCH,
        )

        # First update - all new
        stats1 = scraper.scrape_page_one_update()
        assert stats1["new_count"] > 0

        # Second update - none new (same page)
        stats2 = scraper.scrape_page_one_update()
        assert stats2["new_count"] == 0

    def test_update_detects_field_and_status_changes_without_revision_date(
        self, temp_db, mock_session, monkeypatch
    ):
        """scrape_page_one_update detects status/version/title updates from the listing alone."""
        row = {
            "benchmark_id": "501",
            "title": "CIS CentOS Linux 7 Benchmark",
            "version": "v4.0.0",
            "status": "Published",
            "url": "https://workbench.cisecurity.org/benchmarks/501",
            "platform": "centos",
            "platform_type": "os",
            "community": "CIS CentOS Linux Benchmarks",
            "owner": "cis.author",
        }
        current_rows = [dict(row)]
        scraper = _stub_scraper_pages(
            temp_db, mock_session, monkeypatch, lambda _html: [dict(item) for item in current_rows]
        )

        assert scraper.scrape_page_one_update() == {
            "new_count": 1,
            "updated_count": 0,
        }
        assert scraper.scrape_page_one_update() == {
            "new_count": 0,
            "updated_count": 0,
        }

        current_rows[:] = [{**row, "status": "Final Update", "version": "v4.0.1"}]
        assert scraper.scrape_page_one_update() == {
            "new_count": 0,
            "updated_count": 1,
        }
        saved = temp_db.get_benchmark("501")
        assert saved is not None
        assert saved["status"] == "Final Update"
        assert saved["version"] == "v4.0.1"

    def test_page_one_update_recomputes_latest_versions_when_rows_change(
        self, temp_db, mock_session, monkeypatch
    ):
        """scrape_page_one_update recomputes is_latest flags when a newer benchmark version lands."""
        temp_db.insert_benchmark(
            {
                "benchmark_id": "601",
                "title": "CIS RHEL 9 Benchmark",
                "version": "v1.0.0",
                "status": "Published",
                "url": "https://workbench.cisecurity.org/benchmarks/601",
            }
        )
        temp_db.mark_latest_versions()
        assert temp_db.get_benchmark("601")["is_latest"] is True

        incoming = [
            {
                "benchmark_id": "602",
                "title": "CIS RHEL 9 Benchmark",
                "version": "v2.0.0",
                "status": "Published",
                "url": "https://workbench.cisecurity.org/benchmarks/602",
            }
        ]
        scraper = _stub_scraper_pages(temp_db, mock_session, monkeypatch, lambda _html: incoming)

        stats = scraper.scrape_page_one_update()
        assert stats == {"new_count": 1, "updated_count": 0}
        assert temp_db.get_benchmark("601")["is_latest"] is False
        assert temp_db.get_benchmark("602")["is_latest"] is True

    def test_page_one_update_detects_collection_changes_without_order_false_positives(
        self, temp_db, mock_session, monkeypatch
    ):
        """scrape_page_one_update treats collection sets order-insensitively and updates when tags change."""
        base_row = {
            "benchmark_id": "701",
            "title": "CIS Container Runtime Benchmark",
            "version": "v1.0.0",
            "status": "Published",
            "url": "https://workbench.cisecurity.org/benchmarks/701",
            "collections": ["Linux", "STIG"],
        }
        current_rows = [dict(base_row)]
        scraper = _stub_scraper_pages(
            temp_db, mock_session, monkeypatch, lambda _html: [dict(item) for item in current_rows]
        )

        assert scraper.scrape_page_one_update() == {
            "new_count": 1,
            "updated_count": 0,
        }

        current_rows[:] = [{**base_row, "collections": ["STIG", "Linux"]}]
        assert scraper.scrape_page_one_update() == {
            "new_count": 0,
            "updated_count": 0,
        }

        current_rows[:] = [{**base_row, "collections": ["Linux", "STIG", "Zero Trust"]}]
        assert scraper.scrape_page_one_update() == {
            "new_count": 0,
            "updated_count": 1,
        }
        assert temp_db.get_benchmark("701")["collections"] == ["Linux", "STIG", "Zero Trust"]


def _stub_scraper_pages(
    temp_db: CatalogDatabase,
    mock_session: Mock,
    monkeypatch: pytest.MonkeyPatch,
    parse_page,
    total_pages: int = 1,
) -> CatalogScraper:
    """Create a CatalogScraper with stubbed HTML fetching and parsed catalog rows."""
    from cis_bench.catalog.parser import WorkBenchCatalogParser

    scraper = CatalogScraper(
        temp_db, mock_session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
    )
    monkeypatch.setattr(scraper, "_fetch_page", lambda page_num: f"page-{page_num}")
    monkeypatch.setattr(
        WorkBenchCatalogParser,
        "extract_pagination_info",
        staticmethod(lambda _html: {"total_pages": total_pages}),
    )

    def parse_on_the_scrapers_origin(html: str, *, base_url: str) -> list[dict]:
        assert base_url == BASE  # the scraper parses rows against its own origin
        return parse_page(html)

    monkeypatch.setattr(
        WorkBenchCatalogParser, "parse_catalog_page", staticmethod(parse_on_the_scrapers_origin)
    )
    return scraper


class TestErrorHandling:
    """Test error handling and resilience."""

    def test_failed_page_continues_scraping(self, temp_db, sample_html, stub_session):
        """Test that failing one page doesn't stop the scrape."""
        import requests

        def handler(url):
            # Pages 1-19 succeed, only page 20 fails (5% failure - below 10% threshold)
            if url.endswith("?page=20"):
                raise requests.ConnectionError("Network error on page 20")
            return sample_html

        session, _ = stub_session(handler)

        scraper = CatalogScraper(
            temp_db, session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        # This should not crash even if one page fails (19 succeed, 1 fails = 5% failure)
        stats = scraper.scrape_full_catalog(max_pages=20)

        # Should have completed scrape attempt
        assert "total_benchmarks" in stats
        assert stats["failed_pages"] == [20]
        # At least page 1 should have succeeded
        assert stats["total_benchmarks"] > 0

    def test_scrape_full_catalog_skips_invalid_row_and_keeps_valid_rows(
        self, temp_db, mock_session, monkeypatch, caplog
    ):
        """Test malformed benchmark rows are logged and skipped without failing the page."""
        import logging

        pages = {
            1: [
                {
                    "benchmark_id": "101",
                    "title": "CIS Ubuntu Linux 24.04 LTS Benchmark",
                    "url": "https://workbench.cisecurity.org/benchmarks/101",
                    "status": "Published",
                },
                {
                    "benchmark_id": "102",
                    "title": "Malformed Empty Status Benchmark",
                    "url": "https://workbench.cisecurity.org/benchmarks/102",
                    "status": "",
                },
                {
                    "benchmark_id": "103",
                    "title": "CIS CentOS Linux 7 Benchmark",
                    "url": "https://workbench.cisecurity.org/benchmarks/103",
                    "status": "Final Update",
                },
            ],
            2: [
                {
                    "benchmark_id": "201",
                    "url": "https://workbench.cisecurity.org/benchmarks/201",
                    "status": "Published",
                },
                {
                    "benchmark_id": "202",
                    "title": "CIS Custom Lifecycle Benchmark",
                    "url": "https://workbench.cisecurity.org/benchmarks/202",
                    "status": "Sunset",
                },
            ],
        }
        scraper = _stub_scraper_pages(
            temp_db,
            mock_session,
            monkeypatch,
            lambda html: pages[int(html.split("-")[1])],
            total_pages=2,
        )

        with caplog.at_level(logging.WARNING):
            stats = scraper.scrape_full_catalog(max_pages=2)

        assert stats["failed_pages"] == []
        assert stats["total_benchmarks"] == 3
        assert temp_db.get_benchmark("101")["status"] == "Published"
        assert temp_db.get_benchmark("102") is None
        assert temp_db.get_benchmark("103")["status"] == "Final Update"
        assert temp_db.get_benchmark("201") is None
        assert temp_db.get_benchmark("202")["status"] == "Sunset"
        assert "102" in caplog.text
        assert "201" in caplog.text

    def test_scrape_full_catalog_marks_page_failed_when_all_rows_invalid(
        self, temp_db, mock_session, monkeypatch, caplog
    ):
        """Test a non-empty page where every row fails validation tries all rows then fails page."""
        import logging

        def fake_parse(html: str) -> list[dict]:
            page_num = int(html.split("-")[1])
            if page_num == 2:
                return [
                    {
                        "benchmark_id": "bad-a",
                        "title": "Bad A",
                        "url": "https://workbench.cisecurity.org/benchmarks/bad-a",
                        "status": "",
                    },
                    {
                        "benchmark_id": "bad-b",
                        "title": "Bad B",
                        "url": "https://workbench.cisecurity.org/benchmarks/bad-b",
                        "status": "   ",
                    },
                ]
            return [
                {
                    "benchmark_id": f"ok-{page_num}",
                    "title": f"Valid Benchmark {page_num}",
                    "url": f"https://workbench.cisecurity.org/benchmarks/ok-{page_num}",
                    "status": "Published",
                }
            ]

        scraper = _stub_scraper_pages(
            temp_db, mock_session, monkeypatch, fake_parse, total_pages=20
        )

        with caplog.at_level(logging.WARNING):
            stats = scraper.scrape_full_catalog(max_pages=20)

        assert stats["failed_pages"] == [2]
        assert stats["total_benchmarks"] == 19
        assert "bad-a" in caplog.text
        assert "bad-b" in caplog.text
        assert "All 2 benchmarks on page 2 failed validation" in caplog.text

    def test_scrape_full_catalog_propagates_database_operational_error(
        self, temp_db, mock_session, monkeypatch
    ):
        """Test SQLite OperationalError is re-raised immediately rather than swallowed."""
        from sqlalchemy.exc import OperationalError

        scraper = _stub_scraper_pages(
            temp_db,
            mock_session,
            monkeypatch,
            lambda html: [
                {
                    "benchmark_id": f"id-{html}",
                    "title": f"Benchmark {html}",
                    "url": f"https://workbench.cisecurity.org/benchmarks/{html}",
                    "status": "Published",
                }
            ],
            total_pages=2,
        )

        original_insert = temp_db.insert_benchmark

        def fail_on_page_two(bench: dict) -> None:
            if bench["benchmark_id"] == "id-page-2":
                raise OperationalError("INSERT", {}, Exception("database is locked"))
            original_insert(bench)

        monkeypatch.setattr(temp_db, "insert_benchmark", fail_on_page_two)

        with pytest.raises(OperationalError, match="database is locked"):
            scraper.scrape_full_catalog(max_pages=2)

    def test_scrape_page_one_update_skips_invalid_row_and_fails_if_all_invalid(
        self, temp_db, mock_session, monkeypatch
    ):
        """Test quick page-1 update skips single bad rows but raises when every row fails."""
        current_rows: list[dict] = [
            {
                "benchmark_id": "301",
                "title": "CIS Debian Linux 12 Benchmark",
                "url": "https://workbench.cisecurity.org/benchmarks/301",
                "status": "Final Update",
            },
            {
                "benchmark_id": "302",
                "title": "Invalid Empty Status",
                "url": "https://workbench.cisecurity.org/benchmarks/302",
                "status": "   ",
            },
            {
                "url": "https://workbench.cisecurity.org/benchmarks/missing-id",
                "title": "Missing ID Row",
                "status": "Published",
            },
        ]
        scraper = _stub_scraper_pages(
            temp_db, mock_session, monkeypatch, lambda _html: current_rows
        )

        stats = scraper.scrape_page_one_update()
        assert stats == {"new_count": 1, "updated_count": 0}
        assert temp_db.get_benchmark("301")["status"] == "Final Update"
        assert temp_db.get_benchmark("302") is None

        current_rows[:] = [
            {
                "benchmark_id": "303",
                "title": "All Bad",
                "url": "https://workbench.cisecurity.org/benchmarks/303",
                "status": "",
            }
        ]
        with pytest.raises(ValueError, match="failed validation"):
            scraper.scrape_page_one_update()

    def test_fetch_and_parse_page_propagates_authentication_error_without_retries(
        self, temp_db, mock_session, monkeypatch
    ):
        """_fetch_and_parse_page raises AuthenticationError on the first attempt."""
        from cis_bench.catalog.parser import WorkBenchCatalogParser

        fetch_calls: list[int] = []

        scraper = CatalogScraper(
            temp_db,
            mock_session,
            base_url=BASE,
            timeout=TIMEOUT,
            max_workers=WORKERS,
            batch_size=BATCH,
        )

        def fake_fetch(page_num: int) -> str:
            fetch_calls.append(page_num)
            return "login-html"

        def raise_auth(_html: str, *, base_url: str) -> list[dict]:
            raise AuthenticationError("Not authenticated")

        monkeypatch.setattr(scraper, "_fetch_page", fake_fetch)
        monkeypatch.setattr(WorkBenchCatalogParser, "parse_catalog_page", staticmethod(raise_auth))

        with pytest.raises(AuthenticationError, match="Not authenticated"):
            scraper._fetch_and_parse_page(2)

        assert fetch_calls == [2]

    def test_scrape_full_catalog_propagates_authentication_error_from_worker_page(
        self, temp_db, mock_session, monkeypatch
    ):
        """scrape_full_catalog aborts immediately with AuthenticationError when session expires mid-scrape."""

        def fake_parse(html: str) -> list[dict]:
            page_num = int(html.split("-")[1])
            if page_num == 2:
                raise AuthenticationError("Session expired on page 2")
            return [
                {
                    "benchmark_id": "101",
                    "title": "CIS Ubuntu Linux 24.04 LTS Benchmark",
                    "url": "https://workbench.cisecurity.org/benchmarks/101",
                    "status": "Published",
                }
            ]

        scraper = _stub_scraper_pages(temp_db, mock_session, monkeypatch, fake_parse, total_pages=3)

        with pytest.raises(AuthenticationError, match="Session expired on page 2"):
            scraper.scrape_full_catalog(max_pages=3)

    def test_scrape_full_catalog_includes_page_one_in_failure_rate_denominator(
        self, temp_db, mock_session, monkeypatch
    ):
        """1 failed page out of 10 total pages (10.0%) succeeds when Page 1 is counted in denominator."""

        def fake_parse(html: str) -> list[dict]:
            page_num = int(html.split("-")[1])
            if page_num == 2:
                raise RuntimeError("Transient 502 on page 2")
            return [
                {
                    "benchmark_id": str(1000 + page_num),
                    "title": f"CIS Benchmark {page_num}",
                    "url": f"https://workbench.cisecurity.org/benchmarks/{1000 + page_num}",
                    "status": "Published",
                }
            ]

        scraper = _stub_scraper_pages(
            temp_db, mock_session, monkeypatch, fake_parse, total_pages=10
        )

        stats = scraper.scrape_full_catalog(max_pages=10)

        assert stats["failed_pages"] == [2]
        assert stats["pages_scraped"] == 10
        assert stats["total_benchmarks"] == 9
        assert stats["success_rate"] == pytest.approx(0.9)

    def test_scrape_full_catalog_raises_value_error_when_page_one_returns_zero_rows(
        self, temp_db, mock_session, monkeypatch
    ):
        """scrape_full_catalog raises ValueError immediately when Page 1 returns 0 parsed rows."""
        scraper = _stub_scraper_pages(
            temp_db, mock_session, monkeypatch, lambda _html: [], total_pages=5
        )

        with pytest.raises(ValueError, match="Connected but no benchmarks found"):
            scraper.scrape_full_catalog(max_pages=5)


class TestRefreshDownloadedRevisionDates:
    """check-updates fetches the detail page of each downloaded benchmark, never the whole catalog."""

    def _seed(self, db, bid, version="v1.0.0"):
        from cis_bench.catalog.database import serialize_benchmark_json
        from cis_bench.models.benchmark import Benchmark, Recommendation

        db.insert_benchmark(
            {
                "benchmark_id": bid,
                "title": f"CIS Benchmark {bid}",
                "version": version,
                "url": f"https://workbench.cisecurity.org/benchmarks/{bid}",
                "status": "Published",
            }
        )
        copy = Benchmark(
            title=f"CIS Benchmark {bid}",
            benchmark_id=bid,
            url=f"https://workbench.cisecurity.org/benchmarks/{bid}",
            version=version,
            scraper_version="v2_2026_01",
            total_recommendations=1,
            recommendations=[
                Recommendation(
                    ref="1.1.1",
                    title="Ensure the example setting is configured",
                    url=f"https://workbench.cisecurity.org/sections/1/recommendations/{bid}1",
                    assessment_status="Automated",
                )
            ],
        )
        content_json, content_hash = serialize_benchmark_json(copy)
        db.save_downloaded(bid, content_json, content_hash, 1, version=version)

    @staticmethod
    def _response(html, status=200):
        response = Mock()
        response.text = html
        response.status_code = status
        response.raise_for_status = Mock()
        return response

    def test_stores_the_iso_publication_date_for_each_downloaded_benchmark(self, temp_db):
        self._seed(temp_db, "401")
        self._seed(temp_db, "402")
        temp_db.insert_benchmark(
            {
                "benchmark_id": "403",
                "title": "Not downloaded",
                "version": "v1.0.0",
                "url": "https://workbench.cisecurity.org/benchmarks/403",
                "status": "Published",
            }
        )
        session = Mock()
        session.get = Mock(
            return_value=self._response(
                "<html><body><span>Published 2 months ago on Aug 28th 2025</span></body></html>"
            )
        )
        scraper = CatalogScraper(
            temp_db, session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        refreshed = scraper.refresh_downloaded_pages()

        assert refreshed == 2
        fetched = sorted(call.args[0] for call in session.get.call_args_list)
        assert fetched == [
            "https://workbench.cisecurity.org/benchmarks/401",
            "https://workbench.cisecurity.org/benchmarks/402",
        ]
        # What WorkBench shows now goes on the catalog row; the copy keeps its own date
        assert temp_db.get_benchmark("401")["published_date"] == date(2025, 8, 28)
        assert temp_db.get_benchmark("402")["published_date"] == date(2025, 8, 28)
        assert temp_db.get_downloaded("401")["published_date"] is None
        assert temp_db.get_benchmark("403")["published_date"] is None

    def test_the_description_on_the_page_is_recorded_too(self, temp_db):
        self._seed(temp_db, "401")
        session = Mock()
        session.get = Mock(
            return_value=self._response(
                "<p>Published</p> 1 year ago on Aug 28th 2025"
                '<wb-recommendation-data attribute="overview" text="Guidance for 401.">'
                "</wb-recommendation-data>"
            )
        )

        CatalogScraper(
            temp_db, session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        ).refresh_downloaded_pages()

        assert temp_db.get_benchmark("401")["description"] == "Guidance for 401."

    def test_a_page_read_by_check_updates_has_its_addresses_decoded(self, temp_db):
        self._seed(temp_db, "401")
        cf_info = "9df4f3fbf2ddf8e5fcf0edf1f8b3fef2f0"  # info@example.com
        session = Mock()
        session.get = Mock(
            return_value=self._response(
                "<p>Published</p> 1 year ago on Aug 28th 2025<h2>Overview</h2>"
                f'<p>Write <span class="__cf_email__" data-cfemail="{cf_info}">[email protected]</span></p>'
            )
        )

        CatalogScraper(
            temp_db, session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        ).refresh_downloaded_pages()

        assert temp_db.get_benchmark("401")["description"] == "Write info@example.com"

    def test_a_benchmark_workbench_no_longer_has_is_reported_and_the_rest_are_checked(
        self, temp_db, stub_session, caplog
    ):
        """WorkBench answering 404 for one downloaded benchmark does not stop the check."""
        from tests.conftest import StubReply

        self._seed(temp_db, "401")
        self._seed(temp_db, "402")
        page = "<html><body><span>Published 2 months ago on Aug 28th 2025</span></body></html>"
        session, _ = stub_session(
            lambda url: StubReply(body="gone", status=404) if url.endswith("/401") else page
        )
        scraper = CatalogScraper(
            temp_db, session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        with caplog.at_level("WARNING", logger="cis_bench.catalog.scraper"):
            refreshed = scraper.refresh_downloaded_pages()

        assert refreshed == 1
        assert temp_db.get_benchmark("402")["published_date"] == date(2025, 8, 28)
        assert temp_db.get_benchmark("401")["published_date"] is None
        assert [r.getMessage() for r in caplog.records if r.levelname == "WARNING"] == [
            "WorkBench no longer has benchmark 401 (HTTP 404); its downloaded copy was not checked"
        ]

    def test_another_http_error_still_stops_the_check(self, temp_db, stub_session):
        import requests

        from tests.conftest import StubReply

        self._seed(temp_db, "401")
        session, _ = stub_session(lambda url: StubReply(body="forbidden", status=403))
        scraper = CatalogScraper(
            temp_db, session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        with pytest.raises(requests.HTTPError):
            scraper.refresh_downloaded_pages()

    def test_a_malformed_stored_id_is_skipped_and_never_fetched(self, temp_db, caplog):
        """The detail URL goes through the same validator as every other WorkBench URL."""
        self._seed(temp_db, "407")
        self._seed(temp_db, "../admin")
        session = Mock()
        session.get = Mock(
            return_value=self._response(
                "<html><body><p>Published</p> 1 year ago on Aug 28th 2025</body></html>"
            )
        )

        with caplog.at_level("WARNING"):
            refreshed = CatalogScraper(
                temp_db,
                session,
                base_url=BASE,
                timeout=TIMEOUT,
                max_workers=WORKERS,
                batch_size=BATCH,
            ).refresh_downloaded_pages()

        assert refreshed == 1
        assert [c.args[0] for c in session.get.call_args_list] == [
            "https://workbench.cisecurity.org/benchmarks/407"
        ]
        assert "../admin" in caplog.text

    def test_page_without_a_date_leaves_the_row_unchanged(self, temp_db):
        self._seed(temp_db, "404")
        session = Mock()
        session.get = Mock(return_value=self._response("<html><body>No date here</body></html>"))

        refreshed = CatalogScraper(
            temp_db, session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        ).refresh_downloaded_pages()

        assert refreshed == 0
        assert temp_db.get_benchmark("404")["published_date"] is None

    def test_login_page_raises_authentication_error_immediately(self, temp_db):
        self._seed(temp_db, "405")
        self._seed(temp_db, "406")
        session = Mock()
        session.get = Mock(
            return_value=self._response(
                '<html><body><form action="/login"><input name="password"></form></body></html>'
            )
        )

        with pytest.raises(AuthenticationError):
            CatalogScraper(
                temp_db,
                session,
                base_url=BASE,
                timeout=TIMEOUT,
                max_workers=WORKERS,
                batch_size=BATCH,
            ).refresh_downloaded_pages()

        assert session.get.call_count == 1


def _listing(rows, total_pages, with_pager=True):
    """A listing page with the given (benchmark_id, title, version, status) rows."""
    body = "".join(
        f'<tr><td><a href="/benchmarks/{bid}">{title}</a></td><td>{version}</td>'
        f"<td>{status}</td><td>Test Community</td><td>Test Collection</td><td>testuser</td></tr>"
        for bid, title, version, status in rows
    )
    pager = "".join(f"<a>{n}</a>" for n in range(1, total_pages + 1)) if with_pager else ""
    return (
        "<table><tr><th>Title</th><th>Version</th><th>Status</th><th>Community</th>"
        f"<th>Collections</th><th>Owner</th></tr>{body}</table><nav>{pager}</nav>"
    )


def _page_number(url):
    import re

    match = re.search(r"[?&]page=(\d+)", url)
    assert match, url
    return int(match.group(1))


class TestACompleteRefreshMarksWithdrawnBenchmarks:
    """A benchmark WorkBench no longer lists is marked Withdrawn, only by a complete refresh."""

    FOO = ("101", "CIS Foo Benchmark", "v1.0.0", "Published")
    BAR = ("102", "CIS Bar Benchmark", "v2.0.0", "Published")
    OLD_BAR = ("103", "CIS Bar Benchmark", "v1.0.0", "Published")

    @staticmethod
    def _refresh(db, stub_session, pages, with_pager=True, **kwargs):
        """Run a full refresh of a catalog whose page n lists pages[n]; a page may raise."""

        def handler(url):
            rows = pages[_page_number(url)]
            if isinstance(rows, Exception):
                raise rows
            return _listing(rows, len(pages), with_pager=with_pager)

        session, _ = stub_session(handler)
        scraper = CatalogScraper(
            db, session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )
        return scraper.scrape_full_catalog(**kwargs)

    @staticmethod
    def _status(db, benchmark_id):
        row = db.get_benchmark(benchmark_id)
        return row["status"], bool(row["is_latest"])

    @staticmethod
    def _ids(db, **filters):
        return sorted(str(r["benchmark_id"]) for r in db.search("", limit=None, **filters))

    def test_a_complete_refresh_marks_a_benchmark_that_is_no_longer_listed_withdrawn(
        self, temp_db, stub_session
    ):
        self._refresh(temp_db, stub_session, {1: [self.FOO, self.BAR], 2: [self.OLD_BAR]})
        assert self._status(temp_db, "101") == ("Published", True)

        stats = self._refresh(temp_db, stub_session, {1: [self.BAR], 2: [self.OLD_BAR]})

        assert stats["withdrawn"] == 1
        assert self._status(temp_db, "101") == ("Withdrawn", False)
        assert self._ids(temp_db) == ["102", "103"]
        assert self._ids(temp_db, status="Withdrawn") == ["101"]
        assert self._ids(temp_db, status="all") == ["101", "102", "103"]
        assert self._ids(temp_db, status="all", latest_only=True) == ["102"]

    def test_withdrawing_the_latest_release_makes_the_older_one_latest(self, temp_db, stub_session):
        self._refresh(temp_db, stub_session, {1: [self.FOO, self.BAR], 2: [self.OLD_BAR]})
        assert self._status(temp_db, "103") == ("Published", False)

        self._refresh(temp_db, stub_session, {1: [self.FOO], 2: [self.OLD_BAR]})

        assert self._status(temp_db, "102") == ("Withdrawn", False)
        assert self._status(temp_db, "103") == ("Published", True)

    def test_a_benchmark_listed_again_gets_its_status_back(self, temp_db, stub_session):
        self._refresh(temp_db, stub_session, {1: [self.FOO, self.BAR], 2: [self.OLD_BAR]})
        self._refresh(temp_db, stub_session, {1: [self.BAR], 2: [self.OLD_BAR]})

        stats = self._refresh(temp_db, stub_session, {1: [self.FOO, self.BAR], 2: [self.OLD_BAR]})

        assert stats["withdrawn"] == 0
        assert self._status(temp_db, "101") == ("Published", True)

    def test_a_withdrawn_benchmark_keeps_its_downloaded_copy(self, temp_db, stub_session):
        self._refresh(temp_db, stub_session, {1: [self.FOO, self.BAR], 2: [self.OLD_BAR]})
        temp_db.save_downloaded("101", '{"version": "v1.0.0"}', "hash", 10, version="v1.0.0")

        self._refresh(temp_db, stub_session, {1: [self.BAR], 2: [self.OLD_BAR]})

        assert self._status(temp_db, "101") == ("Withdrawn", False)
        assert temp_db.get_downloaded("101")["version"] == "v1.0.0"
        assert temp_db.list_downloaded_benchmark_ids() == ["101"]

    def test_a_refresh_with_a_failed_page_marks_nothing(self, temp_db, stub_session):
        import requests

        self._refresh(temp_db, stub_session, {1: [self.FOO, self.BAR], 2: [self.OLD_BAR]})

        # One failed page of twelve: under the 10% abort threshold, so the refresh finishes.
        pages = {1: [self.BAR], **{n: [self.OLD_BAR] for n in range(2, 12)}}
        pages[12] = requests.ConnectionError("page 12 down")
        stats = self._refresh(temp_db, stub_session, pages)

        assert stats["failed_pages"] == [12]
        assert stats["withdrawn"] is None
        assert self._status(temp_db, "101") == ("Published", True)

    def test_a_refresh_limited_to_some_pages_marks_nothing(self, temp_db, stub_session):
        self._refresh(temp_db, stub_session, {1: [self.FOO, self.BAR], 2: [self.OLD_BAR]})

        stats = self._refresh(
            temp_db, stub_session, {1: [self.BAR], 2: [self.OLD_BAR]}, max_pages=1
        )

        assert stats["withdrawn"] is None
        assert self._status(temp_db, "101") == ("Published", True)

    def test_a_refresh_that_got_an_empty_page_marks_nothing(self, temp_db, stub_session):
        self._refresh(temp_db, stub_session, {1: [self.FOO, self.BAR], 2: [self.OLD_BAR]})

        stats = self._refresh(temp_db, stub_session, {1: [self.BAR], 2: []})

        assert stats["withdrawn"] is None
        assert self._status(temp_db, "101") == ("Published", True)
        assert self._status(temp_db, "103") == ("Published", False)

    def test_a_refresh_that_could_not_count_the_pages_marks_nothing(self, temp_db, stub_session):
        self._refresh(temp_db, stub_session, {1: [self.FOO, self.BAR], 2: [self.OLD_BAR]})

        pages = {n: [self.BAR] for n in range(1, 71)}
        stats = self._refresh(temp_db, stub_session, pages, with_pager=False)

        assert stats["withdrawn"] is None
        assert self._status(temp_db, "101") == ("Published", True)


class TestARefreshLogsOnlyRunLevelLinesAtInfo:
    def test_a_full_refresh_logs_summaries_at_info_and_per_page_detail_at_debug(
        self, temp_db, sample_html, stub_session, caplog
    ):
        session, _ = stub_session(lambda url: sample_html)
        scraper = CatalogScraper(
            temp_db, session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        with caplog.at_level("INFO", logger="cis_bench"):
            scraper.scrape_full_catalog(max_pages=3)

        info = [r.getMessage() for r in caplog.records if r.levelname == "INFO"]
        assert not [m for m in info if m.startswith("Parsed ")]
        assert not [m for m in info if "schema" in m.lower() or "FTS5" in m]
        assert "Will scrape 3 pages (detected from pagination)" in info
        assert any(m.startswith("Scrape complete: ") for m in info)


class TestScraperCountsAgreeWithTheNumber:
    @pytest.mark.parametrize(("attempts", "noun"), [(1, "attempt"), (3, "attempts")])
    def test_a_fetch_error_counts_its_attempts(self, attempts, noun):
        from cis_bench.exceptions import FetchError

        assert str(FetchError("https://x", attempts, "timed out")).endswith(
            f"timed out after {attempts} {noun}"
        )

    @pytest.mark.parametrize(
        ("completed", "total", "expected"), [(1, 1, "(1/1 page)"), (1, 3, "(1/3 pages)")]
    )
    def test_the_progress_column_counts_the_pages(self, completed, total, expected):
        from types import SimpleNamespace

        from cis_bench.catalog.scraper import PagesColumn

        task = SimpleNamespace(completed=completed, total=total)
        assert PagesColumn().render(task).plain == expected

    @pytest.mark.parametrize(
        ("found", "expected"),
        [(1, "Scraping catalog | 1 benchmark found"), (2, "Scraping catalog | 2 benchmarks found")],
    )
    def test_the_progress_description_counts_the_benchmarks(self, found, expected):
        from cis_bench.catalog.scraper import progress_description

        assert progress_description(found) == expected

    @pytest.mark.parametrize(
        ("invalid", "expected"), [(1, "The 1 benchmark"), (2, "All 2 benchmarks")]
    )
    def test_a_page_whose_benchmarks_all_fail_validation_says_how_many(
        self, temp_db, mock_session, invalid, expected
    ):
        scraper = CatalogScraper(
            temp_db,
            mock_session,
            base_url=BASE,
            timeout=TIMEOUT,
            max_workers=WORKERS,
            batch_size=BATCH,
        )

        with pytest.raises(ValueError, match=f"{expected} on page 4 failed validation"):
            scraper._insert_page_benchmarks([{} for _ in range(invalid)], 4)

    @pytest.mark.parametrize(
        ("failing", "expected"), [(1, "1 page failed."), (2, "2 pages failed.")]
    )
    def test_an_aborted_scrape_counts_the_failed_pages(
        self, temp_db, sample_html, stub_session, failing, expected
    ):
        def answer(url):
            if url.endswith("?page=1"):
                return sample_html
            raise ConnectionError("unreachable")

        session, _ = stub_session(answer)
        scraper = CatalogScraper(
            temp_db, session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        with pytest.raises(Exception, match=f"Scraping aborted: {expected}"):
            scraper.scrape_full_catalog(max_pages=1 + failing)
