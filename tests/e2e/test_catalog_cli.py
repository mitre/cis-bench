"""End-to-end tests for catalog CLI commands."""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from cis_bench.cli.app import cli


@pytest.fixture
def runner():
    """Create Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def isolated_catalog(runner, tmp_path):
    """Create isolated catalog database for testing."""
    # Use tmp_path for catalog to avoid polluting real catalog
    with runner.isolated_filesystem(temp_dir=tmp_path):
        yield tmp_path


class TestCatalogHelp:
    """Test catalog help and command discovery."""

    def test_catalog_command_exists(self, runner):
        """Test catalog command is available."""
        result = runner.invoke(cli, ["catalog", "--help"])
        assert result.exit_code == 0
        assert "catalog" in result.output.lower()

    def test_catalog_shows_subcommands(self, runner):
        """Test catalog help shows all subcommands."""
        result = runner.invoke(cli, ["catalog", "--help"])

        assert "refresh" in result.output
        assert "update" in result.output
        assert "search" in result.output
        assert "list" in result.output
        assert "info" in result.output
        assert "platforms" in result.output
        assert "stats" in result.output
        assert "download" in result.output


class TestCatalogRefresh:
    """Test catalog refresh command."""

    def test_refresh_help(self, runner):
        """Test refresh command help."""
        result = runner.invoke(cli, ["catalog", "refresh", "--help"])
        assert result.exit_code == 0
        assert "refresh" in result.output.lower()

    @patch("cis_bench.cli.commands.catalog.AuthManager")
    @patch("cis_bench.cli.commands.catalog.CatalogScraper")
    def test_refresh_with_mocked_scraper(self, mock_scraper_class, mock_auth, runner):
        """Test refresh command with mocked dependencies."""
        # Mock auth
        mock_session = Mock()
        mock_auth.load_cookies_from_browser.return_value = mock_session

        # Mock scraper
        mock_scraper = Mock()
        mock_scraper.test_connection.return_value = True
        mock_scraper.scrape_full_catalog.return_value = {
            "total_benchmarks": 20,
            "pages_scraped": 1,
            "failed_pages": [],
            "success_rate": 1.0,
        }
        mock_scraper_class.return_value = mock_scraper

        result = runner.invoke(cli, ["catalog", "refresh", "--max-pages", "1"])

        # Should succeed
        assert result.exit_code == 0
        assert "complete" in result.output.lower()

    def test_refresh_accepts_max_pages_option(self, runner):
        """Test refresh accepts max-pages option."""
        result = runner.invoke(cli, ["catalog", "refresh", "--help"])

        # Should document max-pages option
        assert "--max-pages" in result.output


class TestCatalogSearch:
    """Test catalog search command."""

    def test_search_help(self, runner):
        """Test search command help."""
        result = runner.invoke(cli, ["catalog", "search", "--help"])
        assert result.exit_code == 0

    def test_search_command_works(self, runner):
        """Test search command executes."""
        result = runner.invoke(cli, ["catalog", "search", "ubuntu"])

        # Should either show results or helpful message
        assert result.exit_code == 0 or "not found" in result.output.lower()


class TestCatalogList:
    """Test catalog list command."""

    def test_list_help(self, runner):
        """Test list command help."""
        result = runner.invoke(cli, ["catalog", "list", "--help"])
        assert result.exit_code == 0

    def test_list_command_works(self, runner):
        """Test list command executes."""
        result = runner.invoke(cli, ["catalog", "list"])

        # Should either show results or helpful message
        assert result.exit_code == 0 or "not found" in result.output.lower()


class TestCatalogPlatforms:
    """Test catalog platforms command."""

    def test_platforms_help(self, runner):
        """Test platforms command help."""
        result = runner.invoke(cli, ["catalog", "platforms", "--help"])
        assert result.exit_code == 0


class TestCatalogStats:
    """Test catalog stats command."""

    def test_stats_help(self, runner):
        """Test stats command help."""
        result = runner.invoke(cli, ["catalog", "stats", "--help"])
        assert result.exit_code == 0


class TestCatalogInfo:
    """Test catalog info command."""

    def test_info_help(self, runner):
        """Test info command help."""
        result = runner.invoke(cli, ["catalog", "info", "--help"])
        assert result.exit_code == 0

    def test_info_requires_argument(self, runner):
        """Test info requires benchmark ID."""
        result = runner.invoke(cli, ["catalog", "info"])

        # Should show error about missing argument
        assert result.exit_code != 0


class TestCatalogDownload:
    """Test catalog download command."""

    def test_download_help(self, runner):
        """Test download command help."""
        result = runner.invoke(cli, ["catalog", "download", "--help"])
        assert result.exit_code == 0

    def test_download_requires_argument(self, runner):
        """Test download requires ID or name."""
        result = runner.invoke(cli, ["catalog", "download"])

        assert result.exit_code != 0
