"""Export service - coordinates export operations for benchmarks and diffs.

This service provides a unified interface for exporting:
- Single benchmarks to various formats
- Diff comparisons to supported formats
- Batch exports of multiple benchmarks

It wraps the existing exporter infrastructure and adds:
- Path generation with customizable patterns
- Progress callbacks for batch operations
- Context-aware format availability
"""

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

# Format availability by export context
FORMATS_BY_CONTEXT = {
    "single": ["json", "yaml", "csv", "markdown", "xccdf"],
    "diff": ["json", "markdown", "csv"],  # XCCDF doesn't make sense for diffs
    "batch": ["json", "yaml", "csv", "markdown", "xccdf"],
}


@dataclass
class ExportConfig:
    """Configuration for an export operation.

    Attributes:
        format: Export format (json, yaml, csv, markdown, xccdf)
        output_dir: Directory to write output files
        style: XCCDF style (disa or cis) - only used for xccdf format
        filename_pattern: Pattern for generating filenames
            Placeholders: {id}, {title}, {version}
            Default: "{id}_{title}"
        overwrite: Whether to overwrite existing files
    """

    format: str
    output_dir: Path | None = None
    style: str | None = None
    filename_pattern: str | None = None
    overwrite: bool = True


@dataclass
class ExportResult:
    """Result of an export operation.

    Attributes:
        success: Whether export succeeded
        path: Path to created file (if success)
        benchmark_id: ID of exported benchmark
        error: Error message (if failed)
    """

    success: bool
    benchmark_id: str = ""
    path: Path | None = None
    error: str | None = None


