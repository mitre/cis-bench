"""The catalog keeps what a release's WorkBench page says about it beyond the listing:
release type, parent benchmark, audience, acknowledgements and milestone on the release's
row, and its contributors, assets and revision history in tables of their own."""

from contextlib import closing
from datetime import datetime

import pytest
from sqlmodel import Session

from cis_bench.catalog.database import CatalogDatabase
from cis_bench.catalog.models import (
    BenchmarkAsset,
    BenchmarkContributor,
    CatalogBenchmark,
    RevisionHistory,
)

ROW = {
    "release_type": "Planned Update",
    "parent_benchmark_id": "11111",
    "parent_benchmark_url": "https://workbench.cisecurity.org/benchmarks/11111",
    "intended_audience": "Administrators who install and run the example platform.",
    "acknowledgements": "The example platform community.",
    "milestone_name": "Example Platform v2.0.0",
    "milestone_url": "https://workbench.cisecurity.org/community/42/milestones/7",
}
CONTRIBUTORS = ["Alex Example", "Sam Sample", "Alex Example"]
ASSETS = [
    {"title": "Example OS 9", "cpe_id": "cpe:2.3:o:example:example_os:9:*:*:*:*:*:*:*"},
    {"title": "Example OS 10", "cpe_id": "cpe:2.3:o:example:example_os:10:*:*:*:*:*:*:*"},
]
REVISIONS = [
    {"revised_at": datetime(2025, 9, 23, 14, 54), "author": "Alex", "modification_count": 1},
    {"revised_at": datetime(2025, 9, 23, 14, 53), "author": None, "modification_count": None},
]


@pytest.fixture
def db(tmp_path):
    with closing(CatalogDatabase(tmp_path / "catalog.db")) as database:
        database.initialize_schema()
        for benchmark_id in ("100", "200"):
            database.insert_benchmark(
                {
                    "benchmark_id": benchmark_id,
                    "title": "CIS Example Platform Benchmark",
                    "version": f"v{benchmark_id[0]}.0.0",
                    "url": f"https://workbench.cisecurity.org/benchmarks/{benchmark_id}",
                    "status": "Published",
                }
            )
        yield database


def _record(db, benchmark_id, row, contributors, assets, revisions):
    """Write page metadata for a release, the list rows in reverse order so the order read
    back comes from each row's place in its list, not from when it was written."""
    with Session(db.engine) as session:
        benchmark = session.get(CatalogBenchmark, benchmark_id)
        for name, value in row.items():
            setattr(benchmark, name, value)
        session.add(benchmark)
        for place, name in reversed(list(enumerate(contributors))):
            session.add(
                BenchmarkContributor(benchmark_id=benchmark_id, sort_order=place, name=name)
            )
        for place, asset in reversed(list(enumerate(assets))):
            session.add(BenchmarkAsset(benchmark_id=benchmark_id, sort_order=place, **asset))
        for place, revision in reversed(list(enumerate(revisions))):
            session.add(RevisionHistory(benchmark_id=benchmark_id, sort_order=place, **revision))
        session.commit()


def test_get_benchmark_returns_the_page_metadata_recorded_for_the_release(db):
    _record(db, "100", ROW, CONTRIBUTORS, ASSETS, REVISIONS)

    row = db.get_benchmark("100")

    assert {name: row[name] for name in ROW} == ROW
    assert row["contributors"] == CONTRIBUTORS
    assert row["assets"] == ASSETS
    assert row["revision_history"] == REVISIONS


def test_a_release_without_page_metadata_reads_as_none_and_empty_lists(db):
    row = db.get_benchmark("200")

    assert {name: row[name] for name in ROW} == dict.fromkeys(ROW)
    assert (row["contributors"], row["assets"], row["revision_history"]) == ([], [], [])


def test_each_release_reads_only_its_own_lists(db):
    _record(db, "100", {}, ["Alex Example"], ASSETS[:1], REVISIONS[:1])
    _record(db, "200", {}, ["Sam Sample"], ASSETS[1:], REVISIONS[1:])

    first, second = db.get_benchmark("100"), db.get_benchmark("200")

    assert (first["contributors"], first["assets"], first["revision_history"]) == (
        ["Alex Example"],
        ASSETS[:1],
        REVISIONS[:1],
    )
    assert (second["contributors"], second["assets"], second["revision_history"]) == (
        ["Sam Sample"],
        ASSETS[1:],
        REVISIONS[1:],
    )


def test_catalog_refresh_keeps_the_page_metadata(db):
    # The listing carries none of it; refreshing a release must not erase it.
    _record(db, "100", ROW, CONTRIBUTORS, ASSETS, REVISIONS)

    db.insert_benchmark(
        {
            "benchmark_id": "100",
            "title": "CIS Example Platform Benchmark",
            "version": "v1.0.1",
            "url": "https://workbench.cisecurity.org/benchmarks/100",
            "status": "Published",
            "collections": ["Example"],
        }
    )
    row = db.get_benchmark("100")

    assert row["version"] == "v1.0.1"
    assert {name: row[name] for name in ROW} == ROW
    assert (row["contributors"], row["assets"], row["revision_history"]) == (
        CONTRIBUTORS,
        ASSETS,
        REVISIONS,
    )
