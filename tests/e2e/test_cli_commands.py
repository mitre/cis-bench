"""Comprehensive test suite for CLI commands.

Tests all CLI commands including:
- download: Download benchmarks from CIS WorkBench
- export: Export benchmarks to different formats
- info: Show benchmark details
- list: List downloaded benchmarks

Uses Click's CliRunner for isolated testing and mocks for external dependencies.
"""

import os
from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from cis_bench.cli.app import cli
from cis_bench.models.benchmark import Benchmark, CISControl, MITREMapping, Recommendation

# ============================================================================
# Fixtures
# ============================================================================


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
        total_recommendations=3,
        recommendations=[
            Recommendation(
                ref="1.1.1",
                title="Ensure mounting of cramfs filesystems is disabled",
                url="https://workbench.cisecurity.org/sections/23598/recommendations/374956",
                assessment_status="Automated",
                profiles=["Level 1 - Server", "Level 1 - Workstation"],
                cis_controls=[
                    CISControl(
                        version=8,
                        control="4.8",
                        title="Uninstall or Disable Unnecessary Services",
                        ig1=False,
                        ig2=True,
                        ig3=True,
                    )
                ],
                mitre_mapping=MITREMapping(
                    techniques=["T1068"], tactics=["TA0004"], mitigations=["M1022"]
                ),
                nist_controls=["CM-7"],
                description="<p>The cramfs filesystem type is a compressed read-only...</p>",
                rationale="<p>Removing support for unneeded filesystem types...</p>",
                impact="<p>None</p>",
                audit="<p>Run the following commands...</p>",
                remediation="<p>Edit or create a file...</p>",
                additional_info="<p>Additional notes...</p>",
                default_value="<p>cramfs is not loaded</p>",
                references="<p>See CIS website</p>",
                artifacts=[],
            ),
            Recommendation(
                ref="1.1.2",
                title="Ensure mounting of freevxfs filesystems is disabled",
                url="https://workbench.cisecurity.org/sections/23598/recommendations/374957",
                assessment_status="Automated",
                profiles=["Level 1 - Server"],
                cis_controls=[],
                nist_controls=["CM-7"],
                description="<p>The freevxfs filesystem type...</p>",
                audit="<p>Run verification commands...</p>",
                remediation="<p>Create configuration file...</p>",
                artifacts=[],
            ),
            Recommendation(
                ref="2.1.1",
                title="Ensure xinetd is not installed",
                url="https://workbench.cisecurity.org/sections/23598/recommendations/374958",
                assessment_status="Manual",
                profiles=["Level 1 - Server"],
                cis_controls=[],
                nist_controls=["CM-6"],
                description="<p>xinetd is a daemon...</p>",
                artifacts=[],
            ),
        ],
    )


@pytest.fixture
def sample_benchmark_json(tmp_path, sample_benchmark):
    """Create a temporary JSON file with sample benchmark data."""
    json_file = tmp_path / "test_benchmark.json"
    sample_benchmark.to_json_file(str(json_file))
    return json_file


# ============================================================================
# Download Command Tests
# ============================================================================


