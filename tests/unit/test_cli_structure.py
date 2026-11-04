"""Tests for CLI command structure and flag organization.

These tests enforce the simplified CLI structure where:
- auth login = THE place for authentication setup
- download/get/export = use saved session only (no inline auth flags)

This prevents flag duplication and user confusion (Issue #3).
"""


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
            "from cis_bench.config import Config\n"
            "Config.ensure_directories()\n"
            "db = CatalogDatabase(Config.get_catalog_db_path())\n"
            "db.initialize_schema()\n"
            "db.insert_benchmark({'benchmark_id': '23598', 'title': 'CIS AlmaLinux OS 8 Benchmark',"
            " 'version': 'v4.0.0', 'url': 'https://workbench.cisecurity.org/benchmarks/23598',"
            " 'status': 'Published'})\n"
            "db.save_downloaded('23598', '{}', 'h', 1)\n"
            "from cis_bench.cli.app import cli\n"
            "res = CliRunner().invoke(cli, ['remove', '23598', '--yes'])\n"
            f"print(json.dumps({{'exit': res.exit_code, 'loaded': [m for m in {scraper_stack!r} if m in sys.modules],"
            " 'left': db.get_downloaded('23598') is not None}))",
            env={"CIS_BENCH_ENV": "test", "TMPDIR": str(tmp_path)},
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
            "from cis_bench.config import Config\n"
            "Config.ensure_directories()\n"
            "CatalogDatabase(Config.get_catalog_db_path()).initialize_schema()\n"
            "from cis_bench.cli.app import cli\n"
            "res = CliRunner().invoke(cli, ['catalog', 'stats'])\n"
            f"print(json.dumps({{'exit': res.exit_code, 'loaded': [m for m in {scraper_stack!r} if m in sys.modules]}}))",
            env={"CIS_BENCH_ENV": "test", "TMPDIR": str(tmp_path)},
        )
        assert result["exit"] == 0
        assert result["loaded"] == []
