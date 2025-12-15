"""Unit tests for top-level search command."""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from cis_bench.cli.app import cli


@pytest.fixture
def runner():
    """Create Click CLI test runner."""
    return CliRunner()


# ============================================================================
# Tests: Search Command Behavior
# ============================================================================


class TestSearchCommand:
    """Test top-level search command (catalog-aware)."""

    def test_search_without_catalog_shows_helpful_message(self, runner, tmp_path):
        """Search shows helpful message when catalog doesn't exist."""
        with runner.isolated_filesystem():
            # Point to non-existent catalog
            nonexistent_path = tmp_path / "nonexistent" / "catalog.db"

            with patch("cis_bench.cli.commands.search.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = nonexistent_path

                result = runner.invoke(cli, ["search", "ubuntu"])

                assert result.exit_code == 1
                assert "Local catalog not found" in result.output
                assert "catalog refresh" in result.output
                assert "one-time setup" in result.output

    def test_search_with_catalog_returns_results(self, runner, tmp_path):
        """Search returns results when catalog exists."""
        with runner.isolated_filesystem():
            catalog_path = tmp_path / "catalog.db"
            catalog_path.touch()

            with patch("cis_bench.cli.commands.search.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path
                mock_config.get_search_default_limit.return_value = 1000
                mock_config.get_table_title_width.return_value = 90

                # Mock CatalogDatabase and CatalogSearch
                with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                    mock_db = Mock()
                    mock_db_class.return_value = mock_db

                    with patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class:
                        mock_search = Mock()
                        mock_search_class.return_value = mock_search

                        # Mock search results
                        mock_search.search.return_value = [
                            {
                                "benchmark_id": "23598",
                                "title": "CIS AlmaLinux OS 8 Benchmark",
                                "version": "v4.0.0",
                                "status": "Published",
                            },
                            {
                                "benchmark_id": "22605",
                                "title": "CIS Ubuntu Linux 20.04 Benchmark",
                                "version": "v2.0.0",
                                "status": "Published",
                            },
                        ]

                        result = runner.invoke(cli, ["search", "linux"])

                        assert result.exit_code == 0
                        assert "Found 2 benchmark(s)" in result.output
                        # Check for titles in table (IDs might not be in captured text)
                        assert "AlmaLinux" in result.output
                        assert "Ubuntu" in result.output
                        # Verify search was called correctly
                        assert mock_search.search.called

    def test_search_with_filters(self, runner, tmp_path):
        """Search respects platform, status, and latest filters."""
        with runner.isolated_filesystem():
            catalog_path = tmp_path / "catalog.db"
            catalog_path.touch()

            with patch("cis_bench.cli.commands.search.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path
                mock_config.get_search_default_limit.return_value = 1000
                mock_config.get_table_title_width.return_value = 90

                with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                    mock_db = Mock()
                    mock_db_class.return_value = mock_db

                    with patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class:
                        mock_search = Mock()
                        mock_search_class.return_value = mock_search
                        mock_search.search.return_value = [
                            {
                                "benchmark_id": "23598",
                                "title": "CIS Ubuntu Linux 22.04 Benchmark",
                                "version": "v1.0.0",
                                "status": "Published",
                            }
                        ]

                        result = runner.invoke(
                            cli,
                            [
                                "search",
                                "ubuntu",
                                "--platform",
                                "ubuntu",
                                "--status",
                                "Published",
                                "--latest",
                            ],
                        )

                        assert result.exit_code == 0

                        # Verify filters were passed
                        call_kwargs = mock_search.search.call_args[1]
                        assert call_kwargs["platform"] == "ubuntu"
                        assert call_kwargs["status"] == "Published"
                        assert call_kwargs["latest_only"] is True

    def test_search_without_query_lists_all(self, runner, tmp_path):
        """Search without query lists all benchmarks."""
        with runner.isolated_filesystem():
            catalog_path = tmp_path / "catalog.db"
            catalog_path.touch()

            with patch("cis_bench.cli.commands.search.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path
                mock_config.get_search_default_limit.return_value = 1000
                mock_config.get_table_title_width.return_value = 90

                with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                    mock_db = Mock()
                    mock_db_class.return_value = mock_db

                    with patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class:
                        mock_search = Mock()
                        mock_search_class.return_value = mock_search
                        mock_search.search.return_value = [
                            {
                                "benchmark_id": "23598",
                                "title": "CIS AlmaLinux OS 8 Benchmark",
                                "version": "v4.0.0",
                                "status": "Published",
                            }
                        ]

                        result = runner.invoke(cli, ["search"])

                        assert result.exit_code == 0
                        assert "Listing benchmarks" in result.output
                        # Now calls search("") instead of list_all
                        assert mock_search.search.called

    def test_search_no_results_message(self, runner, tmp_path):
        """Search shows friendly message when no results found."""
        with runner.isolated_filesystem():
            catalog_path = tmp_path / "catalog.db"
            catalog_path.touch()

            with patch("cis_bench.cli.commands.search.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path
                mock_config.get_search_default_limit.return_value = 1000
                mock_config.get_table_title_width.return_value = 90

                with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                    mock_db = Mock()
                    mock_db_class.return_value = mock_db

                    with patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class:
                        mock_search = Mock()
                        mock_search_class.return_value = mock_search
                        mock_search.search.return_value = []

                        result = runner.invoke(cli, ["search", "nonexistent"])

                        assert result.exit_code == 0
                        assert "No results found" in result.output

    def test_search_shows_next_steps(self, runner, tmp_path):
        """Search shows helpful next steps after results."""
        with runner.isolated_filesystem():
            catalog_path = tmp_path / "catalog.db"
            catalog_path.touch()

            with patch("cis_bench.cli.commands.search.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path
                mock_config.get_search_default_limit.return_value = 1000
                mock_config.get_table_title_width.return_value = 90

                with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                    mock_db = Mock()
                    mock_db_class.return_value = mock_db

                    with patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class:
                        mock_search = Mock()
                        mock_search_class.return_value = mock_search
                        mock_search.search.return_value = [
                            {
                                "benchmark_id": "23598",
                                "title": "Test Benchmark",
                                "version": "v1.0.0",
                                "status": "Published",
                            }
                        ]

                        result = runner.invoke(cli, ["search", "test"])

                        assert result.exit_code == 0
                        assert "Next steps:" in result.output
                        assert "cis-bench download" in result.output
                        assert "cis-bench catalog info" in result.output
                        assert "cis-bench get" in result.output

    def test_search_limit_parameter(self, runner, tmp_path):
        """Search respects limit parameter."""
        with runner.isolated_filesystem():
            catalog_path = tmp_path / "catalog.db"
            catalog_path.touch()

            with patch("cis_bench.cli.commands.search.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path
                mock_config.get_search_default_limit.return_value = 1000
                mock_config.get_table_title_width.return_value = 90

                with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                    mock_db = Mock()
                    mock_db_class.return_value = mock_db

                    with patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class:
                        mock_search = Mock()
                        mock_search_class.return_value = mock_search
                        mock_search.search.return_value = []

                        result = runner.invoke(cli, ["search", "test", "--limit", "5"])

                        assert result.exit_code == 0

                        # Verify limit was passed
                        call_kwargs = mock_search.search.call_args[1]
                        assert call_kwargs["limit"] == 5

    def test_search_handles_database_errors_gracefully(self, runner, tmp_path):
        """Search handles database errors gracefully."""
        with runner.isolated_filesystem():
            catalog_path = tmp_path / "catalog.db"
            catalog_path.touch()

            with patch("cis_bench.cli.commands.search.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path

                with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                    mock_db_class.side_effect = Exception("Database error")

                    result = runner.invoke(cli, ["search", "test"])

                    assert result.exit_code == 1
                    assert "Search failed" in result.output