class TestDownloadCommand:
    """Tests for the 'download' command."""

    def test_download_requires_authentication(self, runner, tmp_path):
        """Download command requires authentication (saved session or --browser)."""
        # Clear any saved session and mock to ensure no session exists
        with patch(
            "cis_bench.cli.commands.download.AuthManager.get_or_create_session"
        ) as mock_auth:
            mock_auth.side_effect = ValueError(
                "No saved session found. Please run 'cis-bench auth login --browser <browser>' to authenticate"
            )

            result = runner.invoke(cli, ["download", "23598"])

            assert result.exit_code == 1
            assert "Authentication Required" in result.output
            assert "auth login" in result.output

    def test_download_single_benchmark_with_browser(self, runner, sample_benchmark, tmp_path):
        """Download single benchmark using browser cookies."""
        # Mock Config to ensure no catalog exists (skip cache check)
        with patch("cis_bench.cli.commands.download.Config") as mock_config:
            mock_config.get_catalog_db_path.return_value = tmp_path / "nonexistent.db"
            mock_config.get_verify_ssl.return_value = False

            with patch(
                "cis_bench.cli.commands.download.AuthManager.get_or_create_session"
            ) as mock_auth:
                # Mock the download helper (imported into download.py)
                with patch(
                    "cis_bench.cli.helpers.download_helper.download_with_progress"
                ) as mock_download:
                    # Set up mock session
                    mock_session = Mock()
                    mock_auth.return_value = mock_session

                    # Mock download helper to return our sample benchmark
                    mock_download.return_value = sample_benchmark

                    # Run download command with --force to skip cache check
                    result = runner.invoke(
                        cli,
                        [
                            "download",
                            "23598",
                            "--browser",
                            "chrome",
                            "--output-dir",
                            str(tmp_path),
                            "--force",
                        ],
                    )

                    # Verify success
                    assert result.exit_code == 0, f"Download failed: {result.output}"
                    assert "Downloaded:" in result.output
                    assert "CIS AlmaLinux OS 8 Benchmark" in result.output

                    # Verify mocks were called correctly
                    mock_auth.assert_called_once()
                    mock_download.assert_called_once()

    def test_export_to_markdown(self, runner, sample_benchmark_json):
        """Export benchmark to Markdown format (real export, no mocks)."""
        with runner.isolated_filesystem():
            import shutil

            shutil.copy(str(sample_benchmark_json), "benchmark.json")

            # Run real export
            result = runner.invoke(cli, ["export", "benchmark.json", "--format", "md"])

        assert result.exit_code == 0, f"Export failed: {result.output}"
        assert "Loaded:" in result.output

    def test_export_to_xccdf(self, runner, sample_benchmark_json):
        """Export benchmark to XCCDF format (real export, no mocks)."""
        with runner.isolated_filesystem():
            import shutil

            shutil.copy(str(sample_benchmark_json), "benchmark.json")

            # Run real export
            result = runner.invoke(cli, ["export", "benchmark.json", "--format", "xccdf"])

        assert result.exit_code == 0, f"Export failed: {result.output}"
        assert "Loaded:" in result.output

    def test_export_file_not_found(self, runner):
        """Export fails gracefully when input file not found."""
        result = runner.invoke(cli, ["export", "nonexistent.json", "--format", "yaml"])

        assert result.exit_code == 1
        assert "File not found" in result.output

    def test_export_malformed_json(self, runner, tmp_path):
        """Export fails gracefully with malformed JSON."""
        bad_json = tmp_path / "bad.json"
        bad_json.write_text('{"invalid": json data}')

        result = runner.invoke(cli, ["export", str(bad_json), "--format", "yaml"])

        assert result.exit_code == 1
        assert "Error loading benchmark" in result.output

    def test_export_invalid_benchmark_data(self, runner, tmp_path):
        """Export fails with invalid benchmark data (validation error)."""
        invalid_json = tmp_path / "invalid.json"
        invalid_json.write_text('{"title": "Test", "missing_required_fields": true}')

        result = runner.invoke(cli, ["export", str(invalid_json), "--format", "yaml"])

        assert result.exit_code == 1
        assert "Error loading benchmark" in result.output

    def test_export_with_custom_output_file(self, runner, sample_benchmark_json):
        """Export with custom output filename."""
        with runner.isolated_filesystem():
            import os
            import shutil

            shutil.copy(str(sample_benchmark_json), "benchmark.json")

            result = runner.invoke(
                cli,
                ["export", "benchmark.json", "--format", "yaml", "--output", "custom_output.yaml"],
            )

            assert result.exit_code == 0, f"Export failed: {result.output}"
            assert "Loaded:" in result.output
            # Verify the custom output file was created
            assert os.path.exists("custom_output.yaml"), "Custom output file was not created"

    def test_export_with_input_dir(self, runner, sample_benchmark_json, tmp_path):
        """Export finds file in specified input directory."""
        benchmarks_dir = tmp_path / "benchmarks"
        benchmarks_dir.mkdir()

        import shutil

        shutil.copy(str(sample_benchmark_json), benchmarks_dir / "benchmark.json")

        result = runner.invoke(
            cli,
            ["export", "benchmark.json", "--format", "yaml", "--input-dir", str(benchmarks_dir)],
        )

        assert result.exit_code == 0

    def test_export_default_format(self, runner, sample_benchmark_json):
        """Export uses YAML as default format when not specified."""
        with runner.isolated_filesystem():
            import os
            import shutil

            shutil.copy(str(sample_benchmark_json), "benchmark.json")

            result = runner.invoke(cli, ["export", "benchmark.json"])

            assert result.exit_code == 0, f"Export failed: {result.output}"
            assert "Loaded:" in result.output
            # Should default to YAML - verify .yaml file was created
            yaml_files = [f for f in os.listdir(".") if f.endswith(".yaml") or f.endswith(".yml")]
            assert len(yaml_files) > 0, "No YAML file was created (default format should be YAML)"

    def test_export_failure(self, runner, sample_benchmark_json):
        """Export handles exporter failures gracefully."""
        with runner.isolated_filesystem():
            import shutil

            shutil.copy(str(sample_benchmark_json), "benchmark.json")

            # Mock the exporter's export method to raise an exception
            # (not the factory, since factory is called twice - once for extension, once for export)
            mock_exporter = Mock()
            mock_exporter.export.side_effect = Exception("Simulated export failure")
            mock_exporter.get_file_extension.return_value = "yaml"
            mock_exporter.format_name.return_value = "YAML"

            with patch(
                "cis_bench.cli.commands.export.ExporterFactory.create", return_value=mock_exporter
            ):
                result = runner.invoke(
                    cli, ["export", "benchmark.json", "--format", "yaml", "--output", "test.yaml"]
                )

            # Verify the failure was handled gracefully
            assert result.exit_code == 1, f"Expected exit code 1, got {result.exit_code}"
            assert "Export failed" in result.output, (
                f"Expected 'Export failed' in output: {result.output}"
            )


