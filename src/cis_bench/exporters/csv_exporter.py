"""CSV exporter - flattened tabular format."""

import csv
import logging

from cis_bench.models.benchmark import Benchmark
from cis_bench.utils.field_transformers import (
    CISControlFormatter,
    RecommendationFieldTransformer,
    SafeFieldAccessor,
)

from .base import BaseExporter, ExporterFactory

logger = logging.getLogger(__name__)


class CSVExporter(BaseExporter):
    """Export benchmark to CSV format (flattened, text-only)."""

    def export(self, benchmark: Benchmark, output_path: str) -> str:
        """Export to CSV with flattened structure and HTML stripped.

        Args:
            benchmark: Validated Benchmark (Pydantic model)
            output_path: Path to output CSV file

        Returns:
            Path to created file
        """
        logger.info(f"Exporting benchmark to CSV: {output_path}")
        logger.debug(
            f"Benchmark: {benchmark.title}, Recommendations: {benchmark.total_recommendations}"
        )

        rows = []

        for rec in benchmark.recommendations:
            # Use DRY helpers to eliminate duplication
            html_fields = RecommendationFieldTransformer.strip_all_html(rec)

            # Flatten nested structures
            row = {
                # Benchmark core metadata
                "benchmark_title": benchmark.title,
                "benchmark_id": benchmark.benchmark_id,
                "benchmark_version": benchmark.version,
                "benchmark_published_date": benchmark.published_date,
                "benchmark_release_type": benchmark.release_type,
                # Benchmark attribution
                "benchmark_contributors": (
                    ", ".join(benchmark.contributors) if benchmark.contributors else None
                ),
                # Benchmark lineage
                "benchmark_parent_url": str(benchmark.parent_benchmark_url)
                if benchmark.parent_benchmark_url
                else None,
                "benchmark_parent_title": benchmark.parent_benchmark_title,
                # Benchmark assets (CPE-IDs)
                "benchmark_cpe_ids": (
                    ", ".join([a.cpe_id for a in benchmark.assets]) if benchmark.assets else None
                ),
                # Recommendation core
                "ref": rec.ref,
                "title": rec.title,
                "url": str(rec.url),
                "assessment_status": rec.assessment_status,
                # Lists using DRY helpers
                "profiles": SafeFieldAccessor.get_list_as_csv(rec.profiles),
                "nist_controls": SafeFieldAccessor.get_list_as_csv(rec.nist_controls),
                # CIS Controls using DRY helper
                "cis_controls_v8": CISControlFormatter.filter_by_version(rec.cis_controls, 8),
                "cis_controls_v7": CISControlFormatter.filter_by_version(rec.cis_controls, 7),
                # MITRE using DRY helper
                "mitre_techniques": SafeFieldAccessor.get_mitre_field(rec, "techniques"),
                "mitre_tactics": SafeFieldAccessor.get_mitre_field(rec, "tactics"),
                "mitre_mitigations": SafeFieldAccessor.get_mitre_field(rec, "mitigations"),
                # Parent using DRY helper
                "parent": SafeFieldAccessor.get_parent_title(rec),
                # Content (HTML stripped) - using DRY helper
                "description": html_fields["description"],
                "rationale": html_fields["rationale"],
                "impact": html_fields["impact"],
                "audit": html_fields["audit"],
                "remediation": html_fields["remediation"],
                "additional_info": html_fields["additional_info"],
                "default_value": html_fields["default_value"],
                # Artifacts count
                "artifacts_count": len(rec.artifacts) if rec.artifacts else 0,
            }

            rows.append(row)

        # Write CSV
        if rows:
            logger.debug(f"Writing {len(rows)} rows to CSV")
            fieldnames = rows[0].keys()

            with open(output_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

            logger.info(f"Successfully exported CSV with {len(rows)} rows to {output_path}")
        else:
            logger.warning("No recommendations to export - writing empty CSV")

        return output_path

    def get_file_extension(self) -> str:
        return "csv"

    def format_name(self) -> str:
        return "CSV"


# Auto-register
ExporterFactory.register("csv", CSVExporter)
