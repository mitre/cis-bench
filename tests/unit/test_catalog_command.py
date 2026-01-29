"""Unit tests for catalog CLI commands.

Tests for src/cis_bench/cli/commands/catalog.py covering:
- catalog refresh command
- catalog update command
- catalog search command
- catalog list command
- catalog info command
- catalog platforms command
- catalog stats command
- catalog download command
- catalog check-updates command

Focus on missing coverage lines: 74-76, 99, 110-116, 131-153, 182-185, 190->193,
199, 205-227, 246-249, 254, 262-271, 290-339, 357-393, 411-443, 461-505, 516-543
"""

from unittest.mock import MagicMock, Mock, patch

import pytest
from click.testing import CliRunner

from cis_bench.cli.app import cli
from cis_bench.exceptions import AuthenticationError


@pytest.fixture
def runner():
    """Create Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_db():
    """Create mock CatalogDatabase."""
    db = MagicMock()
    db.db_path = MagicMock()
    db.db_path.exists.return_value = True
    db.initialize_schema = MagicMock()
    db.get_catalog_stats.return_value = {
        "total_benchmarks": 100,
        "published_benchmarks": 90,
        "downloaded_benchmarks": 5,
        "platforms": 10,
        "communities": 8,
    }
    db.get_metadata.return_value = "2025-01-01 12:00:00"
    db.list_platforms.return_value = [
        {"name": "Operating System", "count": 50},
        {"name": "Cloud", "count": 30},
    ]
    db.get_benchmark.return_value = {
        "benchmark_id": "23598",
        "title": "CIS Ubuntu Linux 20.04 LTS Benchmark",
        "version": "v2.0.1",
        "url": "https://workbench.cisecurity.org/benchmarks/23598",
        "status": "Published",
        "platform": "Operating System",
        "community": "Ubuntu",
        "owner": "cis-admin",
        "published_date": "2024-08-01",
        "last_revision_date": "2024-08-15",
        "description": "Security configuration benchmark for Ubuntu 20.04",
        "is_latest": True,
        "metadata_json": None,
    }
    db.check_updates_available.return_value = []
    return db


@pytest.fixture
def mock_search():
    """Create mock CatalogSearch."""
    search = MagicMock()
    search.search.return_value = [
        {
            "benchmark_id": "23598",
            "title": "CIS Ubuntu Linux 20.04 LTS Benchmark",
            "version": "v2.0.1",
            "status": "Published",
            "platform": "Operating System",
            "community": "Ubuntu",
            "url": "https://workbench.cisecurity.org/benchmarks/23598",
            "is_latest": True,
            "published_date": "2024-08-01",
        }
    ]
    search.list_all_published.return_value = search.search.return_value
    search.list_by_platform.return_value = search.search.return_value
    search.format_result_for_display.return_value = (
        "[23598] CIS Ubuntu Linux 20.04 LTS Benchmark v2.0.1\n"
        "        Platform: Operating System | Published: 2024-08-01 | Latest"
    )
    return search


class TestCatalogRefreshCommand:
    """Tests for catalog refresh command."""

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    @patch("cis_bench.cli.commands.catalog.AuthManager")
    @patch("cis_bench.cli.commands.catalog.CatalogScraper")
    @patch("cis_bench.cli.commands.catalog.Config")
    def test_refresh_success(
        self, mock_config, mock_scraper_class, mock_auth, mock_get_db, runner, mock_db
    ):
        """Test successful catalog refresh."""
        mock_get_db.return_value = mock_db
        mock_config.get_verify_ssl.return_value = False

        mock_session = Mock()
        mock_auth.get_or_create_session.return_value = mock_session
        mock_auth.validate_session.return_value = True

        mock_scraper = Mock()
        mock_scraper.test_connection.return_value = True
        mock_scraper.scrape_full_catalog.return_value = {
            "total_benchmarks": 100,
            "pages_scraped": 68,
            "failed_pages": [],
        }
        mock_scraper_class.return_value = mock_scraper

        result = runner.invoke(cli, ["catalog", "refresh", "--max-pages", "1"])

        assert result.exit_code == 0
        assert "complete" in result.output.lower()
        mock_db.initialize_schema.assert_called_once()

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    @patch("cis_bench.cli.commands.catalog.AuthManager")
    @patch("cis_bench.cli.commands.catalog.Config")
    def test_refresh_invalid_session(self, mock_config, mock_auth, mock_get_db, runner, mock_db):
        """Test refresh with invalid session (lines 74-76)."""
        mock_get_db.return_value = mock_db
        mock_config.get_verify_ssl.return_value = False

        mock_session = Mock()
        mock_auth.get_or_create_session.return_value = mock_session
        mock_auth.validate_session.return_value = False  # Invalid session

        result = runner.invoke(cli, ["catalog", "refresh"])

        assert result.exit_code == 1
        assert "Session invalid or expired" in result.output
        assert "cis-bench auth login" in result.output

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    @patch("cis_bench.cli.commands.catalog.AuthManager")
    @patch("cis_bench.cli.commands.catalog.CatalogScraper")
    @patch("cis_bench.cli.commands.catalog.Config")
    def test_refresh_with_failed_pages(
        self, mock_config, mock_scraper_class, mock_auth, mock_get_db, runner, mock_db
    ):
        """Test refresh showing failed pages (line 99)."""
        mock_get_db.return_value = mock_db
        mock_config.get_verify_ssl.return_value = False

        mock_session = Mock()
        mock_auth.get_or_create_session.return_value = mock_session
        mock_auth.validate_session.return_value = True

        mock_scraper = Mock()
        mock_scraper.test_connection.return_value = True
        mock_scraper.scrape_full_catalog.return_value = {
            "total_benchmarks": 95,
            "pages_scraped": 68,
            "failed_pages": [3, 15, 42],  # Some pages failed
        }
        mock_scraper_class.return_value = mock_scraper

        result = runner.invoke(cli, ["catalog", "refresh"])

        assert result.exit_code == 0
        assert "Failed pages" in result.output
        assert "3" in result.output

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    @patch("cis_bench.cli.commands.catalog.AuthManager")
    @patch("cis_bench.cli.commands.catalog.Config")
    def test_refresh_authentication_error(
        self, mock_config, mock_auth, mock_get_db, runner, mock_db
    ):
        """Test refresh with AuthenticationError (lines 110-116)."""
        mock_get_db.return_value = mock_db
        mock_config.get_verify_ssl.return_value = False

        mock_auth.get_or_create_session.side_effect = AuthenticationError("No cookies found")

        result = runner.invoke(cli, ["catalog", "refresh"])

        assert result.exit_code == 1
        assert "Authentication required" in result.output

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    @patch("cis_bench.cli.commands.catalog.AuthManager")
    @patch("cis_bench.cli.commands.catalog.CatalogScraper")
    @patch("cis_bench.cli.commands.catalog.Config")
    def test_refresh_generic_error(
        self, mock_config, mock_scraper_class, mock_auth, mock_get_db, runner, mock_db
    ):
        """Test refresh with generic exception (lines 114-116)."""
        mock_get_db.return_value = mock_db
        mock_config.get_verify_ssl.return_value = False

        mock_session = Mock()
        mock_auth.get_or_create_session.return_value = mock_session
        mock_auth.validate_session.return_value = True

        mock_scraper = Mock()
        mock_scraper.test_connection.side_effect = RuntimeError("Connection failed")
        mock_scraper_class.return_value = mock_scraper

        result = runner.invoke(cli, ["catalog", "refresh"])

        assert result.exit_code == 1
        assert "Catalog refresh failed" in result.output


class TestCatalogUpdateCommand:
    """Tests for catalog update command."""

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    @patch("cis_bench.cli.commands.catalog.AuthManager")
    @patch("cis_bench.cli.commands.catalog.CatalogScraper")
    def test_update_success(self, mock_scraper_class, mock_auth, mock_get_db, runner, mock_db):
        """Test successful catalog update (lines 131-153)."""
        mock_get_db.return_value = mock_db

        mock_session = Mock()
        mock_auth.load_cookies_from_browser.return_value = mock_session

        mock_scraper = Mock()
        mock_scraper.scrape_page_one_update.return_value = {
            "new_count": 5,
            "updated_count": 3,
        }
        mock_scraper_class.return_value = mock_scraper

        result = runner.invoke(cli, ["catalog", "update"])

        assert result.exit_code == 0
        assert "Catalog updated" in result.output
        assert "New benchmarks" in result.output

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    def test_update_catalog_not_initialized(self, mock_get_db, runner):
        """Test update when catalog doesn't exist (lines 134-138)."""
        mock_db = MagicMock()
        mock_db.db_path = MagicMock()
        mock_db.db_path.exists.return_value = False
        mock_get_db.return_value = mock_db

        result = runner.invoke(cli, ["catalog", "update"])

        assert result.exit_code == 1
        assert "Catalog not initialized" in result.output
        assert "cis-bench catalog refresh" in result.output

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    @patch("cis_bench.cli.commands.catalog.AuthManager")
    @patch("cis_bench.cli.commands.catalog.CatalogScraper")
    def test_update_failure(self, mock_scraper_class, mock_auth, mock_get_db, runner, mock_db):
        """Test update failure (lines 151-153)."""
        mock_get_db.return_value = mock_db

        mock_session = Mock()
        mock_auth.load_cookies_from_browser.return_value = mock_session

        mock_scraper = Mock()
        mock_scraper.scrape_page_one_update.side_effect = RuntimeError("Network error")
        mock_scraper_class.return_value = mock_scraper

        result = runner.invoke(cli, ["catalog", "update"])

        assert result.exit_code == 1
        assert "Update failed" in result.output


