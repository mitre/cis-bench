"""Tests for shared catalog enrichment service."""

import tempfile
from pathlib import Path

import pytest
from sqlmodel import Session, select

from cis_bench.catalog.database import CatalogDatabase
from cis_bench.catalog.enrichment import EnrichmentService
from cis_bench.catalog.models import BenchmarkAsset, RevisionHistory
from cis_bench.models.benchmark import Benchmark, RevisionHistoryEntry
from cis_bench.models.benchmark import BenchmarkAsset as PydanticAsset


@pytest.fixture
def temp_catalog_with_benchmark():
    """Create catalog with a test benchmark."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = CatalogDatabase(db_path)
        db.initialize_schema()

        # Insert minimal benchmark (like from catalog scraping)
        db.insert_benchmark(
            {
                "benchmark_id": "18208",
                "title": "Test Benchmark",
                "version": "v1.0.0",
                "url": "https://workbench.cisecurity.org/benchmarks/18208",
                "status": "Published",
            }
        )

        yield db


class TestEnrichmentService:
    """Test shared enrichment service (DRY)."""

    def test_enrich_updates_catalog_entry(self, temp_catalog_with_benchmark):
        """Test enrichment updates catalog_benchmarks fields."""
        db = temp_catalog_with_benchmark

        # Create Benchmark with extended metadata
        benchmark = Benchmark(
            title="Test Benchmark",
            benchmark_id="18208",
            url="https://workbench.cisecurity.org/benchmarks/18208",
            version="v1.0.0",
            published_date="Jun 24th 2024",
            release_type="Planned Update",
            contributors=["Alice", "Bob"],
            scraper_version="v1_test",
            total_recommendations=0,
            recommendations=[],
        )

        # Before enrichment
        before = db.get_benchmark("18208")
        assert before["release_type"] is None
        assert before["contributors"] is None

        # Enrich
        result = EnrichmentService.enrich_catalog_entry("18208", benchmark, db.engine)

        assert result is True

        # After enrichment
        after = db.get_benchmark("18208")
        assert after["published_date"] == "Jun 24th 2024"
        assert after["release_type"] == "Planned Update"
        assert "Alice" in after["contributors"]

    def test_enrich_populates_assets_table(self, temp_catalog_with_benchmark):
        """Test enrichment populates benchmark_assets table."""
        db = temp_catalog_with_benchmark

        benchmark = Benchmark(
            title="Test",
            benchmark_id="18208",
            url="https://workbench.cisecurity.org/benchmarks/18208",
            version="v1.0.0",
            assets=[PydanticAsset(title="Test OS", cpe_id="cpe:2.3:o:test:test:1:*:*:*:*:*:*:*")],
            scraper_version="v1_test",
            total_recommendations=0,
            recommendations=[],
        )

        EnrichmentService.enrich_catalog_entry("18208", benchmark, db.engine)

        # Verify assets table populated
        with Session(db.engine) as session:
            assets = session.exec(
                select(BenchmarkAsset).where(BenchmarkAsset.benchmark_id == "18208")
            ).all()
            assert len(assets) == 1
            assert assets[0].cpe_id == "cpe:2.3:o:test:test:1:*:*:*:*:*:*:*"

    def test_enrich_populates_revision_history(self, temp_catalog_with_benchmark):
        """Test enrichment populates revision_history table."""
        db = temp_catalog_with_benchmark

        benchmark = Benchmark(
            title="Test",
            benchmark_id="18208",
            url="https://workbench.cisecurity.org/benchmarks/18208",
            version="v1.0.0",
            revision_history=[
                RevisionHistoryEntry(
                    revision_date="1 year ago", author="Alice", modification_count=5
                )
            ],
            scraper_version="v1_test",
            total_recommendations=0,
            recommendations=[],
        )

        EnrichmentService.enrich_catalog_entry("18208", benchmark, db.engine)

        # Verify revision history table populated
        with Session(db.engine) as session:
            revisions = session.exec(
                select(RevisionHistory).where(RevisionHistory.benchmark_id == "18208")
            ).all()
            assert len(revisions) == 1
            assert revisions[0].author == "Alice"

    def test_enrich_handles_missing_catalog_entry(self, temp_catalog_with_benchmark):
        """Test enrichment gracefully handles missing catalog entry."""
        db = temp_catalog_with_benchmark

        benchmark = Benchmark(
            title="Test",
            benchmark_id="99999",  # Doesn't exist in catalog
            url="https://workbench.cisecurity.org/benchmarks/99999",
            version="v1.0.0",
            scraper_version="v1_test",
            total_recommendations=0,
            recommendations=[],
        )

        # Should return False but not crash
        result = EnrichmentService.enrich_catalog_entry("99999", benchmark, db.engine)

        assert result is False

    def test_enrich_clears_old_data_on_update(self, temp_catalog_with_benchmark):
        """Test enrichment clears old assets/revisions when updating."""
        db = temp_catalog_with_benchmark

        # First enrichment with data
        benchmark1 = Benchmark(
            title="Test",
            benchmark_id="18208",
            url="https://workbench.cisecurity.org/benchmarks/18208",
            version="v1.0.0",
            assets=[PydanticAsset(title="Asset1", cpe_id="cpe:2.3:o:test:1:*:*:*:*:*:*:*:*")],
            scraper_version="v1_test",
            total_recommendations=0,
            recommendations=[],
        )
        EnrichmentService.enrich_catalog_entry("18208", benchmark1, db.engine)

        # Second enrichment with empty assets (should clear)
        benchmark2 = Benchmark(
            title="Test",
            benchmark_id="18208",
            url="https://workbench.cisecurity.org/benchmarks/18208",
            version="v1.0.0",
            assets=[],  # Empty - should clear old assets
            scraper_version="v1_test",
            total_recommendations=0,
            recommendations=[],
        )
        EnrichmentService.enrich_catalog_entry("18208", benchmark2, db.engine)

        # Verify assets cleared
        with Session(db.engine) as session:
            assets = session.exec(
                select(BenchmarkAsset).where(BenchmarkAsset.benchmark_id == "18208")
            ).all()
            assert len(assets) == 0
