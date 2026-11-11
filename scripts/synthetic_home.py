#!/usr/bin/env python3
"""Build a cis-bench data folder that holds the synthetic benchmarks as downloads.

    python scripts/synthetic_home.py <folder>
    CIS_BENCH_HOME=<folder> cis-bench list

Every tests/fixtures/benchmarks/synthetic_*.json becomes a catalog row and a downloaded copy.
A copy is stored as its file holds it, so one written the way an earlier version stored
copies is loaded the way such a copy is. Every word of the synthetic benchmarks is our own,
so command output from this folder can be shown in the documentation. No session is saved
and nothing is sent to CIS WorkBench.

The folder must be new or empty: the script never writes into a folder that holds anything.
"""

import argparse
import os
import sys
from contextlib import closing
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "benchmarks"

# What the catalog listing would say about each synthetic benchmark (the files hold the
# benchmark itself, not its listing).
LISTING = {
    "90001": {"platform": "synthetic-enterprise", "platform_type": "os", "is_latest": True},
    "90002": {"platform": "synthetic-linux", "platform_type": "os", "is_latest": True},
    "90003": {"platform": "synthetic-linux", "platform_type": "os", "is_latest": False},
    "90004": {"platform": "synthetic-cloud", "platform_type": "cloud", "is_latest": True},
    "90005": {"platform": "synthetic-windows-server", "platform_type": "os", "is_latest": True},
}
COMMUNITY = "Synthetic Benchmarks"


def build(folder: Path) -> list[tuple[str, str, str]]:
    """Fill ``folder`` with the synthetic benchmarks; the (ID, title, version) of each."""
    from cis_bench.catalog.database import (
        CatalogDatabase,
        deserialize_benchmark_json,
        serialize_benchmark_json,
    )
    from cis_bench.config import CATALOG_DB_FILE_NAME, HOME_VARIABLE, xdg_folders
    from cis_bench.models.benchmark import BenchmarkPage

    # The data folder cis-bench uses when CIS_BENCH_HOME names this folder.
    data = xdg_folders({HOME_VARIABLE: str(folder)}, home=Path.home(), windows=os.name == "nt").data

    built = []
    with closing(CatalogDatabase(data / CATALOG_DB_FILE_NAME)) as db:
        db.initialize_schema()
        for path in sorted(FIXTURES.glob("synthetic_*.json")):
            stored = path.read_text(encoding="utf-8")
            benchmark = deserialize_benchmark_json(stored)
            db.insert_benchmark(
                {
                    "benchmark_id": benchmark.benchmark_id,
                    "title": benchmark.title,
                    "version": benchmark.version,
                    "url": str(benchmark.url),
                    "status": "Published",
                    "community": COMMUNITY,
                    **LISTING[benchmark.benchmark_id],
                }
            )
            # The hash is the one a download of this content gets; the stored text is the
            # file's own, whatever form it was written in.
            _, content_hash = serialize_benchmark_json(benchmark)
            # The catalog row records an instant. A copy written without a zone on its time
            # (as earlier versions wrote them) keeps that time in its own text; its row
            # records when the folder was built, since a zone is never guessed.
            downloaded_at = benchmark.downloaded_at
            db.save_downloaded(
                benchmark.benchmark_id,
                stored,
                content_hash,
                len(benchmark.recommendations),
                version=benchmark.version,
                downloaded_at=downloaded_at if downloaded_at.tzinfo is not None else None,
                published_date=benchmark.published_date,
                benchmark=benchmark,
            )
            db.record_page(
                benchmark.benchmark_id,
                BenchmarkPage(
                    title=benchmark.title,
                    published_date=benchmark.published_date,
                    description=benchmark.description,
                    profile_definitions=benchmark.profile_definitions,
                ),
            )
            built.append((benchmark.benchmark_id, benchmark.title, benchmark.version))
    return built


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path, help="a new or empty folder")
    folder = parser.parse_args(argv).folder

    if folder.exists() and (not folder.is_dir() or any(folder.iterdir())):
        print(f"{folder} is not an empty folder; give a new or empty one.", file=sys.stderr)
        return 1
    folder.mkdir(parents=True, exist_ok=True)

    for benchmark_id, title, version in sorted(build(folder)):
        print(f"{benchmark_id}  {title} {version}")
    print(f"\nUse it with: CIS_BENCH_HOME={folder} cis-bench list")
    return 0


if __name__ == "__main__":
    sys.exit(main())
