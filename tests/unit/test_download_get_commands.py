"""Unit tests for download and get commands - error paths and missing coverage.

This module tests the uncovered lines in:
- cli/commands/download.py
- cli/commands/get.py

Focuses on:
- Logging configuration
- Error handling paths
- File-based URL input
- Edge cases in argument handling
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from cis_bench.cli.app import cli
from cis_bench.exceptions import NoSavedSessionError, TLSVerificationError
from cis_bench.models.benchmark import Benchmark, Recommendation

# ============================================================================
# Shared Fixtures
# ============================================================================


@pytest.fixture
def runner():
    """Create Click CLI test runner and prune closed stderr handlers on teardown."""
    import logging

    cli_runner = CliRunner()
    yield cli_runner
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        stream = getattr(handler, "stream", None)
        if stream is not None and getattr(stream, "closed", False):
            root_logger.removeHandler(handler)


@pytest.fixture
def sample_benchmark():
    """Create a sample benchmark for testing."""
    return Benchmark(
        title="CIS Test Benchmark",
        benchmark_id="12345",
        url="https://workbench.cisecurity.org/benchmarks/12345",
        version="v1.0.0",
        downloaded_at=datetime(2025, 1, 1),
        scraper_version="1.0.0",
        total_recommendations=2,
        recommendations=[
            Recommendation(
                ref="1.1.1",
                title="Test Recommendation 1",
                url="https://workbench.cisecurity.org/sections/12345/recommendations/1",
                assessment_status="Automated",
                profiles=["Level 1"],
                description="Test description",
                rationale="Test rationale",
                impact="Test impact",
                audit="Test audit",
                remediation="Test remediation",
            ),
            Recommendation(
                ref="1.1.2",
                title="Test Recommendation 2",
                url="https://workbench.cisecurity.org/sections/12345/recommendations/2",
                assessment_status="Manual",
                profiles=["Level 2"],
                description="Test description 2",
                rationale="Test rationale 2",
                impact="Test impact 2",
                audit="Test audit 2",
                remediation="Test remediation 2",
            ),
        ],
    )


# ============================================================================
# Download Command Tests - Error Paths
# ============================================================================


class TestDownloadLoggingConfig:
    """Test download command logging configuration (lines 71-73)."""

    def test_download_verbose_flag_configures_logging(self, runner):
        """Download with --verbose flag configures debug logging."""
        with patch("cis_bench.fetcher.auth.AuthManager.get_or_create_session") as mock_auth:
            mock_auth.side_effect = NoSavedSessionError("No saved session found")

            with patch("cis_bench.utils.logging_config.LoggingConfig") as mock_logging:
                result = runner.invoke(cli, ["download", "12345", "--verbose"])

                # Should call logging setup
                mock_logging.setup_from_flags.assert_called_once_with(quiet=False, verbose=True)

    def test_download_debug_flag_configures_logging(self, runner):
        """Download with --debug flag configures debug logging."""
        with patch("cis_bench.fetcher.auth.AuthManager.get_or_create_session") as mock_auth:
            mock_auth.side_effect = NoSavedSessionError("No saved session found")

            with patch("cis_bench.utils.logging_config.LoggingConfig") as mock_logging:
                result = runner.invoke(cli, ["download", "12345", "--debug"])

                mock_logging.setup_from_flags.assert_called_once_with(quiet=False, verbose=True)

    def test_download_quiet_flag_configures_logging(self, runner):
        """Download with --quiet flag configures quiet logging."""
        with patch("cis_bench.fetcher.auth.AuthManager.get_or_create_session") as mock_auth:
            mock_auth.side_effect = NoSavedSessionError("No saved session found")

            with patch("cis_bench.utils.logging_config.LoggingConfig") as mock_logging:
                result = runner.invoke(cli, ["download", "12345", "--quiet"])

                mock_logging.setup_from_flags.assert_called_once_with(quiet=True, verbose=False)


class TestDownloadAuthErrors:
    """Test download command authentication error handling (lines 96-102)."""

    def test_download_no_session_shows_auth_required(self, runner):
        """Download without session shows authentication required message."""
        with patch("cis_bench.fetcher.auth.AuthManager.get_or_create_session") as mock_auth:
            mock_auth.side_effect = NoSavedSessionError("No saved session found")

            result = runner.invoke(cli, ["download", "12345"])

            assert result.exit_code == 1
            assert "Authentication Required" in result.output
            assert "cis-bench auth login" in result.output

    def test_download_generic_auth_error_shows_refresh_message(self, runner):
        """Download with generic auth error shows session refresh message."""
        with patch("cis_bench.fetcher.auth.AuthManager.get_or_create_session") as mock_auth:
            mock_auth.side_effect = Exception("Cookie extraction failed [/x]")

            result = runner.invoke(cli, ["download", "12345"])

            assert result.exit_code == 1
            assert result.output.count("Cookie extraction failed [/x]") == 1
            assert "Traceback" not in result.output
            assert "Authentication Failed" in result.output
            assert "session may have expired" in result.output
            assert "cis-bench auth login" in result.output

    def test_download_forwards_configured_verify_ssl_and_surfaces_invalid_workbench_url(
        self, runner, sample_benchmark, tmp_path, monkeypatch, auth_manager_class
    ):
        """Download builds its AuthManager with CIS_BENCH_VERIFY_SSL and surfaces invalid URL errors."""
        auth = auth_manager_class.return_value
        with patch("cis_bench.fetcher.workbench.WorkbenchScraper") as mock_scraper_cls:
            monkeypatch.setenv("CIS_BENCH_VERIFY_SSL", "false")
            monkeypatch.setenv("CIS_BENCH_HOME", str(tmp_path / "missing"))
            auth.get_or_create_session.return_value = Mock()
            mock_scraper = Mock()
            mock_scraper.download_benchmark.return_value = sample_benchmark
            mock_scraper_cls.return_value = mock_scraper

            ok_result = runner.invoke(cli, ["download", "12345"])
            assert ok_result.exit_code == 0, ok_result.output
            assert auth_manager_class.call_args.kwargs["verify_ssl"] is False
            auth.get_or_create_session.assert_called_once_with()

        monkeypatch.setenv("CIS_BENCH_WORKBENCH_URL", "http://workbench.cisecurity.org")
        bad_url_result = runner.invoke(cli, ["download", "12345"])
        assert bad_url_result.exit_code == 1
        assert "Configuration Error" in bad_url_result.output
        assert "CIS_BENCH_WORKBENCH_URL" in bad_url_result.output
        assert "Authentication Required" not in bad_url_result.output
        auth.get_or_create_session.assert_called_once_with()


class TestDownloadRequestTimeoutSetting:
    """A bad CIS_BENCH_REQUEST_TIMEOUT is a configuration error reported before any network call."""

    def test_download_rejects_bad_request_timeout_before_auth(self, runner, tmp_path, monkeypatch):
        monkeypatch.setenv("CIS_BENCH_REQUEST_TIMEOUT", "abc")
        with (
            patch("cis_bench.fetcher.auth.AuthManager.get_or_create_session") as mock_auth,
        ):
            monkeypatch.setenv("CIS_BENCH_HOME", str(tmp_path / "missing"))
            result = runner.invoke(cli, ["download", "12345"])

        assert result.exit_code == 1
        assert "Configuration Error" in result.output
        assert "CIS_BENCH_REQUEST_TIMEOUT" in result.output
        mock_auth.assert_not_called()


class TestDownloadFileInput:
    """Test download command file-based URL input (lines 112-119, 125)."""

    def test_download_from_file_with_urls(
        self, runner, sample_benchmark, tmp_path, monkeypatch, working_dir
    ):
        """Download reads full URLs from file."""
        # Create URL file
        url_file = tmp_path / "urls.txt"
        url_file.write_text(
            "https://workbench.cisecurity.org/benchmarks/12345\n"
            "https://workbench.cisecurity.org/benchmarks/67890\n"
        )

        with patch("cis_bench.fetcher.auth.AuthManager.get_or_create_session") as mock_auth:
            mock_session = Mock()
            mock_auth.return_value = mock_session

            with patch("cis_bench.fetcher.workbench.WorkbenchScraper") as mock_scraper_class:
                mock_scraper = Mock()
                mock_scraper_class.return_value = mock_scraper
                mock_scraper.download_benchmark.return_value = sample_benchmark

                # A data folder with no catalog.db: no cache check
                monkeypatch.setenv("CIS_BENCH_HOME", "no-catalog")

                result = runner.invoke(cli, ["download", "--file", str(url_file)])

                assert result.exit_code == 0
                # Should download both benchmarks
                assert mock_scraper.download_benchmark.call_count == 2

    def test_download_from_file_with_ids(
        self, runner, sample_benchmark, tmp_path, monkeypatch, working_dir
    ):
        """Download reads benchmark IDs from file and constructs URLs."""
        # Create ID file
        id_file = tmp_path / "ids.txt"
        id_file.write_text("12345\n67890\n# This is a comment\n")

        with patch("cis_bench.fetcher.auth.AuthManager.get_or_create_session") as mock_auth:
            mock_session = Mock()
            mock_auth.return_value = mock_session

            with patch("cis_bench.fetcher.workbench.WorkbenchScraper") as mock_scraper_class:
                mock_scraper = Mock()
                mock_scraper_class.return_value = mock_scraper
                mock_scraper.download_benchmark.return_value = sample_benchmark

                # A data folder with no catalog.db: no cache check
                monkeypatch.setenv("CIS_BENCH_HOME", "no-catalog")

                result = runner.invoke(cli, ["download", "--file", str(id_file)])

                assert result.exit_code == 0
                # Should download 2 benchmarks (comment ignored)
                assert mock_scraper.download_benchmark.call_count == 2

    def test_download_url_argument_passed_through(
        self, runner, sample_benchmark, monkeypatch, working_dir
    ):
        """Download passes through full URLs from arguments."""
        with patch("cis_bench.fetcher.auth.AuthManager.get_or_create_session") as mock_auth:
            mock_session = Mock()
            mock_auth.return_value = mock_session

            with patch("cis_bench.fetcher.workbench.WorkbenchScraper") as mock_scraper_class:
                mock_scraper = Mock()
                mock_scraper_class.return_value = mock_scraper
                mock_scraper.download_benchmark.return_value = sample_benchmark

                # A data folder with no catalog.db: no cache check
                monkeypatch.setenv("CIS_BENCH_HOME", "no-catalog")

                result = runner.invoke(
                    cli,
                    [
                        "download",
                        "https://workbench.cisecurity.org/benchmarks/12345",
                    ],
                )

                assert result.exit_code == 0
                # Verify URL was passed through (not modified)
                call_args = mock_scraper.download_benchmark.call_args
                assert "12345" in call_args[0][0]


class TestDownloadMissingArgs:
    """Test download command with missing arguments (lines 129-134)."""

    def test_download_no_ids_no_file_shows_error(self, runner):
        """Download without IDs or file shows error."""
        with patch("cis_bench.fetcher.auth.AuthManager.get_or_create_session") as mock_auth:
            mock_session = Mock()
            mock_auth.return_value = mock_session

            result = runner.invoke(cli, ["download"])

            assert result.exit_code == 1
            assert "Must specify benchmark IDs or --file" in result.output

    def test_download_empty_file_shows_error(self, runner, tmp_path):
        """Download with empty file shows no benchmarks error."""
        # Create empty URL file
        url_file = tmp_path / "empty.txt"
        url_file.write_text("# Only comments\n# No actual URLs\n")

        with patch("cis_bench.fetcher.auth.AuthManager.get_or_create_session") as mock_auth:
            mock_session = Mock()
            mock_auth.return_value = mock_session

            result = runner.invoke(cli, ["download", "--file", str(url_file)])

            assert result.exit_code == 1
            assert "No benchmarks to download" in result.output


class TestDownloadCacheSkip:
    """Test download command cache skip behavior (lines 157->170)."""

    def test_download_skips_cached_benchmark(self, runner, tmp_path, monkeypatch):
        """Download skips already cached benchmarks."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))

        with patch("cis_bench.fetcher.auth.AuthManager.get_or_create_session") as mock_auth:
            mock_session = Mock()
            mock_auth.return_value = mock_session

            with patch("cis_bench.fetcher.workbench.WorkbenchScraper") as mock_scraper_class:
                mock_scraper = Mock()
                mock_scraper_class.return_value = mock_scraper

                with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                    mock_db = Mock()
                    mock_db_class.return_value = mock_db
                    # Return cached benchmark
                    mock_db.get_downloaded.return_value = {
                        "benchmark_id": "12345",
                        "downloaded_at": "2025-01-01T00:00:00",
                        "recommendation_count": 10,
                    }

                    result = runner.invoke(cli, ["download", "12345"])

                    assert result.exit_code == 0
                    assert "already cached" in result.output
                    assert "Use --force to re-download" in result.output
                    # Should NOT have called download
                    mock_scraper.download_benchmark.assert_not_called()

    def test_download_force_overrides_cache(self, runner, sample_benchmark, tmp_path, monkeypatch):
        """Download with --force re-downloads cached benchmark."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))

        with patch("cis_bench.fetcher.auth.AuthManager.get_or_create_session") as mock_auth:
            mock_session = Mock()
            mock_auth.return_value = mock_session

            with patch("cis_bench.fetcher.workbench.WorkbenchScraper") as mock_scraper_class:
                mock_scraper = Mock()
                mock_scraper_class.return_value = mock_scraper
                mock_scraper.download_benchmark.return_value = sample_benchmark

                with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                    mock_db = Mock()
                    mock_db_class.return_value = mock_db

                    result = runner.invoke(cli, ["download", "12345", "--force"])

                    assert result.exit_code == 0
                    # Should have called download despite cache check
                    mock_scraper.download_benchmark.assert_called()


class TestDownloadExportErrors:
    """Test download command export error handling (lines 241-243)."""

    def test_download_export_failure_continues(
        self, runner, sample_benchmark, tmp_path, monkeypatch
    ):
        """Download continues after export failure for a format."""
        monkeypatch.setenv("CIS_BENCH_HOME", str(tmp_path / "nonexistent"))

        with patch("cis_bench.fetcher.auth.AuthManager.get_or_create_session") as mock_auth:
            mock_session = Mock()
            mock_auth.return_value = mock_session

            with patch("cis_bench.fetcher.workbench.WorkbenchScraper") as mock_scraper_class:
                mock_scraper = Mock()
                mock_scraper_class.return_value = mock_scraper
                mock_scraper.download_benchmark.return_value = sample_benchmark

                with patch("cis_bench.cli.commands.download.ExporterFactory") as mock_factory:
                    mock_exporter = Mock()
                    mock_exporter.export.side_effect = Exception("Disk full [/x]")
                    mock_exporter.format_name.return_value = "JSON"
                    mock_exporter.get_file_extension.return_value = "json"
                    mock_factory.create.return_value = mock_exporter

                    result = runner.invoke(cli, ["download", "12345"])

                    assert result.exit_code == 1
                    assert result.output.count("export failed: Disk full [/x]") == 1
                    assert "Traceback" not in result.output
                    assert "Download complete!" not in result.output


class TestDownloadBenchmarkErrors:
    """Test download command benchmark download errors (lines 247-253)."""

    def test_download_benchmark_failure_continues_to_next(
        self, runner, sample_benchmark, tmp_path, monkeypatch
    ):
        """Download continues to next benchmark after failure."""
        monkeypatch.setenv("CIS_BENCH_HOME", str(tmp_path / "nonexistent"))

        with patch("cis_bench.fetcher.auth.AuthManager.get_or_create_session") as mock_auth:
            mock_session = Mock()
            mock_auth.return_value = mock_session

            with patch("cis_bench.fetcher.workbench.WorkbenchScraper") as mock_scraper_class:
                mock_scraper = Mock()
                mock_scraper_class.return_value = mock_scraper

                # First fails, second succeeds
                mock_scraper.download_benchmark.side_effect = [
                    Exception("Network error [/x]"),
                    sample_benchmark,
                ]

                with patch("cis_bench.cli.commands.download.ExporterFactory") as mock_factory:
                    mock_exporter = Mock()
                    mock_exporter.format_name.return_value = "JSON"
                    mock_exporter.get_file_extension.return_value = "json"
                    # A real exporter writes the file; the command then reports its size.
                    mock_exporter.export.side_effect = lambda _benchmark, path: open(
                        path, "w"
                    ).close()
                    mock_factory.create.return_value = mock_exporter

                    result = runner.invoke(cli, ["download", "12345", "67890"])

                    # The second benchmark is still downloaded, but the run reports failure.
                    assert mock_scraper.download_benchmark.call_count == 2
                    assert result.exit_code == 1
                    assert "Error" in result.output
                    assert result.output.count("Error: Network error [/x]") == 1
                    assert "Download complete!" not in result.output
                    assert "1 of 2" in result.output
                    # A failed benchmark is reported in one line; the traceback is debug detail.
                    assert "Traceback" not in result.output

    def test_download_stops_at_an_expired_session_and_exits_1(
        self, runner, sample_benchmark, tmp_path, monkeypatch
    ):
        from cis_bench.exceptions import AuthenticationError

        monkeypatch.setenv("CIS_BENCH_HOME", str(tmp_path / "nonexistent"))
        with (
            patch(
                "cis_bench.fetcher.auth.AuthManager.get_or_create_session",
                return_value=Mock(),
            ),
            patch("cis_bench.fetcher.workbench.WorkbenchScraper") as mock_scraper_class,
        ):
            mock_scraper = Mock()
            mock_scraper_class.return_value = mock_scraper
            mock_scraper.download_benchmark.side_effect = [
                AuthenticationError(
                    "WorkBench returned the login page for https://workbench.cisecurity.org/"
                    "benchmarks/12345; the saved session has expired [/x]"
                ),
                sample_benchmark,
            ]

            result = runner.invoke(cli, ["download", "12345", "67890"])

        assert result.exit_code == 1
        assert mock_scraper.download_benchmark.call_count == 1  # 67890 never attempted
        assert result.output.count("[/x]") == 1  # long message wraps; the markup token must survive
        assert "cis-bench auth login" in result.output
        assert "Traceback" not in result.output
        assert "Download complete!" not in result.output


# ============================================================================
# Get Command Tests - Error Paths
# ============================================================================


class TestGetLoggingConfig:
    """Test get command logging configuration (lines 78-80)."""

    def test_get_verbose_flag_configures_logging(self, runner, tmp_path, monkeypatch):
        """Get with --verbose flag configures debug logging."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "100")

        with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
            mock_db = Mock()
            mock_db_class.return_value = mock_db

            with patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class:
                mock_search = Mock()
                mock_search_class.return_value = mock_search
                mock_search.search.return_value = []

                with patch("cis_bench.utils.logging_config.LoggingConfig") as mock_logging:
                    result = runner.invoke(cli, ["get", "test", "--verbose", "--non-interactive"])

                    mock_logging.setup_from_flags.assert_called_once_with(quiet=False, verbose=True)

    def test_get_quiet_flag_configures_logging(self, runner, tmp_path, monkeypatch):
        """Get with --quiet flag configures quiet logging."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "100")

        with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
            mock_db = Mock()
            mock_db_class.return_value = mock_db

            with patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class:
                mock_search = Mock()
                mock_search_class.return_value = mock_search
                mock_search.search.return_value = []

                with patch("cis_bench.utils.logging_config.LoggingConfig") as mock_logging:
                    result = runner.invoke(cli, ["get", "test", "--quiet", "--non-interactive"])

                    mock_logging.setup_from_flags.assert_called_once_with(quiet=True, verbose=False)


class TestGetSearchErrors:
    """Test get command search error handling (lines 120-122)."""

    def test_get_search_failure_shows_error(self, runner, tmp_path, monkeypatch):
        """Get shows error when search fails."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "100")

        with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
            mock_db = Mock()
            mock_db_class.return_value = mock_db

            with patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class:
                mock_search = Mock()
                mock_search_class.return_value = mock_search
                mock_search.search.side_effect = Exception("Database corrupted [/x]")

                result = runner.invoke(cli, ["get", "test", "--non-interactive"])

                assert result.exit_code == 1
                assert result.output.count("Search failed: Database corrupted [/x]") == 1
                assert "Traceback" not in result.output


