"""list and info: "downloaded" means in the database cache; files in the benchmarks folder are
exports, shown separately."""

import json
from datetime import UTC, datetime

import pytest
from click.testing import CliRunner

from cis_bench.catalog.database import CatalogDatabase, serialize_benchmark_json
from cis_bench.cli.app import cli
from cis_bench.models.benchmark import Benchmark, Recommendation
from tests.conftest import unusable_command_hints


@pytest.fixture
def runner():
    return CliRunner()


def _benchmark(benchmark_id: str, title: str, version: str) -> Benchmark:
    return Benchmark(
        title=title,
        benchmark_id=benchmark_id,
        url=f"https://workbench.cisecurity.org/benchmarks/{benchmark_id}",
        version=version,
        downloaded_at=datetime(2026, 11, 6, 12, 0, 0),
        scraper_version="1.0.0",
        total_recommendations=1,
        recommendations=[
            Recommendation(
                ref="1.1.1",
                title="Only recommendation",
                url=f"https://workbench.cisecurity.org/sections/{benchmark_id}/recommendations/1",
                assessment_status="Automated",
                profiles=["Level 1"],
                description="d",
                rationale="r",
                impact="i",
                audit="a",
                remediation="m",
            )
        ],
    )


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A data folder with one cached benchmark (201) and one exported file of another (300)."""
    db = CatalogDatabase(tmp_path / "catalog.db")
    try:
        db.initialize_schema()
        for bid, title, version in (
            ("201", "CIS Cached Benchmark", "v2.0.1"),
            ("300", "CIS Exported Only Benchmark", "v3.0.0"),
        ):
            db.insert_benchmark(
                {
                    "benchmark_id": bid,
                    "title": title,
                    "version": version,
                    "url": f"https://workbench.cisecurity.org/benchmarks/{bid}",
                    "status": "Published",
                }
            )
        content_json, content_hash = serialize_benchmark_json(
            _benchmark("201", "CIS Cached Benchmark", "v2.0.1")
        )
        db.save_downloaded("201", content_json, content_hash, 1, version="v2.0.1")
    finally:
        db.close()
    exports = tmp_path / "benchmarks"
    exports.mkdir()
    (exports / "cis_exported_only_benchmark_v300.json").write_text(
        _benchmark("300", "CIS Exported Only Benchmark", "v3.0.0").model_dump_json()
    )
    (exports / "cis_exported_only_benchmark_v300.yaml").write_text("title: whatever\n")
    monkeypatch.setenv("CIS_BENCH_HOME", str(tmp_path))
    monkeypatch.setenv("COLUMNS", "120")  # a terminal wide enough that the table does not wrap
    return tmp_path


class TestListShowsTheCacheAndTheExportedFiles:
    def test_cached_benchmarks_and_exported_files_are_listed_under_their_own_headings(
        self, runner, home
    ):
        result = runner.invoke(cli, ["list"])

        assert result.exit_code == 0, result.output
        cache, _, files = result.output.partition("Exported files in")
        assert "Downloaded benchmarks (1)" in cache
        assert "CIS Cached Benchmark" in " ".join(cache.split())  # the table may wrap it
        assert "201" in cache
        assert "CIS Exported Only Benchmark" not in cache
        assert str(home / "benchmarks") in files
        assert "cis_exported_only_benchmark_v300.json" in files
        assert "cis_exported_only_benchmark_v300.yaml" in files

    def test_a_removed_benchmark_leaves_the_cache_list_but_its_files_stay(self, runner, home):
        assert runner.invoke(cli, ["remove", "201", "--yes"]).exit_code == 0

        result = runner.invoke(cli, ["list"])

        assert result.exit_code == 0, result.output
        assert "No benchmarks are downloaded" in result.output
        assert "cis-bench download <ID>" in result.output
        assert "CIS Cached Benchmark" not in result.output
        assert "cis_exported_only_benchmark_v300.json" in result.output
        assert unusable_command_hints(result.output) == []

    def test_a_deleted_exported_file_does_not_change_what_is_downloaded(self, runner, home):
        for path in (home / "benchmarks").iterdir():
            path.unlink()

        result = runner.invoke(cli, ["list"])

        assert result.exit_code == 0, result.output
        assert "Downloaded benchmarks (1)" in result.output
        assert "CIS Cached Benchmark" in " ".join(result.output.split())
        assert "Exported files in" in result.output
        assert "none" in result.output

    def test_json_output_carries_both_with_their_source(self, runner, home):
        result = runner.invoke(cli, ["list", "--output-format", "json"])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert [b["benchmark_id"] for b in data["downloaded"]] == ["201"]
        assert data["downloaded"][0]["title"] == "CIS Cached Benchmark"
        assert data["downloaded"][0]["recommendations"] == 1
        assert data["exported_files"]["folder"] == str(home / "benchmarks")
        assert data["exported_files"]["files"] == [
            "cis_exported_only_benchmark_v300.json",
            "cis_exported_only_benchmark_v300.yaml",
        ]

    def test_csv_output_lists_the_downloaded_benchmarks(self, runner, home):
        result = runner.invoke(cli, ["list", "--output-format", "csv"])

        assert result.exit_code == 0, result.output
        lines = result.output.strip().splitlines()
        assert lines[0].startswith("benchmark_id,title,version,recommendations")
        assert lines[1].startswith("201,CIS Cached Benchmark,v2.0.1,1")


class TestListCopesWithWhatTheCacheMayHold:
    def test_a_benchmark_downloaded_while_absent_from_the_catalog_is_listed_from_its_content(
        self, runner, home
    ):
        db = CatalogDatabase(home / "catalog.db")
        try:
            content_json, content_hash = serialize_benchmark_json(
                _benchmark("6467", "CIS Newer Than The Catalog Benchmark", "v1.0.0")
            )
            db.save_downloaded("6467", content_json, content_hash, 1, version="v1.0.0")
        finally:
            db.close()

        result = runner.invoke(cli, ["list", "--output-format", "json"])

        assert result.exit_code == 0, result.output
        downloaded = json.loads(result.output)["downloaded"]
        assert [(b["benchmark_id"], b["title"]) for b in downloaded] == [
            ("201", "CIS Cached Benchmark"),
            ("6467", "CIS Newer Than The Catalog Benchmark"),
        ]

    def test_ids_are_ordered_as_numbers(self, runner, home):
        db = CatalogDatabase(home / "catalog.db")
        try:
            for bid in ("10000", "99"):
                content_json, content_hash = serialize_benchmark_json(
                    _benchmark(bid, f"B {bid}", "v1")
                )
                db.save_downloaded(bid, content_json, content_hash, 1, version="v1")
        finally:
            db.close()

        result = runner.invoke(cli, ["list", "--output-format", "csv"])

        assert result.exit_code == 0, result.output
        assert [line.split(",")[0] for line in result.output.strip().splitlines()[1:]] == [
            "99",
            "201",
            "10000",
        ]

    def test_a_corrupt_cached_copy_is_reported_and_the_others_are_listed(self, runner, home):
        db = CatalogDatabase(home / "catalog.db")
        try:
            db.save_downloaded("300", "{not json", "hash-bad", 0, version="v3.0.0")
        finally:
            db.close()

        result = runner.invoke(cli, ["list"])

        assert result.exit_code == 0, result.output
        assert "Traceback" not in result.output
        assert "Downloaded benchmarks (2)" in result.output
        flat = " ".join(result.output.split())
        assert "CIS Cached Benchmark" in flat
        assert "300" in flat and "unreadable" in flat


class TestInfoReadsTheCacheByIdAndAFileByPath:
    def test_info_with_an_id_shows_the_cached_benchmark(self, runner, home):
        result = runner.invoke(cli, ["info", "201"])

        assert result.exit_code == 0, result.output
        assert "CIS Cached Benchmark" in result.output
        assert "v2.0.1" in result.output
        assert "Source: cache" in result.output

    def test_info_with_an_id_that_is_not_downloaded_says_so(self, runner, home):
        result = runner.invoke(cli, ["info", "300"])

        assert result.exit_code == 1
        assert "Benchmark 300 is not downloaded" in result.output
        assert "cis-bench download 300" in result.output
        assert unusable_command_hints(result.output) == []

    def test_info_with_a_corrupt_cached_copy_reports_it_without_a_traceback(self, runner, home):
        db = CatalogDatabase(home / "catalog.db")
        try:
            db.save_downloaded("300", "{not json", "hash-bad", 0, version="v3.0.0")
        finally:
            db.close()

        result = runner.invoke(cli, ["info", "300"])

        assert result.exit_code == 1
        assert "Traceback" not in result.output
        assert "Error:" in result.output

    def test_info_with_a_file_path_still_inspects_that_file(self, runner, home):
        path = home / "benchmarks" / "cis_exported_only_benchmark_v300.json"

        by_path = runner.invoke(cli, ["info", str(path)])
        by_name = runner.invoke(cli, ["info", "cis_exported_only_benchmark_v300.json"])

        for result in (by_path, by_name):
            assert result.exit_code == 0, result.output
            assert "CIS Exported Only Benchmark" in result.output
            assert "Source: file" in result.output

    def test_info_json_names_its_source(self, runner, home):
        result = runner.invoke(cli, ["info", "201", "--output-format", "json"])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["benchmark_id"] == "201"
        assert data["source"] == "cache"
        assert data["file"] is None

        path = home / "benchmarks" / "cis_exported_only_benchmark_v300.json"
        by_path = runner.invoke(cli, ["info", str(path), "--output-format", "json"])

        data = json.loads(by_path.output)
        assert data["benchmark_id"] == "300"
        assert data["source"] == "file"
        assert data["file"] == str(path)


class TestDownloadTimes:
    """A download has one instant: the cache row and the benchmark JSON carry the same aware time,
    structured output gives it in ISO 8601 with its offset, tables in the viewer's zone."""

    INSTANT = datetime(2026, 11, 7, 2, 5, 58, tzinfo=UTC)

    @pytest.fixture
    def downloaded_at_a_known_instant(self, tmp_path, monkeypatch):
        benchmark = _benchmark("201", "CIS Cached Benchmark", "v2.0.1").model_copy(
            update={"downloaded_at": self.INSTANT}
        )
        db = CatalogDatabase(tmp_path / "catalog.db")
        try:
            db.initialize_schema()
            db.insert_benchmark(
                {
                    "benchmark_id": "201",
                    "title": "CIS Cached Benchmark",
                    "version": "v2.0.1",
                    "url": "https://workbench.cisecurity.org/benchmarks/201",
                    "status": "Published",
                }
            )
            content_json, content_hash = serialize_benchmark_json(benchmark)
            db.save_downloaded(
                "201",
                content_json,
                content_hash,
                1,
                version="v2.0.1",
                downloaded_at=benchmark.downloaded_at,
            )
        finally:
            db.close()
        (tmp_path / "benchmarks").mkdir()
        monkeypatch.setenv("CIS_BENCH_HOME", str(tmp_path))
        monkeypatch.setenv("COLUMNS", "120")
        return tmp_path

    def test_list_and_info_show_the_same_download_time(
        self, runner, downloaded_at_a_known_instant, new_york_clock
    ):
        listed = runner.invoke(cli, ["list", "--output-format", "csv"])
        shown = runner.invoke(cli, ["info", "201", "--output-format", "json"])

        assert listed.exit_code == 0, listed.output
        assert shown.exit_code == 0, shown.output
        header, row = listed.output.strip().splitlines()
        csv_time = dict(zip(header.split(","), row.split(","), strict=True))["downloaded_at"]
        assert csv_time == "2026-11-07T02:05:58+00:00"
        assert json.loads(shown.output)["downloaded_at"] == csv_time

    def test_tables_show_the_download_time_in_the_local_zone(
        self, runner, downloaded_at_a_known_instant, new_york_clock
    ):
        listed = runner.invoke(cli, ["list"])
        shown = runner.invoke(cli, ["info", "201"])

        assert listed.exit_code == 0, listed.output
        assert shown.exit_code == 0, shown.output
        assert "2026-11-06 21:05:58 EST" in " ".join(listed.output.split())
        assert "Downloaded: 2026-11-06 21:05:58 EST" in shown.output

    def test_json_and_yaml_lists_carry_the_offset(self, runner, downloaded_at_a_known_instant):
        as_json = runner.invoke(cli, ["list", "--output-format", "json"])
        as_yaml = runner.invoke(cli, ["list", "--output-format", "yaml"])

        assert as_json.exit_code == 0, as_json.output
        assert as_yaml.exit_code == 0, as_yaml.output
        assert json.loads(as_json.output)["downloaded"][0]["downloaded_at"] == (
            "2026-11-07T02:05:58+00:00"
        )
        assert "2026-11-07T02:05:58+00:00" in as_yaml.output

    def test_a_file_from_an_earlier_version_keeps_its_zoneless_time(
        self, runner, downloaded_at_a_known_instant, new_york_clock
    ):
        old = downloaded_at_a_known_instant / "benchmarks" / "old.json"
        old.write_text(_benchmark("300", "CIS Old Benchmark", "v1.0.0").model_dump_json())

        table = runner.invoke(cli, ["info", str(old)])
        structured = runner.invoke(cli, ["info", str(old), "--output-format", "json"])

        assert table.exit_code == 0, table.output
        assert "Downloaded: 2026-11-06 12:00:00 (zone not recorded)" in table.output
        assert json.loads(structured.output)["downloaded_at"] == "2026-11-06T12:00:00"
