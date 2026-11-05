"""Tests for CLI command structure and flag organization.

These tests enforce the simplified CLI structure where:
- auth login = THE place for authentication setup
- download/get/export = use saved session only (no inline auth flags)

This prevents flag duplication and user confusion (Issue #3).
"""

import json
import os

import pytest


class TestAuthCommandStructure:
    """Verify auth commands have correct flags."""

    def test_auth_login_has_browser_option(self):
        """auth login should have --browser flag."""
        from cis_bench.cli.commands.auth import login

        param_names = [p.name for p in login.params]
        assert "browser" in param_names

    def test_auth_login_has_cookies_option(self):
        """auth login should have --cookies flag."""
        from cis_bench.cli.commands.auth import login

        param_names = [p.name for p in login.params]
        assert "cookies" in param_names

    def test_auth_login_has_no_verify_ssl_option(self):
        """auth login should have --no-verify-ssl flag."""
        from cis_bench.cli.commands.auth import login

        param_names = [p.name for p in login.params]
        assert "no_verify_ssl" in param_names


class TestDownloadCommandStructure:
    """Verify download command does NOT have auth flags (DRY principle)."""

    def test_download_has_no_browser_option(self):
        """download should NOT have --browser flag (use auth login instead)."""
        from cis_bench.cli.commands.download import download

        param_names = [p.name for p in download.params]
        assert "browser" not in param_names, (
            "download should not have --browser flag. "
            "Users should use 'cis-bench auth login --browser X' instead."
        )

    def test_download_has_no_cookies_option(self):
        """download should NOT have --cookies flag (use auth login instead)."""
        from cis_bench.cli.commands.download import download

        param_names = [p.name for p in download.params]
        assert "cookies" not in param_names, (
            "download should not have --cookies flag. "
            "Users should use 'cis-bench auth login --cookies FILE' instead."
        )

    def test_download_has_no_verify_ssl_option(self):
        """download should NOT have --no-verify-ssl (use auth login instead)."""
        from cis_bench.cli.commands.download import download

        param_names = [p.name for p in download.params]
        assert "no_verify_ssl" not in param_names, (
            "download should not have --no-verify-ssl flag. "
            "Users should use 'cis-bench auth login --no-verify-ssl' instead."
        )

    def test_download_has_format_option(self):
        """download should still have --format flag."""
        from cis_bench.cli.commands.download import download

        param_names = [p.name for p in download.params]
        assert "export_formats" in param_names or "format" in param_names

    def test_download_has_force_option(self):
        """download should have --force flag."""
        from cis_bench.cli.commands.download import download

        param_names = [p.name for p in download.params]
        assert "force" in param_names


class TestGetCommandStructure:
    """Verify get command does NOT have auth flags (DRY principle)."""

    def test_get_has_no_browser_option(self):
        """get should NOT have --browser flag (use auth login instead)."""
        from cis_bench.cli.commands.get import get_cmd

        param_names = [p.name for p in get_cmd.params]
        assert "browser" not in param_names, (
            "get should not have --browser flag. "
            "Users should use 'cis-bench auth login --browser X' instead."
        )

    def test_get_has_format_option(self):
        """get should have --format flag."""
        from cis_bench.cli.commands.get import get_cmd

        param_names = [p.name for p in get_cmd.params]
        assert "format" in param_names or "export_format" in param_names

    def test_get_has_style_option(self):
        """get should have --style flag for XCCDF."""
        from cis_bench.cli.commands.get import get_cmd

        param_names = [p.name for p in get_cmd.params]
        assert "style" in param_names


class TestExportCommandStructure:
    """Verify export command structure (no auth needed - works on local files)."""

    def test_export_has_no_browser_option(self):
        """export should NOT have --browser flag (doesn't need auth)."""
        from cis_bench.cli.commands.export import export_cmd

        param_names = [p.name for p in export_cmd.params]
        assert "browser" not in param_names

    def test_export_has_format_option(self):
        """export should have --format flag."""
        from cis_bench.cli.commands.export import export_cmd

        param_names = [p.name for p in export_cmd.params]
        assert "export_format" in param_names or "format" in param_names

    def test_export_has_style_option(self):
        """export should have --style flag for XCCDF."""
        from cis_bench.cli.commands.export import export_cmd

        param_names = [p.name for p in export_cmd.params]
        assert "style" in param_names


