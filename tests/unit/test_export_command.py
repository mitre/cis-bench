"""Unit tests for export command.

Tests both file-based and database-based export functionality.
"""

import warnings
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from bs4 import MarkupResemblesLocatorWarning
from click.testing import CliRunner

from cis_bench.cli.app import cli
from cis_bench.models.benchmark import Benchmark, Recommendation


@pytest.fixture
def runner():
    """Create Click CLI test runner and prune closed stderr handlers on teardown."""
    import logging

    cli_runner = CliRunner()
    yield cli_runner
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        stream = getattr(handler, "stream", None)
        if stream is not None and getattr(stream, "closed", False):
            root_logger.removeHandler(handler)


@pytest.fixture
def sample_benchmark():
    """Create a sample benchmark for testing."""
    return Benchmark(
        title="CIS AlmaLinux OS 8 Benchmark",
        benchmark_id="23598",
        url="https://workbench.cisecurity.org/benchmarks/23598",
        version="v4.0.0",
        downloaded_at=datetime(2025, 10, 18, 12, 0, 0),
        scraper_version="v1_2025_10",
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


@pytest.fixture
def sample_benchmark_json(sample_benchmark, tmp_path):
    """Create a temporary JSON file with sample benchmark."""
    json_file = tmp_path / "benchmark.json"
    json_file.write_text(sample_benchmark.model_dump_json(indent=2))
    return json_file


# ============================================================================
# Tests: File-based Export (Existing Functionality)
# ============================================================================


class TestExportFromFile:
    """Test export command with file paths (existing functionality)."""

    def test_export_from_file_yaml(self, runner, sample_benchmark_json, working_dir):
        """Export benchmark from file to YAML format."""
        import shutil

        shutil.copy(str(sample_benchmark_json), "benchmark.json")

        result = runner.invoke(cli, ["export", "benchmark.json", "--format", "yaml"])

        assert result.exit_code == 0, f"Export failed: {result.output}"
        assert "Loaded: CIS AlmaLinux OS 8 Benchmark" in result.output
        assert "Exported 2 recommendations" in result.output
        assert Path("benchmark.yaml").exists()

    def test_export_from_file_csv(self, runner, sample_benchmark_json, working_dir):
        """Export benchmark from file to CSV format."""
        import shutil

        shutil.copy(str(sample_benchmark_json), "benchmark.json")

        result = runner.invoke(cli, ["export", "benchmark.json", "--format", "csv"])

        assert result.exit_code == 0
        assert Path("benchmark.csv").exists()

    def test_export_from_file_markdown(self, runner, sample_benchmark_json, working_dir):
        """Export benchmark from file to Markdown format."""
        import shutil

        shutil.copy(str(sample_benchmark_json), "benchmark.json")

        result = runner.invoke(cli, ["export", "benchmark.json", "--format", "markdown"])

        assert result.exit_code == 0
        assert Path("benchmark.md").exists()

    def test_output_option_refuses_a_directory(self, runner, sample_benchmark_json, working_dir):
        """-o names a file; a directory is a usage error before any export work."""
        import shutil

        shutil.copy(str(sample_benchmark_json), "benchmark.json")
        Path("out").mkdir()

        with patch("cis_bench.exporters.ExporterFactory.create") as create:
            result = runner.invoke(cli, ["export", "benchmark.json", "-o", "out"])

        assert result.exit_code == 2, result.output
        assert "'--output' / '-o'" in result.output
        assert "is a directory" in result.output
        assert "Traceback" not in result.output
        create.assert_not_called()
        assert list(Path("out").iterdir()) == []

    def test_output_option_help_points_at_output_dir_for_folders(self, runner):
        result = runner.invoke(cli, ["export", "--help"])

        assert result.exit_code == 0
        help_text = " ".join(result.output.split())
        assert "--output-dir" in help_text.split("-o, --output", 1)[1].split("--output-dir ", 1)[0]

    def test_markdown_export_of_a_field_that_is_only_a_url_prints_no_parser_warning(
        self, runner, sample_benchmark, working_dir
    ):
        """A recommendation whose text is just a URL exports without bs4's URL warning."""
        url_only = sample_benchmark.model_copy(deep=True)
        url_only.recommendations[0].description = "https://www.cisecurity.org/benchmark/almalinux"
        Path("benchmark.json").write_text(url_only.model_dump_json())

        with warnings.catch_warnings(record=True) as seen:
            warnings.simplefilter("always")
            result = runner.invoke(cli, ["export", "benchmark.json", "--format", "markdown"])

        assert result.exit_code == 0, result.output
        assert [w for w in seen if issubclass(w.category, MarkupResemblesLocatorWarning)] == []
        assert "https://www.cisecurity.org/benchmark/almalinux" in Path("benchmark.md").read_text()

    def test_markdown_export_writes_the_download_time_with_its_offset(
        self, runner, sample_benchmark, working_dir
    ):
        """A document carries the instant in ISO 8601 with its offset, as the other exports do."""
        aware = sample_benchmark.model_copy(
            update={"downloaded_at": datetime(2026, 11, 7, 2, 5, 58, tzinfo=UTC)}
        )
        Path("benchmark.json").write_text(aware.model_dump_json())

        result = runner.invoke(cli, ["export", "benchmark.json", "--format", "markdown"])

        assert result.exit_code == 0, result.output
        assert "**Downloaded:** 2026-11-07T02:05:58+00:00  " in Path("benchmark.md").read_text()

    def test_export_from_file_xccdf_disa(self, runner, sample_benchmark_json, working_dir):
        """Export benchmark from file to XCCDF DISA format."""
        import shutil

        shutil.copy(str(sample_benchmark_json), "benchmark.json")

        result = runner.invoke(
            cli, ["export", "benchmark.json", "--format", "xccdf", "--style", "disa"]
        )

        assert result.exit_code == 0
        assert Path("benchmark.xml").exists()

    def test_export_from_file_xccdf_cis(self, runner, sample_benchmark_json, working_dir):
        """Export benchmark from file to XCCDF CIS format."""
        import shutil

        shutil.copy(str(sample_benchmark_json), "benchmark.json")

        result = runner.invoke(
            cli, ["export", "benchmark.json", "--format", "xccdf", "--style", "cis"]
        )

        assert result.exit_code == 0
        assert Path("benchmark.xml").exists()

    def test_a_batch_with_one_failed_export_exits_1(
        self, runner, sample_benchmark_json, working_dir
    ):
        """One good and one missing benchmark: exit 1, the good export still written."""
        result = runner.invoke(
            cli, ["export", str(sample_benchmark_json), "nonexistent.json", "--format", "yaml"]
        )

        assert result.exit_code == 1, result.output
        assert "Export complete with errors." in result.output
        assert "1 succeeded, 1 failed." in result.output
        assert [path.suffix for path in working_dir.iterdir()] == [".yaml"]

    def test_a_batch_where_every_export_succeeds_exits_0(
        self, runner, sample_benchmark_json, working_dir
    ):
        result = runner.invoke(
            cli,
            ["export", str(sample_benchmark_json), str(sample_benchmark_json), "--format", "yaml"],
        )

        assert result.exit_code == 0, result.output
        assert "Export complete! 2 benchmarks exported." in result.output

    def test_an_id_with_surrounding_spaces_still_reads_the_cache(
        self, runner, sample_benchmark, tmp_path, monkeypatch, working_dir
    ):
        from cis_bench.catalog.database import CatalogDatabase, serialize_benchmark_json

        db = CatalogDatabase(tmp_path / "catalog.db")
        try:
            db.initialize_schema()
            db.insert_benchmark(
                {
                    "benchmark_id": "23598",
                    "title": "CIS AlmaLinux OS 8 Benchmark",
                    "version": "v4.0.0",
                    "url": "https://workbench.cisecurity.org/benchmarks/23598",
                    "status": "Published",
                }
            )
            content_json, content_hash = serialize_benchmark_json(sample_benchmark)
            db.save_downloaded("23598", content_json, content_hash, 3, version="v4.0.0")
        finally:
            db.close()
        monkeypatch.setenv("CIS_BENCH_HOME", str(tmp_path))

        result = runner.invoke(cli, ["export", " 23598 ", "--format", "yaml"])

        assert result.exit_code == 0, result.output
        assert [path.suffix for path in working_dir.iterdir()] == [".yaml"]

    def test_a_string_of_non_ascii_digits_is_a_file_name_not_an_id(self, runner):
        """Every command uses the same test for a benchmark ID: ASCII digits only."""
        result = runner.invoke(
            cli, ["export", "\u0662\u0663\u0665\u0669\u0668", "--format", "yaml"]
        )

        assert result.exit_code == 1
        assert "File not found" in result.output

    def test_export_file_not_found(self, runner):
        """Export fails gracefully when file not found."""
        result = runner.invoke(cli, ["export", "nonexistent.json", "--format", "yaml"])

        assert result.exit_code == 1
        assert "File not found" in result.output

    def test_export_with_custom_output_file(self, runner, sample_benchmark_json, working_dir):
        """Export with custom output filename."""
        import shutil

        shutil.copy(str(sample_benchmark_json), "benchmark.json")

        result = runner.invoke(
            cli, ["export", "benchmark.json", "--format", "yaml", "--output", "custom.yaml"]
        )

        assert result.exit_code == 0
        assert Path("custom.yaml").exists()

    def test_export_prints_title_and_paths_verbatim(self, runner, sample_benchmark, working_dir):
        sample_benchmark.title = "CIS T [/t]"
        Path("in[x].json").write_text(sample_benchmark.model_dump_json())

        result = runner.invoke(
            cli, ["export", "in[x].json", "--format", "yaml", "--output", "out[o].yaml"]
        )

        assert result.exit_code == 0, result.output
        assert Path("out[o].yaml").exists()
        assert "Loaded: CIS T [/t]" in result.output
        assert "recommendations to out[o].yaml" in result.output  # the INFO log line also names it

    def test_export_missing_file_prints_its_path_verbatim(self, runner, tmp_path, monkeypatch):
        # A short relative data folder keeps the printed path on one line.
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("CIS_BENCH_HOME", "data")
        result = runner.invoke(cli, ["export", "missing[/p].json", "--format", "yaml"])

        assert result.exit_code == 1
        assert isinstance(result.exception, SystemExit)  # handled, not a crash in the handler
        assert "Traceback" not in result.output
        # the INFO log line also names the file; check the error line itself
        assert "Error: File not found: data/benchmarks/missing[/p].json" in result.output

    def test_export_failure_prints_one_line_without_a_traceback(
        self, runner, sample_benchmark_json
    ):
        with patch("cis_bench.cli.commands.export.ExporterFactory") as mock_factory:
            mock_factory.create.return_value.export.side_effect = Exception("Disk full [/e]")

            result = runner.invoke(cli, ["export", str(sample_benchmark_json), "--format", "yaml"])

        assert result.exit_code == 1
        assert result.output.count("Export failed: Disk full [/e]") == 1
        assert "Traceback" not in result.output

    def test_export_failure_traceback_is_written_with_verbose(self, runner, sample_benchmark_json):
        with patch("cis_bench.cli.commands.export.ExporterFactory") as mock_factory:
            mock_factory.create.return_value.export.side_effect = Exception("Disk full")

            result = runner.invoke(
                cli, ["--verbose", "export", str(sample_benchmark_json), "--format", "yaml"]
            )

        assert result.exit_code == 1
        assert "Traceback" in result.output


# ============================================================================
# Tests: Database-based Export (NEW Functionality)
# ============================================================================


class TestExportFromDatabase:
    """Test export command with benchmark IDs (new functionality)."""

    def test_export_from_db_by_id(
        self, runner, sample_benchmark, tmp_path, monkeypatch, working_dir
    ):
        """Export benchmark from database by ID."""
        # Create empty catalog file so .exists() check passes
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))

        # Mock CatalogDatabase (imported inside function, so patch at source)
        with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
            mock_db = Mock()
            mock_db_class.return_value = mock_db

            # Simulate downloaded benchmark in database
            mock_db.get_downloaded.return_value = {
                "benchmark_id": "23598",
                "content_json": sample_benchmark.model_dump_json(),
                "downloaded_at": datetime.now(),
                "recommendation_count": 2,
            }

            result = runner.invoke(cli, ["export", "23598", "--format", "yaml"])

            assert result.exit_code == 0, f"Export failed: {result.output}"
            assert "Loaded from cache: CIS AlmaLinux OS 8 Benchmark" in result.output
            assert "Exported 2 recommendations" in result.output
            assert Path("benchmark_23598.yaml").exists()

    def test_export_from_db_benchmark_not_downloaded(self, runner, tmp_path, monkeypatch):
        """Export fails when benchmark ID not in database."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))

        with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
            mock_db = Mock()
            mock_db_class.return_value = mock_db
            mock_db.get_downloaded.return_value = None  # Not found

            result = runner.invoke(cli, ["export", "23598", "--format", "yaml"])

            assert result.exit_code == 1
            assert "Benchmark 23598 not downloaded" in result.output
            assert "cis-bench download 23598" in result.output

    def test_export_from_db_catalog_not_exists(self, runner, tmp_path, monkeypatch):
        """Export fails when catalog database doesn't exist."""
        # Point to non-existent catalog
        nonexistent_path = tmp_path / "nonexistent" / "catalog.db"

        monkeypatch.setenv("CIS_BENCH_HOME", str(nonexistent_path.parent))

        result = runner.invoke(cli, ["export", "23598", "--format", "yaml"])

        assert result.exit_code == 1
        assert "Catalog database not found" in result.output
        assert "catalog refresh" in result.output

    def test_export_from_db_xccdf_with_style(
        self, runner, sample_benchmark, tmp_path, monkeypatch, working_dir
    ):
        """Export from database to XCCDF with CIS style."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))

        with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
            mock_db = Mock()
            mock_db_class.return_value = mock_db
            mock_db.get_downloaded.return_value = {
                "benchmark_id": "23598",
                "content_json": sample_benchmark.model_dump_json(),
                "downloaded_at": datetime.now(),
                "recommendation_count": 2,
            }

            result = runner.invoke(cli, ["export", "23598", "--format", "xccdf", "--style", "cis"])

            assert result.exit_code == 0
            assert Path("benchmark_23598.xml").exists()

    def test_export_from_db_with_custom_output(
        self, runner, sample_benchmark, tmp_path, monkeypatch, working_dir
    ):
        """Export from database with custom output filename."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))

        with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
            mock_db = Mock()
            mock_db_class.return_value = mock_db
            mock_db.get_downloaded.return_value = {
                "benchmark_id": "23598",
                "content_json": sample_benchmark.model_dump_json(),
                "downloaded_at": datetime.now(),
                "recommendation_count": 2,
            }

            result = runner.invoke(
                cli, ["export", "23598", "--format", "yaml", "--output", "custom.yaml"]
            )

            assert result.exit_code == 0
            assert Path("custom.yaml").exists()
            assert not Path("benchmark_23598.yaml").exists()

    def test_export_from_db_invalid_json_in_database(self, runner, tmp_path, monkeypatch):
        """Export fails gracefully when database contains invalid JSON."""
        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))

        with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
            mock_db = Mock()
            mock_db_class.return_value = mock_db
            mock_db.get_downloaded.return_value = {
                "benchmark_id": "23598",
                "content_json": "{invalid json}",  # Invalid JSON
                "downloaded_at": datetime.now(),
                "recommendation_count": 2,
            }

            result = runner.invoke(cli, ["export", "23598", "--format", "yaml"])

            assert result.exit_code == 1
            assert "Error loading from database" in result.output
            # pydantic's message carries bracketed detail that must not be read as markup
            assert "[type=json_invalid" in result.output
            assert "Traceback" not in result.output


