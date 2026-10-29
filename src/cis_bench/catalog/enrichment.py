"""Catalog enrichment service.

Shared service for enriching catalog database with metadata from downloaded benchmarks.
Used by both direct download and catalog download commands (DRY principle).
"""

import logging
import re

from sqlmodel import Session

from cis_bench.catalog.models import BenchmarkAsset, CatalogBenchmark, RevisionHistory
from cis_bench.models.benchmark import Benchmark

logger = logging.getLogger(__name__)


class EnrichmentService:
    """Service for enriching catalog with benchmark metadata."""

    @staticmethod
    def enrich_catalog_entry(benchmark_id: str, benchmark: Benchmark, db_engine) -> bool:
        """Enrich catalog entry with metadata from downloaded benchmark.

        Updates the catalog_benchmarks entry with metadata extracted from
        the benchmark detail page and populates related tables (assets, revision_history).

        This is called by BOTH:
        - cis-bench download (if catalog exists)
        - cis-bench catalog download (always)

        Args:
            benchmark_id: Benchmark ID
            benchmark: Downloaded Benchmark object with full metadata
            db_engine: SQLAlchemy engine for catalog database

        Returns:
            True if enrichment succeeded, False otherwise
        """
        try:
            with Session(db_engine) as session:
                # Get catalog entry
                catalog_benchmark = session.get(CatalogBenchmark, benchmark_id)
                if not catalog_benchmark:
                    logger.debug(f"Catalog entry not found for {benchmark_id}, skipping enrichment")
                    return False

                # Update catalog entry with metadata from Benchmark object
                if benchmark.published_date:
                    catalog_benchmark.published_date = benchmark.published_date
                if benchmark.description:
                    catalog_benchmark.description = benchmark.description
                if benchmark.release_type:
                    catalog_benchmark.release_type = benchmark.release_type
                if benchmark.contributors:
                    # Convert list to comma-separated string for DB
                    catalog_benchmark.contributors = ", ".join(benchmark.contributors)
                if benchmark.parent_benchmark_url:
                    catalog_benchmark.parent_benchmark_url = str(benchmark.parent_benchmark_url)
                    # Extract parent_benchmark_id from URL
                    match = re.search(r"/benchmarks/(\d+)", str(benchmark.parent_benchmark_url))
                    if match:
                        catalog_benchmark.parent_benchmark_id = match.group(1)
                if benchmark.intended_audience:
                    catalog_benchmark.intended_audience = benchmark.intended_audience
                if benchmark.acknowledgements:
                    catalog_benchmark.acknowledgements = benchmark.acknowledgements
                if benchmark.milestone_name:
                    catalog_benchmark.milestone_name = benchmark.milestone_name
                if benchmark.milestone_url:
                    catalog_benchmark.milestone_url = str(benchmark.milestone_url)
                if benchmark.community_url:
                    # Update community if we got a URL and the community exists
                    match = re.search(r"/communities/(\d+)", str(benchmark.community_url))
                    if match and catalog_benchmark.community:
                        catalog_benchmark.community.url = str(benchmark.community_url)

                # Clear and insert assets (always clear, even if empty list)
                from sqlalchemy import text

                session.execute(
                    text("DELETE FROM benchmark_assets WHERE benchmark_id = :bid"),
                    {"bid": benchmark_id},
                )
                for asset_data in benchmark.assets:
                    asset = BenchmarkAsset(
                        benchmark_id=benchmark_id,
                        title=asset_data.title,
                        cpe_id=asset_data.cpe_id,
                    )
                    session.add(asset)

                # Clear and insert revision history (always clear, even if empty list)
                session.execute(
                    text("DELETE FROM revision_history WHERE benchmark_id = :bid"),
                    {"bid": benchmark_id},
                )
                for idx, rev_data in enumerate(benchmark.revision_history):
                    revision = RevisionHistory(
                        benchmark_id=benchmark_id,
                        revision_date=rev_data.revision_date,
                        author=rev_data.author,
                        modification_count=rev_data.modification_count,
                        diff_url=rev_data.diff_url,
                        sort_order=idx,
                    )
                    session.add(revision)

                session.commit()
                logger.info(f"Catalog entry enriched for {benchmark_id}")
                return True

        except Exception as e:
            logger.error(f"Enrichment failed for {benchmark_id}: {e}", exc_info=True)
            return False
