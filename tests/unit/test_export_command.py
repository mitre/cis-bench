"""Unit tests for export command.

Tests both file-based and database-based export functionality.
"""

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

    def test_export_from_file_yaml(self, runner, sample_benchmark_json):
        """Export benchmark from file to YAML format."""
        with runner.isolated_filesystem():
            import shutil

            shutil.copy(str(sample_benchmark_json), "benchmark.json")

            result = runner.invoke(cli, ["export", "benchmark.json", "--format", "yaml"])

            assert result.exit_code == 0, f"Export failed: {result.output}"
            assert "Loaded: CIS AlmaLinux OS 8 Benchmark" in result.output
            assert "Exported 2 recommendations" in result.output
            assert Path("benchmark.yaml").exists()

    def test_export_from_file_csv(self, runner, sample_benchmark_json):
        """Export benchmark from file to CSV format."""
        with runner.isolated_filesystem():
            import shutil

            shutil.copy(str(sample_benchmark_json), "benchmark.json")

            result = runner.invoke(cli, ["export", "benchmark.json", "--format", "csv"])

            assert result.exit_code == 0
            assert Path("benchmark.csv").exists()

    def test_export_from_file_markdown(self, runner, sample_benchmark_json):
        """Export benchmark from file to Markdown format."""
        with runner.isolated_filesystem():
            import shutil

            shutil.copy(str(sample_benchmark_json), "benchmark.json")

            result = runner.invoke(cli, ["export", "benchmark.json", "--format", "markdown"])

            assert result.exit_code == 0
            assert Path("benchmark.md").exists()

    def test_export_from_file_xccdf_disa(self, runner, sample_benchmark_json):
        """Export benchmark from file to XCCDF DISA format."""
        with runner.isolated_filesystem():
            import shutil

            shutil.copy(str(sample_benchmark_json), "benchmark.json")

            result = runner.invoke(
                cli, ["export", "benchmark.json", "--format", "xccdf", "--style", "disa"]
            )

            assert result.exit_code == 0
            assert Path("benchmark.xml").exists()

    def test_export_from_file_xccdf_cis(self, runner, sample_benchmark_json):
        """Export benchmark from file to XCCDF CIS format."""
        with runner.isolated_filesystem():
            import shutil

            shutil.copy(str(sample_benchmark_json), "benchmark.json")

            result = runner.invoke(
                cli, ["export", "benchmark.json", "--format", "xccdf", "--style", "cis"]
            )

            assert result.exit_code == 0
            assert Path("benchmark.xml").exists()

    def test_export_file_not_found(self, runner):
        """Export fails gracefully when file not found."""
        result = runner.invoke(cli, ["export", "nonexistent.json", "--format", "yaml"])

        assert result.exit_code == 1
        assert "File not found" in result.output

    def test_export_with_custom_output_file(self, runner, sample_benchmark_json):
        """Export with custom output filename."""
        with runner.isolated_filesystem():
            import shutil

            shutil.copy(str(sample_benchmark_json), "benchmark.json")

            result = runner.invoke(
                cli, ["export", "benchmark.json", "--format", "yaml", "--output", "custom.yaml"]
            )

            assert result.exit_code == 0
            assert Path("custom.yaml").exists()


# ============================================================================
# Tests: Database-based Export (NEW Functionality)
# ============================================================================