class TestCatalogSearchCommand:
    """Tests for catalog search command."""

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    @patch("cis_bench.cli.commands.catalog.CatalogSearch")
    def test_search_catalog_not_found(self, mock_search_class, mock_get_db, runner):
        """Test search when catalog doesn't exist (lines 182-185)."""
        mock_db = MagicMock()
        mock_db.db_path = MagicMock()
        mock_db.db_path.exists.return_value = False
        mock_get_db.return_value = mock_db

        result = runner.invoke(cli, ["catalog", "search", "ubuntu"])

        assert result.exit_code == 1
        assert "Catalog not found" in result.output
        assert "cis-bench catalog refresh" in result.output

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    @patch("cis_bench.cli.commands.catalog.CatalogSearch")
    @patch("cis_bench.cli.commands.catalog.Config")
    def test_search_uses_default_limit(
        self, mock_config, mock_search_class, mock_get_db, runner, mock_db, mock_search
    ):
        """Test search uses config default limit (lines 190-191)."""
        mock_get_db.return_value = mock_db
        mock_search_class.return_value = mock_search
        mock_config.get_search_default_limit.return_value = 500

        result = runner.invoke(cli, ["catalog", "search", "ubuntu"])

        assert result.exit_code == 0
        mock_search.search.assert_called_once()
        # Verify limit was passed from config
        call_kwargs = mock_search.search.call_args.kwargs
        assert call_kwargs["limit"] == 500

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    @patch("cis_bench.cli.commands.catalog.CatalogSearch")
    @patch("cis_bench.cli.commands.catalog.Config")
    def test_search_no_results_table_format(
        self, mock_config, mock_search_class, mock_get_db, runner, mock_db
    ):
        """Test search with no results in table format (line 199-201)."""
        mock_get_db.return_value = mock_db
        mock_search = MagicMock()
        mock_search.search.return_value = []
        mock_search_class.return_value = mock_search
        mock_config.get_search_default_limit.return_value = 1000

        result = runner.invoke(cli, ["catalog", "search", "nonexistent"])

        assert result.exit_code == 0
        assert "No benchmarks found" in result.output

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    @patch("cis_bench.cli.commands.catalog.CatalogSearch")
    @patch("cis_bench.cli.commands.catalog.Config")
    @patch("cis_bench.cli.commands.catalog.output_data")
    def test_search_no_results_json_format(
        self, mock_output, mock_config, mock_search_class, mock_get_db, runner, mock_db
    ):
        """Test search with no results in JSON format (lines 198-199)."""
        mock_get_db.return_value = mock_db
        mock_search = MagicMock()
        mock_search.search.return_value = []
        mock_search_class.return_value = mock_search
        mock_config.get_search_default_limit.return_value = 1000

        # Note: output_data calls sys.exit(0) but mock prevents that
        mock_output.return_value = None

        result = runner.invoke(cli, ["catalog", "search", "nonexistent", "-o", "json"])

        # output_data was called with empty list
        mock_output.assert_called_once_with([], "json")

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    @patch("cis_bench.cli.commands.catalog.CatalogSearch")
    @patch("cis_bench.cli.commands.catalog.Config")
    @patch("cis_bench.cli.commands.catalog.output_data")
    def test_search_results_json_format(
        self, mock_output, mock_config, mock_search_class, mock_get_db, runner, mock_db, mock_search
    ):
        """Test search with results in JSON format (lines 205-215)."""
        mock_get_db.return_value = mock_db
        mock_search_class.return_value = mock_search
        mock_config.get_search_default_limit.return_value = 1000
        mock_output.return_value = None

        result = runner.invoke(cli, ["catalog", "search", "ubuntu", "-o", "json"])

        # output_data was called with results
        assert mock_output.called
        call_args = mock_output.call_args
        assert call_args[0][1] == "json"  # format is json
        assert "benchmark_id" in call_args[1]["csv_fields"]

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    @patch("cis_bench.cli.commands.catalog.CatalogSearch")
    @patch("cis_bench.cli.commands.catalog.Config")
    def test_search_results_table_format(
        self, mock_config, mock_search_class, mock_get_db, runner, mock_db, mock_search
    ):
        """Test search with results in table format (lines 218-223)."""
        mock_get_db.return_value = mock_db
        mock_search_class.return_value = mock_search
        mock_config.get_search_default_limit.return_value = 1000

        result = runner.invoke(cli, ["catalog", "search", "ubuntu"])

        assert result.exit_code == 0
        assert "Found 1 benchmarks" in result.output
        mock_search.format_result_for_display.assert_called()

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    @patch("cis_bench.cli.commands.catalog.CatalogSearch")
    @patch("cis_bench.cli.commands.catalog.Config")
    def test_search_with_explicit_limit(
        self, mock_config, mock_search_class, mock_get_db, runner, mock_db, mock_search
    ):
        """Test search with explicit limit (branch 190->193)."""
        mock_get_db.return_value = mock_db
        mock_search_class.return_value = mock_search

        result = runner.invoke(cli, ["catalog", "search", "ubuntu", "--limit", "25"])

        assert result.exit_code == 0
        # Config.get_search_default_limit should NOT be called when limit is provided
        mock_config.get_search_default_limit.assert_not_called()
        # Verify explicit limit was passed
        call_kwargs = mock_search.search.call_args.kwargs
        assert call_kwargs["limit"] == 25

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    @patch("cis_bench.cli.commands.catalog.CatalogSearch")
    @patch("cis_bench.cli.commands.catalog.Config")
    def test_search_failure(self, mock_config, mock_search_class, mock_get_db, runner, mock_db):
        """Test search failure (lines 225-227)."""
        mock_get_db.return_value = mock_db
        mock_search = MagicMock()
        mock_search.search.side_effect = RuntimeError("Database error")
        mock_search_class.return_value = mock_search
        mock_config.get_search_default_limit.return_value = 1000

        result = runner.invoke(cli, ["catalog", "search", "ubuntu"])

        assert result.exit_code == 1
        assert "Search failed" in result.output


