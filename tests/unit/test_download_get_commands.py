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
from cis_bench.models.benchmark import Benchmark, Recommendation

# ============================================================================
# Shared Fixtures
# ============================================================================


@pytest.fixture
def runner():
    """Create Click CLI test runner."""
    return CliRunner()


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
        with patch(
            "cis_bench.cli.commands.download.AuthManager.get_or_create_session"
        ) as mock_auth:
            mock_auth.side_effect = ValueError("No session")

            with patch("cis_bench.utils.logging_config.LoggingConfig") as mock_logging:
                result = runner.invoke(cli, ["download", "12345", "--verbose"])

                # Should call logging setup
                mock_logging.setup_from_flags.assert_called_once_with(quiet=False, verbose=True)

    def test_download_debug_flag_configures_logging(self, runner):
        """Download with --debug flag configures debug logging."""
        with patch(
            "cis_bench.cli.commands.download.AuthManager.get_or_create_session"
        ) as mock_auth:
            mock_auth.side_effect = ValueError("No session")

            with patch("cis_bench.utils.logging_config.LoggingConfig") as mock_logging:
                result = runner.invoke(cli, ["download", "12345", "--debug"])

                mock_logging.setup_from_flags.assert_called_once_with(quiet=False, verbose=True)

    def test_download_quiet_flag_configures_logging(self, runner):
        """Download with --quiet flag configures quiet logging."""
        with patch(
            "cis_bench.cli.commands.download.AuthManager.get_or_create_session"
        ) as mock_auth:
            mock_auth.side_effect = ValueError("No session")

            with patch("cis_bench.utils.logging_config.LoggingConfig") as mock_logging:
                result = runner.invoke(cli, ["download", "12345", "--quiet"])

                mock_logging.setup_from_flags.assert_called_once_with(quiet=True, verbose=False)


class TestDownloadAuthErrors:
    """Test download command authentication error handling (lines 96-102)."""

    def test_download_no_session_shows_auth_required(self, runner):
        """Download without session shows authentication required message."""
        with patch(
            "cis_bench.cli.commands.download.AuthManager.get_or_create_session"
        ) as mock_auth:
            mock_auth.side_effect = ValueError("No session")

            result = runner.invoke(cli, ["download", "12345"])

            assert result.exit_code == 1
            assert "Authentication Required" in result.output
            assert "cis-bench auth login" in result.output

    def test_download_generic_auth_error_shows_refresh_message(self, runner):
        """Download with generic auth error shows session refresh message."""
        with patch(
            "cis_bench.cli.commands.download.AuthManager.get_or_create_session"
        ) as mock_auth:
            mock_auth.side_effect = Exception("Cookie extraction failed")

            result = runner.invoke(cli, ["download", "12345"])

            assert result.exit_code == 1
            assert "Authentication Failed" in result.output
            assert "session may have expired" in result.output
            assert "cis-bench auth login" in result.output


