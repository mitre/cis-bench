"""CSV exporter - flattened tabular format."""

import csv
import logging
from gettext import ngettext

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
        """Export to CSV with a flattened structure; text fields are written as stored.

        Args:
            benchmark: Validated Benchmark (Pydantic model)
            output_path: Path to output CSV file

        Returns:
            Path to created file
        """
        logger.debug(f"Exporting benchmark to CSV: {output_path}")
        logger.debug(
            f"Benchmark: {benchmark.title}, Recommendations: {benchmark.total_recommendations}"
        )

        rows = []

        for rec in benchmark.recommendations:
            # The text fields as stored (Markdown; a placeholder such as <user> is text)
            text_fields = RecommendationFieldTransformer.stored_text(rec)

            # Flatten nested structures
            row = {
                # Benchmark metadata
                "benchmark_title": benchmark.title,
                "benchmark_id": benchmark.benchmark_id,
                "benchmark_version": benchmark.version,
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
                # Content, as stored
                "description": text_fields["description"],
                "rationale": text_fields["rationale"],
                "impact": text_fields["impact"],
                "audit": text_fields["audit"],
                "remediation": text_fields["remediation"],
                "additional_info": text_fields["additional_info"],
                "default_value": text_fields["default_value"],
                # Artifacts count
                "artifacts_count": len(rec.artifacts) if rec.artifacts else 0,
            }

            rows.append(row)

        # Write CSV
        if rows:
            logger.debug(
                ngettext(
                    "Writing {count} row to CSV", "Writing {count} rows to CSV", len(rows)
                ).format(count=len(rows))
            )
            fieldnames = rows[0].keys()

            with open(output_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

            logger.debug(
                ngettext(
                    "Successfully exported CSV with {count} row to {path}",
                    "Successfully exported CSV with {count} rows to {path}",
                    len(rows),
                ).format(count=len(rows), path=output_path)
            )
        else:
            logger.warning("No recommendations to export - writing empty CSV")

        return output_path

    def get_file_extension(self) -> str:
        return "csv"

    def format_name(self) -> str:
        return "CSV"


# Auto-register
ExporterFactory.register("csv", CSVExporter)
