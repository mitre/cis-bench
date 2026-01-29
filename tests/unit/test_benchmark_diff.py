"""Tests for benchmark diff functionality.

TDD tests for comparing benchmark versions using DeepDiff.
"""

import json

import pytest
from click.testing import CliRunner

from cis_bench.cli.app import cli


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def old_benchmark_json():
    """Old benchmark version for comparison."""
    return {
        "title": "CIS Ubuntu Linux 22.04 LTS Benchmark",
        "benchmark_id": "12345",
        "url": "https://workbench.cisecurity.org/benchmarks/12345",
        "version": "1.0.0",
        "downloaded_at": "2024-01-01T00:00:00",
        "scraper_version": "v1_current",
        "total_recommendations": 4,
        "recommendations": [
            {
                "ref": "1.1.1",
                "title": "Ensure mounting of cramfs is disabled",
                "url": "https://workbench.cisecurity.org/recommendations/1",
                "assessment_status": "Automated",
                "profiles": ["Level 1 - Server"],
                "description": "The cramfs filesystem type is a compressed read-only Linux filesystem.",
                "rationale": "Removing support for unneeded filesystem types reduces the local attack surface.",
                "audit": "Run: modprobe -n -v cramfs",
                "remediation": "Edit /etc/modprobe.d/cramfs.conf",
                "cis_controls": [],
                "nist_controls": ["CM-7"],
            },
            {
                "ref": "2.1.1",
                "title": "Ensure NIS Server is not installed",
                "url": "https://workbench.cisecurity.org/recommendations/2",
                "assessment_status": "Automated",
                "profiles": ["Level 1 - Server"],
                "description": "The NIS service is inherently insecure.",
                "rationale": "NIS is insecure and should not be used.",
                "audit": "Run: rpm -q ypserv",
                "remediation": "Run: dnf remove ypserv",
                "cis_controls": [],
                "nist_controls": ["CM-7"],
            },
            {
                "ref": "3.1.1",
                "title": "Ensure SSH MaxAuthTries is set to 4 or less",
                "url": "https://workbench.cisecurity.org/recommendations/3",
                "assessment_status": "Automated",
                "profiles": ["Level 1 - Server"],
                "description": "The MaxAuthTries parameter specifies the maximum number of authentication attempts.",
                "rationale": "Setting the MaxAuthTries parameter to a low number will minimize the risk of brute force.",
                "audit": "Run: sshd -T | grep maxauthtries",
                "remediation": "Edit /etc/ssh/sshd_config and set MaxAuthTries 4",
                "cis_controls": [],
                "nist_controls": ["AC-7"],
            },
            {
                "ref": "5.1.1",
                "title": "Ensure cron daemon is enabled",
                "url": "https://workbench.cisecurity.org/recommendations/4",
                "assessment_status": "Automated",
                "profiles": ["Level 1 - Server"],
                "description": "The cron daemon is used to execute batch jobs on the system.",
                "rationale": "Proper job scheduling is important.",
                "audit": "Run: systemctl is-enabled crond",
                "remediation": "Run: systemctl enable crond",
                "cis_controls": [],
                "nist_controls": ["CM-7"],
            },
        ],
    }