class TestGetTitleWrapping:
    """The get results table shows a long title whole instead of cutting it."""

    def test_get_shows_a_long_title_whole(self, runner, tmp_path, monkeypatch):
        """A title longer than the column folds onto further lines; no character is dropped."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "100")

        with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
            mock_db = Mock()
            mock_db_class.return_value = mock_db

            with patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class:
                mock_search = Mock()
                mock_search_class.return_value = mock_search

                # One 100-character word: wider than the title column, so it must fold
                long_title = "A" * 100
                mock_search.search.return_value = [
                    {
                        "benchmark_id": "1",
                        "title": long_title,
                        "version": "v1",
                        "status": "Published",
                    },
                    {
                        "benchmark_id": "2",
                        "title": "Short title",
                        "version": "v2",
                        "status": "Published",
                    },
                ]

                result = runner.invoke(cli, ["get", "test", "--non-interactive"])

                table_rows = [line for line in result.output.splitlines() if "│" in line]
                assert sum(line.count("A") for line in table_rows) == 100
                assert "\u2026" not in result.output
                assert "..." not in result.output


class TestGetInteractiveSelection:
    """Test get command interactive selection (lines 156-178)."""

    def test_get_interactive_selection_cancelled(self, runner, tmp_path, monkeypatch):
        """Get shows cancelled message when user cancels selection."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "100")

        with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
            mock_db = Mock()
            mock_db_class.return_value = mock_db

            with patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class:
                mock_search = Mock()
                mock_search_class.return_value = mock_search
                mock_search.search.return_value = [
                    {"benchmark_id": "1", "title": "A", "version": "v1", "status": "P"},
                    {"benchmark_id": "2", "title": "B", "version": "v2", "status": "P"},
                ]

                with patch("cis_bench.cli.commands.get.questionary") as mock_q:
                    mock_select = Mock()
                    mock_select.ask.return_value = None  # User cancelled
                    mock_q.select.return_value = mock_select

                    result = runner.invoke(cli, ["get", "test"])

                    assert result.exit_code == 0
                    assert "Cancelled" in result.output

    def test_get_interactive_selection_exception_falls_back(self, runner, tmp_path, monkeypatch):
        """Get falls back to non-interactive when questionary fails."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "100")

        with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
            mock_db = Mock()
            mock_db_class.return_value = mock_db

            with patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class:
                mock_search = Mock()
                mock_search_class.return_value = mock_search
                mock_search.search.return_value = [
                    {"benchmark_id": "1", "title": "A", "version": "v1", "status": "P"},
                    {"benchmark_id": "2", "title": "B", "version": "v2", "status": "P"},
                ]

                with patch("cis_bench.cli.commands.get.questionary") as mock_q:
                    mock_q.select.side_effect = Exception("Terminal not supported")

                    result = runner.invoke(cli, ["get", "test"])

                    # Should fall back to non-interactive mode
                    assert result.exit_code == 0
                    assert "Multiple matches found" in result.output

    def test_get_interactive_selection_success(
        self, runner, sample_benchmark, tmp_path, monkeypatch, working_dir
    ):
        """Get with interactive selection proceeds to download."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "100")

        with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
            mock_db = Mock()
            mock_db_class.return_value = mock_db

            with patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class:
                mock_search = Mock()
                mock_search_class.return_value = mock_search
                mock_search.search.return_value = [
                    {
                        "benchmark_id": "12345",
                        "title": "CIS Test A",
                        "version": "v1",
                        "status": "Published",
                    },
                    {
                        "benchmark_id": "67890",
                        "title": "CIS Test B",
                        "version": "v2",
                        "status": "Published",
                    },
                ]

                # Mock already downloaded
                mock_db.get_downloaded.return_value = {
                    "benchmark_id": "12345",
                    "content_json": sample_benchmark.model_dump_json(),
                    "downloaded_at": datetime.now(),
                }

                with patch("cis_bench.cli.commands.get.questionary") as mock_q:
                    mock_select = Mock()
                    mock_select.ask.return_value = "12345: CIS Test A (v1)"
                    mock_q.select.return_value = mock_select

                    result = runner.invoke(cli, ["get", "test", "-f", "json"])

                    assert result.exit_code == 0
                    assert "Selected: CIS Test A" in result.output


