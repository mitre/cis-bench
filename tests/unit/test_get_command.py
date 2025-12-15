"""Unit tests for get command (unified workflow)."""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from cis_bench.cli.app import cli
from cis_bench.models.benchmark import Benchmark, Recommendation


@pytest.fixture
def runner():
    """Create Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def sample_benchmark():
    """Create a sample benchmark for testing."""
    return Benchmark(
        title="CIS Ubuntu Linux 22.04 Benchmark",
        benchmark_id="23456",
        url="https://workbench.cisecurity.org/benchmarks/23456",
        version="v2.0.0",
        downloaded_at=datetime.now(),
        scraper_version="1.0.0",
        total_recommendations=2,
        recommendations=[
            Recommendation(
                ref="1.1.1",
                title="Test Recommendation 1",
                url="https://workbench.cisecurity.org/sections/23456/recommendations/1",
                assessment_status="Automated",
                profiles=["Level 1"],
                description="Test description 1",
                rationale="Test rationale 1",
                impact="Test impact 1",
                audit="Test audit 1",
                remediation="Test remediation 1",
            ),
            Recommendation(
                ref="1.1.2",
                title="Test Recommendation 2",
                url="https://workbench.cisecurity.org/sections/23456/recommendations/2",
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
# Tests: Get Command - No Catalog
# ============================================================================


class TestGetCommandNoCatalog:
    """Test get command when catalog doesn't exist."""

    def test_get_shows_catalog_required_message(self, runner, tmp_path):
        """Get command shows helpful message when catalog missing."""
        catalog_path = tmp_path / "nonexistent" / "catalog.db"

        with patch("cis_bench.cli.commands.get.Config") as mock_config:
            mock_config.get_catalog_db_path.return_value = catalog_path

            result = runner.invoke(cli, ["get", "ubuntu", "--format", "json"])

            assert result.exit_code == 1
            assert "Catalog not found" in result.output
            assert "catalog refresh" in result.output


# ============================================================================
# Tests: Get Command - Single Result
# ============================================================================


class TestGetCommandSingleResult:
    """Test get command when search returns single result."""

    def test_get_with_single_match_downloads_and_exports(self, runner, sample_benchmark, tmp_path):
        """Get with single search match downloads and exports automatically."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        with patch("cis_bench.cli.commands.get.Config") as mock_config:
            mock_config.get_catalog_db_path.return_value = catalog_path
            mock_config.get_verify_ssl.return_value = False

            with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                mock_db = Mock()
                mock_db_class.return_value = mock_db

                with patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class:
                    mock_search = Mock()
                    mock_search_class.return_value = mock_search

                    # Single result
                    mock_search.search.return_value = [
                        {
                            "benchmark_id": "23456",
                            "title": "CIS Ubuntu Linux 22.04 Benchmark",
                            "version": "v2.0.0",
                            "status": "Published",
                        }
                    ]

                    # Not yet downloaded initially, but available after save
                    def get_downloaded_side_effect(benchmark_id):
                        # First call returns None (not cached), second call returns saved data
                        if not hasattr(get_downloaded_side_effect, "called"):
                            get_downloaded_side_effect.called = True
                            return None
                        else:
                            return {
                                "benchmark_id": "23456",
                                "content_json": sample_benchmark.model_dump_json(),
                                "downloaded_at": datetime.now(),
                            }

                    mock_db.get_downloaded.side_effect = get_downloaded_side_effect

                    # Mock download
                    with patch("cis_bench.cli.commands.get.AuthManager") as mock_auth:
                        mock_session = Mock()
                        mock_auth.get_or_create_session.return_value = mock_session

                        with patch(
                            "cis_bench.cli.helpers.download_helper.download_with_progress"
                        ) as mock_download:
                            mock_download.return_value = sample_benchmark

                            result = runner.invoke(
                                cli, ["get", "ubuntu 22", "--format", "json", "--non-interactive"]
                            )

                            assert result.exit_code == 0
                            assert "Found: CIS Ubuntu" in result.output
                            assert "Downloading benchmark" in result.output
                            assert "Success!" in result.output
                            assert mock_download.called

    def test_get_with_cached_benchmark_skips_download(self, runner, sample_benchmark, tmp_path):
        """Get uses cached benchmark if already downloaded."""
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
                            "benchmark_id": "23456",
                            "title": "Test",
                            "version": "v1",
                            "status": "Published",
                        }
                    ]

                    # Already downloaded
                    mock_db.get_downloaded.return_value = {
                        "benchmark_id": "23456",
                        "content_json": sample_benchmark.model_dump_json(),
                        "downloaded_at": datetime.now(),
                    }

                    result = runner.invoke(
                        cli, ["get", "ubuntu", "--format", "json", "--non-interactive"]
                    )

                    assert result.exit_code == 0
                    assert "already cached" in result.output
                    assert "Success!" in result.output


# ============================================================================
# Tests: Get Command - Multiple Results
# ============================================================================


class TestGetCommandMultipleResults:
    """Test get command when search returns multiple results."""

    def test_get_with_multiple_matches_non_interactive_shows_table(self, runner, tmp_path):
        """Get with multiple matches in non-interactive mode shows table and exits."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        with patch("cis_bench.cli.commands.get.Config") as mock_config:
            mock_config.get_catalog_db_path.return_value = catalog_path
            mock_config.get_table_title_width.return_value = 90

            with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                mock_db = Mock()
                mock_db_class.return_value = mock_db

                with patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class:
                    mock_search = Mock()
                    mock_search_class.return_value = mock_search

                    # Multiple results
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

                    result = runner.invoke(
                        cli, ["get", "ubuntu", "--format", "json", "--non-interactive"]
                    )

                    assert result.exit_code == 0
                    assert "Found 2 benchmarks" in result.output
                    assert "Multiple matches found" in result.output
                    assert "Be more specific" in result.output


# ============================================================================
# Tests: Get Command - No Results
# ============================================================================


class TestGetCommandNoResults:
    """Test get command when search returns no results."""

    def test_get_with_no_matches(self, runner, tmp_path):
        """Get with no search matches shows helpful message."""
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

                    result = runner.invoke(cli, ["get", "nonexistent", "--format", "json"])

                    assert result.exit_code == 1
                    assert "No results found" in result.output