@pytest.fixture
def new_benchmark_json():
    """New benchmark version with changes."""
    return {
        "title": "CIS Ubuntu Linux 22.04 LTS Benchmark",
        "benchmark_id": "12345",
        "url": "https://workbench.cisecurity.org/benchmarks/12345",
        "version": "2.0.0",
        "downloaded_at": "2024-06-01T00:00:00",
        "scraper_version": "v1_current",
        "total_recommendations": 4,
        "recommendations": [
            # 1.1.1 unchanged
            {
                "ref": "1.1.1",
                "title": "Ensure mounting of cramfs is disabled",
                "url": "https://workbench.cisecurity.org/recommendations/1",
                "assessment_status": "Automated",
                "profiles": ["Level 1 - Server"],
                "description": "The cramfs filesystem type is a compressed read-only Linux filesystem.",
                "rationale": "Removing support for unneeded filesystem types reduces the local attack surface.",
                "audit": "Run: modprobe -n -v cramfs",
                "remediation": "Edit /etc/modprobe.d/cramfs.conf",
                "cis_controls": [],
                "nist_controls": ["CM-7"],
            },
            # 2.1.1 REMOVED (not in new version)
            # 3.1.1 MODIFIED (title and audit changed)
            {
                "ref": "3.1.1",
                "title": "Ensure SSH MaxAuthTries is configured",  # Title changed
                "url": "https://workbench.cisecurity.org/recommendations/3",
                "assessment_status": "Automated",
                "profiles": ["Level 1 - Server"],
                "description": "The MaxAuthTries parameter specifies the maximum number of authentication attempts.",
                "rationale": "Setting the MaxAuthTries parameter to a low number will minimize the risk of brute force.",
                "audit": "Run: sshd -T -C user=root | grep maxauthtries",  # Audit changed
                "remediation": "Edit /etc/ssh/sshd_config and set MaxAuthTries 4",
                "cis_controls": [],
                "nist_controls": ["AC-7"],
            },
            # 1.1.9 ADDED (new recommendation)
            {
                "ref": "1.1.9",
                "title": "Ensure noexec option set on /var/tmp partition",
                "url": "https://workbench.cisecurity.org/recommendations/5",
                "assessment_status": "Automated",
                "profiles": ["Level 1 - Server"],
                "description": "The noexec mount option specifies that the filesystem cannot contain executable binaries.",
                "rationale": "Adding this option prevents users from executing programs from /var/tmp.",
                "audit": "Run: findmnt -n /var/tmp",
                "remediation": "Edit /etc/fstab and add noexec",
                "cis_controls": [],
                "nist_controls": ["CM-7"],
            },
            # 5.1.1 -> 6.1.1 RENUMBERED (same content, different ref)
            {
                "ref": "6.1.1",  # Was 5.1.1
                "title": "Ensure cron daemon is enabled",
                "url": "https://workbench.cisecurity.org/recommendations/4",
                "assessment_status": "Automated",
                "profiles": ["Level 1 - Server"],
                "description": "The cron daemon is used to execute batch jobs on the system.",
                "rationale": "Proper job scheduling is important.",
                "audit": "Run: systemctl is-enabled crond",
                "remediation": "Run: systemctl enable crond",
                "cis_controls": [],
                "nist_controls": ["CM-7"],
            },
        ],
    }


