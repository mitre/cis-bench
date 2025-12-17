"""CIS Benchmark CLI - Fetch and manage CIS benchmarks.

This package provides:
- Web scraping from CIS WorkBench
- Export to multiple formats (JSON, YAML, CSV, Markdown, XCCDF)
- Command-line interface
- Pydantic data models with validation
- Adaptable scraping strategies (HTML-change resilient)
"""

from importlib.metadata import version

__version__ = version("cis-bench")
__author__ = "MITRE SAF Team"
__email__ = "saf@mitre.org"

# Core models
# Exporter system
from cis_bench.exporters.base import BaseExporter, ExporterFactory

# Scraper system
from cis_bench.fetcher.strategies.base import ScraperStrategy
from cis_bench.fetcher.strategies.detector import StrategyDetector
from cis_bench.models.benchmark import Benchmark, Recommendation

__all__ = [
    # Version info
    "__version__",
    "__author__",
    "__email__",
    # Models
    "Benchmark",
    "Recommendation",
    # Exporters
    "BaseExporter",
    "ExporterFactory",
    # Scrapers
    "ScraperStrategy",
    "StrategyDetector",
]
