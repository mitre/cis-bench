"""YAML exporter."""

import logging

import yaml

from cis_bench.models.benchmark import Benchmark

from .base import BaseExporter, ExporterFactory

logger = logging.getLogger(__name__)


class YAMLExporter(BaseExporter):
    """Export benchmark to YAML format."""

    def export(self, benchmark: Benchmark, output_path: str) -> str:
        """Export to YAML.

        Args:
            benchmark: Validated Benchmark (Pydantic model)
            output_path: Path to output YAML file

        Returns:
            Path to created file
        """
        logger.info(f"Exporting benchmark to YAML: {output_path}")
        logger.debug(
            f"Benchmark: {benchmark.title}, Recommendations: {benchmark.total_recommendations}"
        )

        # Convert Pydantic model to dict
        data = benchmark.model_dump(mode="python", exclude_none=False)

        # Export to YAML
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

        logger.info(f"Successfully exported YAML to {output_path}")
        return output_path

    def get_file_extension(self) -> str:
        return "yaml"

    def format_name(self) -> str:
        return "YAML"


# Auto-register
ExporterFactory.register("yaml", YAMLExporter)