# ============================================================================
# Tests: Identifier Type Detection
# ============================================================================


class TestIdentifierDetection:
    """Test that export correctly identifies IDs vs file paths."""

    def test_numeric_string_treated_as_id(self, runner, tmp_path, monkeypatch, working_dir):
        """Numeric string is treated as benchmark ID, not filename."""
        # Create a file literally named "23598" to test precedence
        Path("23598").write_text("fake file")

        catalog_path = tmp_path / "catalog.db"
        catalog_path.touch()

        monkeypatch.setenv("CIS_BENCH_HOME", str(catalog_path.parent))

        with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
            mock_db = Mock()
            mock_db_class.return_value = mock_db
            mock_db.get_downloaded.return_value = None

            result = runner.invoke(cli, ["export", "23598", "--format", "yaml"])

            # Should try database, not file (even though file exists)
            assert result.exit_code == 1
            assert "not downloaded" in result.output

    def test_non_numeric_treated_as_file(self, runner, sample_benchmark_json, working_dir):
        """Non-numeric string is treated as file path."""
        import shutil

        shutil.copy(str(sample_benchmark_json), "benchmark.json")

        result = runner.invoke(cli, ["export", "benchmark.json", "--format", "yaml"])

        # Should load from file successfully
        assert result.exit_code == 0
        assert "Loaded: CIS AlmaLinux" in result.output

    def test_path_with_extension_treated_as_file(self, runner, sample_benchmark_json, working_dir):
        """Path with extension is treated as file even if starts with number."""
        import shutil

        # Create file with numeric prefix
        shutil.copy(str(sample_benchmark_json), "23598_benchmark.json")

        result = runner.invoke(cli, ["export", "23598_benchmark.json", "--format", "yaml"])

        # Should load from file (not try database)
        assert result.exit_code == 0
        assert "Loaded: CIS AlmaLinux" in result.output