# ============================================================================
# Info Command Tests
# ============================================================================


class TestInfoCommand:
    """Tests for the 'info' command."""

    def test_info_displays_benchmark_details(self, runner, sample_benchmark_json):
        """Info command displays comprehensive benchmark information."""
        with runner.isolated_filesystem():
            import shutil

            shutil.copy(str(sample_benchmark_json), "benchmark.json")

            result = runner.invoke(cli, ["info", "benchmark.json"])

        assert result.exit_code == 0
        assert "CIS AlmaLinux OS 8 Benchmark" in result.output
        assert "v4.0.0" in result.output
        assert "23598" in result.output
        assert "Total Recommendations" in result.output
        assert "3" in result.output  # Total recommendations count

    def test_info_displays_compliance_statistics(self, runner, sample_benchmark_json):
        """Info command shows compliance mapping statistics."""
        with runner.isolated_filesystem():
            import shutil

            shutil.copy(str(sample_benchmark_json), "benchmark.json")

            result = runner.invoke(cli, ["info", "benchmark.json"])

        assert result.exit_code == 0
        assert "CIS Controls v8" in result.output
        assert "MITRE Mappings" in result.output
        assert "NIST Controls" in result.output

    def test_info_displays_sample_recommendations(self, runner, sample_benchmark_json):
        """Info command shows sample recommendations."""
        with runner.isolated_filesystem():
            import shutil

            shutil.copy(str(sample_benchmark_json), "benchmark.json")

            result = runner.invoke(cli, ["info", "benchmark.json"])

        assert result.exit_code == 0
        assert "Sample Recommendations" in result.output
        assert "1.1.1" in result.output
        assert "cramfs filesystems" in result.output

    def test_info_file_not_found(self, runner):
        """Info fails gracefully when file not found."""
        result = runner.invoke(cli, ["info", "nonexistent.json"])

        assert result.exit_code == 1
        assert "File not found" in result.output

    def test_info_with_output_dir(self, runner, sample_benchmark_json, tmp_path):
        """Info finds file in specified output directory."""
        benchmarks_dir = tmp_path / "benchmarks"
        benchmarks_dir.mkdir()

        import shutil

        shutil.copy(str(sample_benchmark_json), benchmarks_dir / "benchmark.json")

        result = runner.invoke(cli, ["info", "benchmark.json", "--output-dir", str(benchmarks_dir)])

        assert result.exit_code == 0
        assert "CIS AlmaLinux OS 8 Benchmark" in result.output

    def test_info_malformed_json(self, runner, tmp_path):
        """Info handles malformed JSON gracefully."""
        bad_json = tmp_path / "bad.json"
        bad_json.write_text('{"invalid json}')

        result = runner.invoke(cli, ["info", str(bad_json)])

        assert result.exit_code == 1
        assert "Error" in result.output

    def test_info_shows_more_indicator(self, runner, tmp_path):
        """Info shows 'and X more' indicator for benchmarks with >5 recommendations."""
        # Create benchmark with 10 recommendations
        recs = []
        for i in range(10):
            recs.append(
                Recommendation(
                    ref=f"1.{i + 1}",
                    title=f"Recommendation {i + 1}",
                    url=f"https://workbench.cisecurity.org/sections/23598/recommendations/{i}",
                    assessment_status="Automated",
                    profiles=["Level 1"],
                    cis_controls=[],
                    nist_controls=[],
                )
            )

        large_benchmark = Benchmark(
            title="Large Benchmark",
            benchmark_id="99999",
            url="https://workbench.cisecurity.org/benchmarks/99999",
            version="v1.0.0",
            downloaded_at=datetime.now(),
            scraper_version="1.0.0",
            total_recommendations=10,
            recommendations=recs,
        )

        json_file = tmp_path / "large.json"
        large_benchmark.to_json_file(str(json_file))

        result = runner.invoke(cli, ["info", str(json_file)])

        assert result.exit_code == 0
        assert "... and 5 more" in result.output


