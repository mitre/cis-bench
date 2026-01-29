"""Unit and integration tests for batch export functionality.

TDD/BDD tests for exporting multiple benchmarks in a single command.

Feature: Batch Export
  As a security engineer
  I want to export multiple benchmarks at once
  So that I can efficiently generate XCCDF/YAML files for automation

Scenarios tested:
  - Export multiple benchmark IDs in single command
  - Export to output directory with auto-generated filenames
  - Continue on individual failures
  - Progress tracking for multiple exports
  - Backward compatibility with single ID (no breaking change)
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from cis_bench.cli.app import cli
from cis_bench.models.benchmark import Benchmark, Recommendation

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def runner():
    """Create Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def sample_benchmark_1():
    """Create first sample benchmark for testing."""
    return Benchmark(
        title="CIS Ubuntu Linux 22.04 Benchmark",
        benchmark_id="23598",
        url="https://workbench.cisecurity.org/benchmarks/23598",
        version="v1.0.0",
        downloaded_at=datetime(2025, 1, 1),
        scraper_version="1.0.0",
        total_recommendations=2,
        recommendations=[
            Recommendation(
                ref="1.1.1",
                title="Ensure mounting of cramfs is disabled",
                url="https://workbench.cisecurity.org/sections/23598/recommendations/1",
                assessment_status="Automated",
                profiles=["Level 1"],
                description="The cramfs filesystem type is a compressed read-only Linux filesystem.",
                rationale="Removing support for unneeded filesystem types reduces attack surface.",
                impact="None",
                audit="Run the following command",
                remediation="Edit /etc/modprobe.d/cramfs.conf",
            ),
            Recommendation(
                ref="1.1.2",
                title="Ensure mounting of squashfs is disabled",
                url="https://workbench.cisecurity.org/sections/23598/recommendations/2",
                assessment_status="Automated",
                profiles=["Level 2"],
                description="The squashfs filesystem type is a compressed read-only Linux filesystem.",
                rationale="Removing support for unneeded filesystem types reduces attack surface.",
                impact="Snap packages require squashfs",
                audit="Run the following command",
                remediation="Edit /etc/modprobe.d/squashfs.conf",
            ),
        ],
    )


@pytest.fixture
def sample_benchmark_2():
    """Create second sample benchmark for testing."""
    return Benchmark(
        title="CIS RHEL 9 Benchmark",
        benchmark_id="22605",
        url="https://workbench.cisecurity.org/benchmarks/22605",
        version="v1.0.0",
        downloaded_at=datetime(2025, 1, 1),
        scraper_version="1.0.0",
        total_recommendations=1,
        recommendations=[
            Recommendation(
                ref="1.1.1",
                title="Ensure SELinux is installed",
                url="https://workbench.cisecurity.org/sections/22605/recommendations/1",
                assessment_status="Automated",
                profiles=["Level 1"],
                description="SELinux provides Mandatory Access Control.",
                rationale="SELinux provides enhanced security.",
                impact="May require policy configuration",
                audit="rpm -q libselinux",
                remediation="dnf install libselinux",
            ),
        ],
    )


@pytest.fixture
def sample_benchmark_3():
    """Create third sample benchmark for testing."""
    return Benchmark(
        title="CIS AWS Foundations Benchmark",
        benchmark_id="18208",
        url="https://workbench.cisecurity.org/benchmarks/18208",
        version="v2.0.0",
        downloaded_at=datetime(2025, 1, 1),
        scraper_version="1.0.0",
        total_recommendations=1,
        recommendations=[
            Recommendation(
                ref="1.1",
                title="Maintain current contact details",
                url="https://workbench.cisecurity.org/sections/18208/recommendations/1",
                assessment_status="Manual",
                profiles=["Level 1"],
                description="Ensure contact email and phone are current.",
                rationale="AWS needs to be able to contact you.",
                impact="None",
                audit="Check AWS console",
                remediation="Update contact details in AWS console",
            ),
        ],
    )


def mock_db_with_benchmarks(*benchmarks):
    """Helper to create a mock database with multiple benchmarks."""
    benchmark_map = {b.benchmark_id: b for b in benchmarks}

    def get_downloaded(benchmark_id):
        if benchmark_id in benchmark_map:
            b = benchmark_map[benchmark_id]
            return {
                "benchmark_id": benchmark_id,
                "content_json": b.model_dump_json(),
                "downloaded_at": datetime.now(),
                "recommendation_count": len(b.recommendations),
            }
        return None

    mock_db = Mock()
    mock_db.get_downloaded.side_effect = get_downloaded
    return mock_db


