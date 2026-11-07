"""Offline mode: cis-bench never contacts CIS WorkBench, and uses the cache wherever it can.

A command fails only at the point it would open a WorkBench session; everything it can do
from catalog.db (search, cached benchmarks, version comparison) still works.
"""

import click
import pytest
from click.testing import CliRunner

from cis_bench.cli.app import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def probe(monkeypatch):
    """A subcommand that reports what the root command left on the context for it."""
    seen = {}

    @click.command(name="probe")
    @click.pass_context
    def probe_cmd(ctx):
        seen["offline"] = ctx.obj["offline"]
        seen["settings_offline"] = ctx.obj["settings"].offline

    monkeypatch.setitem(cli.commands, "probe", probe_cmd)
    return seen


class TestOfflineSwitch:
    def test_the_flag_turns_offline_on_for_the_run(self, runner, probe):
        result = runner.invoke(cli, ["--offline", "probe"])
        assert result.exit_code == 0, result.output
        assert probe == {"offline": True, "settings_offline": True}

    def test_offline_is_off_by_default(self, runner, probe, monkeypatch):
        monkeypatch.delenv("CIS_BENCH_OFFLINE", raising=False)
        result = runner.invoke(cli, ["probe"])
        assert result.exit_code == 0, result.output
        assert probe == {"offline": False, "settings_offline": False}

    def test_the_setting_turns_offline_on_without_the_flag(self, runner, probe, monkeypatch):
        monkeypatch.setenv("CIS_BENCH_OFFLINE", "true")
        result = runner.invoke(cli, ["probe"])
        assert result.exit_code == 0, result.output
        assert probe == {"offline": True, "settings_offline": True}

    def test_the_flag_beats_a_setting_that_says_online(self, runner, probe, monkeypatch):
        monkeypatch.setenv("CIS_BENCH_OFFLINE", "false")
        result = runner.invoke(cli, ["--offline", "probe"])
        assert result.exit_code == 0, result.output
        assert probe == {"offline": True, "settings_offline": True}

    def test_help_still_works_with_the_flag(self, runner):
        result = runner.invoke(cli, ["--offline", "--help"])
        assert result.exit_code == 0
        assert "--offline" in result.output


# --------------------------------------------------------------------------------------------
# Commands under offline mode, against a real catalog.db with the network blocked
# --------------------------------------------------------------------------------------------

UBUNTU = ("23598", "CIS Ubuntu Linux 20.04 LTS Benchmark")
RHEL = ("21997", "CIS Red Hat Enterprise Linux 9 Benchmark")
DEBIAN = ("19214", "CIS Debian Linux 12 Benchmark")
OFFLINE_HINT = "offline mode is on"


@pytest.fixture
def no_network(monkeypatch):
    """Any HTTP request fails the test: offline mode must not send one."""
    import requests

    def refuse(*args, **kwargs):
        raise AssertionError("an HTTP request was sent while offline")

    monkeypatch.setattr(requests.Session, "send", refuse)


@pytest.fixture
def catalog(data_dir, sample_recommendation_complete, no_network, auth_manager_class):
    """catalog.db in this test's data folder, with three listed benchmarks.

    Listing rows carry what the WorkBench listing carries (no dates, no descriptions).
    ``cached(id, version)`` puts a downloaded copy in the cache through the one cache step.
    """
    from datetime import UTC, date, datetime

    from cis_bench.catalog.database import CatalogDatabase
    from cis_bench.catalog.downloader import CatalogDownloader
    from cis_bench.models.benchmark import Benchmark

    db = CatalogDatabase(data_dir / "catalog.db")
    db.initialize_schema()
    for benchmark_id, title in (UBUNTU, RHEL, DEBIAN):
        db.insert_benchmark(
            {
                "benchmark_id": benchmark_id,
                "title": title,
                "version": "v2.0.1",
                "url": f"https://workbench.cisecurity.org/benchmarks/{benchmark_id}",
                "status": "Published",
                "platform": "Operating System",
                "is_latest": True,
            }
        )

    def cached(benchmark_id: str, version: str = "v2.0.1", rec_title: str | None = None):
        title = dict((UBUNTU, RHEL, DEBIAN))[benchmark_id]
        recommendation = sample_recommendation_complete.model_copy(
            update={"title": rec_title or sample_recommendation_complete.title}
        )
        benchmark = Benchmark(
            title=title,
            benchmark_id=benchmark_id,
            url=f"https://workbench.cisecurity.org/benchmarks/{benchmark_id}",
            version=version,
            downloaded_at=datetime(2026, 11, 1, 12, 0, tzinfo=UTC),
            published_date=date(2026, 10, 1),
            scraper_version="v1_2025_10",
            total_recommendations=1,
            recommendations=[recommendation],
        )
        CatalogDownloader(db).cache(benchmark_id, benchmark)

    db.cached = cached
    yield db
    db.engine.dispose()


