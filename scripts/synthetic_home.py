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
# When the listing these rows stand for was read, recorded as a catalog refresh records it,
# so the folder looks like one where `catalog refresh` has run.
LISTED_AT = "2026-11-10T15:00:00+00:00"


class NotAnEmptyFolder(Exception):
    """The data folder already holds something; nothing was written."""


def data_folder(given: str) -> Path | None:
    """The data folder cis-bench uses when CIS_BENCH_HOME is ``given``, as the CLI reads it
    (surrounding spaces dropped, ~ the home folder); None when ``given`` is blank, which
    cis-bench reads as unset."""
    from cis_bench.config import HOME_VARIABLE, xdg_folders

    if not given.strip():
        return None
    return xdg_folders({HOME_VARIABLE: given}, home=Path.home(), windows=os.name == "nt").data


def prepare(data: Path) -> None:
    """Create the data folder ``data``, which must be new or empty.

    Raises:
        NotAnEmptyFolder: ``data`` is a file, a link, or a folder that holds anything.
    """
    if data.is_symlink() or (data.exists() and (not data.is_dir() or any(data.iterdir()))):
        raise NotAnEmptyFolder(f"{data} is not an empty folder; give a new or empty one.")
    data.mkdir(parents=True, exist_ok=True)


def build(data: Path) -> list[tuple[str, str, str]]:
    """Fill the new or empty data folder ``data`` with the synthetic benchmarks; the (ID,
    title, version) of each.

    Raises:
        NotAnEmptyFolder: ``data`` is not new or empty; nothing was written.
    """
    from cis_bench.catalog.database import (
        CatalogDatabase,
        deserialize_benchmark_json,
        serialize_benchmark_json,
    )
    from cis_bench.config import CATALOG_DB_FILE_NAME
    from cis_bench.models.benchmark import BenchmarkPage

    prepare(data)
    built = []
    with closing(CatalogDatabase(data / CATALOG_DB_FILE_NAME)) as db:
        db.initialize_schema()
        db.set_metadata("last_full_scrape", LISTED_AT)
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
    parser.add_argument("folder", help="a new or empty folder")
    given = parser.parse_args(argv).folder

    # The folder checked is the folder written to: the one CIS_BENCH_HOME=<given> names.
    data = data_folder(given)
    if data is None:
        print("Give a folder: a blank CIS_BENCH_HOME is not set.", file=sys.stderr)
        return 1
    try:
        built = build(data)
    except NotAnEmptyFolder as refusal:
        print(refusal, file=sys.stderr)
        return 1

    for benchmark_id, title, version in sorted(built):
        print(f"{benchmark_id}  {title} {version}")
    print(f"\nUse it with: CIS_BENCH_HOME={data} cis-bench list")
    return 0


if __name__ == "__main__":
    sys.exit(main())