# ============================================================================
# Tests: Backward Compatibility (Single ID still works)
# ============================================================================


class TestSingleExportBackwardCompatibility:
    """Ensure single ID export still works after batch changes."""

    def test_single_id_still_works(self, runner, sample_benchmark_1, tmp_path):
        """Single ID export should work exactly as before."""
        with runner.isolated_filesystem():
            catalog_path = tmp_path / "catalog.db"
            catalog_path.touch()

            with patch("cis_bench.cli.commands.export.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path

                with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                    mock_db_class.return_value = mock_db_with_benchmarks(sample_benchmark_1)

                    result = runner.invoke(cli, ["export", "23598", "--format", "yaml"])

                    assert result.exit_code == 0, f"Single export failed: {result.output}"
                    assert "Exported 2 recommendations" in result.output
                    # Output file should still use old naming for single ID
                    assert Path("benchmark_23598.yaml").exists()

    def test_single_file_still_works(self, runner, sample_benchmark_1):
        """Single file export should work exactly as before."""
        with runner.isolated_filesystem():
            # Create benchmark JSON file
            Path("benchmark.json").write_text(sample_benchmark_1.model_dump_json())

            result = runner.invoke(cli, ["export", "benchmark.json", "--format", "yaml"])

            assert result.exit_code == 0
            assert "Loaded: CIS Ubuntu" in result.output
            assert Path("benchmark.yaml").exists()


# ============================================================================
# Tests: Multiple ID Export (New Functionality)
# ============================================================================


class TestBatchExportMultipleIds:
    """Test exporting multiple benchmark IDs in a single command."""

    def test_export_two_benchmarks(self, runner, sample_benchmark_1, sample_benchmark_2, tmp_path):
        """Export two benchmarks in single command."""
        with runner.isolated_filesystem():
            catalog_path = tmp_path / "catalog.db"
            catalog_path.touch()

            with patch("cis_bench.cli.commands.export.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path

                with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                    mock_db_class.return_value = mock_db_with_benchmarks(
                        sample_benchmark_1, sample_benchmark_2
                    )

                    result = runner.invoke(cli, ["export", "23598", "22605", "--format", "yaml"])

                    assert result.exit_code == 0, f"Batch export failed: {result.output}"
                    # Both benchmarks should be exported
                    assert "Ubuntu" in result.output
                    assert "RHEL" in result.output
                    # Check files exist
                    assert Path("benchmark_23598.yaml").exists()
                    assert Path("benchmark_22605.yaml").exists()

    def test_export_three_benchmarks(
        self, runner, sample_benchmark_1, sample_benchmark_2, sample_benchmark_3, tmp_path
    ):
        """Export three benchmarks in single command."""
        with runner.isolated_filesystem():
            catalog_path = tmp_path / "catalog.db"
            catalog_path.touch()

            with patch("cis_bench.cli.commands.export.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path

                with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                    mock_db_class.return_value = mock_db_with_benchmarks(
                        sample_benchmark_1, sample_benchmark_2, sample_benchmark_3
                    )

                    result = runner.invoke(
                        cli, ["export", "23598", "22605", "18208", "--format", "yaml"]
                    )

                    assert result.exit_code == 0
                    assert Path("benchmark_23598.yaml").exists()
                    assert Path("benchmark_22605.yaml").exists()
                    assert Path("benchmark_18208.yaml").exists()

    def test_export_multiple_with_xccdf(
        self, runner, sample_benchmark_1, sample_benchmark_2, tmp_path
    ):
        """Export multiple benchmarks to XCCDF format."""
        with runner.isolated_filesystem():
            catalog_path = tmp_path / "catalog.db"
            catalog_path.touch()

            with patch("cis_bench.cli.commands.export.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path

                with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                    mock_db_class.return_value = mock_db_with_benchmarks(
                        sample_benchmark_1, sample_benchmark_2
                    )

                    result = runner.invoke(
                        cli, ["export", "23598", "22605", "--format", "xccdf", "--style", "disa"]
                    )

                    assert result.exit_code == 0
                    assert Path("benchmark_23598.xml").exists()
                    assert Path("benchmark_22605.xml").exists()


# ============================================================================
# Tests: Output Directory
# ============================================================================


class TestBatchExportOutputDirectory:
    """Test output directory option for batch exports."""

    def test_export_to_output_dir(self, runner, sample_benchmark_1, sample_benchmark_2, tmp_path):
        """Export multiple benchmarks to specified output directory."""
        with runner.isolated_filesystem():
            catalog_path = tmp_path / "catalog.db"
            catalog_path.touch()

            with patch("cis_bench.cli.commands.export.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path

                with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                    mock_db_class.return_value = mock_db_with_benchmarks(
                        sample_benchmark_1, sample_benchmark_2
                    )

                    result = runner.invoke(
                        cli,
                        ["export", "23598", "22605", "--format", "yaml", "--output-dir", "exports"],
                    )

                    assert result.exit_code == 0
                    assert Path("exports/benchmark_23598.yaml").exists()
                    assert Path("exports/benchmark_22605.yaml").exists()

    def test_output_dir_created_if_not_exists(self, runner, sample_benchmark_1, tmp_path):
        """Output directory is created if it doesn't exist."""
        with runner.isolated_filesystem():
            catalog_path = tmp_path / "catalog.db"
            catalog_path.touch()

            with patch("cis_bench.cli.commands.export.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path

                with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                    mock_db_class.return_value = mock_db_with_benchmarks(sample_benchmark_1)

                    result = runner.invoke(
                        cli,
                        ["export", "23598", "--format", "yaml", "--output-dir", "new/nested/dir"],
                    )

                    assert result.exit_code == 0
                    assert Path("new/nested/dir/benchmark_23598.yaml").exists()


# ============================================================================
# Tests: Error Handling
# ============================================================================


class TestBatchExportErrorHandling:
    """Test error handling for batch exports."""

    def test_continue_on_missing_benchmark(
        self, runner, sample_benchmark_1, sample_benchmark_2, tmp_path
    ):
        """Continue exporting even if one benchmark is missing."""
        with runner.isolated_filesystem():
            catalog_path = tmp_path / "catalog.db"
            catalog_path.touch()

            with patch("cis_bench.cli.commands.export.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path

                with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                    # Only benchmark 1 and 2 exist, 99999 does not
                    mock_db_class.return_value = mock_db_with_benchmarks(
                        sample_benchmark_1, sample_benchmark_2
                    )

                    result = runner.invoke(
                        cli, ["export", "23598", "99999", "22605", "--format", "yaml"]
                    )

                    # Should continue despite missing benchmark
                    # Exit code should be non-zero to indicate partial failure
                    assert (
                        "99999 not downloaded" in result.output
                        or "not found" in result.output.lower()
                    )
                    # But other benchmarks should still be exported
                    assert Path("benchmark_23598.yaml").exists()
                    assert Path("benchmark_22605.yaml").exists()

    def test_all_missing_benchmarks_exits_with_error(self, runner, tmp_path):
        """Exit with error if all benchmarks are missing."""
        with runner.isolated_filesystem():
            catalog_path = tmp_path / "catalog.db"
            catalog_path.touch()

            with patch("cis_bench.cli.commands.export.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path

                with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                    mock_db = Mock()
                    mock_db.get_downloaded.return_value = None  # Nothing found
                    mock_db_class.return_value = mock_db

                    result = runner.invoke(cli, ["export", "99998", "99999", "--format", "yaml"])

                    assert result.exit_code != 0

    def test_no_identifiers_shows_error(self, runner):
        """Show error when no identifiers provided."""
        result = runner.invoke(cli, ["export", "--format", "yaml"])

        # Should show usage error
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "Usage:" in result.output


# ============================================================================
# Tests: Progress Tracking
# ============================================================================


class TestBatchExportProgress:
    """Test progress tracking for batch exports."""

    def test_shows_progress_for_multiple_exports(
        self, runner, sample_benchmark_1, sample_benchmark_2, tmp_path
    ):
        """Show progress indicator for each benchmark."""
        with runner.isolated_filesystem():
            catalog_path = tmp_path / "catalog.db"
            catalog_path.touch()

            with patch("cis_bench.cli.commands.export.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path

                with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                    mock_db_class.return_value = mock_db_with_benchmarks(
                        sample_benchmark_1, sample_benchmark_2
                    )

                    result = runner.invoke(cli, ["export", "23598", "22605", "--format", "yaml"])

                    # Should show progress like [1/2] and [2/2]
                    assert "[1/2]" in result.output or "1 of 2" in result.output.lower()
                    assert "[2/2]" in result.output or "2 of 2" in result.output.lower()

    def test_shows_summary_after_batch_export(
        self, runner, sample_benchmark_1, sample_benchmark_2, tmp_path
    ):
        """Show summary after batch export completes."""
        with runner.isolated_filesystem():
            catalog_path = tmp_path / "catalog.db"
            catalog_path.touch()

            with patch("cis_bench.cli.commands.export.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path

                with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                    mock_db_class.return_value = mock_db_with_benchmarks(
                        sample_benchmark_1, sample_benchmark_2
                    )

                    result = runner.invoke(cli, ["export", "23598", "22605", "--format", "yaml"])

                    # Should show completion summary
                    assert (
                        "complete" in result.output.lower() or "exported" in result.output.lower()
                    )


# ============================================================================
# Tests: Mixed Identifiers (IDs and Files)
# ============================================================================


class TestBatchExportMixedIdentifiers:
    """Test batch export with mix of IDs and file paths."""

    def test_export_id_and_file_together(
        self, runner, sample_benchmark_1, sample_benchmark_2, tmp_path
    ):
        """Export both database IDs and file paths in same command."""
        with runner.isolated_filesystem():
            # Create a benchmark JSON file
            Path("local_benchmark.json").write_text(sample_benchmark_2.model_dump_json())

            catalog_path = tmp_path / "catalog.db"
            catalog_path.touch()

            with patch("cis_bench.cli.commands.export.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path

                with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                    mock_db_class.return_value = mock_db_with_benchmarks(sample_benchmark_1)

                    result = runner.invoke(
                        cli, ["export", "23598", "local_benchmark.json", "--format", "yaml"]
                    )

                    assert result.exit_code == 0
                    # Both should be exported
                    assert Path("benchmark_23598.yaml").exists()
                    assert Path("local_benchmark.yaml").exists()


# ============================================================================
# Integration Tests: Full Workflow
# ============================================================================


class TestBatchExportIntegration:
    """Integration tests for complete batch export workflows."""

    def test_batch_export_xccdf_disa_workflow(
        self, runner, sample_benchmark_1, sample_benchmark_2, sample_benchmark_3, tmp_path
    ):
        """Full workflow: Export 3 benchmarks to XCCDF DISA format."""
        with runner.isolated_filesystem():
            catalog_path = tmp_path / "catalog.db"
            catalog_path.touch()

            with patch("cis_bench.cli.commands.export.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path

                with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                    mock_db_class.return_value = mock_db_with_benchmarks(
                        sample_benchmark_1, sample_benchmark_2, sample_benchmark_3
                    )

                    result = runner.invoke(
                        cli,
                        [
                            "export",
                            "23598",
                            "22605",
                            "18208",
                            "--format",
                            "xccdf",
                            "--style",
                            "disa",
                            "--output-dir",
                            "stig_exports",
                        ],
                    )

                    assert result.exit_code == 0

                    # All XCCDF files should exist
                    assert Path("stig_exports/benchmark_23598.xml").exists()
                    assert Path("stig_exports/benchmark_22605.xml").exists()
                    assert Path("stig_exports/benchmark_18208.xml").exists()

                    # Verify XML content is valid
                    for xml_file in Path("stig_exports").glob("*.xml"):
                        content = xml_file.read_text()
                        assert "<?xml" in content
                        assert "Benchmark" in content

    def test_batch_export_multiple_formats_not_supported(
        self, runner, sample_benchmark_1, tmp_path
    ):
        """Batch export with single format (multiple formats handled by download)."""
        with runner.isolated_filesystem():
            catalog_path = tmp_path / "catalog.db"
            catalog_path.touch()

            with patch("cis_bench.cli.commands.export.Config") as mock_config:
                mock_config.get_catalog_db_path.return_value = catalog_path

                with patch("cis_bench.catalog.database.CatalogDatabase") as mock_db_class:
                    mock_db_class.return_value = mock_db_with_benchmarks(sample_benchmark_1)

                    # Export command takes single format, not multiple
                    # This is by design - use download for multiple formats
                    result = runner.invoke(cli, ["export", "23598", "--format", "yaml"])

                    assert result.exit_code == 0
                    assert Path("benchmark_23598.yaml").exists()
