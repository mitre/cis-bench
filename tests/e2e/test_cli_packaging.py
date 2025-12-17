"""Tests for CLI packaging and installation.

Verifies that the CLI tool is correctly packaged according to Python Packaging
Authority best practices:
- Entry points work correctly
- __main__.py module execution works
- Package metadata is correct

Reference: https://packaging.python.org/en/latest/guides/creating-command-line-tools/
"""

import subprocess
import sys
from importlib.metadata import entry_points, metadata

import pytest


class TestCLIEntryPoints:
    """Tests for CLI entry point configuration."""

    def test_console_script_entry_point_exists(self):
        """Verify cis-bench console_scripts entry point is registered."""
        # Get entry points for console_scripts group
        eps = entry_points()

        # Python 3.12+ returns a SelectableGroups object
        if hasattr(eps, "select"):
            console_scripts = eps.select(group="console_scripts")
        else:
            console_scripts = eps.get("console_scripts", [])

        # Find our entry point
        cis_bench_ep = None
        for ep in console_scripts:
            if ep.name == "cis-bench":
                cis_bench_ep = ep
                break

        assert cis_bench_ep is not None, (
            "cis-bench entry point not found in console_scripts. "
            "Check [project.scripts] in pyproject.toml"
        )
        assert "cis_bench.cli.app:cli" in str(cis_bench_ep.value), (
            f"Entry point target is wrong: {cis_bench_ep.value}"
        )

    def test_pipx_run_entry_point_exists(self):
        """Verify pipx.run entry point is registered for pipx compatibility."""
        eps = entry_points()

        # Python 3.12+ returns a SelectableGroups object
        if hasattr(eps, "select"):
            pipx_eps = eps.select(group="pipx.run")
        else:
            pipx_eps = eps.get("pipx.run", [])

        # Find our entry point
        cis_bench_ep = None
        for ep in pipx_eps:
            if ep.name == "cis-bench":
                cis_bench_ep = ep
                break

        assert cis_bench_ep is not None, (
            "cis-bench entry point not found in pipx.run group. "
            'Check [project.entry-points."pipx.run"] in pyproject.toml'
        )

    def test_entry_point_is_loadable(self):
        """Verify the entry point function can be loaded."""
        eps = entry_points()

        if hasattr(eps, "select"):
            console_scripts = eps.select(group="console_scripts")
        else:
            console_scripts = eps.get("console_scripts", [])

        for ep in console_scripts:
            if ep.name == "cis-bench":
                # This will raise if the module/function doesn't exist
                loaded = ep.load()
                assert callable(loaded), "Entry point must be callable"
                break


class TestModuleExecution:
    """Tests for python -m cis_bench execution."""

    def test_main_module_exists(self):
        """Verify __main__.py exists and is importable."""
        try:
            import cis_bench.__main__  # noqa: F401
        except ImportError as e:
            pytest.fail(
                f"__main__.py is missing or has import errors: {e}. "
                "Users won't be able to run 'python -m cis_bench'"
            )

    def test_module_execution_shows_help(self):
        """Verify 'python -m cis_bench --help' works."""
        result = subprocess.run(
            [sys.executable, "-m", "cis_bench", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, (
            f"'python -m cis_bench --help' failed with exit code {result.returncode}. "
            f"stderr: {result.stderr}"
        )
        assert "CIS Benchmark CLI" in result.stdout, (
            f"Help text not found in output: {result.stdout}"
        )

    def test_module_execution_shows_version(self):
        """Verify 'python -m cis_bench --version' works."""
        result = subprocess.run(
            [sys.executable, "-m", "cis_bench", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, (
            f"'python -m cis_bench --version' failed. stderr: {result.stderr}"
        )
        # Version should be in output
        assert "version" in result.stdout.lower() or "." in result.stdout, (
            f"Version not found in output: {result.stdout}"
        )


class TestPackageMetadata:
    """Tests for package metadata correctness."""

    def test_package_name_correct(self):
        """Verify package name is 'cis-bench'."""
        meta = metadata("cis-bench")
        assert meta["Name"] == "cis-bench"

    def test_package_has_version(self):
        """Verify package has a version."""
        meta = metadata("cis-bench")
        pkg_version = meta["Version"]
        assert pkg_version is not None
        # Version should be semver-like (X.Y.Z)
        parts = pkg_version.split(".")
        assert len(parts) >= 2, f"Version '{pkg_version}' doesn't look like semver"

    def test_cli_version_matches_package_version(self):
        """Verify CLI --version matches package metadata version (no hardcoding)."""
        from cis_bench import __version__

        meta = metadata("cis-bench")
        pkg_version = meta["Version"]

        assert __version__ == pkg_version, (
            f"CLI version ({__version__}) doesn't match package version ({pkg_version}). "
            "Version may be hardcoded instead of using importlib.metadata."
        )

    def test_package_has_description(self):
        """Verify package has a description."""
        meta = metadata("cis-bench")
        assert meta["Summary"] is not None
        assert len(meta["Summary"]) > 10, "Description is too short"

    def test_package_has_required_metadata(self):
        """Verify all required PyPI metadata is present."""
        meta = metadata("cis-bench")

        required_fields = [
            "Name",
            "Version",
            "Summary",
            "Author-email",
            "License",
            "Requires-Python",
        ]

        for field in required_fields:
            assert meta.get(field) is not None, f"Missing required metadata field: {field}"


class TestCLIInvocation:
    """Tests for direct CLI invocation patterns."""

    def test_cli_help_via_subprocess(self):
        """Test CLI help works via subprocess (simulates user invocation)."""
        # This tests the actual installed entry point
        result = subprocess.run(
            ["cis-bench", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, (
            f"'cis-bench --help' failed. This may indicate PATH issues. stderr: {result.stderr}"
        )
        assert "download" in result.stdout.lower()
        assert "export" in result.stdout.lower()

    def test_cli_version_via_subprocess(self):
        """Test CLI version works via subprocess."""
        result = subprocess.run(
            ["cis-bench", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_cli_invalid_command_returns_error(self):
        """Test CLI returns non-zero for invalid commands."""
        result = subprocess.run(
            ["cis-bench", "not-a-real-command"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode != 0, "Invalid command should return non-zero"


class TestInstallationPaths:
    """Tests to verify installation creates correct paths."""

    def test_package_is_importable(self):
        """Verify the package can be imported."""
        try:
            import cis_bench  # noqa: F401
        except ImportError as e:
            pytest.fail(f"Package not importable: {e}")

    def test_cli_module_is_importable(self):
        """Verify CLI module is importable."""
        try:
            from cis_bench.cli.app import cli  # noqa: F401
        except ImportError as e:
            pytest.fail(f"CLI module not importable: {e}")

    def test_cli_function_is_click_command(self):
        """Verify CLI function is a Click command."""
        import click

        from cis_bench.cli.app import cli

        assert isinstance(cli, click.core.Group) or isinstance(cli, click.core.Command), (
            f"cli should be a Click command/group, got {type(cli)}"
        )
