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
    db.close()


def _refused(result, command: str, needs: str):
    """The run stopped at the offline refusal: exit 1, the message on stderr, no session."""
    assert result.exit_code == 1, result.output
    assert f"{command} needs CIS WorkBench to {needs}, and {OFFLINE_HINT}" in result.stderr
    assert "Nothing was sent to WorkBench." in result.stderr
    assert "Run 'cis-bench cache status' to see what is available offline." in result.stderr


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


# --------------------------------------------------------------------------------------------
# cache status: what the tool can do without WorkBench, read from catalog.db and the folders
# --------------------------------------------------------------------------------------------

FULL_REFRESH = "2026-11-02T08:30:00+00:00"


def _session_saved(data_dir, when):
    """A saved session file whose modification time is ``when`` (login writes it then)."""
    import os

    session = data_dir / "session.cookies"
    session.write_text("#LWP-Cookies-2.0\n")
    os.utime(session, (when.timestamp(), when.timestamp()))
    return session


class TestCacheStatus:
    def test_cache_status_lists_catalog_downloads_and_session(self, runner, catalog, data_dir):
        from datetime import UTC, datetime

        catalog.cached(UBUNTU[0])
        catalog.cached(RHEL[0], version="v1.0.0")
        catalog.set_metadata("last_full_scrape", FULL_REFRESH)
        _session_saved(data_dir, datetime(2026, 11, 3, 9, 0, tzinfo=UTC))

        result = runner.invoke(cli, ["--offline", "cache", "status"])

        assert result.exit_code == 0, result.output
        assert "Catalog: 3 benchmarks" in result.output
        assert "Downloaded benchmarks (2)" in result.output
        for benchmark_id, title, version in (
            (UBUNTU[0], UBUNTU[1], "v2.0.1"),
            (RHEL[0], RHEL[1], "v1.0.0"),
        ):
            row = next(line for line in result.output.splitlines() if benchmark_id in line)
            assert version in row
            assert title.split()[1] in row
        assert "Last update: never" in result.output
        assert "Session: saved" in result.output

    def test_json_is_one_object_with_the_same_facts(self, runner, catalog, data_dir):
        import json
        from datetime import UTC, datetime

        catalog.cached(UBUNTU[0])
        catalog.set_metadata("last_full_scrape", FULL_REFRESH)
        saved = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
        session = _session_saved(data_dir, saved)

        result = runner.invoke(cli, ["--offline", "cache", "status", "--output-format", "json"])

        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout) == {
            "catalog": {
                "present": True,
                "benchmarks": 3,
                "last_full_refresh": FULL_REFRESH,
                "last_update": None,
            },
            "downloaded": [
                {
                    "benchmark_id": UBUNTU[0],
                    "title": UBUNTU[1],
                    "version": "v2.0.1",
                    "downloaded_at": "2026-11-01T12:00:00+00:00",
                }
            ],
            "session": {"present": True, "file": str(session), "saved_at": saved.isoformat()},
        }

    def test_nothing_cached_is_three_none_lines_and_creates_no_catalog(
        self, runner, data_dir, no_network
    ):
        import json

        table = runner.invoke(cli, ["--offline", "cache", "status"])
        structured = runner.invoke(cli, ["cache", "status", "--output-format", "json"])

        assert table.exit_code == 0, table.output
        assert "Catalog: none" in table.output
        assert "Downloaded benchmarks: none" in table.output
        assert "Session: none" in table.output
        assert structured.exit_code == 0, structured.output
        assert json.loads(structured.stdout) == {
            "catalog": {
                "present": False,
                "benchmarks": 0,
                "last_full_refresh": None,
                "last_update": None,
            },
            "downloaded": [],
            "session": {
                "present": False,
                "file": str(data_dir / "session.cookies"),
                "saved_at": None,
            },
        }
        assert not (data_dir / "catalog.db").exists()

    def test_a_download_the_catalog_does_not_list_has_the_title_list_shows(
        self, runner, catalog, sample_recommendation_complete
    ):
        import json
        from datetime import UTC, datetime

        from cis_bench.catalog.downloader import CatalogDownloader
        from cis_bench.models.benchmark import Benchmark

        CatalogDownloader(catalog).cache(
            "99999",
            Benchmark(
                title="Example Appliance Benchmark",
                benchmark_id="99999",
                url="https://workbench.cisecurity.org/benchmarks/99999",
                version="v1.0.0",
                downloaded_at=datetime(2026, 11, 1, 12, 0, tzinfo=UTC),
                scraper_version="v2_2026_01",
                total_recommendations=1,
                recommendations=[sample_recommendation_complete],
            ),
        )

        status = runner.invoke(cli, ["--offline", "cache", "status", "-o", "json"])
        listed = runner.invoke(cli, ["--offline", "list", "-o", "json"])

        assert status.exit_code == 0, status.output
        titles = {
            item["benchmark_id"]: item["title"] for item in json.loads(status.stdout)["downloaded"]
        }
        listed_titles = {
            item["benchmark_id"]: item["title"] for item in json.loads(listed.stdout)["downloaded"]
        }
        assert titles == listed_titles == {"99999": "Example Appliance Benchmark"}

    def test_an_unreadable_copy_the_catalog_does_not_list_is_still_listed(self, runner, catalog):
        import json

        catalog.save_downloaded("99999", "{}", "h", 1)

        status = runner.invoke(cli, ["--offline", "cache", "status", "-o", "json"])
        table = runner.invoke(cli, ["--offline", "cache", "status"])

        assert status.exit_code == 0, status.output
        assert [
            (item["benchmark_id"], item["title"])
            for item in json.loads(status.stdout)["downloaded"]
        ] == [("99999", None)]
        assert table.exit_code == 0, table.output
        assert "unreadable cached copy" in table.output

    def test_a_catalog_file_listing_no_benchmarks_is_no_catalog(self, runner, data_dir, no_network):
        import json

        from cis_bench.catalog.database import CatalogDatabase

        db = CatalogDatabase(data_dir / "catalog.db")
        db.initialize_schema()
        db.close()

        result = runner.invoke(cli, ["--offline", "cache", "status", "-o", "json"])

        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["catalog"] == {
            "present": False,
            "benchmarks": 0,
            "last_full_refresh": None,
            "last_update": None,
        }

    def test_a_catalog_file_that_cannot_be_read_is_an_error_naming_it(
        self, runner, data_dir, no_network
    ):
        catalog_db = data_dir / "catalog.db"
        catalog_db.write_bytes(b"this is not a SQLite database" * 100)

        result = runner.invoke(cli, ["--offline", "cache", "status"])

        assert result.exit_code == 1, result.output
        assert result.exception is None or isinstance(result.exception, SystemExit)
        assert f"{catalog_db} cannot be read" in result.stderr
        assert "Catalog: none" not in result.output

    def test_last_update_is_reported_when_the_catalog_was_updated(self, runner, catalog):
        import json

        catalog.set_metadata("last_update_scrape", "2026-11-04T10:00:00+00:00")

        result = runner.invoke(cli, ["--offline", "cache", "status", "-o", "json"])

        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["catalog"]["last_update"] == "2026-11-04T10:00:00+00:00"


class TestCacheStatusCountsTheCatalog:
    @pytest.mark.parametrize(("count", "expected"), [(1, "1 benchmark"), (2, "2 benchmarks")])
    def test_the_catalog_line_agrees_with_the_number(self, capsys, count, expected):
        from cis_bench.cli.commands.cache import _print_catalog

        _print_catalog(
            {"present": True, "benchmarks": count, "last_full_refresh": None, "last_update": None}
        )

        assert f"Catalog: {expected}\n" in capsys.readouterr().out
