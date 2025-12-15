"""JSON exporter - our native canonical format."""

import logging

from cis_bench.models.benchmark import Benchmark

from .base import BaseExporter, ExporterFactory

logger = logging.getLogger(__name__)


class JSONExporter(BaseExporter):
    """Export benchmark to JSON format (our canonical format)."""

    def export(self, benchmark: Benchmark, output_path: str) -> str:
        """Export to JSON with all data preserved.

        Args:
            benchmark: Validated Benchmark (Pydantic model)
            output_path: Path to output JSON file

        Returns:
            Path to created file
        """
        logger.debug(f"Exporting benchmark to JSON: {output_path}")
        logger.debug(
            f"Benchmark: {benchmark.title}, Recommendations: {benchmark.total_recommendations}"
        )

        # Use Pydantic's built-in JSON export
        benchmark.to_json_file(output_path)

        logger.debug(f"Successfully exported JSON to {output_path}")
        return output_path

    def get_file_extension(self) -> str:
        return "json"

    def format_name(self) -> str:
        return "JSON"


# Auto-register with factory
ExporterFactory.register("json", JSONExporter)
