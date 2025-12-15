"""Markdown exporter for documentation."""

import logging

from cis_bench.models.benchmark import Benchmark
from cis_bench.utils.field_transformers import (
    CISControlFormatter,
    RecommendationFieldTransformer,
    SafeFieldAccessor,
)

from .base import BaseExporter, ExporterFactory

logger = logging.getLogger(__name__)


class MarkdownExporter(BaseExporter):
    """Export benchmark to Markdown format for documentation."""

    def export(self, benchmark: Benchmark, output_path: str) -> str:
        """Export to Markdown with HTML converted to Markdown.

        Args:
            benchmark: Validated Benchmark (Pydantic model)
            output_path: Path to output Markdown file

        Returns:
            Path to created file
        """
        logger.info(f"Exporting benchmark to Markdown: {output_path}")
        logger.debug(
            f"Benchmark: {benchmark.title}, Recommendations: {benchmark.total_recommendations}"
        )

        with open(output_path, "w", encoding="utf-8") as f:
            # Title and metadata
            f.write(f"# {benchmark.title}\n\n")
            f.write(f"**Version:** {benchmark.version}  \n")
            f.write(f"**Benchmark ID:** {benchmark.benchmark_id}  \n")
            f.write(f"**Total Recommendations:** {benchmark.total_recommendations}  \n")
            f.write(f"**Downloaded:** {benchmark.downloaded_at.strftime('%Y-%m-%d %H:%M:%S')}  \n")
            f.write(f"**Source:** {benchmark.url}\n\n")
            f.write("---\n\n")

            # Table of Contents
            f.write("## Table of Contents\n\n")
            for rec in benchmark.recommendations:
                f.write(f"- [{rec.ref} - {rec.title}](#{rec.ref.replace('.', '')})\n")
            f.write("\n---\n\n")

            # Each recommendation
            for rec in benchmark.recommendations:
                anchor = rec.ref.replace(".", "")
                f.write(f"## {rec.ref} - {rec.title} {{#{anchor}}}\n\n")

                # Use DRY helpers
                markdown_fields = RecommendationFieldTransformer.markdown_all(rec)

                # Metadata table
                f.write("| Property | Value |\n")
                f.write("|----------|-------|\n")
                f.write(f"| Assessment | {rec.assessment_status} |\n")
                f.write(
                    f"| Profiles | {SafeFieldAccessor.get_list_as_csv(rec.profiles) or 'None'} |\n"
                )

                # CIS Controls - using DRY helper
                if rec.cis_controls:
                    controls_text = CISControlFormatter.format_all_with_version(rec.cis_controls)
                    f.write(f"| CIS Controls | {controls_text} |\n")

                # MITRE - using DRY helper
                mitre_techniques = SafeFieldAccessor.get_mitre_field(rec, "techniques")
                if mitre_techniques:
                    f.write(f"| MITRE Techniques | {mitre_techniques} |\n")

                # NIST - using DRY helper
                nist_controls = SafeFieldAccessor.get_list_as_csv(rec.nist_controls)
                if nist_controls:
                    f.write(f"| NIST 800-53 | {nist_controls} |\n")

                f.write("\n")

                # Parent - using DRY helper
                parent_link = SafeFieldAccessor.format_parent_link(rec, format="markdown")
                if parent_link:
                    f.write(f"**Parent:** {parent_link}\n\n")

                # Content sections - using DRY helper (already markdown converted)
                if markdown_fields["description"]:
                    f.write("### Description\n\n")
                    f.write(markdown_fields["description"])
                    f.write("\n\n")

                if markdown_fields["rationale"]:
                    f.write("### Rationale\n\n")
                    f.write(markdown_fields["rationale"])
                    f.write("\n\n")

                if markdown_fields["impact"]:
                    f.write("### Impact\n\n")
                    f.write(markdown_fields["impact"])
                    f.write("\n\n")

                if markdown_fields["audit"]:
                    f.write("### Audit Procedure\n\n")
                    f.write(markdown_fields["audit"])
                    f.write("\n\n")

                if markdown_fields["remediation"]:
                    f.write("### Remediation\n\n")
                    f.write(markdown_fields["remediation"])
                    f.write("\n\n")

                if markdown_fields["additional_info"]:
                    f.write("### Additional Information\n\n")
                    f.write(markdown_fields["additional_info"])
                    f.write("\n\n")

                # Artifacts
                if rec.artifacts:
                    f.write("### Artifacts\n\n")
                    for art in rec.artifacts:
                        f.write(f"- **{art.view_level}** ({art.status}): {art.title}\n")
                    f.write("\n")

                f.write("---\n\n")

        logger.info(
            f"Successfully exported Markdown with {len(benchmark.recommendations)} recommendations to {output_path}"
        )
        return output_path

    def get_file_extension(self) -> str:
        return "md"

    def format_name(self) -> str:
        return "Markdown"


# Auto-register
ExporterFactory.register("markdown", MarkdownExporter)
ExporterFactory.register("md", MarkdownExporter)  # Alias
