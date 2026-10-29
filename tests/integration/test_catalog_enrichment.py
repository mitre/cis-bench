"""Integration tests for catalog enrichment after benchmark download.

Tests that downloading a benchmark enriches the catalog entry with metadata
from the detail page and populates related tables (assets, revision_history).
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlmodel import Session, select

from cis_bench.catalog.database import CatalogDatabase
from cis_bench.catalog.downloader import CatalogDownloader
from cis_bench.catalog.models import BenchmarkAsset, RevisionHistory
from cis_bench.fetcher.workbench import WorkbenchScraper


@pytest.fixture
def temp_catalog():
    """Create temporary catalog database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = CatalogDatabase(db_path)
        db.initialize_schema()

        # Insert a test benchmark (minimal data from catalog scraping)
        db.insert_benchmark(
            {
                "benchmark_id": "18208",
                "title": "CIS AlmaLinux OS 9 Benchmark v2.0.0",
                "version": "v2.0.0",
                "url": "https://workbench.cisecurity.org/benchmarks/18208",
                "status": "Published",
            }
        )

        yield db


@pytest.fixture
def mock_scraper():
    """Create mock scraper that returns a Benchmark with extended metadata."""
    scraper = Mock(spec=WorkbenchScraper)

    def mock_fetch_benchmark(url):
        """Return a mock Benchmark with full metadata."""
        from cis_bench.models.benchmark import Benchmark, BenchmarkAsset, RevisionHistoryEntry

        return Benchmark(
            title="CIS AlmaLinux OS 9 Benchmark v2.0.0",
            benchmark_id="18208",
            url=url,
            version="v2.0.0",
            # Extended metadata
            published_date="Jun 24th 2024",
            published_relative="1 year ago on Jun 24th 2024",
            description="Security guidance for AlmaLinux 9 systems.",
            release_type="Planned Update",
            contributors=["Eric Pinnell", "Thomas Sjögren", "James Trigg"],
            parent_benchmark_url="https://workbench.cisecurity.org/benchmarks/16763",
            parent_benchmark_title="CIS Fedora 34 Benchmark",
            community_url="https://workbench.cisecurity.org/communities/139",
            milestone_name="CIS AlmaLinux 9 v2.0.0",
            milestone_url="https://workbench.cisecurity.org/community/139/milestones/956",
            intended_audience="System administrators and security specialists.",
            acknowledgements="Thanks to all Linux benchmark contributors.",
            assets=[
                BenchmarkAsset(
                    title="AlmaLinux OS 9", cpe_id="cpe:2.3:o:almalinux:almalinux:9:*:*:*:*:*:*:*"
                )
            ],
            revision_history=[
                RevisionHistoryEntry(
                    revision_date="1 year ago", author="Eric", modification_count=5, diff_url=None
                )
            ],
            scraper_version="v1_test",
            total_recommendations=0,
            recommendations=[],
        )

    scraper.fetch_benchmark = mock_fetch_benchmark
    return scraper


class TestCatalogEnrichment:
    """Test catalog enrichment after benchmark download."""

    def test_download_enriches_catalog_entry(self, temp_catalog, mock_scraper):
        """Test that downloading updates catalog entry with extended metadata."""
        downloader = CatalogDownloader(temp_catalog, mock_scraper)

        # Before download - catalog has minimal data
        before = temp_catalog.get_benchmark("18208")
        assert before["release_type"] is None
        assert before["contributors"] is None
        assert before["parent_benchmark_url"] is None

        # Download
        result = downloader.download_by_id("18208")

        # After download - catalog enriched
        after = temp_catalog.get_benchmark("18208")
        assert after["published_date"] == "Jun 24th 2024"
        assert after["release_type"] == "Planned Update"
        assert "Eric Pinnell" in after["contributors"]
        assert after["parent_benchmark_url"] == "https://workbench.cisecurity.org/benchmarks/16763"
        assert after["parent_benchmark_id"] == "16763"
        assert "System administrators" in after["intended_audience"]
        assert after["milestone_name"] == "CIS AlmaLinux 9 v2.0.0"

    def test_download_populates_assets_table(self, temp_catalog, mock_scraper):
        """Test that downloading populates benchmark_assets table."""
        downloader = CatalogDownloader(temp_catalog, mock_scraper)

        # Download
        downloader.download_by_id("18208")

        # Verify assets table populated
        with Session(temp_catalog.engine) as session:
            assets = session.exec(
                select(BenchmarkAsset).where(BenchmarkAsset.benchmark_id == "18208")
            ).all()

            assert len(assets) == 1
            assert assets[0].title == "AlmaLinux OS 9"
            assert assets[0].cpe_id == "cpe:2.3:o:almalinux:almalinux:9:*:*:*:*:*:*:*"

    def test_download_populates_revision_history_table(self, temp_catalog, mock_scraper):
        """Test that downloading populates revision_history table."""
        downloader = CatalogDownloader(temp_catalog, mock_scraper)

        # Download
        downloader.download_by_id("18208")

        # Verify revision_history table populated
        with Session(temp_catalog.engine) as session:
            revisions = session.exec(
                select(RevisionHistory).where(RevisionHistory.benchmark_id == "18208")
            ).all()

            assert len(revisions) == 1
            assert revisions[0].revision_date == "1 year ago"
            assert revisions[0].author == "Eric"
            assert revisions[0].modification_count == 5

    def test_re_download_updates_enrichment(self, temp_catalog, mock_scraper):
        """Test that re-downloading updates the enrichment data."""
        downloader = CatalogDownloader(temp_catalog, mock_scraper)

        # First download
        downloader.download_by_id("18208", force=True)

        # Modify the mock to return different data
        def new_mock_fetch(url):
            from cis_bench.models.benchmark import Benchmark

            return Benchmark(
                title="CIS AlmaLinux OS 9 Benchmark v2.0.0",
                benchmark_id="18208",
                url=url,
                version="v2.0.0",
                release_type="Major Update",  # Changed
                contributors=["New Contributor"],  # Changed
                assets=[],  # Cleared
                revision_history=[],  # Cleared
                scraper_version="v1_test",
                total_recommendations=0,
                recommendations=[],
            )

        mock_scraper.fetch_benchmark = new_mock_fetch

        # Second download
        downloader.download_by_id("18208", force=True)

        # Verify catalog updated
        after = temp_catalog.get_benchmark("18208")
        assert after["release_type"] == "Major Update"
        assert after["contributors"] == "New Contributor"

        # Verify assets cleared
        with Session(temp_catalog.engine) as session:
            assets = session.exec(
                select(BenchmarkAsset).where(BenchmarkAsset.benchmark_id == "18208")
            ).all()
            assert len(assets) == 0