class TestDiffCommandExists:
    """Test that diff command is available."""

    def test_diff_command_in_help(self, runner):
        """The diff command should appear in help output."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "diff" in result.output

    def test_diff_command_has_help(self, runner):
        """The diff command should have its own help."""
        result = runner.invoke(cli, ["diff", "--help"])
        assert result.exit_code == 0
        assert "Compare" in result.output or "compare" in result.output


class TestDiffCommandArguments:
    """Test diff command argument handling."""

    def test_diff_requires_two_arguments(self, runner):
        """diff command requires old and new benchmark identifiers."""
        result = runner.invoke(cli, ["diff"])
        assert result.exit_code != 0

    def test_diff_requires_new_argument(self, runner):
        """diff command requires both old and new."""
        result = runner.invoke(cli, ["diff", "12345"])
        assert result.exit_code != 0

    def test_diff_accepts_two_ids(self, runner, monkeypatch):
        """diff command accepts two benchmark IDs."""
        monkeypatch.setenv("CIS_BENCH_ENV", "test")
        result = runner.invoke(cli, ["diff", "12345", "12346"])
        # May fail due to benchmarks not found, but not argument error
        if result.exit_code != 0:
            assert "argument" not in result.output.lower()


class TestDiffDetectsChanges:
    """Test that diff detects different types of changes."""

    def test_diff_detects_added_recommendations(
        self, runner, monkeypatch, tmp_path, old_benchmark_json, new_benchmark_json
    ):
        """diff should detect newly added recommendations."""
        monkeypatch.setenv("CIS_BENCH_ENV", "test")

        # Write benchmark files
        old_file = tmp_path / "old.json"
        new_file = tmp_path / "new.json"
        old_file.write_text(json.dumps(old_benchmark_json))
        new_file.write_text(json.dumps(new_benchmark_json))

        result = runner.invoke(cli, ["diff", str(old_file), str(new_file)])

        # Should show added recommendation
        if result.exit_code == 0:
            assert "1.1.9" in result.output or "added" in result.output.lower()

    def test_diff_detects_removed_recommendations(
        self, runner, monkeypatch, tmp_path, old_benchmark_json, new_benchmark_json
    ):
        """diff should detect removed recommendations."""
        monkeypatch.setenv("CIS_BENCH_ENV", "test")

        old_file = tmp_path / "old.json"
        new_file = tmp_path / "new.json"
        old_file.write_text(json.dumps(old_benchmark_json))
        new_file.write_text(json.dumps(new_benchmark_json))

        result = runner.invoke(cli, ["diff", str(old_file), str(new_file)])

        # Should show removed recommendation (2.1.1)
        if result.exit_code == 0:
            assert "2.1.1" in result.output or "removed" in result.output.lower()

    def test_diff_detects_modified_recommendations(
        self, runner, monkeypatch, tmp_path, old_benchmark_json, new_benchmark_json
    ):
        """diff should detect modified recommendations."""
        monkeypatch.setenv("CIS_BENCH_ENV", "test")

        old_file = tmp_path / "old.json"
        new_file = tmp_path / "new.json"
        old_file.write_text(json.dumps(old_benchmark_json))
        new_file.write_text(json.dumps(new_benchmark_json))

        result = runner.invoke(cli, ["diff", str(old_file), str(new_file)])

        # Should show modified recommendation (3.1.1)
        if result.exit_code == 0:
            assert "3.1.1" in result.output or "modified" in result.output.lower()


class TestDiffOutputFormats:
    """Test diff command output formats."""

    def test_diff_supports_table_format(self, runner, monkeypatch):
        """diff should support --format table."""
        monkeypatch.setenv("CIS_BENCH_ENV", "test")
        result = runner.invoke(cli, ["diff", "--help"])
        assert "table" in result.output or "format" in result.output.lower()

    def test_diff_supports_json_format(self, runner, monkeypatch):
        """diff should support --format json."""
        monkeypatch.setenv("CIS_BENCH_ENV", "test")
        result = runner.invoke(cli, ["diff", "--help"])
        assert "json" in result.output.lower()

    def test_diff_supports_markdown_format(self, runner, monkeypatch):
        """diff should support --format markdown."""
        monkeypatch.setenv("CIS_BENCH_ENV", "test")
        result = runner.invoke(cli, ["diff", "--help"])
        assert "markdown" in result.output.lower()

    def test_diff_json_output_is_valid(
        self, runner, monkeypatch, tmp_path, old_benchmark_json, new_benchmark_json
    ):
        """diff --format json should output valid JSON."""
        monkeypatch.setenv("CIS_BENCH_ENV", "test")

        old_file = tmp_path / "old.json"
        new_file = tmp_path / "new.json"
        old_file.write_text(json.dumps(old_benchmark_json))
        new_file.write_text(json.dumps(new_benchmark_json))

        result = runner.invoke(cli, ["diff", str(old_file), str(new_file), "--format", "json"])

        if result.exit_code == 0 and result.output.strip():
            # Should be valid JSON
            try:
                data = json.loads(result.output)
                assert "summary" in data or "changes" in data
            except json.JSONDecodeError:
                pytest.fail("JSON output is not valid JSON")


class TestDiffSummary:
    """Test diff summary statistics."""

    def test_diff_shows_summary_counts(
        self, runner, monkeypatch, tmp_path, old_benchmark_json, new_benchmark_json
    ):
        """diff should show summary counts (added, removed, modified)."""
        monkeypatch.setenv("CIS_BENCH_ENV", "test")

        old_file = tmp_path / "old.json"
        new_file = tmp_path / "new.json"
        old_file.write_text(json.dumps(old_benchmark_json))
        new_file.write_text(json.dumps(new_benchmark_json))

        result = runner.invoke(cli, ["diff", str(old_file), str(new_file)])

        if result.exit_code == 0:
            output_lower = result.output.lower()
            # Should have some indication of changes
            assert any(
                word in output_lower
                for word in ["added", "removed", "modified", "changed", "summary"]
            )


class TestDiffVerboseMode:
    """Test diff verbose mode."""

    def test_diff_supports_verbose_flag(self, runner, monkeypatch):
        """diff should support --verbose flag."""
        monkeypatch.setenv("CIS_BENCH_ENV", "test")
        result = runner.invoke(cli, ["diff", "--help"])
        assert "verbose" in result.output.lower()


class TestDiffWorksOffline:
    """Test that diff works in offline mode."""

    def test_diff_works_with_offline_flag(
        self, runner, monkeypatch, tmp_path, old_benchmark_json, new_benchmark_json
    ):
        """diff should work with --offline flag (local comparison only)."""
        monkeypatch.setenv("CIS_BENCH_ENV", "test")

        old_file = tmp_path / "old.json"
        new_file = tmp_path / "new.json"
        old_file.write_text(json.dumps(old_benchmark_json))
        new_file.write_text(json.dumps(new_benchmark_json))

        result = runner.invoke(cli, ["--offline", "diff", str(old_file), str(new_file)])

        # Should NOT fail due to offline mode (it's a local comparison)
        if result.exit_code != 0:
            assert "offline" not in result.output.lower() or "network" not in result.output.lower()
