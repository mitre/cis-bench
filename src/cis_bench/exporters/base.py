"""Base exporter classes and factory pattern."""

import logging
from abc import ABC, abstractmethod

from cis_bench.models.benchmark import Benchmark

logger = logging.getLogger(__name__)


class BaseExporter(ABC):
    """Abstract base class for all exporters.

    All exporters must implement this interface. Exporters convert
    from our canonical Pydantic Benchmark model to various output formats.
    """

    @abstractmethod
    def export(self, benchmark: Benchmark, output_path: str) -> str:
        """Export benchmark to file.

        Args:
            benchmark: Validated Benchmark instance (Pydantic model)
            output_path: Path to output file

        Returns:
            Path to created file

        Raises:
            IOError: If file cannot be written
            ValueError: If benchmark data is invalid
        """
        pass

    @abstractmethod
    def get_file_extension(self) -> str:
        """Get default file extension for this format.

        Returns:
            File extension without dot (e.g., 'xml', 'yaml', 'csv')
        """
        pass

    @abstractmethod
    def format_name(self) -> str:
        """Get human-readable format name.

        Returns:
            Format name (e.g., 'XCCDF', 'YAML', 'CSV')
        """
        pass


class ExporterFactory:
    """Factory for creating exporters with registration pattern.

    Exporters self-register by calling ExporterFactory.register()
    at module import time. This allows dynamic discovery of formats.
    """

    _exporters: dict[str, type[BaseExporter]] = {}

    @classmethod
    def register(cls, format_type: str, exporter_class: type[BaseExporter]):
        """Register an exporter for a format.

        Args:
            format_type: Format identifier (e.g., 'xccdf', 'yaml')
            exporter_class: Exporter class (not instance)

        Example:
            ExporterFactory.register('xccdf', XCCDFExporter)
        """
        logger.debug(f"Registering exporter: {format_type} -> {exporter_class.__name__}")
        cls._exporters[format_type.lower()] = exporter_class

    @classmethod
    def create(cls, format_type: str, **kwargs) -> BaseExporter:
        """Create an exporter instance for the given format.

        Args:
            format_type: Format identifier (case-insensitive)
            **kwargs: Additional parameters to pass to exporter constructor
                     (e.g., style="disa" for XCCDF exporter)

        Returns:
            Exporter instance

        Raises:
            ValueError: If format is not supported

        Example:
            >>> exporter = ExporterFactory.create("xccdf", style="disa")
            >>> exporter = ExporterFactory.create("csv")
        """
        format_type = format_type.lower()
        logger.debug(f"Creating exporter for format: {format_type}, kwargs: {kwargs}")

        if format_type not in cls._exporters:
            available = ", ".join(sorted(cls.available_formats()))
            logger.error(f"Unsupported export format: '{format_type}'. Available: {available}")
            raise ValueError(
                f"Unsupported export format: '{format_type}'. Available formats: {available}"
            )

        exporter_class = cls._exporters[format_type]
        logger.debug(f"Created exporter: {exporter_class.__name__}")
        return exporter_class(**kwargs)

    @classmethod
    def available_formats(cls) -> list[str]:
        """Get list of available export formats.

        Returns:
            Sorted list of format identifiers
        """
        return sorted(cls._exporters.keys())

    @classmethod
    def get_exporter_info(cls) -> list[dict[str, str]]:
        """Get information about all registered exporters.

        Returns:
            List of dicts with format, name, extension
        """
        info = []
        for format_type, exporter_class in sorted(cls._exporters.items()):
            exporter = exporter_class()
            info.append(
                {
                    "format": format_type,
                    "name": exporter.format_name(),
                    "extension": exporter.get_file_extension(),
                }
            )
        return info