def _refused(result, command: str, needs: str):
    """The run stopped at the offline refusal: exit 1, the message on stderr, no session."""
    assert result.exit_code == 1, result.output
    assert f"{command} needs CIS WorkBench to {needs}, and {OFFLINE_HINT}" in result.stderr
    assert "Nothing was sent to WorkBench." in result.stderr


class TestRefusedWhereWorkBenchIsNeeded:
    def test_auth_login(self, runner, catalog, auth_manager_class):
        result = runner.invoke(cli, ["--offline", "auth", "login"])
        _refused(result, "cis-bench auth login", "log in")
        auth_manager_class.assert_not_called()

    def test_auth_status(self, runner, catalog, auth_manager_class):
        result = runner.invoke(cli, ["--offline", "auth", "status"])
        _refused(result, "cis-bench auth status", "check the saved session")
        auth_manager_class.assert_not_called()

    def test_catalog_refresh_touches_nothing(
        self, runner, data_dir, no_network, auth_manager_class
    ):
        result = runner.invoke(cli, ["--offline", "catalog", "refresh"])
        _refused(result, "cis-bench catalog refresh", "read the catalog")
        auth_manager_class.assert_not_called()
        assert not (data_dir / "catalog.db").exists()

    def test_catalog_update(self, runner, catalog, auth_manager_class):
        result = runner.invoke(cli, ["--offline", "catalog", "update"])
        _refused(result, "cis-bench catalog update", "read the catalog")
        auth_manager_class.assert_not_called()

    def test_catalog_download_of_a_benchmark_not_downloaded(
        self, runner, catalog, auth_manager_class
    ):
        result = runner.invoke(cli, ["--offline", "catalog", "download", UBUNTU[0]])
        _refused(result, "cis-bench catalog download", "download a benchmark")
        auth_manager_class.assert_not_called()
        assert catalog.get_downloaded(UBUNTU[0]) is None

    def test_catalog_download_of_an_out_of_date_copy(self, runner, catalog, auth_manager_class):
        catalog.cached(UBUNTU[0], version="v1.0.0")
        result = runner.invoke(cli, ["--offline", "catalog", "download", UBUNTU[0]])
        _refused(result, "cis-bench catalog download", "download a benchmark")
        auth_manager_class.assert_not_called()
        assert catalog.get_downloaded(UBUNTU[0])["version"] == "v1.0.0"

    def test_download_of_a_benchmark_not_downloaded(self, runner, catalog, auth_manager_class):
        result = runner.invoke(cli, ["--offline", "download", UBUNTU[0]])
        assert result.exit_code == 1, result.output
        assert f"benchmark {UBUNTU[0]}" in result.output
        assert OFFLINE_HINT in result.output
        auth_manager_class.assert_not_called()

    def test_get_of_a_benchmark_not_downloaded(
        self, runner, catalog, auth_manager_class, working_dir
    ):
        result = runner.invoke(cli, ["--offline", "get", UBUNTU[0], "--format", "yaml"])
        _refused(result, "cis-bench get", f"download benchmark {UBUNTU[0]}")
        assert "Downloading" not in result.output
        auth_manager_class.assert_not_called()
        assert list(working_dir.iterdir()) == []

    def test_diff_with_a_benchmark_not_downloaded(self, runner, catalog, auth_manager_class):
        catalog.cached(UBUNTU[0])
        result = runner.invoke(cli, ["--offline", "diff", UBUNTU[0], RHEL[0]])
        _refused(result, "cis-bench diff", f"download benchmark {RHEL[0]}")
        assert "downloading" not in result.output.lower()
        auth_manager_class.assert_not_called()


