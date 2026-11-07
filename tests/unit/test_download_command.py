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
        self, runner, sample_benchmark, tmp_path, monkeypatch
    ):
        """Download saves benchmark to catalog database if it exists."""
        # Create catalog database file
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        # The test catalog is catalog.db in the data folder
        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))

        # Mock AuthManager to return session
        mock_session = Mock()
        monkeypatch.setenv("CIS_BENCH_VERIFY_SSL", "false")
        with patch("cis_bench.fetcher.auth.AuthManager.get_or_create_session") as mock_auth:
            mock_auth.return_value = mock_session

            # Mock WorkbenchScraper to return sample benchmark
            with patch("cis_bench.fetcher.workbench.WorkbenchScraper") as mock_scraper_class:
                mock_scraper = Mock()
                mock_scraper_class.return_value = mock_scraper
                mock_scraper.download_benchmark.return_value = sample_benchmark

                # Mock CatalogDatabase
                with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                    mock_db = Mock()
                    mock_db_class.return_value = mock_db

                    result = runner.invoke(
                        cli,
                        ["download", "23598"],
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

    def test_download_works_without_catalog_database(
        self, runner, sample_benchmark, tmp_path, monkeypatch
    ):
        """Download still works when catalog database doesn't exist."""
        # Point to non-existent catalog
        nonexistent_path = tmp_path / "nonexistent" / "catalog.db"

        monkeypatch.setenv("CIS_BENCH_HOME", str(nonexistent_path.parent))

        mock_session = Mock()
        with patch("cis_bench.fetcher.auth.AuthManager.get_or_create_session") as mock_auth:
            mock_auth.return_value = mock_session

            with patch("cis_bench.fetcher.workbench.WorkbenchScraper") as mock_scraper_class:
                mock_scraper = Mock()
                mock_scraper_class.return_value = mock_scraper
                mock_scraper.download_benchmark.return_value = sample_benchmark

                result = runner.invoke(
                    cli,
                    ["download", "23598"],
                )

                # Should succeed even without catalog
                assert result.exit_code == 0, f"Download failed: {result.output}"

                # Should NOT show caching message
                assert "Cached in database" not in result.output

                # Should still save the JSON file (default format) in the data folder
                assert list((nonexistent_path.parent / "benchmarks").glob("*.json"))

    def test_a_failed_cache_write_fails_that_benchmark_but_keeps_its_exports(
        self, runner, sample_benchmark, tmp_path, monkeypatch
    ):
        """The download is not thrown away: its exports are written, the failure is reported,
        and the command exits 1 because not everything asked for was done."""
        from sqlalchemy.exc import OperationalError

        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
        monkeypatch.setenv("CIS_BENCH_VERIFY_SSL", "false")

        with (
            patch("cis_bench.fetcher.auth.AuthManager.get_or_create_session"),
            patch("cis_bench.fetcher.workbench.WorkbenchScraper") as mock_scraper_class,
            patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class,
        ):
            mock_scraper_class.return_value.download_benchmark.return_value = sample_benchmark
            mock_db = mock_db_class.return_value
            mock_db.get_downloaded.return_value = None
            mock_db.get_benchmark.return_value = None
            mock_db.save_downloaded.side_effect = OperationalError(
                "INSERT", {}, Exception("database is locked [/x]")
            )

            result = runner.invoke(cli, ["download", "23598"])

        assert result.exit_code == 1, result.output
        flat = " ".join(result.output.split())
        assert "Could not cache 23598:" in flat
        assert "database is locked [/x]" in flat
        assert "INSERT" not in result.output
        assert "Cached in database" not in result.output
        assert "1 of 1 benchmark(s) failed (23598)" in flat
        assert "Traceback" not in result.output
        assert list((tmp_path / "benchmarks").glob("*.json"))

    def test_an_unexpected_cache_error_is_not_swallowed(
        self, runner, sample_benchmark, tmp_path, monkeypatch
    ):
        """Only database and OS errors are a failed cache write; anything else is a bug."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()
        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))

        with (
            patch("cis_bench.fetcher.auth.AuthManager.get_or_create_session"),
            patch("cis_bench.fetcher.workbench.WorkbenchScraper") as mock_scraper_class,
            patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class,
        ):
            mock_scraper_class.return_value.download_benchmark.return_value = sample_benchmark
            mock_db = mock_db_class.return_value
            mock_db.get_downloaded.return_value = None
            mock_db.save_downloaded.side_effect = TypeError("a bug")

            result = runner.invoke(cli, ["download", "23598"])

        assert result.exit_code == 1
        assert "Could not cache" not in result.output

    def test_download_multiple_benchmarks_caches_all(
        self, runner, sample_benchmark, tmp_path, monkeypatch
    ):
        """Download of multiple benchmarks caches all to database."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
        monkeypatch.setenv("CIS_BENCH_VERIFY_SSL", "false")

        mock_session = Mock()
        with patch("cis_bench.fetcher.auth.AuthManager.get_or_create_session") as mock_auth:
            mock_auth.return_value = mock_session

            with patch("cis_bench.fetcher.workbench.WorkbenchScraper") as mock_scraper_class:
                mock_scraper = Mock()
                mock_scraper_class.return_value = mock_scraper
                mock_scraper.download_benchmark.return_value = sample_benchmark

                with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                    mock_db = Mock()
                    mock_db_class.return_value = mock_db

                    result = runner.invoke(
                        cli,
                        ["download", "23598", "22605"],
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

    def test_download_then_export_by_id_workflow(
        self, runner, sample_benchmark, tmp_path, monkeypatch, working_dir
    ):
        """Complete workflow: download → cache → export by ID."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
        monkeypatch.setenv("CIS_BENCH_VERIFY_SSL", "false")

        mock_session = Mock()
        with patch("cis_bench.fetcher.auth.AuthManager.get_or_create_session") as mock_auth:
            mock_auth.return_value = mock_session

            with patch("cis_bench.fetcher.workbench.WorkbenchScraper") as mock_scraper_class:
                mock_scraper = Mock()
                mock_scraper_class.return_value = mock_scraper
                mock_scraper.download_benchmark.return_value = sample_benchmark

                with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                    mock_db = Mock()
                    mock_db_class.return_value = mock_db

                    # Step 1: Download
                    download_result = runner.invoke(
                        cli,
                        ["download", "23598"],
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

                    # Step 2: Export by ID from the same data folder
                    monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))

                    export_result = runner.invoke(
                        cli,
                        ["export", "23598", "--format", "yaml"],
                    )

                    assert export_result.exit_code == 0
                    assert "Loaded from cache" in export_result.output
                    assert Path("benchmark_23598.yaml").exists()

    def test_download_uses_configured_workbench_base_url(
        self, runner, sample_benchmark, tmp_path, monkeypatch
    ):
        """download constructs benchmark URLs from CIS_BENCH_WORKBENCH_URL."""
        monkeypatch.setenv("CIS_BENCH_WORKBENCH_URL", "https://workbench-staging.cisecurity.org")
        nonexistent_path = tmp_path / "nonexistent" / "catalog.db"
        with (
            patch(
                "cis_bench.fetcher.auth.AuthManager.get_or_create_session",
                return_value=Mock(),
            ),
            patch("cis_bench.fetcher.workbench.WorkbenchScraper") as mock_scraper_class,
        ):
            monkeypatch.setenv("CIS_BENCH_HOME", str(nonexistent_path.parent))
            mock_scraper = Mock()
            mock_scraper.download_benchmark.return_value = sample_benchmark
            mock_scraper_class.return_value = mock_scraper

            result = runner.invoke(cli, ["download", "23598"])

            assert result.exit_code == 0, result.output
            assert (
                mock_scraper.download_benchmark.call_args[0][0]
                == "https://workbench-staging.cisecurity.org/benchmarks/23598"
            )


class TestDownloadWithAnInvalidWorkbenchUrl:
    @pytest.mark.parametrize("workbench_url", ["ftp://x", "not-a-url"])
    def test_invalid_workbench_url_stops_download_and_keeps_the_saved_session(
        self, runner, data_dir, monkeypatch, workbench_url
    ):
        """An invalid CIS_BENCH_WORKBENCH_URL is a configuration error; the saved session is untouched."""
        session_file = data_dir / "session.cookies"
        original = b"# Netscape HTTP Cookie File\n.cisecurity.org\tTRUE\t/\tTRUE\t0\tsid\tabc\n"
        session_file.write_bytes(original)
        monkeypatch.setenv("CIS_BENCH_WORKBENCH_URL", workbench_url)

        result = runner.invoke(cli, ["download", "23598"])

        assert result.exit_code == 1
        assert "Configuration Error" in result.output
        assert "CIS_BENCH_WORKBENCH_URL" in result.output
        assert session_file.exists()
        assert session_file.read_bytes() == original