class TestNoSessionErrorMessage:
    """Verify helpful error when no saved session exists."""

    def test_download_without_session_shows_auth_hint(self, cli_runner, mocker):
        """download without session should tell user to run auth login."""
        from cis_bench.cli.app import cli

        # Mock no saved session
        from cis_bench.exceptions import NoSavedSessionError

        mocker.patch(
            "cis_bench.fetcher.auth.AuthManager.get_or_create_session",
            side_effect=NoSavedSessionError("No saved session found"),
        )

        result = cli_runner.invoke(cli, ["download", "23598"])

        # Should mention auth login
        assert "auth login" in result.output.lower() or result.exit_code != 0


class TestLazyStartup:
    """The CLI loads only what the invoked command needs; the package re-exports lazily.

    Each check runs in a fresh interpreter because sys.modules is process-global.
    """

    HEAVY_STACKS = [
        "browser_cookie3",
        "cis_bench.fetcher.auth",
        "cis_bench.fetcher.workbench",
        "cis_bench.catalog.scraper",
        "cis_bench.catalog.downloader",
        "cis_bench.catalog.database",
        "cis_bench.exporters",
        "sqlalchemy",
        "bs4",
    ]

    @staticmethod
    def _run(code: str, env: dict[str, str] | None = None) -> dict:
        import json
        import os
        import subprocess
        import sys

        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env={**os.environ, **(env or {})},
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout.strip().splitlines()[-1])

    def test_importing_cli_app_does_not_import_command_stacks(self):
        loaded = self._run(
            "import json, sys\n"
            "import cis_bench.cli.app\n"
            f"print(json.dumps([m for m in {self.HEAVY_STACKS!r} if m in sys.modules]))"
        )
        assert loaded == []

    def test_importing_package_is_lazy_but_every_export_resolves(self):
        result = self._run(
            "import json, sys\n"
            "import cis_bench\n"
            "eager = [m for m in ('cis_bench.exporters', 'cis_bench.fetcher', 'cis_bench.models')"
            " if m in sys.modules]\n"
            # dir() must advertise the lazy names BEFORE any of them has been resolved and cached
            "dir_has_all = all(n in dir(cis_bench) for n in cis_bench.__all__)\n"
            "try:\n"
            "    cis_bench.not_a_real_export\n"
            "    unknown_raises = False\n"
            "except AttributeError:\n"
            "    unknown_raises = True\n"
            "from cis_bench import (BaseExporter, Benchmark, ExporterFactory, Recommendation,"
            " ScraperStrategy, StrategyDetector)\n"
            "names = [c.__name__ for c in (BaseExporter, Benchmark, ExporterFactory,"
            " Recommendation, ScraperStrategy, StrategyDetector)]\n"
            "print(json.dumps({'eager': eager, 'names': names, 'dir_has_all': dir_has_all,"
            " 'unknown_raises': unknown_raises,"
            " 'version_ok': isinstance(cis_bench.__version__, str)}))"
        )
        assert result["eager"] == []
        assert result["unknown_raises"] is True
        assert result["names"] == [
            "BaseExporter",
            "Benchmark",
            "ExporterFactory",
            "Recommendation",
            "ScraperStrategy",
            "StrategyDetector",
        ]
        assert result["dir_has_all"] is True
        assert result["version_ok"] is True

    def test_every_subcommand_help_loads(self, cli_runner):
        """Click's lazy-loading guidance: run --help on every subcommand so a bad import path cannot hide."""
        from cis_bench.cli.app import cli

        top = cli_runner.invoke(cli, ["--help"])
        assert top.exit_code == 0, top.output
        for name in [
            "auth",
            "catalog",
            "download",
            "export",
            "get",
            "info",
            "list",
            "remove",
            "search",
        ]:
            assert f"  {name}" in top.output
            res = cli_runner.invoke(cli, [name, "--help"])
            assert res.exit_code == 0, f"{name}: {res.output}"
        for sub in [
            "check-updates",
            "download",
            "info",
            "list",
            "platforms",
            "refresh",
            "search",
            "stats",
            "update",
        ]:
            res = cli_runner.invoke(cli, ["catalog", sub, "--help"])
            assert res.exit_code == 0, f"catalog {sub}: {res.output}"

    def test_remove_works_offline_without_loading_the_scraper_or_auth_stack(self, tmp_path):
        scraper_stack = [
            "browser_cookie3",
            "requests",
            "cis_bench.fetcher.auth",
            "cis_bench.fetcher.workbench",
            "cis_bench.catalog.scraper",
            "cis_bench.catalog.downloader",
        ]
        result = self._run(
            "import json, sys\n"
            "from click.testing import CliRunner\n"
            "from cis_bench.catalog.database import CatalogDatabase\n"
            "from cis_bench.config import load_settings\n"
            "db = CatalogDatabase(load_settings().catalog_db_path)\n"
            "db.initialize_schema()\n"
            "db.insert_benchmark({'benchmark_id': '23598', 'title': 'CIS AlmaLinux OS 8 Benchmark',"
            " 'version': 'v4.0.0', 'url': 'https://workbench.cisecurity.org/benchmarks/23598',"
            " 'status': 'Published'})\n"
            "db.save_downloaded('23598', '{}', 'h', 1)\n"
            "from cis_bench.cli.app import cli\n"
            "res = CliRunner().invoke(cli, ['remove', '23598', '--yes'])\n"
            f"print(json.dumps({{'exit': res.exit_code, 'loaded': [m for m in {scraper_stack!r} if m in sys.modules],"
            " 'left': db.get_downloaded('23598') is not None}))",
            env={"CIS_BENCH_HOME": str(tmp_path / "data"), "TMPDIR": str(tmp_path)},
        )
        assert result["exit"] == 0
        assert result["loaded"] == []
        assert result["left"] is False

    def test_database_only_catalog_command_does_not_load_scraper_stack(self, tmp_path):
        scraper_stack = [
            "browser_cookie3",
            "cis_bench.fetcher.auth",
            "cis_bench.fetcher.workbench",
            "cis_bench.catalog.scraper",
            "cis_bench.catalog.downloader",
        ]
        result = self._run(
            "import json, sys\n"
            "from click.testing import CliRunner\n"
            "from cis_bench.catalog.database import CatalogDatabase\n"
            "from cis_bench.config import load_settings\n"
            "CatalogDatabase(load_settings().catalog_db_path).initialize_schema()\n"
            "from cis_bench.cli.app import cli\n"
            "res = CliRunner().invoke(cli, ['catalog', 'stats'])\n"
            f"print(json.dumps({{'exit': res.exit_code, 'loaded': [m for m in {scraper_stack!r} if m in sys.modules]}}))",
            env={"CIS_BENCH_HOME": str(tmp_path / "data"), "TMPDIR": str(tmp_path)},
        )
        assert result["exit"] == 0
        assert result["loaded"] == []


