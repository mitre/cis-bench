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

    def test_get_shows_catalog_required_message(self, runner, tmp_path, monkeypatch):
        """Get command shows helpful message when catalog missing."""
        catalog_path = tmp_path / "nonexistent" / "catalog.db"

        monkeypatch.setenv("CIS_BENCH_DATA_DIR", str(catalog_path.parent))
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "100")

        result = runner.invoke(cli, ["get", "ubuntu", "--format", "json"])

        assert result.exit_code == 1
        assert "Catalog not found" in result.output
        assert "catalog refresh" in result.output


# ============================================================================
# Tests: Get Command - Single Result
# ============================================================================


class TestGetCommandSingleResult:
    """Test get command when search returns single result."""

    def test_get_with_single_match_downloads_and_exports(
        self, runner, sample_benchmark, tmp_path, monkeypatch
    ):
        """Get with single search match downloads and exports automatically."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_DATA_DIR", str(catalog_path.parent))
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "100")
        monkeypatch.setenv("CIS_BENCH_VERIFY_SSL", "false")

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
                with patch("cis_bench.fetcher.auth.AuthManager") as mock_auth:
                    mock_session = Mock()
                    mock_auth.return_value.get_or_create_session.return_value = mock_session

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

    def test_get_uses_configured_workbench_base_url(
        self, runner, sample_benchmark, tmp_path, monkeypatch
    ):
        """get constructs uncached benchmark download URLs from CIS_BENCH_WORKBENCH_URL."""
        monkeypatch.setenv("CIS_BENCH_WORKBENCH_URL", "https://workbench-staging.cisecurity.org")
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        with (
            patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class,
            patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class,
            patch("cis_bench.fetcher.auth.AuthManager") as mock_auth,
            patch("cis_bench.cli.helpers.download_helper.download_with_progress") as mock_download,
        ):
            monkeypatch.setenv("CIS_BENCH_DATA_DIR", str(catalog_path.parent))
            monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "100")
            mock_db = Mock()
            mock_db_class.return_value = mock_db
            mock_db.get_downloaded.side_effect = [
                None,
                {
                    "benchmark_id": "23456",
                    "content_json": sample_benchmark.model_dump_json(),
                    "downloaded_at": datetime.now(),
                },
            ]
            mock_search = Mock()
            mock_search_class.return_value = mock_search
            mock_search.search.return_value = [
                {
                    "benchmark_id": "23456",
                    "title": "CIS Ubuntu Linux 22.04 Benchmark",
                    "version": "v2.0.0",
                    "status": "Published",
                }
            ]
            mock_auth.return_value.get_or_create_session.return_value = Mock()
            mock_download.return_value = sample_benchmark

            result = runner.invoke(
                cli,
                [
                    "get",
                    "ubuntu 22",
                    "--format",
                    "json",
                    "--output",
                    str(tmp_path / "out.json"),
                    "--non-interactive",
                ],
            )

            assert result.exit_code == 0, result.output
            assert (
                mock_download.call_args[0][1]
                == "https://workbench-staging.cisecurity.org/benchmarks/23456"
            )

    def test_get_with_cached_benchmark_skips_download(
        self, runner, sample_benchmark, tmp_path, monkeypatch
    ):
        """Get uses cached benchmark if already downloaded."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_DATA_DIR", str(catalog_path.parent))
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "100")

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

    def test_get_with_multiple_matches_non_interactive_shows_table(
        self, runner, tmp_path, monkeypatch
    ):
        """Get with multiple matches in non-interactive mode shows table and exits."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_DATA_DIR", str(catalog_path.parent))
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "100")

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

    def test_get_with_no_matches(self, runner, tmp_path, monkeypatch):
        """Get with no search matches shows helpful message."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_DATA_DIR", str(catalog_path.parent))
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "100")

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


