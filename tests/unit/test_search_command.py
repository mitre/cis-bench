"""Unit tests for top-level search command."""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from cis_bench.cli.app import cli
from tests.conftest import unusable_command_hints


@pytest.fixture
def runner():
    """Create Click CLI test runner and prune closed logging handlers after invocation."""
    import logging

    yield CliRunner()
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        stream = getattr(handler, "stream", None)
        if stream is not None and getattr(stream, "closed", False):
            root_logger.removeHandler(handler)


# ============================================================================
# Tests: Search Command Behavior
# ============================================================================


class TestSearchCommand:
    """Test top-level search command (catalog-aware)."""

    def test_search_without_catalog_shows_helpful_message(self, runner, tmp_path, monkeypatch):
        """Search shows helpful message when catalog doesn't exist."""
        # Point to non-existent catalog
        nonexistent_path = tmp_path / "nonexistent" / "catalog.db"

        monkeypatch.setenv("CIS_BENCH_HOME", str(nonexistent_path.parent))

        result = runner.invoke(cli, ["search", "ubuntu"])

        assert result.exit_code == 1
        assert "Local catalog not found" in result.output
        assert "catalog refresh" in result.output
        assert "one-time setup" in result.output

    def test_search_with_catalog_returns_results(self, runner, tmp_path, monkeypatch):
        """Search returns results when catalog exists."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "1000")

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

    def test_search_with_filters(self, runner, tmp_path, monkeypatch):
        """Search respects platform, status, and latest filters."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "1000")

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

    def test_search_without_query_lists_all(self, runner, tmp_path, monkeypatch):
        """Search without query lists all benchmarks."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "1000")

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

    def test_search_no_results_message(self, runner, tmp_path, monkeypatch):
        """Search shows friendly message when no results found."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "1000")

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

    def test_search_shows_next_steps(self, runner, tmp_path, monkeypatch):
        """Search shows helpful next steps after results."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "1000")

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

        # Outside the patches above: resolving a hinted command imports its module.
        assert unusable_command_hints(result.output) == []

    def test_search_limit_parameter(self, runner, tmp_path, monkeypatch):
        """Search respects limit parameter."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "1000")

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

    def test_search_handles_database_errors_gracefully(self, runner, tmp_path, monkeypatch):
        """Search handles database errors gracefully."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))

        with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
            mock_db_class.side_effect = Exception("Database error [/e]")

            result = runner.invoke(cli, ["search", "test"])

            assert result.exit_code == 1
            assert result.output.count("Search failed: Database error [/e]") == 1
            assert "Traceback" not in result.output

    def test_search_failure_traceback_is_written_with_verbose(self, runner, tmp_path, monkeypatch):
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()
        with (
            patch("cis_bench.catalog.database.CatalogDatabase", side_effect=Exception("boom")),
        ):
            monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))

            result = runner.invoke(cli, ["--verbose", "search", "test"])

        assert result.exit_code == 1
        assert "Traceback" in result.output

    def test_search_table_prints_titles_versions_and_statuses_verbatim(
        self, runner, tmp_path, monkeypatch
    ):
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()
        with (
            patch("cis_bench.catalog.database.CatalogDatabase"),
            patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class,
        ):
            monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
            monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "1000")
            mock_search_class.return_value.search.return_value = [
                {
                    "benchmark_id": "1",
                    "title": "CIS T [/t]",
                    "version": "v1 [/v]",
                    "status": "P [/s]",
                }
            ]

            result = runner.invoke(cli, ["search", "linux"])

        assert result.exit_code == 0, result.output
        assert "CIS T [/t]" in result.output
        assert "v1 [/v]" in result.output
        assert "P [/s]" in result.output

    def test_search_escapes_rich_markup_in_query(self, runner, tmp_path, monkeypatch):
        """Bracketed queries such as [/opt] render literally without raising MarkupError."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        with (
            patch("cis_bench.catalog.database.CatalogDatabase"),
            patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class,
        ):
            monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
            monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "1000")
            mock_search = Mock()
            mock_search.search.return_value = []
            mock_search_class.return_value = mock_search

            result = runner.invoke(cli, ["search", "[/opt]"])

            assert result.exit_code == 0
            assert "Searching for: [/opt]" in result.output
            assert "No results found" in result.output

    def test_search_status_all_and_blank_return_all_statuses_against_real_db(
        self, runner, tmp_path, monkeypatch
    ):
        """--status all (case-insensitive) and blank --status return all statuses without bogus filter hints."""
        import json

        from cis_bench.catalog.database import CatalogDatabase

        catalog_path = tmp_path / "catalog.db"
        db = CatalogDatabase(catalog_path)
        try:
            db.initialize_schema()
            for bid, status in [
                ("501", "Published"),
                ("502", "Archived"),
                ("503", "Draft"),
                ("504", "Final Update"),
            ]:
                db.insert_benchmark(
                    {
                        "benchmark_id": bid,
                        "title": f"CIS Multi Status Benchmark {bid}",
                        "version": "v1.0.0",
                        "url": f"https://workbench.cisecurity.org/benchmarks/{bid}",
                        "status": status,
                    }
                )
        finally:
            db.engine.dispose()

        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "1000")

        for flag_val in ("all", "ALL", ""):
            res = runner.invoke(cli, ["search", "--status", flag_val, "--output-format", "json"])
            assert res.exit_code == 0
            payload = json.loads(res.stdout)
            assert sorted(item["benchmark_id"] for item in payload) == [
                "501",
                "502",
                "503",
                "504",
            ]

        empty_res = runner.invoke(cli, ["search", "nonexistent-xyz", "--status", "all"])
        assert empty_res.exit_code == 0
        assert "No results found" in empty_res.output
        assert "Try removing some filters" not in empty_res.output