class TestCatalogListCommand:
    """Tests for catalog list command."""

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    @patch("cis_bench.cli.commands.catalog.CatalogSearch")
    def test_list_catalog_not_found(self, mock_search_class, mock_get_db, runner):
        """Test list when catalog doesn't exist (lines 246-249)."""
        mock_db = MagicMock()
        mock_db.db_path = MagicMock()
        mock_db.db_path.exists.return_value = False
        mock_get_db.return_value = mock_db

        result = runner.invoke(cli, ["catalog", "list"])

        assert result.exit_code == 1
        assert "Catalog not found" in result.output

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    @patch("cis_bench.cli.commands.catalog.CatalogSearch")
    def test_list_with_platform_filter(
        self, mock_search_class, mock_get_db, runner, mock_db, mock_search
    ):
        """Test list with platform filter (line 254)."""
        mock_get_db.return_value = mock_db
        mock_search_class.return_value = mock_search

        result = runner.invoke(cli, ["catalog", "list", "--platform", "Operating System"])

        assert result.exit_code == 0
        mock_search.list_by_platform.assert_called_once()

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    @patch("cis_bench.cli.commands.catalog.CatalogSearch")
    def test_list_no_results(self, mock_search_class, mock_get_db, runner, mock_db):
        """Test list with no results (lines 258-260)."""
        mock_get_db.return_value = mock_db
        mock_search = MagicMock()
        mock_search.list_all_published.return_value = []
        mock_search_class.return_value = mock_search

        result = runner.invoke(cli, ["catalog", "list"])

        assert result.exit_code == 0
        assert "No benchmarks found" in result.output

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    @patch("cis_bench.cli.commands.catalog.CatalogSearch")
    def test_list_with_results(self, mock_search_class, mock_get_db, runner, mock_db, mock_search):
        """Test list with results (lines 262-267)."""
        mock_get_db.return_value = mock_db
        mock_search_class.return_value = mock_search

        result = runner.invoke(cli, ["catalog", "list"])

        assert result.exit_code == 0
        assert "1 benchmarks" in result.output
        mock_search.format_result_for_display.assert_called()

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    @patch("cis_bench.cli.commands.catalog.CatalogSearch")
    def test_list_failure(self, mock_search_class, mock_get_db, runner, mock_db):
        """Test list failure (lines 269-271)."""
        mock_get_db.return_value = mock_db
        mock_search = MagicMock()
        mock_search.list_all_published.side_effect = RuntimeError("Database error")
        mock_search_class.return_value = mock_search

        result = runner.invoke(cli, ["catalog", "list"])

        assert result.exit_code == 1
        assert "List failed" in result.output


