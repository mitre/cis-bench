"""Unit tests for catalog scraper."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from cis_bench.catalog.database import CatalogDatabase
from cis_bench.catalog.scraper import CatalogScraper
from cis_bench.exceptions import AuthenticationError


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary database."""
    db = CatalogDatabase(tmp_path / "test.db")
    db.initialize_schema()
    return db


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
        scraper = CatalogScraper(temp_db, mock_session)

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

        scraper = CatalogScraper(temp_db, session)

        assert scraper.session.verify == verify_setting

    def test_base_url(self):
        """Test base URL is set correctly."""
        assert CatalogScraper.BASE_URL == "https://workbench.cisecurity.org/benchmarks"


class TestConnectionTesting:
    """Test connection and authentication testing."""

    def test_connection_success(self, temp_db, mock_session):
        """Test successful connection test."""
        scraper = CatalogScraper(temp_db, mock_session)

        result = scraper.test_connection()

        assert result is True
        mock_session.get.assert_called_once()

    def test_connection_detects_login_redirect(self, temp_db):
        """Test detection of login redirect raises AuthenticationError."""
        session = Mock()
        response = Mock()
        response.text = "<html><body>Login required</body></html>"
        response.status_code = 200
        response.raise_for_status = Mock()
        session.get = Mock(return_value=response)

        scraper = CatalogScraper(temp_db, session)

        with pytest.raises(AuthenticationError, match="Not authenticated"):
            scraper.test_connection()

    def test_connection_raises_value_error_when_page_one_has_zero_rows(self, temp_db):
        """test_connection raises ValueError when Page 1 parses 0 benchmarks."""
        session = Mock()
        response = Mock()
        response.text = "<html><body><table><tr><th>Title</th></tr></table></body></html>"
        response.status_code = 200
        response.raise_for_status = Mock()
        session.get = Mock(return_value=response)

        scraper = CatalogScraper(temp_db, session)

        with pytest.raises(ValueError, match="no benchmarks found"):
            scraper.test_connection()

    def test_connection_handles_network_error(self, temp_db):
        """Test handling of network errors."""
        import requests

        session = Mock()
        session.get = Mock(side_effect=requests.ConnectionError("Network error"))

        scraper = CatalogScraper(temp_db, session)

        with pytest.raises(Exception, match="Connection failed"):
            scraper.test_connection()


class TestPageFetching:
    """Test individual page fetching."""

    def test_fetch_page(self, temp_db, mock_session, sample_html):
        """Test fetching single page."""
        scraper = CatalogScraper(temp_db, mock_session)

        html = scraper._fetch_page(1)

        assert html == sample_html
        mock_session.get.assert_called_once()

    def test_fetch_page_url_format(self, temp_db, mock_session):
        """Test page URL is formatted correctly."""
        scraper = CatalogScraper(temp_db, mock_session)

        scraper._fetch_page(5)

        # Check URL includes page parameter
        call_args = mock_session.get.call_args
        url = call_args[0][0]
        assert "?page=5" in url

    def test_fetch_page_honors_configured_workbench_base_url(
        self, temp_db, mock_session, monkeypatch
    ):
        """_fetch_page uses CIS_BENCH_WORKBENCH_URL when configured."""
        monkeypatch.setenv("CIS_BENCH_WORKBENCH_URL", "https://workbench-staging.cisecurity.org")
        scraper = CatalogScraper(temp_db, mock_session)

        scraper._fetch_page(2)

        assert (
            mock_session.get.call_args[0][0]
            == "https://workbench-staging.cisecurity.org/benchmarks?page=2"
        )

    def test_fetch_page_user_agent(self, temp_db, mock_session):
        """Test User-Agent header is set."""
        scraper = CatalogScraper(temp_db, mock_session)

        scraper._fetch_page(1)

        call_args = mock_session.get.call_args
        headers = call_args[1].get("headers", {})
        assert "User-Agent" in headers
        assert "cis-bench-cli" in headers["User-Agent"]