class TestGetDownloadErrors:
    """Test get command download error handling (lines 240-251)."""

    def test_get_download_auth_required(self, runner, tmp_path, monkeypatch):
        """Get shows auth required when download session missing."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "100")

        with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
            mock_db = Mock()
            mock_db_class.return_value = mock_db
            mock_db.get_downloaded.return_value = None  # Not cached

            with patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class:
                mock_search = Mock()
                mock_search_class.return_value = mock_search
                mock_search.search.return_value = [
                    {
                        "benchmark_id": "12345",
                        "title": "Test",
                        "version": "v1",
                        "status": "Published",
                    }
                ]

                with patch("cis_bench.fetcher.auth.AuthManager") as mock_auth:
                    mock_auth.return_value.get_or_create_session.side_effect = NoSavedSessionError(
                        "No saved session found"
                    )

                    result = runner.invoke(cli, ["get", "test", "--non-interactive"])

                    assert result.exit_code == 1
                    assert "Authentication Required" in result.output

    @staticmethod
    def _invoke_get_with_failing_download(runner, tmp_path, monkeypatch, global_flags=()):
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()
        with (
            patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class,
            patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class,
            patch("cis_bench.fetcher.auth.AuthManager") as mock_auth,
            patch("cis_bench.cli.helpers.download_helper.download_with_progress") as mock_dl,
        ):
            monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
            monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "100")
            mock_db_class.return_value.get_downloaded.return_value = None  # Not cached
            mock_search_class.return_value.search.return_value = [
                {"benchmark_id": "12345", "title": "Test", "version": "v1", "status": "Published"}
            ]
            mock_auth.return_value.get_or_create_session.return_value = Mock()
            mock_dl.side_effect = Exception("Network timeout [/x]")

            return runner.invoke(cli, [*global_flags, "get", "test", "--non-interactive"])

    def test_get_download_generic_error(self, runner, tmp_path, monkeypatch):
        """Get prints a failed download as one line, verbatim, without a traceback."""
        result = self._invoke_get_with_failing_download(runner, tmp_path, monkeypatch)

        assert result.exit_code == 1
        assert result.output.count("Download failed: Network timeout [/x]") == 1
        assert "Traceback" not in result.output

    def test_get_download_error_traceback_is_written_with_verbose(
        self, runner, tmp_path, monkeypatch
    ):
        result = self._invoke_get_with_failing_download(
            runner, tmp_path, monkeypatch, global_flags=["-v"]
        )

        assert result.exit_code == 1
        assert "Traceback" in result.output

    def test_get_download_expired_session_shows_the_relogin_message(
        self, runner, tmp_path, monkeypatch
    ):
        from cis_bench.exceptions import AuthenticationError

        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()
        with (
            patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class,
            patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class,
            patch("cis_bench.fetcher.auth.AuthManager") as mock_auth,
            patch("cis_bench.cli.helpers.download_helper.download_with_progress") as mock_dl,
        ):
            monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
            monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "100")
            mock_db_class.return_value.get_downloaded.return_value = None
            mock_search_class.return_value.search.return_value = [
                {"benchmark_id": "12345", "title": "Test", "version": "v1", "status": "Published"}
            ]
            mock_auth.return_value.get_or_create_session.return_value = Mock()
            mock_dl.side_effect = AuthenticationError(
                "WorkBench returned the login page; the saved session has expired [/x]"
            )

            result = runner.invoke(cli, ["get", "test", "--non-interactive"])

        assert result.exit_code == 1
        assert result.output.count("the saved session has expired [/x]") == 1
        assert "cis-bench auth login" in result.output
        assert "Download failed" not in result.output

    def test_get_forwards_configured_verify_ssl_and_surfaces_invalid_workbench_url(
        self, runner, sample_benchmark, tmp_path, monkeypatch
    ):
        """Get builds its AuthManager with CIS_BENCH_VERIFY_SSL and surfaces invalid URL errors."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        with (
            patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class,
            patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class,
            patch("cis_bench.fetcher.auth.AuthManager") as mock_auth,
            patch("cis_bench.cli.helpers.download_helper.download_with_progress") as mock_dl,
        ):
            monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
            monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "100")
            monkeypatch.setenv("CIS_BENCH_VERIFY_SSL", "false")
            mock_db = Mock()
            mock_db_class.return_value = mock_db
            mock_db.get_downloaded.side_effect = [
                None,
                {
                    "benchmark_id": "12345",
                    "content_json": sample_benchmark.model_dump_json(),
                    "downloaded_at": datetime.now(),
                },
            ]
            mock_search = Mock()
            mock_search_class.return_value = mock_search
            mock_search.search.return_value = [
                {
                    "benchmark_id": "12345",
                    "title": "Test",
                    "version": "v1",
                    "status": "Published",
                }
            ]
            mock_auth.return_value.get_or_create_session.return_value = Mock()
            mock_dl.return_value = sample_benchmark

            ok_res = runner.invoke(
                cli,
                [
                    "get",
                    "test",
                    "--format",
                    "json",
                    "--output",
                    str(tmp_path / "out.json"),
                    "--non-interactive",
                ],
            )
            assert ok_res.exit_code == 0, ok_res.output
            assert mock_auth.call_args.kwargs["verify_ssl"] is False
            mock_auth.return_value.get_or_create_session.assert_called_once_with()

            mock_db.get_downloaded.side_effect = None
            mock_db.get_downloaded.return_value = None
            monkeypatch.setenv("CIS_BENCH_WORKBENCH_URL", "http://workbench.cisecurity.org")
            bad_url_res = runner.invoke(cli, ["get", "test", "--non-interactive"])
            assert bad_url_res.exit_code == 1
            assert "Configuration Error" in bad_url_res.output
            assert "CIS_BENCH_WORKBENCH_URL" in bad_url_res.output
            assert "Authentication Required" not in bad_url_res.output
            mock_auth.return_value.get_or_create_session.assert_called_once_with()