class TestCatalogInfoCommand:
    """Tests for catalog info command."""

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    def test_info_catalog_not_found(self, mock_get_db, runner):
        """Test info when catalog doesn't exist (lines 293-297)."""
        mock_db = MagicMock()
        mock_db.db_path = MagicMock()
        mock_db.db_path.exists.return_value = False
        mock_get_db.return_value = mock_db

        result = runner.invoke(cli, ["catalog", "info", "23598"])

        assert result.exit_code == 1
        assert "Catalog not found" in result.output

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    def test_info_benchmark_not_found(self, mock_get_db, runner, mock_db):
        """Test info when benchmark doesn't exist (lines 301-303)."""
        mock_db.get_benchmark.return_value = None
        mock_get_db.return_value = mock_db

        result = runner.invoke(cli, ["catalog", "info", "99999"])

        assert result.exit_code == 1
        assert "not found in catalog" in result.output

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    @patch("cis_bench.cli.commands.catalog.output_data")
    def test_info_json_format(self, mock_output, mock_get_db, runner, mock_db):
        """Test info with JSON format (lines 306-307)."""
        mock_get_db.return_value = mock_db
        mock_output.return_value = None

        result = runner.invoke(cli, ["catalog", "info", "23598", "-o", "json"])

        mock_output.assert_called()
        assert mock_output.call_args[0][1] == "json"

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    def test_info_table_format_full_details(self, mock_get_db, runner, mock_db):
        """Test info with table format showing all details (lines 310-335)."""
        mock_get_db.return_value = mock_db

        result = runner.invoke(cli, ["catalog", "info", "23598"])

        assert result.exit_code == 0
        assert "CIS Ubuntu Linux 20.04 LTS Benchmark" in result.output
        assert "Version: v2.0.1" in result.output
        assert "ID: 23598" in result.output
        assert "Status: Published" in result.output
        assert "Platform: Operating System" in result.output
        assert "Community: Ubuntu" in result.output
        assert "Owner: cis-admin" in result.output
        assert "Published: 2024-08-01" in result.output
        assert "URL:" in result.output
        assert "cis-bench catalog download 23598" in result.output

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    def test_info_without_optional_fields(self, mock_get_db, runner):
        """Test info display without optional fields (lines 312-328 conditionals)."""
        mock_db = MagicMock()
        mock_db.db_path = MagicMock()
        mock_db.db_path.exists.return_value = True
        # Benchmark with minimal fields
        mock_db.get_benchmark.return_value = {
            "benchmark_id": "12345",
            "title": "Minimal Benchmark",
            "version": None,
            "url": "https://example.com",
            "status": "Draft",
            "platform": None,
            "community": None,
            "owner": None,
            "published_date": None,
            "last_revision_date": None,
            "description": None,
            "is_latest": False,
            "metadata_json": None,
        }
        mock_get_db.return_value = mock_db

        result = runner.invoke(cli, ["catalog", "info", "12345"])

        assert result.exit_code == 0
        assert "Minimal Benchmark" in result.output
        assert "Version:" not in result.output  # No version

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    def test_info_with_description(self, mock_get_db, runner, mock_db):
        """Test info shows truncated description (lines 332-333)."""
        mock_get_db.return_value = mock_db

        result = runner.invoke(cli, ["catalog", "info", "23598"])

        assert result.exit_code == 0
        # Description should be shown (truncated to 200 chars)
        assert "Security configuration benchmark" in result.output

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    def test_info_failure(self, mock_get_db, runner, mock_db):
        """Test info failure (lines 337-339)."""
        mock_db.get_benchmark.side_effect = RuntimeError("Database error")
        mock_get_db.return_value = mock_db

        result = runner.invoke(cli, ["catalog", "info", "23598"])

        assert result.exit_code == 1
        assert "Info failed" in result.output