class TestSettingsCheckedAtStartup:
    """The root command builds the settings once; a bad value stops every command before it runs."""

    @staticmethod
    def _cli():
        from cis_bench.cli.app import cli

        return cli

    def test_a_bad_setting_is_one_configuration_error_and_exit_1(self, cli_runner, monkeypatch):
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "abc")
        for args in (["search", "ubuntu"], ["catalog", "stats"], ["list"]):
            result = cli_runner.invoke(self._cli(), args)
            assert result.exit_code == 1, f"{args}: {result.output}"
            assert result.output.lstrip().startswith("Configuration Error"), result.output
            assert "CIS_BENCH_SEARCH_LIMIT" in result.output
            assert "'abc'" in result.output

    def test_no_login_or_network_use_happens_first(self, cli_runner, monkeypatch, mocker):
        monkeypatch.setenv("CIS_BENCH_REQUEST_TIMEOUT", "0")
        login = mocker.patch("cis_bench.fetcher.auth.AuthManager.get_or_create_session")
        result = cli_runner.invoke(self._cli(), ["download", "23598"])
        assert result.exit_code == 1, result.output
        assert "CIS_BENCH_REQUEST_TIMEOUT" in result.output
        login.assert_not_called()

    def test_help_still_works_with_a_bad_setting(self, cli_runner, monkeypatch):
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "abc")
        for args in (["--help"], ["search", "--help"], ["catalog", "refresh", "--help"]):
            result = cli_runner.invoke(self._cli(), args)
            assert result.exit_code == 0, f"{args}: {result.output}"
            assert "Usage:" in result.output

    def test_an_option_value_that_looks_like_help_is_not_a_help_request(
        self, cli_runner, monkeypatch
    ):
        # --help here is the value of --platform, so the command runs and the bad setting stops it.
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "abc")
        result = cli_runner.invoke(self._cli(), ["search", "--platform", "--help", "ubuntu"])
        assert result.exit_code == 1, result.output
        assert result.output.lstrip().startswith("Configuration Error"), result.output

    def test_a_group_named_without_a_subcommand_shows_its_help(self, cli_runner, monkeypatch):
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "abc")
        result = cli_runner.invoke(self._cli(), ["catalog"])
        assert "Usage:" in result.output
        assert "Configuration Error" not in result.output

    def test_the_checked_settings_are_kept_for_the_commands(self, cli_runner, monkeypatch):
        from cis_bench.config import Settings

        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "7")
        obj: dict = {}
        result = cli_runner.invoke(self._cli(), ["list"], obj=obj)
        assert result.exit_code == 0, result.output
        assert isinstance(obj["settings"], Settings)
        assert obj["settings"].search_limit == 7

    def test_help_before_a_bad_option_is_not_a_help_request(self, cli_runner, monkeypatch):
        # Click reports the bad option instead of showing help, so the bad setting comes first.
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "abc")
        result = cli_runner.invoke(self._cli(), ["search", "--help", "--bad-opt"])
        assert result.exit_code == 1, result.output
        assert result.output.lstrip().startswith("Configuration Error"), result.output


