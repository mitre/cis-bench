"""Unit tests for --force flag behavior on download command."""

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
        title="CIS Test Benchmark",
        benchmark_id="12345",
        url="https://workbench.cisecurity.org/benchmarks/12345",
        version="v1.0.0",
        downloaded_at=datetime.now(),
        scraper_version="1.0.0",
        total_recommendations=1,
        recommendations=[
            Recommendation(
                ref="1.1.1",
                title="Test Recommendation",
                url="https://workbench.cisecurity.org/sections/12345/recommendations/1",
                assessment_status="Automated",
                profiles=["Level 1"],
                description="Test",
                rationale="Test",
                impact="Test",
                audit="Test",
                remediation="Test",
            ),
        ],
    )


# ============================================================================
# Tests: Force Flag Behavior
# ============================================================================


class TestForceFlag:
    """Test --force flag on download command."""

    def test_download_without_force_skips_cached_benchmark(self, runner, tmp_path):
        """Download without --force skips already cached benchmark."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        with patch("cis_bench.cli.commands.download.Config") as mock_config:
            mock_config.get_catalog_db_path.return_value = catalog_path
            mock_config.get_verify_ssl.return_value = False

            with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                mock_db = Mock()
                mock_db_class.return_value = mock_db

                # Simulate cached benchmark
                mock_db.get_downloaded.return_value = {
                    "benchmark_id": "12345",
                    "downloaded_at": datetime.now(),
                    "recommendation_count": 100,
                }

                with patch(
                    "cis_bench.cli.commands.download.AuthManager.get_or_create_session"
                ) as mock_auth:
                    mock_session = Mock()
                    mock_auth.return_value = mock_session

                    result = runner.invoke(cli, ["download", "12345"])

                    assert result.exit_code == 0
                    assert "already cached" in result.output
                    assert "Use --force to re-download" in result.output

    def test_download_with_force_downloads_even_if_cached(self, runner, sample_benchmark, tmp_path):
        """Download with --force re-downloads even if benchmark is cached."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        with patch("cis_bench.cli.commands.download.Config") as mock_config:
            mock_config.get_catalog_db_path.return_value = catalog_path
            mock_config.get_verify_ssl.return_value = False

            with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                mock_db = Mock()
                mock_db_class.return_value = mock_db

                # Simulate cached benchmark
                mock_db.get_downloaded.return_value = {
                    "benchmark_id": "12345",
                    "downloaded_at": datetime.now(),
                    "recommendation_count": 100,
                }

                with patch(
                    "cis_bench.cli.commands.download.AuthManager.get_or_create_session"
                ) as mock_auth:
                    mock_session = Mock()
                    mock_auth.return_value = mock_session

                    with patch(
                        "cis_bench.cli.helpers.download_helper.download_with_progress"
                    ) as mock_download:
                        mock_download.return_value = sample_benchmark

                        result = runner.invoke(cli, ["download", "12345", "--force"])

                        assert result.exit_code == 0
                        # Should NOT say "already cached"
                        assert "already cached" not in result.output
                        # Should actually download
                        assert "Downloaded:" in result.output
                        mock_download.assert_called_once()

    def test_download_with_force_on_non_cached_benchmark(self, runner, sample_benchmark, tmp_path):
        """Download with --force on non-cached benchmark works normally."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        with patch("cis_bench.cli.commands.download.Config") as mock_config:
            mock_config.get_catalog_db_path.return_value = catalog_path
            mock_config.get_verify_ssl.return_value = False

            with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                mock_db = Mock()
                mock_db_class.return_value = mock_db

                # Not cached
                mock_db.get_downloaded.return_value = None

                with patch(
                    "cis_bench.cli.commands.download.AuthManager.get_or_create_session"
                ) as mock_auth:
                    mock_session = Mock()
                    mock_auth.return_value = mock_session

                    with patch(
                        "cis_bench.cli.helpers.download_helper.download_with_progress"
                    ) as mock_download:
                        mock_download.return_value = sample_benchmark

                        result = runner.invoke(cli, ["download", "12345", "--force"])

                        assert result.exit_code == 0
                        assert "Downloaded:" in result.output
                        mock_download.assert_called_once()

    def test_cache_check_skipped_when_no_catalog_exists(self, runner, sample_benchmark, tmp_path):
        """Cache check is skipped when catalog database doesn't exist."""
        catalog_path = tmp_path / "nonexistent" / "catalog.db"

        with patch("cis_bench.cli.commands.download.Config") as mock_config:
            mock_config.get_catalog_db_path.return_value = catalog_path
            mock_config.get_verify_ssl.return_value = False

            with patch(
                "cis_bench.cli.commands.download.AuthManager.get_or_create_session"
            ) as mock_auth:
                mock_session = Mock()
                mock_auth.return_value = mock_session

                with patch(
                    "cis_bench.cli.helpers.download_helper.download_with_progress"
                ) as mock_download:
                    mock_download.return_value = sample_benchmark

                    result = runner.invoke(cli, ["download", "12345"])

                    assert result.exit_code == 0
                    # No catalog, so no cache check - just downloads
                    assert "Downloaded:" in result.output
                    mock_download.assert_called_once()