class TestGetXccdfExport:
    """Test get command XCCDF export with style (lines 269, 274->280)."""

    def test_get_xccdf_format_uses_style(self, runner, sample_benchmark, tmp_path, monkeypatch):
        """Get with xccdf format uses --style option."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "100")

        with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
            mock_db = Mock()
            mock_db_class.return_value = mock_db

            with patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class:
                mock_search = Mock()
                mock_search_class.return_value = mock_search
                mock_search.search.return_value = [
                    {
                        "benchmark_id": "12345",
                        "title": "Test",
                        "version": "v1",
                        "status": "Published",
                    }
                ]

                # Already downloaded
                mock_db.get_downloaded.return_value = {
                    "benchmark_id": "12345",
                    "content_json": sample_benchmark.model_dump_json(),
                    "downloaded_at": datetime.now(),
                }

                with patch("cis_bench.cli.commands.get.ExporterFactory") as mock_factory:
                    mock_exporter = Mock()
                    mock_exporter.format_name.return_value = "XCCDF"
                    mock_exporter.get_file_extension.return_value = "xml"
                    mock_factory.create.return_value = mock_exporter

                    result = runner.invoke(
                        cli,
                        [
                            "get",
                            "test",
                            "-f",
                            "xccdf",
                            "--style",
                            "cis",
                            "--non-interactive",
                        ],
                    )

                    # Verify style was passed to factory
                    mock_factory.create.assert_called_once_with("xccdf", style="cis")

    def test_get_auto_generates_output_filename(
        self, runner, sample_benchmark, tmp_path, monkeypatch, working_dir
    ):
        """Get auto-generates output filename when not specified."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "100")

        with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
            mock_db = Mock()
            mock_db_class.return_value = mock_db

            with patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class:
                mock_search = Mock()
                mock_search_class.return_value = mock_search
                mock_search.search.return_value = [
                    {
                        "benchmark_id": "12345",
                        "title": "Test",
                        "version": "v1",
                        "status": "Published",
                    }
                ]

                mock_db.get_downloaded.return_value = {
                    "benchmark_id": "12345",
                    "content_json": sample_benchmark.model_dump_json(),
                    "downloaded_at": datetime.now(),
                }

                with patch("cis_bench.cli.commands.get.ExporterFactory") as mock_factory:
                    mock_exporter = Mock()
                    mock_exporter.format_name.return_value = "YAML"
                    mock_exporter.get_file_extension.return_value = "yaml"

                    # Make export create the file so os.path.getsize works
                    def create_file(benchmark, output_path):
                        Path(output_path).write_text("test content")

                    mock_exporter.export.side_effect = create_file
                    mock_factory.create.return_value = mock_exporter

                    result = runner.invoke(
                        cli,
                        ["get", "test", "-f", "yaml", "--non-interactive"],
                    )

                    assert result.exit_code == 0
                    # Should have used auto-generated filename
                    call_args = mock_exporter.export.call_args
                    assert "benchmark_12345.yaml" in str(call_args)