class TestExportFromDatabase:
    """Test export command with benchmark IDs (new functionality)."""

    def test_export_from_db_by_id(self, runner, sample_benchmark, tmp_path):
        """Export benchmark from database by ID."""
        with runner.isolated_filesystem():
            # Create empty catalog file so .exists() check passes
            catalog_path = tmp_path / "catalog.db"
            catalog_path.touch()

            with patch("cis_bench.cli.commands.export.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path

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

    def test_export_from_db_benchmark_not_downloaded(self, runner, tmp_path):
        """Export fails when benchmark ID not in database."""
        with runner.isolated_filesystem():
            catalog_path = tmp_path / "catalog.db"
            catalog_path.touch()

            with patch("cis_bench.cli.commands.export.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path

                with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                    mock_db = Mock()
                    mock_db_class.return_value = mock_db
                    mock_db.get_downloaded.return_value = None  # Not found

                    result = runner.invoke(cli, ["export", "23598", "--format", "yaml"])

                    assert result.exit_code == 1
                    assert "Benchmark 23598 not downloaded" in result.output
                    assert "cis-bench download 23598" in result.output

    def test_export_from_db_catalog_not_exists(self, runner, tmp_path):
        """Export fails when catalog database doesn't exist."""
        with runner.isolated_filesystem():
            # Point to non-existent catalog
            nonexistent_path = tmp_path / "nonexistent" / "catalog.db"

            with patch("cis_bench.cli.commands.export.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = nonexistent_path

                result = runner.invoke(cli, ["export", "23598", "--format", "yaml"])

                assert result.exit_code == 1
                assert "Catalog database not found" in result.output
                assert "catalog refresh" in result.output

    def test_export_from_db_xccdf_with_style(self, runner, sample_benchmark, tmp_path):
        """Export from database to XCCDF with CIS style."""
        with runner.isolated_filesystem():
            catalog_path = tmp_path / "catalog.db"
            catalog_path.touch()

            with patch("cis_bench.cli.commands.export.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path

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
                        cli, ["export", "23598", "--format", "xccdf", "--style", "cis"]
                    )

                    assert result.exit_code == 0
                    assert Path("benchmark_23598.xml").exists()

    def test_export_from_db_with_custom_output(self, runner, sample_benchmark, tmp_path):
        """Export from database with custom output filename."""
        with runner.isolated_filesystem():
            catalog_path = tmp_path / "catalog.db"
            catalog_path.touch()

            with patch("cis_bench.cli.commands.export.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path

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

    def test_export_from_db_invalid_json_in_database(self, runner, tmp_path):
        """Export fails gracefully when database contains invalid JSON."""
        with runner.isolated_filesystem():
            catalog_path = tmp_path / "catalog.db"
            catalog_path.touch()

            with patch("cis_bench.cli.commands.export.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path

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


# ============================================================================
# Tests: Identifier Type Detection
# ============================================================================


class TestIdentifierDetection:
    """Test that export correctly identifies IDs vs file paths."""

    def test_numeric_string_treated_as_id(self, runner, tmp_path):
        """Numeric string is treated as benchmark ID, not filename."""
        with runner.isolated_filesystem():
            # Create a file literally named "23598" to test precedence
            Path("23598").write_text("fake file")

            catalog_path = tmp_path / "catalog.db"
            catalog_path.touch()

            with patch("cis_bench.cli.commands.export.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path

                with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                    mock_db = Mock()
                    mock_db_class.return_value = mock_db
                    mock_db.get_downloaded.return_value = None

                    result = runner.invoke(cli, ["export", "23598", "--format", "yaml"])

                    # Should try database, not file (even though file exists)
                    assert result.exit_code == 1
                    assert "not downloaded" in result.output

    def test_non_numeric_treated_as_file(self, runner, sample_benchmark_json):
        """Non-numeric string is treated as file path."""
        with runner.isolated_filesystem():
            import shutil

            shutil.copy(str(sample_benchmark_json), "benchmark.json")

            result = runner.invoke(cli, ["export", "benchmark.json", "--format", "yaml"])

            # Should load from file successfully
            assert result.exit_code == 0
            assert "Loaded: CIS AlmaLinux" in result.output

    def test_path_with_extension_treated_as_file(self, runner, sample_benchmark_json):
        """Path with extension is treated as file even if starts with number."""
        with runner.isolated_filesystem():
            import shutil

            # Create file with numeric prefix
            shutil.copy(str(sample_benchmark_json), "23598_benchmark.json")

            result = runner.invoke(cli, ["export", "23598_benchmark.json", "--format", "yaml"])

            # Should load from file (not try database)
            assert result.exit_code == 0
            assert "Loaded: CIS AlmaLinux" in result.output
