"""CIS benchmark catalog management, search, scraping, and caching."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cis_bench.catalog.database import (
        CatalogDatabase,
        deserialize_benchmark_json,
        normalize_status_filter,
        serialize_benchmark_json,
    )
    from cis_bench.catalog.downloader import CatalogDownloader
    from cis_bench.catalog.fts import build_fts_query
    from cis_bench.catalog.models import (
        BenchmarkCollection,
        BenchmarkStatus,
        BenchmarkStatusModel,
        CatalogBenchmark,
        Collection,
        Community,
        DownloadedBenchmark,
        Owner,
        Platform,
        ScrapeMetadata,
    )
    from cis_bench.catalog.parser import WorkBenchCatalogParser
    from cis_bench.catalog.scraper import CatalogScraper
    from cis_bench.catalog.search import CatalogSearch

_EXPORT_MODULES: dict[str, str] = {
    "BenchmarkCollection": "cis_bench.catalog.models",
    "BenchmarkStatus": "cis_bench.catalog.models",
    "BenchmarkStatusModel": "cis_bench.catalog.models",
    "CatalogBenchmark": "cis_bench.catalog.models",
    "CatalogDatabase": "cis_bench.catalog.database",
    "CatalogDownloader": "cis_bench.catalog.downloader",
    "CatalogScraper": "cis_bench.catalog.scraper",
    "CatalogSearch": "cis_bench.catalog.search",
    "Collection": "cis_bench.catalog.models",
    "Community": "cis_bench.catalog.models",
    "DownloadedBenchmark": "cis_bench.catalog.models",
    "Owner": "cis_bench.catalog.models",
    "Platform": "cis_bench.catalog.models",
    "ScrapeMetadata": "cis_bench.catalog.models",
    "WorkBenchCatalogParser": "cis_bench.catalog.parser",
    "build_fts_query": "cis_bench.catalog.fts",
    "deserialize_benchmark_json": "cis_bench.catalog.database",
    "normalize_status_filter": "cis_bench.catalog.database",
    "serialize_benchmark_json": "cis_bench.catalog.database",
}

__all__ = [
    "BenchmarkCollection",
    "BenchmarkStatus",
    "BenchmarkStatusModel",
    "CatalogBenchmark",
    "CatalogDatabase",
    "CatalogDownloader",
    "CatalogScraper",
    "CatalogSearch",
    "Collection",
    "Community",
    "DownloadedBenchmark",
    "Owner",
    "Platform",
    "ScrapeMetadata",
    "WorkBenchCatalogParser",
    "build_fts_query",
    "deserialize_benchmark_json",
    "normalize_status_filter",
    "serialize_benchmark_json",
]


def __getattr__(name: str) -> object:
    """Lazily import catalog submodules so read-only search avoids HTTP/cookie imports."""
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_name)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Expose lazy public exports to interactive introspection."""
    return sorted({*globals().keys(), *__all__})