class TestGetExportErrors:
    """Test get command export error handling (lines 293-296)."""

    def test_get_export_failure_shows_error(self, runner, sample_benchmark, tmp_path, monkeypatch):
        """Get shows error when export fails."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "100")

        with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
            mock_db = Mock()
            mock_db_class.return_value = mock_db

            with patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class:
                mock_search = Mock()
                mock_search_class.return_value = mock_search
                mock_search.search.return_value = [
                    {
                        "benchmark_id": "12345",
                        "title": "Test",
                        "version": "v1",
                        "status": "Published",
                    }
                ]

                mock_db.get_downloaded.return_value = {
                    "benchmark_id": "12345",
                    "content_json": sample_benchmark.model_dump_json(),
                    "downloaded_at": datetime.now(),
                }

                with patch("cis_bench.cli.commands.get.ExporterFactory") as mock_factory:
                    mock_exporter = Mock()
                    mock_exporter.format_name.return_value = "JSON"
                    mock_exporter.get_file_extension.return_value = "json"
                    mock_exporter.export.side_effect = Exception("Write permission denied [/x]")
                    mock_factory.create.return_value = mock_exporter

                    result = runner.invoke(cli, ["get", "test", "-f", "json", "--non-interactive"])

                    assert result.exit_code == 1
                    assert result.output.count("Export failed: Write permission denied [/x]") == 1
                    assert "Traceback" not in result.output


class TestOutsideTextIsPrintedVerbatim:
    """Titles, versions, statuses, the query and paths reach the terminal as written."""

    @staticmethod
    def _writing_exporter(mock_factory):
        exporter = mock_factory.create.return_value
        exporter.format_name.return_value = "JSON"
        exporter.get_file_extension.return_value = "json"
        exporter.export.side_effect = lambda _benchmark, path: Path(path).write_text("{}")
        return exporter

    def test_get_prints_query_title_and_output_path_verbatim(
        self, runner, sample_benchmark, tmp_path, monkeypatch, working_dir
    ):
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()
        with (
            patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class,
            patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class,
            patch("cis_bench.cli.commands.get.ExporterFactory") as mock_factory,
        ):
            monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
            monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "100")
            mock_search_class.return_value.search.return_value = [
                {"benchmark_id": "12345", "title": "CIS T [/t]", "version": "v1", "status": "P"}
            ]
            mock_db_class.return_value.get_downloaded.return_value = {
                "benchmark_id": "12345",
                "content_json": sample_benchmark.model_dump_json(),
                "downloaded_at": datetime.now(),
            }
            self._writing_exporter(mock_factory)

            result = runner.invoke(
                cli, ["get", "web[x]", "-f", "json", "-o", "out[o].json", "--non-interactive"]
            )

        assert result.exit_code == 0, result.output
        assert "Searching for: web[x]" in result.output
        assert "Found: CIS T [/t]" in result.output
        assert "Output: out[o].json" in result.output

    def test_get_lists_matches_verbatim(self, runner, tmp_path, monkeypatch):
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()
        with (
            patch("cis_bench.catalog.database.CatalogDatabase"),
            patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class,
        ):
            monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
            monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "100")
            mock_search_class.return_value.search.return_value = [
                {
                    "benchmark_id": "1",
                    "title": "CIS A [/a]",
                    "version": "v1 [/v]",
                    "status": "P [/s]",
                },
                {"benchmark_id": "2", "title": "CIS B", "version": "v2", "status": "Published"},
            ]

            result = runner.invoke(cli, ["get", "web[x]", "--non-interactive"])

        assert "matching 'web[x]'" in result.output
        assert "CIS A [/a]" in result.output
        assert "v1 [/v]" in result.output
        assert "P [/s]" in result.output

    def test_get_without_a_catalog_prints_the_query_verbatim(self, runner, tmp_path, monkeypatch):
        monkeypatch.setenv("CIS_BENCH_HOME", str(tmp_path / "missing"))
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "100")

        result = runner.invoke(cli, ["get", "web[x]"])

        assert result.exit_code == 1
        assert 'cis-bench get "web[x]"' in result.output

    def test_get_prints_downloaded_title_verbatim(
        self, runner, sample_benchmark, tmp_path, monkeypatch, working_dir
    ):
        sample_benchmark.title = "CIS T [/t]"
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()
        with (
            patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class,
            patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class,
            patch("cis_bench.fetcher.auth.AuthManager"),
            patch(
                "cis_bench.cli.helpers.download_helper.download_with_progress",
                return_value=sample_benchmark,
            ),
            patch("cis_bench.cli.commands.get.ExporterFactory") as mock_factory,
        ):
            monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
            monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "100")
            mock_search_class.return_value.search.return_value = [
                {"benchmark_id": "23598", "title": "CIS T", "version": "v1", "status": "P"}
            ]
            mock_db_class.return_value.get_downloaded.side_effect = [
                None,
                {"benchmark_id": "23598", "content_json": sample_benchmark.model_dump_json()},
            ]
            self._writing_exporter(mock_factory)

            result = runner.invoke(cli, ["get", "web", "-f", "json", "--non-interactive"])

        assert result.exit_code == 0, result.output
        assert "Downloaded: CIS T [/t]" in result.output

    def test_download_prints_title_verbatim(
        self, runner, sample_benchmark, tmp_path, monkeypatch, working_dir
    ):
        sample_benchmark.title = "CIS T [/t]"
        with (
            patch("cis_bench.fetcher.auth.AuthManager.get_or_create_session"),
            patch("cis_bench.fetcher.workbench.WorkbenchScraper") as mock_scraper_class,
            patch("cis_bench.cli.commands.download.ExporterFactory") as mock_factory,
        ):
            monkeypatch.setenv("CIS_BENCH_HOME", str(tmp_path / "nonexistent"))
            mock_scraper_class.return_value.download_benchmark.return_value = sample_benchmark
            self._writing_exporter(mock_factory)

            result = runner.invoke(cli, ["download", "23598", "-o", "o[x]"])

        assert result.exit_code == 0, result.output
        assert "Downloaded: CIS T [/t]" in result.output
        assert "Exported JSON: o[x]/cis_t_t.json" in result.output


class TestGetNonInteractiveMode:
    """Test get command non-interactive mode display (lines 181->192)."""

    def test_get_non_interactive_shows_instructions(self, runner, tmp_path, monkeypatch):
        """Get in non-interactive mode shows helpful instructions."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "100")

        with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
            mock_db = Mock()
            mock_db_class.return_value = mock_db

            with patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class:
                mock_search = Mock()
                mock_search_class.return_value = mock_search
                mock_search.search.return_value = [
                    {
                        "benchmark_id": "1",
                        "title": "Ubuntu 20.04",
                        "version": "v1",
                        "status": "Published",
                    },
                    {
                        "benchmark_id": "2",
                        "title": "Ubuntu 22.04",
                        "version": "v2",
                        "status": "Published",
                    },
                ]

                result = runner.invoke(cli, ["get", "ubuntu", "--non-interactive"])

                assert result.exit_code == 0
                assert "Multiple matches found" in result.output
                assert "Be more specific" in result.output
                assert "cis-bench download" in result.output