class TestStatusFilterPassThrough:
    """The search command forwards --status as typed; normalization lives in the database layer."""

    def test_search_forwards_raw_status_to_catalog_search(self, runner, tmp_path, monkeypatch):
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()
        with (
            patch("cis_bench.catalog.database.CatalogDatabase"),
            patch("cis_bench.catalog.search.CatalogSearch") as mock_search_class,
        ):
            monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))
            monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "1000")
            mock_search = mock_search_class.return_value
            mock_search.search.return_value = []

            result = runner.invoke(cli, ["search", "ubuntu", "--status", " ALL "])

        assert result.exit_code == 0, result.output
        assert mock_search.search.call_args.kwargs["status"] == " ALL "


class TestSearchShowsWhatTheLimitCutOff:
    def test_a_cut_off_list_says_how_many_matched_and_how_to_see_more(
        self, runner, small_catalog, monkeypatch
    ):
        monkeypatch.setenv("CIS_BENCH_HOME", str(small_catalog.parent))
        result = runner.invoke(cli, ["search", "sample", "--limit", "2"])

        assert result.exit_code == 0, result.output
        assert "Showing 2 of 5 results; use --limit to see more" in result.output

    def test_a_whole_list_says_so(self, runner, small_catalog, monkeypatch):
        monkeypatch.setenv("CIS_BENCH_HOME", str(small_catalog.parent))
        result = runner.invoke(cli, ["search", "sample"])

        assert result.exit_code == 0, result.output
        assert "Showing 5 of 5 results" in result.output
        assert "use --limit" not in result.output

    def test_the_search_limit_setting_is_the_limit_when_no_flag_is_given(
        self, runner, small_catalog, monkeypatch
    ):
        monkeypatch.setenv("CIS_BENCH_HOME", str(small_catalog.parent))
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "2")
        result = runner.invoke(cli, ["search", "sample"])

        assert result.exit_code == 0, result.output
        assert "Showing 2 of 5 results; use --limit to see more" in result.output


class TestSearchTitleWidthSetting:
    LONG_TITLE = "CIS Sample Benchmark for a Platform With a Long Name"

    @staticmethod
    def _title_cells(output: str) -> list[str]:
        """The Title cell of every table body row, as printed (one padding space each side)."""
        return [line.split("│")[2] for line in output.splitlines() if line.startswith("│")]

    def test_table_title_width_setting_caps_the_title_column(self, runner, tmp_path, monkeypatch):
        """CIS_BENCH_TABLE_TITLE_WIDTH=30 keeps the Title column of search output at 30 characters."""
        from cis_bench.catalog.database import CatalogDatabase

        db = CatalogDatabase(tmp_path / "catalog.db")
        try:
            db.initialize_schema()
            db.insert_benchmark(
                {
                    "benchmark_id": "701",
                    "title": self.LONG_TITLE,
                    "version": "v1.0.0",
                    "url": "https://workbench.cisecurity.org/benchmarks/701",
                    "status": "Published",
                }
            )
            db.mark_latest_versions()
        finally:
            db.engine.dispose()
        monkeypatch.setenv("CIS_BENCH_HOME", str(tmp_path))

        monkeypatch.delenv("CIS_BENCH_TABLE_TITLE_WIDTH", raising=False)
        default = runner.invoke(cli, ["search", "sample"])
        assert default.exit_code == 0, default.output
        assert max(len(cell) - 2 for cell in self._title_cells(default.output)) > 30

        monkeypatch.setenv("CIS_BENCH_TABLE_TITLE_WIDTH", "30")
        capped = runner.invoke(cli, ["search", "sample"])

        assert capped.exit_code == 0, capped.output
        cells = self._title_cells(capped.output)
        assert max(len(cell) - 2 for cell in cells) == 30
        assert " ".join(cell.strip() for cell in cells) == self.LONG_TITLE
