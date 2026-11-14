"""Tests for `cis-bench remove`: deleting a downloaded benchmark's cached copy."""

from datetime import UTC, datetime

import pytest
from click.testing import CliRunner

from cis_bench.catalog.database import CatalogDatabase
from cis_bench.cli.app import cli


def _catalog_row(benchmark_id: str, title: str) -> dict:
    return {
        "benchmark_id": benchmark_id,
        "title": title,
        "version": "v4.0.0",
        "url": f"https://workbench.cisecurity.org/benchmarks/{benchmark_id}",
        "status": "Published",
        "platform": "Operating System",
        "community": "CIS AlmaLinux Benchmarks",
        "collections": ["Operating System"],
    }


@pytest.fixture
def db(tmp_path):
    database = CatalogDatabase(tmp_path / "catalog.db")
    database.initialize_schema()
    database.insert_benchmark(_catalog_row("23598", "CIS AlmaLinux OS 8 Benchmark"))
    database.insert_benchmark(_catalog_row("24000", "CIS AlmaLinux OS 9 Benchmark"))
    database.save_downloaded(
        "23598",
        "{}",
        "h1",
        322,
        version="v4.0.0",
        downloaded_at=datetime(2026, 11, 7, 2, 5, 58, tzinfo=UTC),
    )
    database.save_downloaded("24000", "{}", "h2", 300, version="v4.0.0")
    yield database
    database.close()


@pytest.fixture
def run(db, monkeypatch):
    monkeypatch.setenv("CIS_BENCH_HOME", str(db.db_path.parent))
    monkeypatch.setenv("COLUMNS", "120")  # a terminal wide enough that a line does not wrap

    def invoke(*args, input=None):
        return CliRunner().invoke(cli, ["remove", *args], input=input)

    return invoke


class TestRemoveCommand:
    def test_removes_the_cached_copy_and_keeps_the_catalog_row(self, db, run):
        result = run("23598", "--yes")

        assert result.exit_code == 0, result.output
        assert db.get_downloaded("23598") is None
        assert db.get_downloaded("24000") is not None
        assert db.get_benchmark("23598") is not None
        assert "23598" in result.output

    def test_lists_what_will_be_removed_and_asks_first(self, db, run, new_york_clock):
        result = run("23598", input="n\n")

        assert result.exit_code != 0
        assert db.get_downloaded("23598") is not None
        assert "CIS AlmaLinux OS 8 Benchmark" in result.output
        assert "v4.0.0" in result.output
        assert "(downloaded 2026-11-06 21:05:58 EST)" in result.output

        result = run("23598", input="y\n")

        assert result.exit_code == 0, result.output
        assert db.get_downloaded("23598") is None

    @pytest.mark.parametrize(
        ("references", "expected"),
        [
            (("23598",), "Remove 1 cached benchmark?"),
            (("23598", "24000"), "Remove 2 cached benchmarks?"),
        ],
    )
    def test_the_prompt_counts_the_benchmarks(self, run, references, expected):
        result = run(*references, input="n\n")

        assert expected in result.output

    def test_a_benchmark_that_is_not_downloaded_is_reported_and_fails_the_run(self, db, run):
        db.insert_benchmark(_catalog_row("25000", "CIS Rocky Linux 9 Benchmark"))

        result = run("25000", "23598", "--yes")

        assert result.exit_code == 1
        assert "25000" in result.output and "not downloaded" in result.output
        assert db.get_downloaded("23598") is None  # the downloaded one is still removed

    def test_a_bad_reference_removes_nothing(self, db, run):
        result = run("23598", "not-an-id", "--yes")

        assert result.exit_code == 1
        assert db.get_downloaded("23598") is not None

    @pytest.mark.parametrize(
        "reference",
        ["/benchmarks/23598", "https://workbench.cisecurity.org/benchmarks/23598"],
    )
    def test_accepts_the_same_references_as_download(self, db, run, reference):
        result = run(reference, "--yes")

        assert result.exit_code == 0, result.output
        assert db.get_downloaded("23598") is None

    def test_a_repeated_reference_is_removed_once(self, db, run):
        result = run("23598", "23598", "--yes")

        assert result.exit_code == 0, result.output
        assert result.output.count("Removed") == 1

    def test_says_exported_files_are_kept_and_how_to_refresh_instead(self, db, run):
        result = run("23598", "--yes")

        assert f"Exported files in {db.db_path.parent / 'benchmarks'}" in result.output
        assert "download 23598 --force" in result.output

    def test_without_a_catalog_database_nothing_is_created(self, tmp_path, monkeypatch):
        missing = tmp_path / "absent" / "catalog.db"
        monkeypatch.setenv("CIS_BENCH_HOME", str(missing.parent))
        result = CliRunner().invoke(cli, ["remove", "23598", "--yes"])

        assert result.exit_code == 1
        assert not missing.exists()

    def test_without_a_catalog_database_prints_its_path_verbatim(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("CIS_BENCH_HOME", "c[x]")
        result = CliRunner().invoke(cli, ["remove", "23598", "--yes"])

        assert result.exit_code == 1
        assert "No catalog database at c[x]/catalog.db" in result.output
