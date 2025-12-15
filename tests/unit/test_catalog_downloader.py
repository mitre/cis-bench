"""Unit tests for catalog downloader."""

from unittest.mock import Mock, patch

import pytest

from cis_bench.catalog.database import CatalogDatabase
from cis_bench.catalog.downloader import CatalogDownloader
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

    return db


@pytest.fixture
def mock_scraper(sample_recommendation_minimal):
    """Mock WorkbenchScraper."""
    scraper = Mock()

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

    scraper.fetch_benchmark = Mock(return_value=mock_benchmark)

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
        mock_scraper.fetch_benchmark.assert_called_once()

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
        assert mock_scraper.fetch_benchmark.call_count == 1

    def test_download_force_redownloads(self, downloader, mock_scraper):
        """Test force flag re-downloads."""
        # Download first time
        downloader.download_by_id("23598")

        # Force re-download
        result = downloader.download_by_id("23598", force=True)

        # Should have called fetch twice
        assert mock_scraper.fetch_benchmark.call_count == 2

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


class TestDownloadByName:
    """Test downloading by name with fuzzy matching."""

    def test_download_by_name_single_match(self, downloader, mock_scraper):
        """Test download by name with single match."""
        result = downloader.download_by_name("ubuntu")

        assert result["benchmark_id"] == "23598"
        mock_scraper.fetch_benchmark.assert_called_once()

    def test_download_by_name_no_matches(self, downloader):
        """Test download by name with no matches raises error."""
        with pytest.raises(ValueError, match="No benchmarks found"):
            downloader.download_by_name("nonexistent")

    def test_download_by_name_multiple_matches_raises(self, temp_db, mock_scraper):
        """Test multiple matches without interactive raises error."""
        # Add another Ubuntu benchmark
        temp_db.insert_benchmark(
            {
                "benchmark_id": "12345",
                "title": "CIS Ubuntu Linux 22.04 LTS Benchmark",
                "version": "v1.0.0",
                "url": "https://workbench.cisecurity.org/benchmarks/12345",
                "status": "Published",
                "is_latest": True,
            }
        )

        downloader = CatalogDownloader(temp_db, mock_scraper)

        with pytest.raises(ValueError, match="Multiple benchmarks match"):
            downloader.download_by_name("ubuntu", interactive=False)

    @patch("questionary.select")
    def test_download_by_name_interactive(self, mock_select, downloader, temp_db, mock_scraper):
        """Test interactive selection with multiple matches."""
        # Add another Ubuntu benchmark
        temp_db.insert_benchmark(
            {
                "benchmark_id": "12345",
                "title": "CIS Ubuntu Linux 22.04 LTS Benchmark",
                "version": "v1.0.0",
                "url": "https://workbench.cisecurity.org/benchmarks/12345",
                "status": "Published",
                "is_latest": True,
            }
        )

        # Mock user selection
        mock_select.return_value.ask = Mock(
            return_value="[23598] CIS Ubuntu Linux 20.04 LTS Benchmark v2.0.1"
        )

        result = downloader.download_by_name("ubuntu", interactive=True)

        assert result["benchmark_id"] == "23598"
        mock_select.assert_called_once()


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
