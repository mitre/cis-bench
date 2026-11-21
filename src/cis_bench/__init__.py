"""CIS Benchmark CLI - Fetch and manage CIS benchmarks.

This package provides:
- Web scraping from CIS WorkBench
- Export to multiple formats (JSON, YAML, CSV, Markdown, XCCDF)
- Command-line interface
- Pydantic data models with validation
- Adaptable scraping strategies (HTML-change resilient)
"""

import importlib
from importlib.metadata import version
from typing import TYPE_CHECKING, Any

__version__ = version("cis-bench")
__author__ = "MITRE SAF Team"
__email__ = "saf@mitre.org"

# Public re-exports resolve on first access (PEP 562) so importing any
# cis_bench submodule does not pay for the exporter, scraper and model stacks.
_LAZY_EXPORTS = {
    "BaseExporter": "cis_bench.exporters.base",
    "ExporterFactory": "cis_bench.exporters.base",
    "ScraperStrategy": "cis_bench.fetcher.strategies.base",
    "StrategyDetector": "cis_bench.fetcher.strategies.detector",
    "Benchmark": "cis_bench.models.benchmark",
    "Recommendation": "cis_bench.models.benchmark",
}

if TYPE_CHECKING:
    from cis_bench.exporters.base import BaseExporter, ExporterFactory
    from cis_bench.fetcher.strategies.base import ScraperStrategy
    from cis_bench.fetcher.strategies.detector import StrategyDetector
    from cis_bench.models.benchmark import Benchmark, Recommendation


def __getattr__(name: str) -> Any:
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(module_name), name)
    globals()[name] = value  # cache so __getattr__ runs once per name
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))


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