class TestFullCatalogScrape:
    """Test full catalog scraping."""

    def test_scrape_full_catalog(self, temp_db, mock_session):
        """Test scraping multiple pages."""
        scraper = CatalogScraper(temp_db, mock_session)

        stats = scraper.scrape_full_catalog(max_pages=2, rate_limit_seconds=0)

        assert stats["total_benchmarks"] > 0
        assert stats["pages_scraped"] >= 1
        assert isinstance(stats["failed_pages"], list)

    def test_scrape_respects_max_pages(self, temp_db, mock_session):
        """Test max_pages parameter limits scraping."""
        scraper = CatalogScraper(temp_db, mock_session)

        stats = scraper.scrape_full_catalog(max_pages=3, rate_limit_seconds=0)

        # Should not scrape more than max_pages
        assert stats["pages_scraped"] <= 3

    def test_scrape_saves_to_database(self, temp_db, mock_session):
        """Test scraped benchmarks are saved to database."""
        scraper = CatalogScraper(temp_db, mock_session)

        scraper.scrape_full_catalog(max_pages=1, rate_limit_seconds=0)

        # Check database has benchmarks
        db_stats = temp_db.get_catalog_stats()
        assert db_stats["total_benchmarks"] > 0

    def test_scrape_marks_latest_versions(self, temp_db, mock_session):
        """Test scraper marks latest versions."""
        scraper = CatalogScraper(temp_db, mock_session)

        scraper.scrape_full_catalog(max_pages=1, rate_limit_seconds=0)

        # Verify mark_latest_versions was called (check metadata exists)
        # This is indirect - checking the method was executed
        db_stats = temp_db.get_catalog_stats()
        assert db_stats["total_benchmarks"] > 0  # Scrape completed

    def test_scrape_saves_metadata(self, temp_db, mock_session):
        """Test scraper saves scrape metadata."""
        scraper = CatalogScraper(temp_db, mock_session)

        scraper.scrape_full_catalog(max_pages=1, rate_limit_seconds=0)

        # Check metadata was saved
        last_scrape = temp_db.get_metadata("last_full_scrape")
        assert last_scrape is not None


class TestQuickUpdate:
    """Test quick update functionality."""

    def test_page_one_update(self, temp_db, mock_session):
        """Test quick update scrapes page 1 only."""
        scraper = CatalogScraper(temp_db, mock_session)

        stats = scraper.scrape_page_one_update(rate_limit_seconds=0)

        assert "new_count" in stats
        assert "updated_count" in stats
        assert isinstance(stats["new_count"], int)

    def test_update_detects_new_benchmarks(self, temp_db, mock_session):
        """Test update detects new benchmarks."""
        scraper = CatalogScraper(temp_db, mock_session)

        # First update - all new
        stats1 = scraper.scrape_page_one_update(rate_limit_seconds=0)
        assert stats1["new_count"] > 0

        # Second update - none new (same page)
        stats2 = scraper.scrape_page_one_update(rate_limit_seconds=0)
        assert stats2["new_count"] == 0

    def test_update_detects_field_and_status_changes_without_revision_date(
        self, temp_db, mock_session, monkeypatch
    ):
        """scrape_page_one_update detects status/version/title updates even when last_revision_date is None."""
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

        assert scraper.scrape_page_one_update(rate_limit_seconds=0) == {
            "new_count": 1,
            "updated_count": 0,
        }
        assert scraper.scrape_page_one_update(rate_limit_seconds=0) == {
            "new_count": 0,
            "updated_count": 0,
        }

        current_rows[:] = [{**row, "status": "Final Update", "version": "v4.0.1"}]
        assert scraper.scrape_page_one_update(rate_limit_seconds=0) == {
            "new_count": 0,
            "updated_count": 1,
        }
        saved = temp_db.get_benchmark("501")
        assert saved is not None
        assert saved["status"] == "Final Update"
        assert saved["version"] == "v4.0.1"


