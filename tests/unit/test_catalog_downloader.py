"""Unit tests for catalog downloader."""

from unittest.mock import Mock, create_autospec, patch

import pytest

from cis_bench.catalog.database import CatalogDatabase
from cis_bench.catalog.downloader import CatalogDownloader
from cis_bench.fetcher.workbench import WorkbenchScraper
from cis_bench.models.benchmark import Benchmark


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary database with sample data."""
    db = CatalogDatabase(tmp_path / "test.db")
    db.initialize_schema()

    # Insert sample catalog entries
    db.insert_benchmark(
        {
            "benchmark_id": "23598",
            "title": "CIS Ubuntu Linux 20.04 LTS Benchmark",
            "version": "v2.0.1",
            "url": "https://workbench.cisecurity.org/benchmarks/23598",
            "status": "Published",
            "platform": "Operating System",
            "is_latest": True,
            "last_revision_date": "2024-11-01",
        }
    )

    yield db
    db.engine.dispose()


@pytest.fixture
def mock_scraper(sample_recommendation_minimal):
    """Mock WorkbenchScraper."""
    scraper = create_autospec(WorkbenchScraper, instance=True)

    # Create real Benchmark object using conftest fixture
    recs = [sample_recommendation_minimal] * 10
    mock_benchmark = Benchmark(
        benchmark_id="23598",
        title="Test Benchmark",
        version="v1.0.0",
        url="https://workbench.cisecurity.org/benchmarks/23598",
        scraper_version="v1_2025_10",
        total_recommendations=len(recs),
        recommendations=recs,
    )

    scraper.download_benchmark.return_value = mock_benchmark

    return scraper


@pytest.fixture
def downloader(temp_db, mock_scraper):
    """Create CatalogDownloader instance."""
    return CatalogDownloader(temp_db, mock_scraper)


class TestDownloadByID:
    """Test downloading by benchmark ID."""

    def test_download_new_benchmark(self, downloader, mock_scraper):
        """Test downloading new benchmark."""
        result = downloader.download_by_id("23598")

        assert result["status"] == "downloaded"
        assert result["benchmark_id"] == "23598"
        assert "content_hash" in result
        mock_scraper.download_benchmark.assert_called_once_with(
            "https://workbench.cisecurity.org/benchmarks/23598"
        )

    def test_download_updates_database(self, downloader, temp_db):
        """Test download saves to database."""
        downloader.download_by_id("23598")

        # Check database
        downloaded = temp_db.get_downloaded("23598")
        assert downloaded is not None
        assert downloaded["benchmark_id"] == "23598"

    def test_download_nonexistent_raises(self, downloader):
        """Test downloading non-existent benchmark raises error."""
        with pytest.raises(ValueError, match="not in catalog"):
            downloader.download_by_id("99999")

    def test_download_already_current_skips(self, downloader, mock_scraper):
        """Test downloading already-current benchmark skips fetch."""
        # Download first time
        downloader.download_by_id("23598")

        # Download again (same revision date)
        result = downloader.download_by_id("23598")

        assert result["status"] == "already_current"
        # Should have called fetch only once (first time)
        assert mock_scraper.download_benchmark.call_count == 1

    def test_download_force_redownloads(self, downloader, mock_scraper):
        """Test force flag re-downloads."""
        # Download first time
        downloader.download_by_id("23598")

        # Force re-download
        downloader.download_by_id("23598", force=True)

        # Should have called fetch twice
        assert mock_scraper.download_benchmark.call_count == 2

    def test_download_unchanged_content_updates_timestamp(self, downloader):
        """Test downloading same content multiple times."""
        # Download first time
        result1 = downloader.download_by_id("23598")

        # Download again (same content)
        result2 = downloader.download_by_id("23598", force=True)

        # Hash should be the same
        assert result1["content_hash"] == result2["content_hash"]
        # Status should indicate unchanged or updated (both valid)
        assert result2["status"] in ("unchanged", "updated")

    def test_download_by_id_strips_query_and_fragment_before_scraping(self, temp_db, mock_scraper):
        """download_by_id canonicalizes stored benchmark URLs before calling WorkbenchScraper."""
        temp_db.insert_benchmark(
            {
                "benchmark_id": "23598",
                "title": "CIS Ubuntu Linux 20.04 LTS Benchmark",
                "version": "v2.0.1",
                "url": "https://workbench.cisecurity.org/benchmarks/23598?ref=catalog#top",
                "status": "Published",
            }
        )
        downloader = CatalogDownloader(temp_db, mock_scraper)

        result = downloader.download_by_id("23598")

        assert result["benchmark_id"] == "23598"
        mock_scraper.download_benchmark.assert_called_once_with(
            "https://workbench.cisecurity.org/benchmarks/23598"
        )

    @pytest.mark.parametrize(
        "tampered_url",
        [
            "https://workbench.cisecurity.org@attacker.example/benchmarks/23598",
            "https://attacker.example/benchmarks/23598",
            "http://workbench.cisecurity.org/benchmarks/23598",
            "https://portal.cisecurity.org/benchmarks/23598",
            "https://workbench.cisecurity.org/benchmarks/99999",
        ],
    )
    def test_download_by_id_rejects_off_origin_or_mismatched_catalog_url(
        self, temp_db, mock_scraper, tampered_url
    ):
        """download_by_id validates stored URL against Config.get_workbench_base_url() and benchmark_id."""
        temp_db.insert_benchmark(
            {
                "benchmark_id": "23598",
                "title": "CIS Ubuntu Linux 20.04 LTS Benchmark",
                "version": "v2.0.1",
                "url": tampered_url,
                "status": "Published",
            }
        )
        downloader = CatalogDownloader(temp_db, mock_scraper)

        with pytest.raises(ValueError, match="Invalid benchmark URL"):
            downloader.download_by_id("23598")

        mock_scraper.download_benchmark.assert_not_called()


class TestDownloadByName:
    """Test downloading by name with fuzzy matching."""

    @pytest.fixture
    def multi_ubuntu_db(self, temp_db):
        """Database with a second Ubuntu benchmark whose version is None."""
        temp_db.insert_benchmark(
            {
                "benchmark_id": "12345",
                "title": "CIS Ubuntu Linux 22.04 LTS Benchmark",
                "version": None,
                "url": "https://workbench.cisecurity.org/benchmarks/12345",
                "status": "Published",
                "is_latest": True,
            }
        )
        return temp_db

    def test_download_by_name_single_match(self, downloader, mock_scraper):
        """Test download by name with single match."""
        result = downloader.download_by_name("ubuntu")

        assert result["benchmark_id"] == "23598"
        mock_scraper.download_benchmark.assert_called_once_with(
            "https://workbench.cisecurity.org/benchmarks/23598"
        )

    def test_download_by_name_forwards_force_flag(self, downloader, mock_scraper):
        """Test force flag is forwarded from download_by_name to download_by_id."""
        downloader.download_by_id("23598")
        assert mock_scraper.download_benchmark.call_count == 1

        cached = downloader.download_by_name("ubuntu", force=False)
        assert cached["status"] == "already_current"
        assert mock_scraper.download_benchmark.call_count == 1

        forced = downloader.download_by_name("ubuntu", force=True)
        assert forced["benchmark_id"] == "23598"
        assert mock_scraper.download_benchmark.call_count == 2

    def test_download_by_name_no_matches(self, downloader):
        """Test download by name with no matches raises error."""
        with pytest.raises(ValueError, match="No benchmarks found"):
            downloader.download_by_name("nonexistent")

    def test_download_by_name_multiple_matches_raises(self, multi_ubuntu_db, mock_scraper):
        """Test multiple matches without interactive raises error."""
        downloader = CatalogDownloader(multi_ubuntu_db, mock_scraper)

        with pytest.raises(ValueError, match="Multiple benchmarks match"):
            downloader.download_by_name("ubuntu", interactive=False)

    @patch("questionary.select")
    def test_download_by_name_interactive(
        self, mock_select, downloader, multi_ubuntu_db, mock_scraper
    ):
        """Test interactive selection passes questionary.Choice objects and omits None versions."""
        import questionary

        downloader.download_by_id("23598")
        mock_select.return_value.ask = Mock(return_value="23598")

        result = downloader.download_by_name("ubuntu", interactive=True, force=True)

        assert result["benchmark_id"] == "23598"
        assert mock_scraper.download_benchmark.call_count == 2
        mock_select.assert_called_once()
        choices = mock_select.call_args.kwargs["choices"]
        assert len(choices) == 2
        assert all(isinstance(choice, questionary.Choice) for choice in choices)
        by_value = {choice.value: choice.title for choice in choices}
        assert by_value == {
            "23598": "[23598] CIS Ubuntu Linux 20.04 LTS Benchmark v2.0.1",
            "12345": "[12345] CIS Ubuntu Linux 22.04 LTS Benchmark",
        }

    @pytest.mark.parametrize("cancelled_value", [None, ""])
    @patch("questionary.select")
    def test_download_by_name_interactive_cancelled_raises(
        self, mock_select, cancelled_value, downloader, multi_ubuntu_db, mock_scraper
    ):
        """Test cancelled interactive selection raises ValueError without downloading."""
        mock_select.return_value.ask = Mock(return_value=cancelled_value)

        with pytest.raises(ValueError, match="Benchmark selection cancelled"):
            downloader.download_by_name("ubuntu", interactive=True)

        mock_scraper.download_benchmark.assert_not_called()


class TestGetDownloaded:
    """Test retrieving downloaded benchmarks."""

    def test_get_downloaded_benchmark(self, downloader):
        """Test getting downloaded benchmark as Benchmark object."""
        # Download first
        downloader.download_by_id("23598")

        # Get it back
        benchmark = downloader.get_downloaded_benchmark("23598")

        assert benchmark is not None
        assert isinstance(benchmark, Benchmark)

    def test_get_nonexistent_downloaded(self, downloader):
        """Test getting non-existent download returns None."""
        benchmark = downloader.get_downloaded_benchmark("99999")

        assert benchmark is None


class TestChangeDetection:
    """Test change detection via content hash."""

    def test_hash_calculation(self, downloader):
        """Test content hash is calculated correctly."""
        result = downloader.download_by_id("23598")

        assert "content_hash" in result
        assert len(result["content_hash"]) == 64  # SHA256 hex digest

    def test_same_content_detected(self, downloader):
        """Test that re-downloading same content has same hash."""
        # Download twice
        result1 = downloader.download_by_id("23598")
        result2 = downloader.download_by_id("23598", force=True)

        # Same hash indicates same content
        assert result1["content_hash"] == result2["content_hash"]

    def test_content_hash_ignores_scrape_timestamp_and_changes_on_content_update(
        self, temp_db, downloader, mock_scraper
    ):
        """Two scrapes of identical benchmark content at different timestamps yield identical content_hash."""
        from datetime import UTC, datetime, timedelta

        temp_db.insert_benchmark(
            {
                "benchmark_id": "23599",
                "title": "CIS Ubuntu Linux 22.04 LTS Benchmark",
                "version": "v2.0.1",
                "url": "https://workbench.cisecurity.org/benchmarks/23599",
                "status": "Published",
            }
        )
        base_benchmark = mock_scraper.download_benchmark.return_value
        t1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        t2 = t1 + timedelta(seconds=30)

        bench_scrape_1 = base_benchmark.model_copy(
            update={"benchmark_id": "23599", "downloaded_at": t1}
        )
        bench_scrape_2 = base_benchmark.model_copy(
            update={"benchmark_id": "23599", "downloaded_at": t2}
        )
        bench_mutated = base_benchmark.model_copy(
            update={"benchmark_id": "23599", "downloaded_at": t2, "version": "v2.0.2"}
        )

        mock_scraper.download_benchmark.side_effect = [
            bench_scrape_1,
            bench_scrape_2,
            bench_mutated,
        ]

        first = downloader.download_by_id("23599")
        second = downloader.download_by_id("23599")
        third = downloader.download_by_id("23599")

        assert first["status"] == "downloaded"
        assert second["status"] == "unchanged"
        assert second["content_hash"] == first["content_hash"]
        assert third["status"] == "updated"
        assert third["content_hash"] != first["content_hash"]


class TestIntegration:
    """Integration tests with real components."""

    def test_full_download_workflow(self, temp_db, mock_scraper):
        """Test complete download workflow."""
        downloader = CatalogDownloader(temp_db, mock_scraper)

        # Search
        search_results = downloader.search.search("ubuntu")
        assert len(search_results) > 0

        # Download
        benchmark_id = search_results[0]["benchmark_id"]
        result = downloader.download_by_id(benchmark_id)

        assert result["status"] in ("downloaded", "already_current")

        # Retrieve
        benchmark = downloader.get_downloaded_benchmark(benchmark_id)
        assert benchmark is not None

    def test_save_downloaded_refreshes_downloaded_at_and_last_accessed_on_redownload(
        self, downloader, temp_db
    ):
        """Re-saving an existing downloaded row refreshes both downloaded_at and last_accessed."""
        from datetime import UTC, datetime

        from sqlmodel import Session

        from cis_bench.catalog.models import DownloadedBenchmark

        downloader.download_by_id("23598")

        stale_ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        with Session(temp_db.engine) as session:
            row = session.get(DownloadedBenchmark, "23598")
            assert row is not None
            row.downloaded_at = stale_ts
            row.last_accessed = stale_ts
            session.commit()

        downloader.download_by_id("23598", force=True)

        refreshed = temp_db.get_downloaded("23598")
        assert refreshed is not None
        assert "last_accessed" in refreshed
        downloaded_at = refreshed["downloaded_at"]
        last_accessed = refreshed["last_accessed"]
        if downloaded_at.tzinfo is None:
            downloaded_at = downloaded_at.replace(tzinfo=UTC)
        if last_accessed.tzinfo is None:
            last_accessed = last_accessed.replace(tzinfo=UTC)
        assert downloaded_at > stale_ts
        assert last_accessed > stale_ts

    def test_get_downloaded_benchmark_uses_model_validate_json(self, downloader, temp_db):
        """get_downloaded_benchmark validates stored JSON directly via Benchmark.model_validate_json."""
        downloader.download_by_id("23598")
        stored = temp_db.get_downloaded("23598")
        assert stored is not None

        with patch.object(
            Benchmark, "model_validate_json", wraps=Benchmark.model_validate_json
        ) as validate_spy:
            loaded = downloader.get_downloaded_benchmark("23598")

        assert loaded is not None
        assert loaded.benchmark_id == "23598"
        validate_spy.assert_called_once_with(stored["content_json"])


class TestCatalogPackageExportsAndBoundaries:
    """Verify cis_bench.catalog public exports and one-way catalog -> fetcher dependency boundary."""

    def test_fetcher_auth_does_not_load_catalog_and_validates_login_html(self):
        """Importing cis_bench.fetcher.auth in a fresh interpreter does not import cis_bench.catalog."""
        import subprocess
        import sys

        import requests

        from cis_bench.fetcher.auth import AuthManager

        probe = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys, cis_bench.fetcher.auth; "
                    "leaked = sorted(m for m in sys.modules "
                    "if m == 'cis_bench.catalog' or m.startswith('cis_bench.catalog.')); "
                    "assert not leaked, f'fetcher.auth imported catalog modules: {leaked}'"
                ),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert probe.returncode == 0, probe.stderr

        session = create_autospec(requests.Session, instance=True)
        session.cookies = requests.cookies.cookiejar_from_dict({"cis_session": "token"})

        login_resp = Mock(
            status_code=200, headers={}, text='<form action="/login"><input name="login"></form>'
        )
        session.get.return_value = login_resp
        assert AuthManager.validate_session(session) is False

        catalog_resp = Mock(
            status_code=200, headers={}, text="<html><body><table></table></body></html>"
        )
        session.get.return_value = catalog_resp
        assert AuthManager.validate_session(session) is True

    def test_catalog_package_exports_public_api_in_any_import_order(self):
        """cis_bench.catalog exports public classes and helpers cleanly regardless of import order."""
        import subprocess
        import sys

        import cis_bench.catalog as catalog_pkg

        expected_exports = {
            "BenchmarkCollection",
            "BenchmarkStatus",
            "BenchmarkStatusModel",
            "CatalogBenchmark",
            "CatalogDatabase",
            "CatalogDownloader",
            "CatalogScraper",
            "CatalogSearch",
            "Collection",
            "Community",
            "DownloadedBenchmark",
            "Owner",
            "Platform",
            "ScrapeMetadata",
            "WorkBenchCatalogParser",
            "build_fts_query",
            "deserialize_benchmark_json",
            "normalize_status_filter",
            "serialize_benchmark_json",
        }
        assert expected_exports.issubset(set(catalog_pkg.__all__))
        for symbol in expected_exports:
            assert getattr(catalog_pkg, symbol) is not None

        for order_stmt in (
            "import cis_bench.fetcher.auth, cis_bench.catalog",
            "import cis_bench.catalog, cis_bench.fetcher.auth",
        ):
            res = subprocess.run(
                [sys.executable, "-c", order_stmt],
                capture_output=True,
                text=True,
                check=False,
            )
            assert res.returncode == 0, res.stderr