class TestCanonicalContentHashConsistency:
    """Verify catalog download, cli download, and cli get write identical canonical JSON and hashes."""

    def test_download_get_and_catalog_downloader_share_identical_content_hash_and_validate_json(
        self, runner, sample_benchmark, tmp_path, monkeypatch, working_dir
    ):
        """All three download paths store identical content_json and content_hash, and get reads via model_validate_json."""
        from unittest.mock import create_autospec

        from cis_bench.catalog.database import CatalogDatabase
        from cis_bench.catalog.downloader import CatalogDownloader
        from cis_bench.fetcher.workbench import WorkbenchScraper

        def make_seeded_db(data_dir_name: str) -> CatalogDatabase:
            """A seeded catalog.db in its own data folder under tmp_path."""
            (tmp_path / data_dir_name).mkdir()
            db = CatalogDatabase(tmp_path / data_dir_name / "catalog.db")
            db.initialize_schema()
            db.insert_benchmark(
                {
                    "benchmark_id": "12345",
                    "title": "CIS Test Benchmark",
                    "version": "v1.0.0",
                    "url": "https://workbench.cisecurity.org/benchmarks/12345",
                    "status": "Published",
                    "is_latest": True,
                }
            )
            return db

        db_catalog = make_seeded_db("catalog_path")
        db_download = make_seeded_db("download_path")
        db_get = make_seeded_db("get_path")

        try:
            scraper = create_autospec(WorkbenchScraper, instance=True)
            scraper.base_url = "https://workbench.cisecurity.org"
            scraper.download_benchmark.return_value = sample_benchmark
            cat_result = CatalogDownloader(db_catalog, scraper).download_by_id("12345")
            row_catalog = db_catalog.get_downloaded("12345")
            assert row_catalog is not None

            with (
                patch(
                    "cis_bench.fetcher.auth.AuthManager.get_or_create_session",
                    return_value=Mock(),
                ),
                patch(
                    "cis_bench.fetcher.workbench.WorkbenchScraper",
                    return_value=scraper,
                ),
            ):
                monkeypatch.setenv("CIS_BENCH_HOME", str(db_download.db_path.parent))
                dl_res = runner.invoke(cli, ["download", "12345", "--force"])
            assert dl_res.exit_code == 0, dl_res.output

            out_yaml = Path("exported_from_get.yaml")
            with (
                patch(
                    "cis_bench.fetcher.auth.AuthManager.get_or_create_session",
                    return_value=Mock(),
                ),
                patch(
                    "cis_bench.fetcher.workbench.WorkbenchScraper",
                    return_value=scraper,
                ),
                patch.object(
                    Benchmark,
                    "model_validate_json",
                    wraps=Benchmark.model_validate_json,
                ) as validate_spy,
            ):
                monkeypatch.setenv("CIS_BENCH_HOME", str(db_get.db_path.parent))
                monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "100")
                get_res = runner.invoke(
                    cli,
                    [
                        "get",
                        "CIS Test Benchmark",
                        "--format",
                        "yaml",
                        "--output",
                        str(out_yaml),
                        "--non-interactive",
                    ],
                )
            assert get_res.exit_code == 0, get_res.output
            assert out_yaml.exists()

            row_download = db_download.get_downloaded("12345")
            row_get = db_get.get_downloaded("12345")
            assert row_download is not None
            assert row_get is not None

            assert row_download["content_hash"] == cat_result["content_hash"]
            assert row_download["content_hash"] == row_catalog["content_hash"]
            assert row_get["content_hash"] == row_catalog["content_hash"]
            assert row_download["content_json"] == row_catalog["content_json"]
            assert row_get["content_json"] == row_catalog["content_json"]
            validate_spy.assert_called_once_with(row_get["content_json"])
        finally:
            db_catalog.engine.dispose()
            db_download.engine.dispose()
            db_get.engine.dispose()


