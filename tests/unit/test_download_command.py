"""Unit tests for download command database caching functionality."""

from datetime import datetime
from pathlib import Path
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
        title="CIS AlmaLinux OS 8 Benchmark",
        benchmark_id="23598",
        url="https://workbench.cisecurity.org/benchmarks/23598",
        version="v4.0.0",
        downloaded_at=datetime(2025, 10, 18, 12, 0, 0),
        scraper_version="1.0.0",
        total_recommendations=2,
        recommendations=[
            Recommendation(
                ref="1.1.1",
                title="Test Recommendation 1",
                url="https://workbench.cisecurity.org/sections/23598/recommendations/374956",
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
                url="https://workbench.cisecurity.org/sections/23598/recommendations/374957",
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
# Tests: Database Caching During Download
# ============================================================================


class TestDownloadDatabaseCaching:
    """Test that download command saves to catalog database when it exists."""

    def test_download_saves_to_database_when_catalog_exists(
        self, runner, sample_benchmark, tmp_path
    ):
        """Download saves benchmark to catalog database if it exists."""
        with runner.isolated_filesystem():
            # Create catalog database file
            catalog_path = tmp_path / "catalog.db"
            catalog_path.touch()

            # Mock Config to return test catalog path
            with patch("cis_bench.cli.commands.download.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path

                # Mock AuthManager to return session
                mock_session = Mock()
                mock_config.get_verify_ssl.return_value = False
                with patch(
                    "cis_bench.cli.commands.download.AuthManager.get_or_create_session"
                ) as mock_auth:
                    mock_auth.return_value = mock_session

                    # Mock WorkbenchScraper to return sample benchmark
                    with patch(
                        "cis_bench.cli.commands.download.WorkbenchScraper"
                    ) as mock_scraper_class:
                        mock_scraper = Mock()
                        mock_scraper_class.return_value = mock_scraper
                        mock_scraper.download_benchmark.return_value = sample_benchmark

                        # Mock CatalogDatabase
                        with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                            mock_db = Mock()
                            mock_db_class.return_value = mock_db

                            result = runner.invoke(
                                cli,
                                ["download", "23598", "--browser", "chrome"],
                            )

                            # Verify command succeeded
                            assert result.exit_code == 0, f"Download failed: {result.output}"

                            # Verify database save was called with new signature
                            assert mock_db.save_downloaded.called
                            call_args = mock_db.save_downloaded.call_args
                            assert call_args.kwargs["benchmark_id"] == "23598"
                            assert call_args.kwargs["recommendation_count"] == 2
                            assert "content_json" in call_args.kwargs
                            assert "content_hash" in call_args.kwargs

                            # Verify output shows caching message
                            assert "Cached in database" in result.output
                            assert "ID: 23598" in result.output

    def test_download_works_without_catalog_database(self, runner, sample_benchmark, tmp_path):
        """Download still works when catalog database doesn't exist."""
        with runner.isolated_filesystem():
            # Point to non-existent catalog
            nonexistent_path = tmp_path / "nonexistent" / "catalog.db"

            with patch("cis_bench.cli.commands.download.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = nonexistent_path

                mock_session = Mock()
                with patch(
                    "cis_bench.cli.commands.download.AuthManager.get_or_create_session"
                ) as mock_auth:
                    mock_auth.return_value = mock_session

                    with patch(
                        "cis_bench.cli.commands.download.WorkbenchScraper"
                    ) as mock_scraper_class:
                        mock_scraper = Mock()
                        mock_scraper_class.return_value = mock_scraper
                        mock_scraper.download_benchmark.return_value = sample_benchmark

                        result = runner.invoke(
                            cli,
                            ["download", "23598", "--browser", "chrome"],
                        )

                        # Should succeed even without catalog
                        assert result.exit_code == 0, f"Download failed: {result.output}"

                        # Should NOT show caching message
                        assert "Cached in database" not in result.output

                        # Should still save JSON file (default format)
                        assert Path("benchmarks").exists()

    def test_download_continues_on_database_error(self, runner, sample_benchmark, tmp_path):
        """Download continues if database save fails."""
        with runner.isolated_filesystem():
            catalog_path = tmp_path / "catalog.db"
            catalog_path.touch()

            with patch("cis_bench.cli.commands.download.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path
                mock_config.get_verify_ssl.return_value = False

                mock_session = Mock()
                with patch(
                    "cis_bench.cli.commands.download.AuthManager.get_or_create_session"
                ) as mock_auth:
                    mock_auth.return_value = mock_session

                    with patch(
                        "cis_bench.cli.commands.download.WorkbenchScraper"
                    ) as mock_scraper_class:
                        mock_scraper = Mock()
                        mock_scraper_class.return_value = mock_scraper
                        mock_scraper.download_benchmark.return_value = sample_benchmark

                        # Mock database to raise error
                        with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                            mock_db = Mock()
                            mock_db_class.return_value = mock_db
                            mock_db.save_downloaded.side_effect = Exception("Database error")

                            result = runner.invoke(
                                cli,
                                ["download", "23598", "--browser", "chrome"],
                            )

                            # Should still succeed
                            assert result.exit_code == 0, f"Download failed: {result.output}"

                            # Should show warning
                            assert "Could not cache in database" in result.output

                            # Should still create JSON file
                            assert Path("benchmarks").exists()

    def test_download_multiple_benchmarks_caches_all(self, runner, sample_benchmark, tmp_path):
        """Download of multiple benchmarks caches all to database."""
        with runner.isolated_filesystem():
            catalog_path = tmp_path / "catalog.db"
            catalog_path.touch()

            with patch("cis_bench.cli.commands.download.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path
                mock_config.get_verify_ssl.return_value = False

                mock_session = Mock()
                with patch(
                    "cis_bench.cli.commands.download.AuthManager.get_or_create_session"
                ) as mock_auth:
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

                            result = runner.invoke(
                                cli,
                                ["download", "23598", "22605", "--browser", "chrome"],
                            )

                            assert result.exit_code == 0, f"Download failed: {result.output}"

                            # Verify both benchmarks were saved
                            assert mock_db.save_downloaded.call_count == 2

                            # Check calls (using kwargs now)
                            calls = mock_db.save_downloaded.call_args_list
                            assert calls[0].kwargs["benchmark_id"] == "23598"
                            assert calls[1].kwargs["benchmark_id"] == "22605"


# ============================================================================
# Tests: Integration with Export
# ============================================================================


class TestDownloadAndExportIntegration:
    """Test that downloaded benchmarks can be exported by ID."""

    def test_download_then_export_by_id_workflow(self, runner, sample_benchmark, tmp_path):
        """Complete workflow: download → cache → export by ID."""
        with runner.isolated_filesystem():
            catalog_path = tmp_path / "catalog.db"
            catalog_path.touch()

            with patch("cis_bench.cli.commands.download.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path
                mock_config.get_verify_ssl.return_value = False

                mock_session = Mock()
                with patch(
                    "cis_bench.cli.commands.download.AuthManager.get_or_create_session"
                ) as mock_auth:
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

                            # Step 1: Download
                            download_result = runner.invoke(
                                cli,
                                ["download", "23598", "--browser", "chrome"],
                            )

                            assert download_result.exit_code == 0
                            assert "Cached in database" in download_result.output

                            # Simulate database having the cached benchmark
                            mock_db.get_downloaded.return_value = {
                                "benchmark_id": "23598",
                                "content_json": sample_benchmark.model_dump_json(),
                                "downloaded_at": datetime.now(),
                                "recommendation_count": 2,
                            }

                            # Step 2: Export by ID (with mocked Config for export too)
                            with patch(
                                "cis_bench.cli.commands.export.Config"
                            ) as mock_export_config:
                                mock_export_config.get_catalog_db_path.return_value = catalog_path

                                export_result = runner.invoke(
                                    cli,
                                    ["export", "23598", "--format", "yaml"],
                                )

                                assert export_result.exit_code == 0
                                assert "Loaded from cache" in export_result.output
                                assert Path("benchmark_23598.yaml").exists()