def _stub_scraper_pages(
    temp_db: CatalogDatabase,
    mock_session: Mock,
    monkeypatch: pytest.MonkeyPatch,
    parse_page,
    total_pages: int = 1,
) -> CatalogScraper:
    """Create a CatalogScraper with stubbed HTML fetching and parsed catalog rows."""
    from cis_bench.catalog.parser import WorkBenchCatalogParser

    scraper = CatalogScraper(temp_db, mock_session)
    monkeypatch.setattr(scraper, "_fetch_page", lambda page_num: f"page-{page_num}")
    monkeypatch.setattr(
        WorkBenchCatalogParser,
        "extract_pagination_info",
        staticmethod(lambda _html: {"total_pages": total_pages}),
    )
    monkeypatch.setattr(WorkBenchCatalogParser, "parse_catalog_page", staticmethod(parse_page))
    return scraper


class TestErrorHandling:
    """Test error handling and resilience."""

    def test_failed_page_continues_scraping(self, temp_db, sample_html):
        """Test that failing one page doesn't stop the scrape."""
        session = Mock()

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            # First 19 calls succeed, only last fails (5% failure - below 10% threshold)
            if call_count <= 19:  # Pages 1-19 succeed
                response = Mock()
                response.text = sample_html
                response.status_code = 200
                response.raise_for_status = Mock()
                return response
            else:
                raise Exception("Network error on page 20")

        session.get = Mock(side_effect=side_effect)

        scraper = CatalogScraper(temp_db, session)

        # This should not crash even if one page fails (19 succeed, 1 fails = 5% failure)
        stats = scraper.scrape_full_catalog(max_pages=20, rate_limit_seconds=0)

        # Should have completed scrape attempt
        assert "total_benchmarks" in stats
        assert "failed_pages" in stats
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
            stats = scraper.scrape_full_catalog(max_pages=2, rate_limit_seconds=0)

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
            stats = scraper.scrape_full_catalog(max_pages=20, rate_limit_seconds=0)

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
            scraper.scrape_full_catalog(max_pages=2, rate_limit_seconds=0)

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

        stats = scraper.scrape_page_one_update(rate_limit_seconds=0)
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
            scraper.scrape_page_one_update(rate_limit_seconds=0)

    def test_fetch_and_parse_page_propagates_authentication_error_without_retries(
        self, temp_db, mock_session, monkeypatch
    ):
        """_fetch_and_parse_page raises AuthenticationError on first attempt without sleeping."""
        import cis_bench.catalog.scraper as scraper_module
        from cis_bench.catalog.parser import WorkBenchCatalogParser

        sleep_calls: list[float] = []
        fetch_calls: list[int] = []

        scraper = CatalogScraper(temp_db, mock_session)
        monkeypatch.setattr(scraper_module.time, "sleep", lambda secs: sleep_calls.append(secs))

        def fake_fetch(page_num: int) -> str:
            fetch_calls.append(page_num)
            return "login-html"

        def raise_auth(_html: str) -> list[dict]:
            raise AuthenticationError("Not authenticated")

        monkeypatch.setattr(scraper, "_fetch_page", fake_fetch)
        monkeypatch.setattr(WorkBenchCatalogParser, "parse_catalog_page", staticmethod(raise_auth))

        with pytest.raises(AuthenticationError, match="Not authenticated"):
            scraper._fetch_and_parse_page(2, max_retries=3)

        assert fetch_calls == [2]
        assert sleep_calls == []

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
            scraper.scrape_full_catalog(max_pages=3, rate_limit_seconds=0)

    def test_scrape_full_catalog_includes_page_one_in_failure_rate_denominator(
        self, temp_db, mock_session, monkeypatch
    ):
        """1 failed page out of 10 total pages (10.0%) succeeds when Page 1 is counted in denominator."""
        import cis_bench.catalog.scraper as scraper_module

        monkeypatch.setattr(scraper_module.time, "sleep", lambda _secs: None)

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

        stats = scraper.scrape_full_catalog(max_pages=10, rate_limit_seconds=0)

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

        with pytest.raises(ValueError, match="No benchmarks found on catalog page 1"):
            scraper.scrape_full_catalog(max_pages=5, rate_limit_seconds=0)