class TestCatalogPlatformsCommand:
    """Tests for catalog platforms command."""

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    def test_platforms_catalog_not_found(self, mock_get_db, runner):
        """Test platforms when catalog doesn't exist (lines 360-364)."""
        mock_db = MagicMock()
        mock_db.db_path = MagicMock()
        mock_db.db_path.exists.return_value = False
        mock_get_db.return_value = mock_db

        result = runner.invoke(cli, ["catalog", "platforms"])

        assert result.exit_code == 1
        assert "Catalog not found" in result.output

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    def test_platforms_no_results_table(self, mock_get_db, runner):
        """Test platforms with no results in table format (lines 368-372)."""
        mock_db = MagicMock()
        mock_db.db_path = MagicMock()
        mock_db.db_path.exists.return_value = True
        mock_db.list_platforms.return_value = []
        mock_get_db.return_value = mock_db

        result = runner.invoke(cli, ["catalog", "platforms"])

        assert result.exit_code == 0
        assert "No platforms found" in result.output

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    @patch("cis_bench.cli.commands.catalog.output_data")
    def test_platforms_no_results_json(self, mock_output, mock_get_db, runner):
        """Test platforms with no results in JSON format (lines 369-370)."""
        mock_db = MagicMock()
        mock_db.db_path = MagicMock()
        mock_db.db_path.exists.return_value = True
        mock_db.list_platforms.return_value = []
        mock_get_db.return_value = mock_db
        mock_output.return_value = None

        result = runner.invoke(cli, ["catalog", "platforms", "-o", "json"])

        mock_output.assert_called_with([], "json")

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    @patch("cis_bench.cli.commands.catalog.output_data")
    def test_platforms_json_format(self, mock_output, mock_get_db, runner, mock_db):
        """Test platforms with JSON format (lines 376-378)."""
        mock_get_db.return_value = mock_db
        mock_output.return_value = None

        result = runner.invoke(cli, ["catalog", "platforms", "-o", "json"])

        mock_output.assert_called()
        call_args = mock_output.call_args
        assert call_args[0][1] == "json"
        assert call_args[1]["csv_fields"] == ["name", "count"]

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    def test_platforms_table_format(self, mock_get_db, runner, mock_db):
        """Test platforms with table format (lines 381-389)."""
        mock_get_db.return_value = mock_db

        result = runner.invoke(cli, ["catalog", "platforms"])

        assert result.exit_code == 0
        assert "Operating System" in result.output
        assert "50" in result.output
        assert "Cloud" in result.output
        assert "30" in result.output

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    def test_platforms_failure(self, mock_get_db, runner, mock_db):
        """Test platforms failure (lines 391-393)."""
        mock_db.list_platforms.side_effect = RuntimeError("Database error")
        mock_get_db.return_value = mock_db

        result = runner.invoke(cli, ["catalog", "platforms"])

        assert result.exit_code == 1
        assert "Platforms list failed" in result.output