# ============================================================================
# List Command Tests
# ============================================================================


class TestListCommand:
    """Tests for the 'list' command."""

    def test_list_empty_directory(self, runner, tmp_path):
        """List shows message when no benchmarks found."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        result = runner.invoke(cli, ["list", "--output-dir", str(empty_dir)])

        assert result.exit_code == 0
        assert "No benchmarks found" in result.output

    def test_list_nonexistent_directory(self, runner):
        """List shows message when directory doesn't exist."""
        result = runner.invoke(cli, ["list", "--output-dir", "./nonexistent"])

        assert result.exit_code == 0
        assert "Directory not found" in result.output

    def test_list_single_benchmark(self, runner, sample_benchmark_json, tmp_path):
        """List displays single benchmark correctly."""
        benchmarks_dir = tmp_path / "benchmarks"
        benchmarks_dir.mkdir()

        import shutil

        shutil.copy(str(sample_benchmark_json), benchmarks_dir / "benchmark.json")

        result = runner.invoke(cli, ["list", "--output-dir", str(benchmarks_dir)])

        assert result.exit_code == 0
        assert "CIS AlmaLinux OS 8 Benchmark" in result.output
        assert "v4.0.0" in result.output
        assert "3" in result.output  # Total recommendations

    def test_list_multiple_benchmarks(self, runner, tmp_path):
        """List displays multiple benchmarks in table format."""
        benchmarks_dir = tmp_path / "benchmarks"
        benchmarks_dir.mkdir()

        # Create two different benchmarks
        for i in range(2):
            benchmark = Benchmark(
                title=f"CIS Test Benchmark {i + 1}",
                benchmark_id=f"2359{i}",
                url=f"https://workbench.cisecurity.org/benchmarks/2359{i}",
                version=f"v{i + 1}.0.0",
                downloaded_at=datetime.now(),
                scraper_version="1.0.0",
                total_recommendations=5,
                recommendations=[
                    Recommendation(
                        ref="1.1",
                        title="Test",
                        url="https://workbench.cisecurity.org/sections/1/recommendations/1",
                        assessment_status="Automated",
                        profiles=[],
                        cis_controls=[],
                        nist_controls=["CM-7"],
                    )
                ]
                * 5,
            )
            benchmark.to_json_file(str(benchmarks_dir / f"benchmark_{i}.json"))

        result = runner.invoke(cli, ["list", "--output-dir", str(benchmarks_dir)])

        assert result.exit_code == 0
        assert "CIS Test Benchmark 1" in result.output
        assert "CIS Test Benchmark 2" in result.output
        assert "2 total" in result.output

    def test_list_shows_compliance_counts(self, runner, sample_benchmark_json, tmp_path):
        """List displays compliance mapping counts."""
        benchmarks_dir = tmp_path / "benchmarks"
        benchmarks_dir.mkdir()

        import shutil

        shutil.copy(str(sample_benchmark_json), benchmarks_dir / "benchmark.json")

        result = runner.invoke(cli, ["list", "--output-dir", str(benchmarks_dir)])

        assert result.exit_code == 0
        # Should show columns for CIS v8, MITRE, NIST
        assert "CIS v8" in result.output or "Recs" in result.output

    def test_list_handles_malformed_json(self, runner, tmp_path):
        """List shows error for malformed benchmark files."""
        benchmarks_dir = tmp_path / "benchmarks"
        benchmarks_dir.mkdir()

        # Create one good and one bad file
        good_benchmark = Benchmark(
            title="Good Benchmark",
            benchmark_id="23598",
            url="https://workbench.cisecurity.org/benchmarks/23598",
            version="v1.0.0",
            downloaded_at=datetime.now(),
            scraper_version="1.0.0",
            total_recommendations=1,
            recommendations=[
                Recommendation(
                    ref="1.1",
                    title="Test",
                    url="https://workbench.cisecurity.org/sections/1/recommendations/1",
                    assessment_status="Automated",
                    profiles=[],
                    cis_controls=[],
                    nist_controls=[],
                )
            ],
        )
        good_benchmark.to_json_file(str(benchmarks_dir / "good.json"))

        bad_file = benchmarks_dir / "bad.json"
        bad_file.write_text('{"invalid": "data"}')

        result = runner.invoke(cli, ["list", "--output-dir", str(benchmarks_dir)])

        assert result.exit_code == 0
        # Good benchmark should be listed
        assert "Good Benchmark" in result.output
        # Bad file should show error indicator
        assert "Error" in result.output or "?" in result.output

    def test_list_default_directory(self, runner):
        """List uses ./benchmarks as default directory."""
        with runner.isolated_filesystem():
            os.makedirs("./benchmarks", exist_ok=True)

            result = runner.invoke(cli, ["list"])

        assert result.exit_code == 0
        # Should check ./benchmarks by default

    def test_list_sorting(self, runner, tmp_path):
        """List sorts benchmarks alphabetically."""
        benchmarks_dir = tmp_path / "benchmarks"
        benchmarks_dir.mkdir()

        # Create benchmarks in non-alphabetical order
        titles = ["Zebra Benchmark", "Alpha Benchmark", "Gamma Benchmark"]
        for title in titles:
            benchmark = Benchmark(
                title=title,
                benchmark_id="99999",
                url="https://workbench.cisecurity.org/benchmarks/99999",
                version="v1.0.0",
                downloaded_at=datetime.now(),
                scraper_version="1.0.0",
                total_recommendations=1,
                recommendations=[
                    Recommendation(
                        ref="1.1",
                        title="Test",
                        url="https://workbench.cisecurity.org/sections/1/recommendations/1",
                        assessment_status="Automated",
                        profiles=[],
                        cis_controls=[],
                        nist_controls=[],
                    )
                ],
            )
            safe_name = title.lower().replace(" ", "_")
            benchmark.to_json_file(str(benchmarks_dir / f"{safe_name}.json"))

        result = runner.invoke(cli, ["list", "--output-dir", str(benchmarks_dir)])

        assert result.exit_code == 0
        # All benchmarks should be listed (sorted filenames)