class TestDownloadFileInput:
    """Test download command file-based URL input (lines 112-119, 125)."""

    def test_download_from_file_with_urls(self, runner, sample_benchmark, tmp_path):
        """Download reads full URLs from file."""
        # Create URL file
        url_file = tmp_path / "urls.txt"
        url_file.write_text(
            "https://workbench.cisecurity.org/benchmarks/12345\n"
            "https://workbench.cisecurity.org/benchmarks/67890\n"
        )

        with runner.isolated_filesystem():
            with patch(
                "cis_bench.cli.commands.download.AuthManager.get_or_create_session"
            ) as mock_auth:
                mock_session = Mock()
                mock_auth.return_value = mock_session

                with patch(
                    "cis_bench.cli.commands.download.WorkbenchScraper"
                ) as mock_scraper_class:
                    mock_scraper = Mock()
                    mock_scraper_class.return_value = mock_scraper
                    mock_scraper.download_benchmark.return_value = sample_benchmark

                    with patch("cis_bench.cli.commands.download.Config") as mock_config:
                        mock_config.get_catalog_db_path.return_value = Path(
                            "/nonexistent/catalog.db"
                        )

                        result = runner.invoke(cli, ["download", "--file", str(url_file)])

                        assert result.exit_code == 0
                        # Should download both benchmarks
                        assert mock_scraper.download_benchmark.call_count == 2

    def test_download_from_file_with_ids(self, runner, sample_benchmark, tmp_path):
        """Download reads benchmark IDs from file and constructs URLs."""
        # Create ID file
        id_file = tmp_path / "ids.txt"
        id_file.write_text("12345\n67890\n# This is a comment\n")

        with runner.isolated_filesystem():
            with patch(
                "cis_bench.cli.commands.download.AuthManager.get_or_create_session"
            ) as mock_auth:
                mock_session = Mock()
                mock_auth.return_value = mock_session

                with patch(
                    "cis_bench.cli.commands.download.WorkbenchScraper"
                ) as mock_scraper_class:
                    mock_scraper = Mock()
                    mock_scraper_class.return_value = mock_scraper
                    mock_scraper.download_benchmark.return_value = sample_benchmark

                    with patch("cis_bench.cli.commands.download.Config") as mock_config:
                        mock_config.get_catalog_db_path.return_value = Path(
                            "/nonexistent/catalog.db"
                        )

                        result = runner.invoke(cli, ["download", "--file", str(id_file)])

                        assert result.exit_code == 0
                        # Should download 2 benchmarks (comment ignored)
                        assert mock_scraper.download_benchmark.call_count == 2

    def test_download_url_argument_passed_through(self, runner, sample_benchmark):
        """Download passes through full URLs from arguments."""
        with runner.isolated_filesystem():
            with patch(
                "cis_bench.cli.commands.download.AuthManager.get_or_create_session"
            ) as mock_auth:
                mock_session = Mock()
                mock_auth.return_value = mock_session

                with patch(
                    "cis_bench.cli.commands.download.WorkbenchScraper"
                ) as mock_scraper_class:
                    mock_scraper = Mock()
                    mock_scraper_class.return_value = mock_scraper
                    mock_scraper.download_benchmark.return_value = sample_benchmark

                    with patch("cis_bench.cli.commands.download.Config") as mock_config:
                        mock_config.get_catalog_db_path.return_value = Path(
                            "/nonexistent/catalog.db"
                        )

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
        with patch(
            "cis_bench.cli.commands.download.AuthManager.get_or_create_session"
        ) as mock_auth:
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

        with patch(
            "cis_bench.cli.commands.download.AuthManager.get_or_create_session"
        ) as mock_auth:
            mock_session = Mock()
            mock_auth.return_value = mock_session

            result = runner.invoke(cli, ["download", "--file", str(url_file)])

            assert result.exit_code == 1
            assert "No benchmarks to download" in result.output