class TestRealDatabaseCanonicalDeserialize:
    """Verify export loads cached benchmarks via canonical serialization and Benchmark.model_validate_json."""

    def test_export_from_real_db_uses_model_validate_json_with_canonical_serialized_payload(
        self, runner, sample_benchmark, tmp_path, monkeypatch, working_dir
    ):
        """export <id> reads stored content_json through Benchmark.model_validate_json against a real database."""
        from cis_bench.catalog.database import CatalogDatabase, serialize_benchmark_json

        db = CatalogDatabase(tmp_path / "catalog.db")
        db.initialize_schema()
        db.insert_benchmark(
            {
                "benchmark_id": "23598",
                "title": sample_benchmark.title,
                "version": sample_benchmark.version,
                "url": str(sample_benchmark.url),
                "status": "Published",
                "is_latest": True,
            }
        )
        content_json, content_hash = serialize_benchmark_json(sample_benchmark)
        db.save_downloaded(
            benchmark_id="23598",
            content_json=content_json,
            content_hash=content_hash,
            recommendation_count=len(sample_benchmark.recommendations),
        )

        try:
            with (
                patch.object(
                    Benchmark,
                    "model_validate_json",
                    wraps=Benchmark.model_validate_json,
                ) as validate_spy,
            ):
                monkeypatch.setenv("CIS_BENCH_HOME", str(db.db_path.parent))
                res = runner.invoke(cli, ["export", "23598", "--format", "yaml"])

            assert res.exit_code == 0, res.output
            validate_spy.assert_called_once_with(content_json)
            exported = Path("benchmark_23598.yaml").read_text(encoding="utf-8")
            assert "CIS AlmaLinux OS 8 Benchmark" in exported
            assert "1.1.1" in exported
            assert "1.1.2" in exported
        finally:
            db.close()