class ExportService:
    """Coordinates export operations for benchmarks and diffs.

    Usage:
        service = ExportService()
        config = ExportConfig(format="json", output_dir=Path("/tmp"))

        # Single export
        result = service.export_single(benchmark, config)

        # Batch export with progress
        results = service.export_batch(
            benchmarks,
            config,
            progress_callback=lambda cur, tot, id: print(f"{cur}/{tot}")
        )

        # Diff export
        result = service.export_diff(comparison, config)
    """

    def __init__(self):
        """Initialize export service."""
        # Ensure exporters are registered
        self._ensure_exporters_loaded()

    def _ensure_exporters_loaded(self) -> None:
        """Ensure all exporters are imported and registered."""
        # Import to trigger registration
        try:
            import cis_bench.exporters.csv_exporter  # noqa: F401
            import cis_bench.exporters.json_exporter  # noqa: F401
            import cis_bench.exporters.markdown_exporter  # noqa: F401
            import cis_bench.exporters.xccdf_unified_exporter  # noqa: F401
            import cis_bench.exporters.yaml_exporter  # noqa: F401
        except ImportError as e:
            logger.warning(f"Could not import some exporters: {e}")

    def get_available_formats(
        self, context: Literal["single", "diff", "batch"] = "single"
    ) -> list[str]:
        """Get available export formats for a given context.

        Args:
            context: Export context - single, diff, or batch

        Returns:
            List of available format identifiers
        """
        return FORMATS_BY_CONTEXT.get(context, FORMATS_BY_CONTEXT["single"])

    def export_single(
        self,
        benchmark: dict,
        config: ExportConfig,
    ) -> ExportResult:
        """Export a single benchmark.

        Args:
            benchmark: Benchmark data dict
            config: Export configuration

        Returns:
            ExportResult with success status and path
        """
        benchmark_id = str(benchmark.get("benchmark_id", "unknown"))

        try:
            # Generate output path
            output_path = self._get_output_path(benchmark, config)

            # Get appropriate exporter
            if config.format == "xccdf":
                result_path = self._export_xccdf(benchmark, output_path, config.style)
            elif config.format == "json":
                result_path = self._export_json(benchmark, output_path)
            elif config.format == "yaml":
                result_path = self._export_yaml(benchmark, output_path)
            elif config.format == "csv":
                result_path = self._export_csv(benchmark, output_path)
            elif config.format == "markdown":
                result_path = self._export_markdown(benchmark, output_path)
            else:
                return ExportResult(
                    success=False,
                    benchmark_id=benchmark_id,
                    error=f"Unsupported format: {config.format}",
                )

            return ExportResult(
                success=True,
                benchmark_id=benchmark_id,
                path=Path(result_path),
            )

        except Exception as e:
            logger.error(f"Export failed for {benchmark_id}: {e}")
            return ExportResult(
                success=False,
                benchmark_id=benchmark_id,
                error=str(e),
            )

    def export_batch(
        self,
        benchmarks: list[dict],
        config: ExportConfig,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> list[ExportResult]:
        """Export multiple benchmarks.

        Args:
            benchmarks: List of benchmark data dicts
            config: Export configuration
            progress_callback: Optional callback(current, total, benchmark_id)

        Returns:
            List of ExportResults, one per benchmark
        """
        results = []
        total = len(benchmarks)

        for i, benchmark in enumerate(benchmarks, 1):
            benchmark_id = str(benchmark.get("benchmark_id", "unknown"))

            if progress_callback:
                progress_callback(i, total, benchmark_id)

            result = self.export_single(benchmark, config)
            results.append(result)

        return results

    def export_diff(
        self,
        comparison: dict,
        config: ExportConfig,
    ) -> ExportResult:
        """Export a diff comparison.

        Args:
            comparison: Comparison data from compare_benchmarks()
            config: Export configuration

        Returns:
            ExportResult with success status and path
        """
        try:
            # Generate filename for diff
            old_ver = comparison.get("old_version", "unknown")
            new_ver = comparison.get("new_version", "unknown")
            title = comparison.get("benchmark_title", "comparison")

            safe_title = self._sanitize_filename(title)
            filename = f"diff_{safe_title}_{old_ver}_to_{new_ver}"

            output_dir = config.output_dir or Path.cwd()
            output_dir.mkdir(parents=True, exist_ok=True)

            if config.format == "json":
                output_path = output_dir / f"{filename}.json"
                self._export_diff_json(comparison, output_path)
            elif config.format == "markdown":
                output_path = output_dir / f"{filename}.md"
                self._export_diff_markdown(comparison, output_path)
            elif config.format == "csv":
                output_path = output_dir / f"{filename}.csv"
                self._export_diff_csv(comparison, output_path)
            else:
                return ExportResult(
                    success=False,
                    error=f"Unsupported diff format: {config.format}",
                )

            return ExportResult(
                success=True,
                path=output_path,
            )

        except Exception as e:
            logger.error(f"Diff export failed: {e}")
            return ExportResult(
                success=False,
                error=str(e),
            )

    def _get_output_path(self, benchmark: dict, config: ExportConfig) -> Path:
        """Generate output path for a benchmark export."""
        benchmark_id = str(benchmark.get("benchmark_id", "unknown"))
        title = benchmark.get("title", "benchmark")
        version = benchmark.get("version", "")

        # Get extension for format
        extension = self._get_extension(config.format)

        # Generate filename
        filename = self._generate_filename(
            benchmark_id=benchmark_id,
            title=title,
            version=version,
            extension=extension,
            pattern=config.filename_pattern,
        )

        # Combine with output directory
        output_dir = config.output_dir or Path.cwd()
        output_dir.mkdir(parents=True, exist_ok=True)

        return output_dir / filename

    def _generate_filename(
        self,
        benchmark_id: str,
        title: str,
        version: str,
        extension: str,
        pattern: str | None = None,
    ) -> str:
        """Generate a filename from benchmark metadata.

        Args:
            benchmark_id: Benchmark ID
            title: Benchmark title
            version: Benchmark version
            extension: File extension (without dot)
            pattern: Optional pattern with placeholders

        Returns:
            Safe filename string
        """
        safe_title = self._sanitize_filename(title)
        safe_version = self._sanitize_filename(version)

        if pattern:
            filename = pattern.format(
                id=benchmark_id,
                title=safe_title,
                version=safe_version,
            )
        else:
            # Default pattern
            filename = f"{benchmark_id}_{safe_title}"

        return f"{filename}.{extension}"

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize a string for use in filenames."""
        # Remove or replace unsafe characters
        safe = re.sub(r'[<>:"/\\|?*]', "_", name)
        # Collapse multiple underscores/spaces
        safe = re.sub(r"[\s_]+", "_", safe)
        # Remove leading/trailing underscores
        safe = safe.strip("_")
        # Truncate if too long
        return safe[:100] if len(safe) > 100 else safe

    def _get_extension(self, format_type: str) -> str:
        """Get file extension for a format."""
        extensions = {
            "json": "json",
            "yaml": "yaml",
            "csv": "csv",
            "markdown": "md",
            "xccdf": "xml",
        }
        return extensions.get(format_type, "txt")

    # --- Individual export methods ---

    def _export_json(self, benchmark: dict, output_path: Path) -> str:
        """Export benchmark as JSON."""
        with open(output_path, "w") as f:
            json.dump(benchmark, f, indent=2, default=str)
        return str(output_path)

    def _export_yaml(self, benchmark: dict, output_path: Path) -> str:
        """Export benchmark as YAML."""
        import yaml

        with open(output_path, "w") as f:
            yaml.dump(benchmark, f, default_flow_style=False, allow_unicode=True)
        return str(output_path)

    def _export_csv(self, benchmark: dict, output_path: Path) -> str:
        """Export benchmark recommendations as CSV."""
        import csv

        recommendations = benchmark.get("recommendations", [])

        with open(output_path, "w", newline="") as f:
            if recommendations:
                writer = csv.DictWriter(f, fieldnames=recommendations[0].keys())
                writer.writeheader()
                writer.writerows(recommendations)
            else:
                f.write("# No recommendations\n")

        return str(output_path)

    def _export_markdown(self, benchmark: dict, output_path: Path) -> str:
        """Export benchmark as Markdown."""
        lines = [
            f"# {benchmark.get('title', 'Benchmark')}",
            "",
            f"**Version:** {benchmark.get('version', 'N/A')}",
            f"**ID:** {benchmark.get('benchmark_id', 'N/A')}",
            "",
            "## Recommendations",
            "",
        ]

        for rec in benchmark.get("recommendations", []):
            lines.append(f"### {rec.get('ref', '')} - {rec.get('title', '')}")
            lines.append("")
            if rec.get("description"):
                lines.append(rec["description"])
                lines.append("")

        with open(output_path, "w") as f:
            f.write("\n".join(lines))

        return str(output_path)

    def _export_xccdf(self, benchmark: dict, output_path: Path, style: str | None) -> str:
        """Export benchmark as XCCDF using unified exporter."""
        from cis_bench.exporters.base import ExporterFactory
        from cis_bench.models.benchmark import Benchmark

        # Convert dict to Pydantic model
        benchmark_model = Benchmark(**benchmark)

        # Create exporter with style
        exporter = ExporterFactory.create("xccdf", style=style or "cis")

        return exporter.export(benchmark_model, str(output_path))

    # --- Diff export methods ---

    def _export_diff_json(self, comparison: dict, output_path: Path) -> None:
        """Export diff as JSON."""
        # Remove unchanged to reduce size
        output = {**comparison}
        if "changes" in output:
            output["changes"] = {k: v for k, v in comparison["changes"].items() if k != "unchanged"}

        with open(output_path, "w") as f:
            json.dump(output, f, indent=2, default=str)

    def _export_diff_markdown(self, comparison: dict, output_path: Path) -> None:
        """Export diff as Markdown."""
        summary = comparison.get("summary", {})
        changes = comparison.get("changes", {})

        lines = [
            "# Benchmark Comparison",
            "",
            f"**{comparison.get('benchmark_title', 'Benchmark')}**: "
            f"{comparison.get('old_version', '?')} → {comparison.get('new_version', '?')}",
            "",
            "## Summary",
            "",
            f"- **Added:** {summary.get('added', 0)}",
            f"- **Removed:** {summary.get('removed', 0)}",
            f"- **Modified:** {summary.get('modified', 0)}",
            f"- **Unchanged:** {summary.get('unchanged', 0)}",
            "",
        ]

        if changes.get("added"):
            lines.append("## Added")
            lines.append("")
            for item in changes["added"]:
                lines.append(f"- **{item.get('ref', '')}**: {item.get('title', '')}")
            lines.append("")

        if changes.get("removed"):
            lines.append("## Removed")
            lines.append("")
            for item in changes["removed"]:
                lines.append(f"- **{item.get('ref', '')}**: {item.get('title', '')}")
            lines.append("")

        if changes.get("modified"):
            lines.append("## Modified")
            lines.append("")
            for item in changes["modified"]:
                lines.append(f"- **{item.get('ref', '')}**: {item.get('title', '')}")
            lines.append("")

        with open(output_path, "w") as f:
            f.write("\n".join(lines))

    def _export_diff_csv(self, comparison: dict, output_path: Path) -> None:
        """Export diff as CSV."""
        import csv

        changes = comparison.get("changes", {})
        rows = []

        for change_type in ["added", "removed", "modified", "renumbered"]:
            for item in changes.get(change_type, []):
                rows.append(
                    {
                        "change_type": change_type,
                        "ref": item.get("ref", item.get("new_ref", "")),
                        "title": item.get("title", ""),
                    }
                )

        with open(output_path, "w", newline="") as f:
            if rows:
                writer = csv.DictWriter(f, fieldnames=["change_type", "ref", "title"])
                writer.writeheader()
                writer.writerows(rows)
            else:
                f.write("change_type,ref,title\n")