class TestGetRequestTimeoutSetting:
    """A bad CIS_BENCH_REQUEST_TIMEOUT is refused before get authenticates to download."""

    def _one_match(self, mock_search_class, mock_db_class, cached):
        mock_search_class.return_value.search.return_value = [
            {
                "benchmark_id": "23456",
                "title": "CIS Ubuntu Linux 22.04 Benchmark",
                "version": "v2.0.0",
                "status": "Published",
            }
        ]
        mock_db_class.return_value.get_downloaded.return_value = cached

    def test_get_rejects_a_bad_timeout_before_authenticating(self, runner, tmp_path, monkeypatch):
        monkeypatch.setenv("CIS_BENCH_REQUEST_TIMEOUT", "inf")
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()
        with (
            patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class,
            patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class,
            patch("cis_bench.fetcher.auth.AuthManager") as mock_auth,
        ):
            monkeypatch.setenv("CIS_BENCH_DATA_DIR", str(catalog_path.parent))
            self._one_match(mock_search_class, mock_db_class, cached=None)
            result = runner.invoke(cli, ["get", "ubuntu 22", "--non-interactive"])

        assert result.exit_code == 1
        assert "Configuration Error" in result.output
        assert "CIS_BENCH_REQUEST_TIMEOUT" in result.output
        mock_auth.return_value.get_or_create_session.assert_not_called()

    def test_get_serving_a_cached_benchmark_still_refuses_a_bad_timeout(
        self, runner, sample_benchmark, tmp_path, monkeypatch
    ):
        # Every setting is checked at startup, whether or not the command uses it.
        monkeypatch.setenv("CIS_BENCH_REQUEST_TIMEOUT", "inf")
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()
        cached = {
            "benchmark_id": "23456",
            "content_json": sample_benchmark.model_dump_json(),
            "downloaded_at": datetime.now(),
        }
        with runner.isolated_filesystem():
            with (
                patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class,
                patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class,
                patch("cis_bench.fetcher.auth.AuthManager") as mock_auth,
            ):
                monkeypatch.setenv("CIS_BENCH_DATA_DIR", str(catalog_path.parent))
                self._one_match(mock_search_class, mock_db_class, cached=cached)
                result = runner.invoke(
                    cli, ["get", "ubuntu 22", "--format", "json", "--non-interactive"]
                )

        assert result.exit_code == 1, result.output
        assert "Configuration Error" in result.output
        assert "CIS_BENCH_REQUEST_TIMEOUT" in result.output
        mock_search_class.assert_not_called()
        mock_auth.return_value.get_or_create_session.assert_not_called()


class TestGetCandidateLimit:
    def test_get_takes_its_candidate_limit_from_the_search_limit_setting(
        self, runner, small_catalog, monkeypatch
    ):
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "3")
        monkeypatch.setenv("CIS_BENCH_DATA_DIR", str(small_catalog.parent))
        result = runner.invoke(cli, ["get", "sample", "--non-interactive"])

        assert "Found 5 benchmarks matching 'sample' (showing the first 3)" in result.output


class TestGetTitleWidthSetting:
    """The table of matches get prints follows CIS_BENCH_TABLE_TITLE_WIDTH, as search's does."""

    LONG_TITLE = "CIS Sample Benchmark for a Platform With a Long Name"

    @staticmethod
    def _title_cells(output: str) -> list[str]:
        """The Title cell of every table body row, as printed (one padding space each side)."""
        return [line.split("│")[2] for line in output.splitlines() if line.startswith("│")]

    def test_table_title_width_setting_caps_the_title_column(self, runner, tmp_path, monkeypatch):
        from cis_bench.catalog.database import CatalogDatabase

        db = CatalogDatabase(tmp_path / "catalog.db")
        try:
            db.initialize_schema()
            for benchmark_id, suffix in (("701", "A"), ("702", "B")):
                db.insert_benchmark(
                    {
                        "benchmark_id": benchmark_id,
                        "title": f"{self.LONG_TITLE} {suffix}",
                        "version": "v1.0.0",
                        "url": f"https://workbench.cisecurity.org/benchmarks/{benchmark_id}",
                        "status": "Published",
                    }
                )
            db.mark_latest_versions()
        finally:
            db.engine.dispose()
        monkeypatch.setenv("CIS_BENCH_DATA_DIR", str(tmp_path))

        monkeypatch.delenv("CIS_BENCH_TABLE_TITLE_WIDTH", raising=False)
        default = runner.invoke(cli, ["get", "sample", "--non-interactive"])
        assert default.exit_code == 0, default.output
        assert max(len(cell) - 2 for cell in self._title_cells(default.output)) > 30

        monkeypatch.setenv("CIS_BENCH_TABLE_TITLE_WIDTH", "30")
        capped = runner.invoke(cli, ["get", "sample", "--non-interactive"])

        assert capped.exit_code == 0, capped.output
        assert max(len(cell) - 2 for cell in self._title_cells(capped.output)) == 30