class TestWorksFromTheCache:
    def test_get_of_a_cached_benchmark_writes_the_export(
        self, runner, catalog, auth_manager_class, working_dir
    ):
        catalog.cached(UBUNTU[0])
        result = runner.invoke(
            cli, ["--offline", "get", UBUNTU[0], "--format", "yaml", "--output", "u.yaml"]
        )
        assert result.exit_code == 0, result.output
        assert "already cached" in result.output
        assert UBUNTU[1] in (working_dir / "u.yaml").read_text()
        auth_manager_class.assert_not_called()

    def test_diff_of_two_cached_benchmarks(self, runner, catalog, auth_manager_class):
        catalog.cached(UBUNTU[0], rec_title="Ensure the old wording")
        catalog.cached(RHEL[0], rec_title="Ensure the new wording")
        result = runner.invoke(cli, ["--offline", "diff", UBUNTU[0], RHEL[0], "--format", "json"])
        assert result.exit_code == 0, result.output
        import json

        comparison = json.loads(result.stdout)
        assert [m["ref"] for m in comparison["changes"]["modified"]] == ["6.1.1"]
        auth_manager_class.assert_not_called()

    def test_download_of_a_cached_benchmark(self, runner, catalog, auth_manager_class):
        catalog.cached(UBUNTU[0])
        result = runner.invoke(cli, ["--offline", "download", UBUNTU[0]])
        assert result.exit_code == 0, result.output
        assert f"Benchmark {UBUNTU[0]} already cached" in result.output
        auth_manager_class.assert_not_called()

    def test_download_of_a_cached_and_a_missing_benchmark_fails_only_the_missing_one(
        self, runner, catalog, auth_manager_class
    ):
        catalog.cached(UBUNTU[0])
        result = runner.invoke(cli, ["--offline", "download", RHEL[0], UBUNTU[0]])
        assert result.exit_code == 1, result.output
        assert f"Benchmark {UBUNTU[0]} already cached" in result.output
        assert f"benchmark {RHEL[0]}" in result.output
        assert OFFLINE_HINT in result.output
        auth_manager_class.assert_not_called()

    def test_catalog_download_of_an_up_to_date_copy(self, runner, catalog, auth_manager_class):
        catalog.cached(UBUNTU[0])
        result = runner.invoke(cli, ["--offline", "catalog", "download", UBUNTU[0]])
        assert result.exit_code == 0, result.output
        assert "Already up to date" in result.output
        auth_manager_class.assert_not_called()

    def test_check_updates_compares_versions_only(self, runner, catalog, auth_manager_class):
        catalog.cached(UBUNTU[0], version="v1.0.0")
        result = runner.invoke(cli, ["--offline", "catalog", "check-updates"])
        assert result.exit_code == 0, result.output
        assert "Checking WorkBench publication dates" not in result.output
        assert "Version: v1.0.0 -> v2.0.1" in result.output
        auth_manager_class.assert_not_called()

    def test_auth_logout(self, runner, data_dir, no_network):
        (data_dir / "session.cookies").write_text("[]")
        result = runner.invoke(cli, ["--offline", "auth", "logout"])
        assert result.exit_code == 0, result.output
        assert not (data_dir / "session.cookies").exists()

    def test_search(self, runner, catalog, auth_manager_class):
        result = runner.invoke(cli, ["--offline", "search", "debian", "--output-format", "json"])
        assert result.exit_code == 0, result.output
        import json

        assert [r["benchmark_id"] for r in json.loads(result.stdout)] == [DEBIAN[0]]
        auth_manager_class.assert_not_called()

    def test_export_info_and_list(self, runner, catalog, auth_manager_class, working_dir):
        catalog.cached(UBUNTU[0])
        exported = runner.invoke(
            cli, ["--offline", "export", UBUNTU[0], "--format", "yaml", "-o", "e.yaml"]
        )
        assert exported.exit_code == 0, exported.output
        assert UBUNTU[1] in (working_dir / "e.yaml").read_text()
        info = runner.invoke(cli, ["--offline", "info", UBUNTU[0], "-o", "json"])
        assert info.exit_code == 0, info.output
        listed = runner.invoke(cli, ["--offline", "list", "-o", "json"])
        assert listed.exit_code == 0, listed.output
        assert UBUNTU[0] in listed.stdout
        auth_manager_class.assert_not_called()