class TestVerifiedTLSByDefault:
    """download and get verify certificates unless CIS_BENCH_VERIFY_SSL opts out."""

    def test_download_defaults_to_verified_tls(
        self, runner, sample_benchmark, tmp_path, monkeypatch, auth_manager_class
    ):
        monkeypatch.delenv("CIS_BENCH_VERIFY_SSL", raising=False)
        auth = auth_manager_class.return_value
        with patch("cis_bench.fetcher.workbench.WorkbenchScraper") as mock_scraper_cls:
            monkeypatch.setenv("CIS_BENCH_HOME", str(tmp_path / "missing"))
            auth.get_or_create_session.return_value = Mock()
            mock_scraper = Mock()
            mock_scraper.download_benchmark.return_value = sample_benchmark
            mock_scraper_cls.return_value = mock_scraper

            result = runner.invoke(cli, ["download", "12345"])

            assert result.exit_code == 0, result.output
            assert auth_manager_class.call_args.kwargs["verify_ssl"] is True
            auth.get_or_create_session.assert_called_once_with()

    def test_download_reports_tls_failure_without_session_hint(self, runner, tmp_path, monkeypatch):
        """A certificate trust failure is not an expired session; say what it is and stop."""
        monkeypatch.delenv("CIS_BENCH_VERIFY_SSL", raising=False)
        with (
            patch(
                "cis_bench.fetcher.auth.AuthManager.get_or_create_session",
                side_effect=TLSVerificationError(
                    "TLS certificate verification failed for workbench.cisecurity.org: "
                    "unable to get local issuer certificate. If a proxy re-signs HTTPS "
                    "traffic, point REQUESTS_CA_BUNDLE at its CA bundle; to skip "
                    "verification entirely set CIS_BENCH_VERIFY_SSL=false."
                ),
            ),
        ):
            monkeypatch.setenv("CIS_BENCH_HOME", str(tmp_path / "missing"))
            result = runner.invoke(cli, ["download", "12345"])

        assert result.exit_code == 1
        assert "TLS certificate verification failed for workbench.cisecurity.org" in result.output
        assert "REQUESTS_CA_BUNDLE" in result.output
        assert "session may have expired" not in result.output
        assert "Authentication Failed" not in result.output

    def test_download_reports_an_unreachable_workbench_without_session_hint(
        self, runner, tmp_path, monkeypatch
    ):
        """A network failure during the session check is not an expired session."""
        from cis_bench.exceptions import FetchError

        with patch(
            "cis_bench.fetcher.auth.AuthManager.get_or_create_session",
            side_effect=FetchError(
                "https://workbench.cisecurity.org/benchmarks", 3, "Read timed out"
            ),
        ):
            monkeypatch.setenv("CIS_BENCH_HOME", str(tmp_path / "missing"))
            result = runner.invoke(cli, ["download", "12345"])

        assert result.exit_code == 1
        assert "Could not reach WorkBench" in result.output
        assert "https://workbench.cisecurity.org/benchmarks: Read timed out after 3 attempts" in (
            result.output.replace("\n", "")
        )
        assert "saved session was kept" in result.output
        assert "may have expired" not in result.output
        assert "auth login" not in result.output
        assert "Traceback" not in result.output

    def test_get_defaults_to_verified_tls(self, runner, sample_benchmark, tmp_path, monkeypatch):
        monkeypatch.delenv("CIS_BENCH_VERIFY_SSL", raising=False)
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        with (
            patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class,
            patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class,
            patch("cis_bench.fetcher.auth.AuthManager") as mock_auth,
            patch("cis_bench.cli.helpers.download_helper.download_with_progress") as mock_dl,
        ):
            monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
            mock_db = Mock()
            mock_db_class.return_value = mock_db
            mock_db.get_downloaded.side_effect = [
                None,
                {
                    "benchmark_id": "12345",
                    "content_json": sample_benchmark.model_dump_json(),
                    "downloaded_at": datetime.now(),
                },
            ]
            mock_search = Mock()
            mock_search_class.return_value = mock_search
            mock_search.search.return_value = [
                {"benchmark_id": "12345", "title": "Test", "version": "v1", "status": "Published"}
            ]
            mock_auth.return_value.get_or_create_session.return_value = Mock()
            mock_dl.return_value = sample_benchmark

            result = runner.invoke(
                cli,
                [
                    "get",
                    "test",
                    "--format",
                    "json",
                    "--output",
                    str(tmp_path / "out.json"),
                    "--non-interactive",
                ],
            )

            assert result.exit_code == 0, result.output
            assert mock_auth.call_args.kwargs["verify_ssl"] is True
            mock_auth.return_value.get_or_create_session.assert_called_once_with()

    def test_get_reports_tls_failure_as_such(self, runner, tmp_path, monkeypatch):
        monkeypatch.delenv("CIS_BENCH_VERIFY_SSL", raising=False)
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()
        with (
            patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class,
            patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class,
            patch("cis_bench.fetcher.auth.AuthManager") as mock_auth,
        ):
            monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
            mock_db = Mock()
            mock_db_class.return_value = mock_db
            mock_db.get_downloaded.return_value = None
            mock_search = Mock()
            mock_search_class.return_value = mock_search
            mock_search.search.return_value = [
                {"benchmark_id": "12345", "title": "Test", "version": "v1", "status": "Published"}
            ]
            mock_auth.return_value.get_or_create_session.side_effect = TLSVerificationError(
                "TLS certificate verification failed for workbench.cisecurity.org: boom. "
                "If a proxy re-signs HTTPS traffic, point REQUESTS_CA_BUNDLE at its CA bundle; "
                "to skip verification entirely set CIS_BENCH_VERIFY_SSL=false."
            )

            result = runner.invoke(cli, ["get", "test", "--non-interactive"])

        assert result.exit_code == 1
        assert "TLS certificate verification failed for workbench.cisecurity.org" in result.output
        assert "REQUESTS_CA_BUNDLE" in result.output
        assert "Download failed" not in result.output

    def test_get_reports_an_unreachable_workbench_as_such(self, runner, tmp_path, monkeypatch):
        from cis_bench.exceptions import FetchError

        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()
        with (
            patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class,
            patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class,
            patch("cis_bench.fetcher.auth.AuthManager") as mock_auth,
        ):
            monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
            mock_db = Mock()
            mock_db_class.return_value = mock_db
            mock_db.get_downloaded.return_value = None
            mock_search = Mock()
            mock_search_class.return_value = mock_search
            mock_search.search.return_value = [
                {"benchmark_id": "12345", "title": "Test", "version": "v1", "status": "Published"}
            ]
            mock_auth.return_value.get_or_create_session.side_effect = FetchError(
                "https://workbench.cisecurity.org/benchmarks", 3, "Read timed out"
            )

            result = runner.invoke(cli, ["get", "test", "--non-interactive"])

        assert result.exit_code == 1
        assert "Could not reach WorkBench" in result.output
        assert "saved session was kept" in result.output
        assert "may have expired" not in result.output
        assert "Traceback" not in result.output