class TestExportLogsNothingAtInfo:
    """An export prints its summary through the console, not a log line per step."""

    @pytest.mark.parametrize(
        "args",
        [
            ["--format", "yaml"],
            ["--format", "csv"],
            ["--format", "markdown"],
            ["--format", "xccdf", "--style", "disa"],
            ["--format", "xccdf", "--style", "cis"],
        ],
    )
    def test_an_export_at_the_default_level_logs_no_info_lines(
        self, runner, sample_benchmark_json, working_dir, args
    ):
        result = runner.invoke(cli, ["export", str(sample_benchmark_json), *args])

        assert result.exit_code == 0, result.output
        assert "Export" in result.output
        # The CLI's logging goes to stderr, which the runner folds into output
        assert "INFO:" not in result.output, result.output


class TestTheStoredMarkdownIsWrittenAsItIs:
    """The CSV and Markdown exports carry the stored text; a placeholder such as <user> survives."""

    @pytest.fixture
    def benchmark_json(self, sample_benchmark, tmp_path):
        first, second = sample_benchmark.recommendations
        rule = first.model_copy(
            update={
                "title": "Ensure <path> is owned by <user>",
                "description": "Owned by the account named in `<user>`.",
                "rationale": "A file owned by <user> is read by <user> alone.",
                "remediation": "Run:\n\n```\n# chage --mindays <N> <user>\n```",
            }
        )
        benchmark = sample_benchmark.model_copy(
            update={"recommendations": [rule, second], "scraper_version": "v2_2026_01"}
        )
        path = tmp_path / "benchmark.json"
        path.write_text(benchmark.model_dump_json(indent=2))
        return path

    def test_the_csv_export_carries_the_stored_text(self, runner, benchmark_json, working_dir):
        import csv

        result = runner.invoke(cli, ["export", str(benchmark_json), "--format", "csv"])

        assert result.exit_code == 0, result.output
        with open("benchmark.csv", newline="", encoding="utf-8") as f:
            row = next(csv.DictReader(f))
        assert row["title"] == "Ensure <path> is owned by <user>"
        assert row["description"] == "Owned by the account named in `<user>`."
        assert row["remediation"] == "Run:\n\n```\n# chage --mindays <N> <user>\n```"

    def test_the_markdown_export_carries_the_stored_text(self, runner, benchmark_json, working_dir):
        result = runner.invoke(cli, ["export", str(benchmark_json), "--format", "markdown"])

        assert result.exit_code == 0, result.output
        text = Path("benchmark.md").read_text(encoding="utf-8")
        assert "```\n# chage --mindays <N> <user>\n```" in text
        assert "Owned by the account named in `<user>`." in text

    def test_a_placeholder_in_prose_renders_as_text(self, runner, benchmark_json, working_dir):
        """A CommonMark renderer with raw HTML on (GitHub, MkDocs) would read <user> in a
        sentence as a tag and show nothing; the export escapes it so the words survive, while
        a placeholder in code is left as it is."""
        from markdown_it import MarkdownIt

        result = runner.invoke(cli, ["export", str(benchmark_json), "--format", "markdown"])

        assert result.exit_code == 0, result.output
        text = Path("benchmark.md").read_text(encoding="utf-8")
        html = MarkdownIt("commonmark").render(text)
        assert "A file owned by &lt;user&gt; is read by &lt;user&gt; alone." in html
        assert "Ensure &lt;path&gt; is owned by &lt;user&gt;" in html
        assert "# chage --mindays &lt;N&gt; &lt;user&gt;" in html
        assert "<user>" not in html and "<path>" not in html

    def test_a_placeholder_in_a_parent_title_renders_as_text(
        self, runner, sample_benchmark, tmp_path, working_dir
    ):
        from markdown_it import MarkdownIt

        from cis_bench.models.benchmark import ParentReference

        first, second = sample_benchmark.recommendations
        child = second.model_copy(
            update={
                "parent": ParentReference(
                    url="https://workbench.cisecurity.org/sections/23598/recommendations/374956",
                    title="Ensure <path> is owned by <user>",
                )
            }
        )
        path = tmp_path / "benchmark.json"
        path.write_text(
            sample_benchmark.model_copy(
                update={"recommendations": [first, child], "scraper_version": "v2_2026_01"}
            ).model_dump_json(indent=2)
        )

        result = runner.invoke(cli, ["export", str(path), "--format", "markdown"])

        assert result.exit_code == 0, result.output
        html = MarkdownIt("commonmark").render(Path("benchmark.md").read_text(encoding="utf-8"))
        assert "Ensure &lt;path&gt; is owned by &lt;user&gt;</a>" in html


class TestExportCountsTheRecommendations:
    @pytest.mark.parametrize(
        ("keep", "expected"), [(1, "1 recommendation to"), (2, "2 recommendations to")]
    )
    def test_the_exported_line_agrees_with_the_number(
        self, runner, sample_benchmark, working_dir, keep, expected
    ):
        sample_benchmark.recommendations = sample_benchmark.recommendations[:keep]
        sample_benchmark.total_recommendations = keep
        Path("in.json").write_text(sample_benchmark.model_dump_json())

        result = runner.invoke(cli, ["export", "in.json", "--format", "yaml", "--output", "o.yaml"])

        assert result.exit_code == 0, result.output
        assert f"Exported {expected} o.yaml" in " ".join(result.output.split())