class TestCatalogStatsCommand:
    """Tests for catalog stats command."""

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    def test_stats_catalog_not_found(self, mock_get_db, runner):
        """Test stats when catalog doesn't exist (lines 414-418)."""
        mock_db = MagicMock()
        mock_db.db_path = MagicMock()
        mock_db.db_path.exists.return_value = False
        mock_get_db.return_value = mock_db

        result = runner.invoke(cli, ["catalog", "stats"])

        assert result.exit_code == 1
        assert "Catalog not found" in result.output

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    @patch("cis_bench.cli.commands.catalog.output_data")
    def test_stats_json_format(self, mock_output, mock_get_db, runner, mock_db):
        """Test stats with JSON format (lines 427-428)."""
        mock_get_db.return_value = mock_db
        mock_output.return_value = None

        result = runner.invoke(cli, ["catalog", "stats", "-o", "json"])

        mock_output.assert_called()
        call_args = mock_output.call_args
        assert call_args[0][1] == "json"
        # Check stats dict has expected keys
        stats = call_args[0][0]
        assert "total_benchmarks" in stats
        assert "last_full_scrape" in stats

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    def test_stats_table_format(self, mock_get_db, runner, mock_db):
        """Test stats with table format (lines 431-436)."""
        mock_get_db.return_value = mock_db

        result = runner.invoke(cli, ["catalog", "stats"])

        assert result.exit_code == 0
        assert "Catalog Statistics" in result.output
        assert "Total benchmarks" in result.output
        assert "100" in result.output
        assert "Published" in result.output
        assert "90" in result.output
        assert "Downloaded" in result.output
        assert "5" in result.output
        assert "Platforms" in result.output
        assert "10" in result.output
        assert "Communities" in result.output
        assert "8" in result.output

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    def test_stats_with_last_scrape(self, mock_get_db, runner, mock_db):
        """Test stats shows last scrape date (lines 438-439)."""
        mock_get_db.return_value = mock_db

        result = runner.invoke(cli, ["catalog", "stats"])

        assert result.exit_code == 0
        assert "Last catalog refresh" in result.output
        assert "2025-01-01" in result.output

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    def test_stats_without_last_scrape(self, mock_get_db, runner):
        """Test stats without last scrape date."""
        mock_db = MagicMock()
        mock_db.db_path = MagicMock()
        mock_db.db_path.exists.return_value = True
        mock_db.get_catalog_stats.return_value = {
            "total_benchmarks": 0,
            "published_benchmarks": 0,
            "downloaded_benchmarks": 0,
            "platforms": 0,
            "communities": 0,
        }
        mock_db.get_metadata.return_value = None
        mock_get_db.return_value = mock_db

        result = runner.invoke(cli, ["catalog", "stats"])

        assert result.exit_code == 0
        assert "Last catalog refresh" not in result.output

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    def test_stats_failure(self, mock_get_db, runner, mock_db):
        """Test stats failure (lines 441-443)."""
        mock_db.get_catalog_stats.side_effect = RuntimeError("Database error")
        mock_get_db.return_value = mock_db

        result = runner.invoke(cli, ["catalog", "stats"])

        assert result.exit_code == 1
        assert "Stats failed" in result.output