class TestDownloadReferenceValidation:
    """download validates every benchmark reference before it authenticates or downloads."""

    @pytest.mark.parametrize(
        ("ref", "fragment"),
        [
            (
                "http://workbench.cisecurity.org/benchmarks/23598",
                "must match configured WorkBench origin",
            ),
            ("https://evil.example/benchmarks/23598", "must match configured WorkBench origin"),
            (
                "https://workbench.cisecurity.org@evil.example/benchmarks/23598",
                "must match configured WorkBench origin",
            ),
            (
                "https://workbench.cisecurity.org/benchmarks/../admin",
                "must match configured WorkBench origin",
            ),
            (
                "https://workbench.cisecurity.org/benchmarks/abc",
                "path must match /benchmarks/<digits>",
            ),
            ("abc", "Invalid benchmark"),
        ],
    )
    def test_rejects_bad_reference_before_any_network_call(self, runner, ref, fragment):
        with (
            patch("cis_bench.fetcher.auth.AuthManager.get_or_create_session") as mock_auth,
            patch("cis_bench.fetcher.workbench.WorkbenchScraper") as mock_scraper_cls,
        ):
            result = runner.invoke(cli, ["download", ref])

        assert result.exit_code == 1
        # Rich wraps long lines in the test console; compare on collapsed whitespace
        assert fragment in " ".join(result.output.split())
        mock_auth.assert_not_called()
        mock_scraper_cls.assert_not_called()

    def test_accepts_id_canonical_url_and_decorated_url(
        self, runner, sample_benchmark, tmp_path, monkeypatch
    ):
        with (
            patch(
                "cis_bench.fetcher.auth.AuthManager.get_or_create_session",
                return_value=Mock(),
            ),
            patch("cis_bench.fetcher.workbench.WorkbenchScraper") as mock_scraper_cls,
        ):
            monkeypatch.setenv("CIS_BENCH_HOME", str(tmp_path / "missing"))
            mock_scraper = Mock()
            mock_scraper.download_benchmark.return_value = sample_benchmark
            mock_scraper_cls.return_value = mock_scraper

            result = runner.invoke(
                cli,
                [
                    "download",
                    "23598",
                    "https://workbench.cisecurity.org/benchmarks/22605",
                    "https://workbench.cisecurity.org/benchmarks/11111?tab=overview#top",
                ],
            )

        assert result.exit_code == 0, result.output
        downloaded = [c.args[0] for c in mock_scraper.download_benchmark.call_args_list]
        assert downloaded == [
            "https://workbench.cisecurity.org/benchmarks/23598",
            "https://workbench.cisecurity.org/benchmarks/22605",
            "https://workbench.cisecurity.org/benchmarks/11111",
        ]

    def test_file_with_one_bad_line_reports_the_line_and_downloads_nothing(self, runner, tmp_path):
        url_file = tmp_path / "urls.txt"
        url_file.write_text(
            "# comment\n23598\nhttp://workbench.cisecurity.org/benchmarks/22605\n11111\n"
        )
        with (
            patch("cis_bench.fetcher.auth.AuthManager.get_or_create_session") as mock_auth,
            patch("cis_bench.fetcher.workbench.WorkbenchScraper") as mock_scraper_cls,
        ):
            result = runner.invoke(cli, ["download", "--file", str(url_file)])

        assert result.exit_code == 1
        flat = " ".join(result.output.split())
        assert "line 3 of" in flat
        assert url_file.name in flat
        assert "must match configured WorkBench origin" in flat
        mock_auth.assert_not_called()
        mock_scraper_cls.assert_not_called()


class TestTypedAuthErrors:
    """No saved session is a typed condition; the commands never match on message text."""

    def test_download_no_saved_session_is_caught_by_type(self, runner):
        with patch(
            "cis_bench.fetcher.auth.AuthManager.get_or_create_session",
            side_effect=NoSavedSessionError("session.cookies is missing"),
        ):
            result = runner.invoke(cli, ["download", "23598"])

        assert result.exit_code == 1
        assert "Authentication Required" in result.output
        assert "cis-bench auth login" in result.output

    def test_download_invalid_workbench_url_is_a_configuration_error(self, runner, monkeypatch):
        """A bad CIS_BENCH_WORKBENCH_URL is reported as configuration, never as a bad reference."""
        monkeypatch.setenv("CIS_BENCH_WORKBENCH_URL", "http://evil.example")
        with patch("cis_bench.fetcher.auth.AuthManager.get_or_create_session") as mock_auth:
            result = runner.invoke(cli, ["download", "23598"])

        flat = " ".join(result.output.split())
        assert result.exit_code == 1
        assert "Configuration Error" in flat
        assert "CIS_BENCH_WORKBENCH_URL" in flat
        assert "Authentication Required" not in flat
        mock_auth.assert_not_called()

    def test_download_file_with_invalid_workbench_url_does_not_blame_a_line(
        self, runner, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("CIS_BENCH_WORKBENCH_URL", "http://evil.example")
        url_file = tmp_path / "ids.txt"
        url_file.write_text("23598\n")
        with patch("cis_bench.fetcher.auth.AuthManager.get_or_create_session") as mock_auth:
            result = runner.invoke(cli, ["download", "--file", str(url_file)])

        flat = " ".join(result.output.split())
        assert result.exit_code == 1
        assert "Configuration Error" in flat
        assert "line 1" not in flat
        mock_auth.assert_not_called()

    def test_get_invalid_workbench_url_is_a_configuration_error(
        self, runner, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("CIS_BENCH_WORKBENCH_URL", "http://evil.example")
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()
        with (
            patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class,
            patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class,
            patch("cis_bench.fetcher.auth.AuthManager") as mock_auth,
        ):
            monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
            mock_db_class.return_value.get_downloaded.return_value = None
            mock_search_class.return_value.search.return_value = [
                {"benchmark_id": "23598", "title": "Test", "version": "v1", "status": "Published"}
            ]
            result = runner.invoke(cli, ["get", "test", "--non-interactive"])

        flat = " ".join(result.output.split())
        assert result.exit_code == 1
        assert "Configuration Error" in flat
        assert "CIS_BENCH_WORKBENCH_URL" in flat
        mock_auth.return_value.get_or_create_session.assert_not_called()

    def test_get_rejects_invalid_catalog_id_before_authenticating(
        self, runner, tmp_path, monkeypatch
    ):
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()
        with (
            patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class,
            patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class,
            patch("cis_bench.fetcher.auth.AuthManager") as mock_auth,
        ):
            monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
            mock_db_class.return_value.get_downloaded.return_value = None
            mock_search_class.return_value.search.return_value = [
                {"benchmark_id": "../etc", "title": "Test", "version": "v1", "status": "Published"}
            ]
            result = runner.invoke(cli, ["get", "test", "--non-interactive"])

        flat = " ".join(result.output.split())
        assert result.exit_code == 1
        assert "Invalid benchmark" in flat
        mock_auth.return_value.get_or_create_session.assert_not_called()

    def test_get_no_saved_session_is_caught_by_type(self, runner, tmp_path, monkeypatch):
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()
        with (
            patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class,
            patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class,
            patch("cis_bench.fetcher.auth.AuthManager") as mock_auth,
        ):
            monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
            mock_db_class.return_value.get_downloaded.return_value = None
            mock_search_class.return_value.search.return_value = [
                {"benchmark_id": "23598", "title": "Test", "version": "v1", "status": "Published"}
            ]
            mock_auth.return_value.get_or_create_session.side_effect = NoSavedSessionError(
                "session.cookies is missing"
            )

            result = runner.invoke(cli, ["get", "test", "--non-interactive"])

        assert result.exit_code == 1
        assert "Authentication Required" in result.output
        assert "Download failed" not in result.output