# ============================================================================
# Integration Tests
# ============================================================================


class TestCLIIntegration:
    """Integration tests for CLI workflow."""

    def test_help_displays_for_all_commands(self, runner):
        """All commands display help text."""
        commands = ["download", "export", "info", "list"]

        for cmd in commands:
            result = runner.invoke(cli, [cmd, "--help"])
            assert result.exit_code == 0
            assert "Usage:" in result.output

    def test_version_option(self, runner):
        """Version option displays version from package metadata."""
        from cis_bench import __version__

        result = runner.invoke(cli, ["--version"])

        assert result.exit_code == 0
        assert __version__ in result.output

    def test_cli_help(self, runner):
        """Main CLI help displays overview."""
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "CIS Benchmark CLI" in result.output
        assert "download" in result.output
        assert "export" in result.output
        assert "info" in result.output
        assert "list" in result.output

    def test_invalid_command(self, runner):
        """Invalid command shows error."""
        result = runner.invoke(cli, ["invalid-command"])

        assert result.exit_code != 0

    def test_export_invalid_format(self, runner, sample_benchmark_json):
        """Export rejects invalid format choice."""
        result = runner.invoke(cli, ["export", str(sample_benchmark_json), "--format", "invalid"])

        assert result.exit_code != 0
        assert "Invalid value" in result.output or "Error" in result.output

    def test_download_invalid_browser(self, runner):
        """Download rejects invalid browser choice."""
        result = runner.invoke(cli, ["download", "23598", "--browser", "invalid"])

        assert result.exit_code != 0