class TestCatalogDownloadCommand:
    """Tests for catalog download command."""

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    def test_download_catalog_not_found(self, mock_get_db, runner):
        """Test download when catalog doesn't exist (lines 464-468)."""
        mock_db = MagicMock()
        mock_db.db_path = MagicMock()
        mock_db.db_path.exists.return_value = False
        mock_get_db.return_value = mock_db

        result = runner.invoke(cli, ["catalog", "download", "23598"])

        assert result.exit_code == 1
        assert "Catalog not found" in result.output

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    @patch("cis_bench.cli.commands.catalog.AuthManager")
    @patch("cis_bench.cli.commands.catalog.WorkbenchScraper")
    @patch("cis_bench.cli.commands.catalog.CatalogDownloader")
    def test_download_by_id_success(
        self, mock_downloader_class, mock_scraper_class, mock_auth, mock_get_db, runner, mock_db
    ):
        """Test download by numeric ID (lines 478-481)."""
        mock_get_db.return_value = mock_db

        mock_session = Mock()
        mock_auth.load_cookies_from_browser.return_value = mock_session

        mock_downloader = Mock()
        mock_downloader.download_by_id.return_value = {
            "status": "downloaded",
            "benchmark_id": "23598",
            "recommendation_count": 150,
            "file_size": 102400,
        }
        mock_downloader_class.return_value = mock_downloader

        result = runner.invoke(cli, ["catalog", "download", "23598"])

        assert result.exit_code == 0
        assert "Downloaded benchmark 23598" in result.output
        assert "Recommendations: 150" in result.output
        mock_downloader.download_by_id.assert_called_once_with("23598", force=False)

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    @patch("cis_bench.cli.commands.catalog.AuthManager")
    @patch("cis_bench.cli.commands.catalog.WorkbenchScraper")
    @patch("cis_bench.cli.commands.catalog.CatalogDownloader")
    def test_download_by_name(
        self, mock_downloader_class, mock_scraper_class, mock_auth, mock_get_db, runner, mock_db
    ):
        """Test download by name (lines 482-487)."""
        mock_get_db.return_value = mock_db

        mock_session = Mock()
        mock_auth.load_cookies_from_browser.return_value = mock_session

        mock_downloader = Mock()
        mock_downloader.download_by_name.return_value = {
            "status": "downloaded",
            "benchmark_id": "23598",
            "recommendation_count": 150,
            "file_size": 102400,
        }
        mock_downloader_class.return_value = mock_downloader

        result = runner.invoke(cli, ["catalog", "download", "ubuntu 20.04", "--interactive"])

        assert result.exit_code == 0
        mock_downloader.download_by_name.assert_called_once_with(
            "ubuntu 20.04", latest=True, interactive=True
        )

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    @patch("cis_bench.cli.commands.catalog.AuthManager")
    @patch("cis_bench.cli.commands.catalog.WorkbenchScraper")
    @patch("cis_bench.cli.commands.catalog.CatalogDownloader")
    def test_download_already_current(
        self, mock_downloader_class, mock_scraper_class, mock_auth, mock_get_db, runner, mock_db
    ):
        """Test download when already current (lines 490-491)."""
        mock_get_db.return_value = mock_db

        mock_session = Mock()
        mock_auth.load_cookies_from_browser.return_value = mock_session

        mock_downloader = Mock()
        mock_downloader.download_by_id.return_value = {
            "status": "already_current",
            "message": "Benchmark 23598 is already up-to-date",
        }
        mock_downloader_class.return_value = mock_downloader

        result = runner.invoke(cli, ["catalog", "download", "23598"])

        assert result.exit_code == 0
        assert "already up-to-date" in result.output

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    @patch("cis_bench.cli.commands.catalog.AuthManager")
    @patch("cis_bench.cli.commands.catalog.WorkbenchScraper")
    @patch("cis_bench.cli.commands.catalog.CatalogDownloader")
    def test_download_unchanged(
        self, mock_downloader_class, mock_scraper_class, mock_auth, mock_get_db, runner, mock_db
    ):
        """Test download with unchanged status (lines 492-493)."""
        mock_get_db.return_value = mock_db

        mock_session = Mock()
        mock_auth.load_cookies_from_browser.return_value = mock_session

        mock_downloader = Mock()
        mock_downloader.download_by_id.return_value = {
            "status": "unchanged",
            "message": "No changes detected",
        }
        mock_downloader_class.return_value = mock_downloader

        result = runner.invoke(cli, ["catalog", "download", "23598"])

        assert result.exit_code == 0
        assert "No changes detected" in result.output

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    @patch("cis_bench.cli.commands.catalog.AuthManager")
    @patch("cis_bench.cli.commands.catalog.WorkbenchScraper")
    @patch("cis_bench.cli.commands.catalog.CatalogDownloader")
    def test_download_with_force(
        self, mock_downloader_class, mock_scraper_class, mock_auth, mock_get_db, runner, mock_db
    ):
        """Test download with force flag."""
        mock_get_db.return_value = mock_db

        mock_session = Mock()
        mock_auth.load_cookies_from_browser.return_value = mock_session

        mock_downloader = Mock()
        mock_downloader.download_by_id.return_value = {
            "status": "downloaded",
            "benchmark_id": "23598",
            "recommendation_count": 150,
            "file_size": 102400,
        }
        mock_downloader_class.return_value = mock_downloader

        result = runner.invoke(cli, ["catalog", "download", "23598", "--force"])

        assert result.exit_code == 0
        mock_downloader.download_by_id.assert_called_once_with("23598", force=True)

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    @patch("cis_bench.cli.commands.catalog.AuthManager")
    @patch("cis_bench.cli.commands.catalog.WorkbenchScraper")
    @patch("cis_bench.cli.commands.catalog.CatalogDownloader")
    def test_download_value_error(
        self, mock_downloader_class, mock_scraper_class, mock_auth, mock_get_db, runner, mock_db
    ):
        """Test download with ValueError (lines 499-501)."""
        mock_get_db.return_value = mock_db

        mock_session = Mock()
        mock_auth.load_cookies_from_browser.return_value = mock_session

        mock_downloader = Mock()
        mock_downloader.download_by_name.side_effect = ValueError(
            "Multiple matches found, use --interactive"
        )
        mock_downloader_class.return_value = mock_downloader

        result = runner.invoke(cli, ["catalog", "download", "ubuntu"])

        assert result.exit_code == 1
        assert "Multiple matches found" in result.output

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    @patch("cis_bench.cli.commands.catalog.AuthManager")
    @patch("cis_bench.cli.commands.catalog.WorkbenchScraper")
    @patch("cis_bench.cli.commands.catalog.CatalogDownloader")
    def test_download_generic_error(
        self, mock_downloader_class, mock_scraper_class, mock_auth, mock_get_db, runner, mock_db
    ):
        """Test download with generic exception (lines 502-505)."""
        mock_get_db.return_value = mock_db

        mock_session = Mock()
        mock_auth.load_cookies_from_browser.return_value = mock_session

        mock_downloader = Mock()
        mock_downloader.download_by_id.side_effect = RuntimeError("Network error")
        mock_downloader_class.return_value = mock_downloader

        result = runner.invoke(cli, ["catalog", "download", "23598"])

        assert result.exit_code == 1
        assert "Download failed" in result.output