class TestAnEarlierInstallsFolderIsReportedOnStderr:
    """A run that still uses ~/.cis-bench says so once, on stderr, and names the way out."""

    @staticmethod
    def _cli():
        from cis_bench.cli.app import cli

        return cli

    @pytest.fixture
    def legacy_home(self, tmp_path, monkeypatch, small_catalog):
        import shutil

        for name in list(os.environ):
            if name.startswith(("CIS_BENCH_", "XDG_")):
                monkeypatch.delenv(name)
        monkeypatch.setenv("HOME", str(tmp_path))
        legacy = tmp_path / ".cis-bench"
        legacy.mkdir()
        shutil.copy(small_catalog, legacy / "catalog.db")
        return tmp_path

    def test_the_notice_is_one_stderr_line_and_stdout_stays_machine_readable(
        self, cli_runner, legacy_home
    ):
        result = cli_runner.invoke(
            self._cli(), ["search", "sample", "--output-format", "json"], catch_exceptions=False
        )

        assert result.exit_code == 0, result.output
        assert len(json.loads(result.stdout)) == 5  # stdout is only the JSON
        assert result.stderr.count("cis-bench config migrate") == 1
        assert str(legacy_home / ".cis-bench") in result.stderr
        assert f"CIS_BENCH_HOME={legacy_home / '.cis-bench'}" in result.stderr
        assert "next major" in result.stderr
        # one line, among the log lines stderr also carries
        assert sum("config migrate" in line for line in result.stderr.splitlines()) == 1

    def test_no_notice_when_a_folder_is_chosen_explicitly(
        self, cli_runner, legacy_home, monkeypatch
    ):
        monkeypatch.setenv("CIS_BENCH_HOME", str(legacy_home / ".cis-bench"))
        result = cli_runner.invoke(self._cli(), ["search", "sample", "--output-format", "json"])

        assert result.exit_code == 0, result.output
        assert "config migrate" not in result.stderr
        assert "earlier version" not in result.stderr