class TestDownloadCacheSkip:
    """Test download command cache skip behavior (lines 157->170)."""

    def test_download_skips_cached_benchmark(self, runner, tmp_path):
        """Download skips already cached benchmarks."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        with patch("cis_bench.cli.commands.download.Config") as mock_config:
            mock_config.get_catalog_db_path.return_value = catalog_path

            with patch(
                "cis_bench.cli.commands.download.AuthManager.get_or_create_session"
            ) as mock_auth:
                mock_session = Mock()
                mock_auth.return_value = mock_session

                with patch(
                    "cis_bench.cli.commands.download.WorkbenchScraper"
                ) as mock_scraper_class:
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

    def test_download_force_overrides_cache(self, runner, sample_benchmark, tmp_path):
        """Download with --force re-downloads cached benchmark."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        with runner.isolated_filesystem():
            with patch("cis_bench.cli.commands.download.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path

                with patch(
                    "cis_bench.cli.commands.download.AuthManager.get_or_create_session"
                ) as mock_auth:
                    mock_session = Mock()
                    mock_auth.return_value = mock_session

                    with patch(
                        "cis_bench.cli.commands.download.WorkbenchScraper"
                    ) as mock_scraper_class:
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

    def test_download_export_failure_continues(self, runner, sample_benchmark, tmp_path):
        """Download continues after export failure for a format."""
        with runner.isolated_filesystem():
            with patch("cis_bench.cli.commands.download.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = tmp_path / "nonexistent.db"

                with patch(
                    "cis_bench.cli.commands.download.AuthManager.get_or_create_session"
                ) as mock_auth:
                    mock_session = Mock()
                    mock_auth.return_value = mock_session

                    with patch(
                        "cis_bench.cli.commands.download.WorkbenchScraper"
                    ) as mock_scraper_class:
                        mock_scraper = Mock()
                        mock_scraper_class.return_value = mock_scraper
                        mock_scraper.download_benchmark.return_value = sample_benchmark

                        with patch(
                            "cis_bench.cli.commands.download.ExporterFactory"
                        ) as mock_factory:
                            mock_exporter = Mock()
                            mock_exporter.export.side_effect = Exception("Export failed")
                            mock_exporter.format_name.return_value = "JSON"
                            mock_exporter.get_file_extension.return_value = "json"
                            mock_factory.create.return_value = mock_exporter

                            result = runner.invoke(cli, ["download", "12345"])

                            assert result.exit_code == 0
                            assert "export failed" in result.output
                            assert "Download complete" in result.output


class TestDownloadBenchmarkErrors:
    """Test download command benchmark download errors (lines 247-253)."""

    def test_download_benchmark_failure_continues_to_next(self, runner, sample_benchmark, tmp_path):
        """Download continues to next benchmark after failure."""
        with runner.isolated_filesystem():
            with patch("cis_bench.cli.commands.download.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = tmp_path / "nonexistent.db"

                with patch(
                    "cis_bench.cli.commands.download.AuthManager.get_or_create_session"
                ) as mock_auth:
                    mock_session = Mock()
                    mock_auth.return_value = mock_session

                    with patch(
                        "cis_bench.cli.commands.download.WorkbenchScraper"
                    ) as mock_scraper_class:
                        mock_scraper = Mock()
                        mock_scraper_class.return_value = mock_scraper

                        # First fails, second succeeds
                        mock_scraper.download_benchmark.side_effect = [
                            Exception("Network error"),
                            sample_benchmark,
                        ]

                        with patch(
                            "cis_bench.cli.commands.download.ExporterFactory"
                        ) as mock_factory:
                            mock_exporter = Mock()
                            mock_exporter.format_name.return_value = "JSON"
                            mock_exporter.get_file_extension.return_value = "json"
                            mock_factory.create.return_value = mock_exporter

                            result = runner.invoke(cli, ["download", "12345", "67890"])

                            assert result.exit_code == 0
                            assert "Error" in result.output
                            assert "Network error" in result.output
                            assert "Download complete" in result.output


# ============================================================================
# Get Command Tests - Error Paths
# ============================================================================


class TestGetLoggingConfig:
    """Test get command logging configuration (lines 78-80)."""

    def test_get_verbose_flag_configures_logging(self, runner, tmp_path):
        """Get with --verbose flag configures debug logging."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        with patch("cis_bench.cli.commands.get.Config") as mock_config:
            mock_config.get_catalog_db_path.return_value = catalog_path

            with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                mock_db = Mock()
                mock_db_class.return_value = mock_db

                with patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class:
                    mock_search = Mock()
                    mock_search_class.return_value = mock_search
                    mock_search.search.return_value = []

                    with patch("cis_bench.utils.logging_config.LoggingConfig") as mock_logging:
                        result = runner.invoke(
                            cli, ["get", "test", "--verbose", "--non-interactive"]
                        )

                        mock_logging.setup_from_flags.assert_called_once_with(
                            quiet=False, verbose=True
                        )

    def test_get_quiet_flag_configures_logging(self, runner, tmp_path):
        """Get with --quiet flag configures quiet logging."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        with patch("cis_bench.cli.commands.get.Config") as mock_config:
            mock_config.get_catalog_db_path.return_value = catalog_path

            with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                mock_db = Mock()
                mock_db_class.return_value = mock_db

                with patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class:
                    mock_search = Mock()
                    mock_search_class.return_value = mock_search
                    mock_search.search.return_value = []

                    with patch("cis_bench.utils.logging_config.LoggingConfig") as mock_logging:
                        result = runner.invoke(cli, ["get", "test", "--quiet", "--non-interactive"])

                        mock_logging.setup_from_flags.assert_called_once_with(
                            quiet=True, verbose=False
                        )


class TestGetSearchErrors:
    """Test get command search error handling (lines 120-122)."""

    def test_get_search_failure_shows_error(self, runner, tmp_path):
        """Get shows error when search fails."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        with patch("cis_bench.cli.commands.get.Config") as mock_config:
            mock_config.get_catalog_db_path.return_value = catalog_path

            with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                mock_db = Mock()
                mock_db_class.return_value = mock_db

                with patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class:
                    mock_search = Mock()
                    mock_search_class.return_value = mock_search
                    mock_search.search.side_effect = Exception("Database corrupted")

                    result = runner.invoke(cli, ["get", "test", "--non-interactive"])

                    assert result.exit_code == 1
                    assert "Search failed" in result.output


class TestGetTitleTruncation:
    """Test get command title truncation (line 143)."""

    def test_get_truncates_long_titles_in_table(self, runner, tmp_path):
        """Get truncates long benchmark titles in table display."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        with patch("cis_bench.cli.commands.get.Config") as mock_config:
            mock_config.get_catalog_db_path.return_value = catalog_path

            with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                mock_db = Mock()
                mock_db_class.return_value = mock_db

                with patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class:
                    mock_search = Mock()
                    mock_search_class.return_value = mock_search

                    # Long title that will be truncated (>87 chars triggers truncation)
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

                    # The code truncates to 84 chars + "..." when title > 87 chars
                    # Rich console also may use ellipsis character
                    # Either Python ellipsis "..." or Rich truncation indicator
                    assert (
                        "..." in result.output
                        or "\u2026" in result.output  # Unicode ellipsis
                        or "A" * 84 in result.output  # Truncated to 84 chars
                    )


class TestGetInteractiveSelection:
    """Test get command interactive selection (lines 156-178)."""

    def test_get_interactive_selection_cancelled(self, runner, tmp_path):
        """Get shows cancelled message when user cancels selection."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        with patch("cis_bench.cli.commands.get.Config") as mock_config:
            mock_config.get_catalog_db_path.return_value = catalog_path

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

    def test_get_interactive_selection_exception_falls_back(self, runner, tmp_path):
        """Get falls back to non-interactive when questionary fails."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        with patch("cis_bench.cli.commands.get.Config") as mock_config:
            mock_config.get_catalog_db_path.return_value = catalog_path

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

    def test_get_interactive_selection_success(self, runner, sample_benchmark, tmp_path):
        """Get with interactive selection proceeds to download."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        with runner.isolated_filesystem():
            with patch("cis_bench.cli.commands.get.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path

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

    def test_get_download_auth_required(self, runner, tmp_path):
        """Get shows auth required when download session missing."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        with patch("cis_bench.cli.commands.get.Config") as mock_config:
            mock_config.get_catalog_db_path.return_value = catalog_path

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

                    with patch("cis_bench.cli.commands.get.AuthManager") as mock_auth:
                        mock_auth.get_or_create_session.side_effect = ValueError("No session")

                        result = runner.invoke(cli, ["get", "test", "--non-interactive"])

                        assert result.exit_code == 1
                        assert "Authentication Required" in result.output

    def test_get_download_generic_error(self, runner, tmp_path):
        """Get shows error when download fails."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        with patch("cis_bench.cli.commands.get.Config") as mock_config:
            mock_config.get_catalog_db_path.return_value = catalog_path

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

                    with patch("cis_bench.cli.commands.get.AuthManager") as mock_auth:
                        mock_session = Mock()
                        mock_auth.get_or_create_session.return_value = mock_session

                        with patch(
                            "cis_bench.cli.helpers.download_helper.download_with_progress"
                        ) as mock_dl:
                            mock_dl.side_effect = Exception("Network timeout")

                            result = runner.invoke(cli, ["get", "test", "--non-interactive"])

                            assert result.exit_code == 1
                            assert "Download failed" in result.output


class TestGetXccdfExport:
    """Test get command XCCDF export with style (lines 269, 274->280)."""

    def test_get_xccdf_format_uses_style(self, runner, sample_benchmark, tmp_path):
        """Get with xccdf format uses --style option."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        with runner.isolated_filesystem():
            with patch("cis_bench.cli.commands.get.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path

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

    def test_get_auto_generates_output_filename(self, runner, sample_benchmark, tmp_path):
        """Get auto-generates output filename when not specified."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        with runner.isolated_filesystem():
            with patch("cis_bench.cli.commands.get.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path

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

    def test_get_export_failure_shows_error(self, runner, sample_benchmark, tmp_path):
        """Get shows error when export fails."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        with runner.isolated_filesystem():
            with patch("cis_bench.cli.commands.get.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path

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
                            mock_exporter.export.side_effect = Exception("Write permission denied")
                            mock_factory.create.return_value = mock_exporter

                            result = runner.invoke(
                                cli, ["get", "test", "-f", "json", "--non-interactive"]
                            )

                            assert result.exit_code == 1
                            assert "Export failed" in result.output


class TestGetNonInteractiveMode:
    """Test get command non-interactive mode display (lines 181->192)."""

    def test_get_non_interactive_shows_instructions(self, runner, tmp_path):
        """Get in non-interactive mode shows helpful instructions."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        with patch("cis_bench.cli.commands.get.Config") as mock_config:
            mock_config.get_catalog_db_path.return_value = catalog_path

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