class TestCatalogCheckUpdatesCommand:
    """Tests for catalog check-updates command."""

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    def test_check_updates_catalog_not_found(self, mock_get_db, runner):
        """Test check-updates when catalog doesn't exist (lines 519-523)."""
        mock_db = MagicMock()
        mock_db.db_path = MagicMock()
        mock_db.db_path.exists.return_value = False
        mock_get_db.return_value = mock_db

        result = runner.invoke(cli, ["catalog", "check-updates"])

        assert result.exit_code == 1
        assert "Catalog not found" in result.output

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    def test_check_updates_no_updates(self, mock_get_db, runner, mock_db):
        """Test check-updates with no updates available (lines 527-529)."""
        mock_get_db.return_value = mock_db

        result = runner.invoke(cli, ["catalog", "check-updates"])

        assert result.exit_code == 0
        assert "All downloaded benchmarks are up-to-date" in result.output

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    def test_check_updates_with_updates(self, mock_get_db, runner):
        """Test check-updates with updates available (lines 531-539)."""
        mock_db = MagicMock()
        mock_db.db_path = MagicMock()
        mock_db.db_path.exists.return_value = True
        mock_db.check_updates_available.return_value = [
            {
                "benchmark_id": "23598",
                "title": "CIS Ubuntu Linux 20.04 LTS Benchmark",
                "version": "v2.0.1",
                "downloaded_at": "2024-07-15",
                "last_revision_date": "2024-08-01",
            },
            {
                "benchmark_id": "23599",
                "title": "CIS CentOS Linux 8 Benchmark",
                "version": "v1.0.0",
                "downloaded_at": "2024-06-01",
                "last_revision_date": "2024-07-15",
            },
        ]
        mock_get_db.return_value = mock_db

        result = runner.invoke(cli, ["catalog", "check-updates"])

        assert result.exit_code == 0
        assert "Updates available for 2 benchmarks" in result.output
        assert "23598" in result.output
        assert "CIS Ubuntu Linux 20.04 LTS Benchmark" in result.output
        assert "Downloaded: 2024-07-15" in result.output
        assert "Latest: 2024-08-01" in result.output
        assert "cis-bench catalog download <id> --force" in result.output

    @patch("cis_bench.cli.commands.catalog.get_catalog_db")
    def test_check_updates_failure(self, mock_get_db, runner, mock_db):
        """Test check-updates failure (lines 541-543)."""
        mock_db.check_updates_available.side_effect = RuntimeError("Database error")
        mock_get_db.return_value = mock_db

        result = runner.invoke(cli, ["catalog", "check-updates"])

        assert result.exit_code == 1
        assert "Check updates failed" in result.output


class TestGetCatalogDb:
    """Tests for get_catalog_db helper function."""

    @patch("cis_bench.cli.commands.catalog.Config")
    @patch("cis_bench.cli.commands.catalog.CatalogDatabase")
    def test_get_catalog_db_creates_db(self, mock_db_class, mock_config, tmp_path):
        """Test get_catalog_db creates database instance."""
        from cis_bench.cli.commands.catalog import get_catalog_db

        db_path = tmp_path / "test.db"
        mock_config.ensure_directories = Mock()
        mock_config.get_catalog_db_path.return_value = db_path
        mock_db = Mock()
        mock_db_class.return_value = mock_db

        result = get_catalog_db()

        mock_config.ensure_directories.assert_called_once()
        mock_db_class.assert_called_once_with(db_path)
        assert result == mock_db
