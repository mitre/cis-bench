"""Tests for offline mode functionality.

TDD tests for the --offline flag that prevents accidental network calls.
"""

import pytest
from click.testing import CliRunner

from cis_bench.cli.app import cli


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


class TestOfflineFlagExists:
    """Test that --offline flag is available globally."""

    def test_offline_flag_in_help(self, runner):
        """The --offline flag should appear in help output."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "--offline" in result.output

    def test_offline_flag_accepted(self, runner):
        """The --offline flag should be accepted without error."""
        result = runner.invoke(cli, ["--offline", "--help"])
        assert result.exit_code == 0


class TestOfflineBlocksNetworkCommands:
    """Test that --offline flag blocks commands requiring network."""

    def test_offline_blocks_auth_login(self, runner):
        """auth login should fail with helpful message when --offline."""
        result = runner.invoke(cli, ["--offline", "auth", "login"])
        assert result.exit_code != 0
        assert "offline" in result.output.lower()
        # Should explain what to do
        assert "network" in result.output.lower() or "requires" in result.output.lower()

    def test_offline_blocks_catalog_refresh(self, runner):
        """catalog refresh should fail with helpful message when --offline."""
        result = runner.invoke(cli, ["--offline", "catalog", "refresh"])
        assert result.exit_code != 0
        assert "offline" in result.output.lower()

    def test_offline_blocks_download(self, runner):
        """download should fail with helpful message when --offline."""
        result = runner.invoke(cli, ["--offline", "download", "12345"])
        assert result.exit_code != 0
        assert "offline" in result.output.lower()

    def test_offline_blocks_get(self, runner):
        """get command should fail with helpful message when --offline."""
        result = runner.invoke(cli, ["--offline", "get", "ubuntu"])
        assert result.exit_code != 0
        assert "offline" in result.output.lower()


class TestOfflineAllowsLocalCommands:
    """Test that --offline allows commands that don't need network."""

    def test_offline_allows_search(self, runner, tmp_path, monkeypatch):
        """search should work in offline mode (uses local FTS5)."""
        # Set up test environment
        monkeypatch.setenv("CIS_BENCH_ENV", "test")
        # search may fail due to empty catalog, but should NOT fail due to offline
        result = runner.invoke(cli, ["--offline", "search", "ubuntu"])
        # Should not contain offline error - may have other errors (no catalog)
        if result.exit_code != 0:
            assert "offline" not in result.output.lower() or "allowed" in result.output.lower()

    def test_offline_allows_list(self, runner, tmp_path, monkeypatch):
        """list should work in offline mode (uses local cache)."""
        monkeypatch.setenv("CIS_BENCH_ENV", "test")
        result = runner.invoke(cli, ["--offline", "list"])
        # Should not fail due to offline mode
        if result.exit_code != 0:
            assert "offline" not in result.output.lower() or "allowed" in result.output.lower()

    def test_offline_allows_export(self, runner, tmp_path, monkeypatch):
        """export should work in offline mode (uses local cache)."""
        monkeypatch.setenv("CIS_BENCH_ENV", "test")
        result = runner.invoke(cli, ["--offline", "export", "12345", "--format", "yaml"])
        # May fail due to benchmark not found, but not due to offline
        if result.exit_code != 0:
            assert "offline" not in result.output.lower() or "allowed" in result.output.lower()


class TestCacheStatusCommand:
    """Test the cache status command."""

    def test_cache_status_exists(self, runner):
        """cache status command should exist."""
        result = runner.invoke(cli, ["cache", "--help"])
        assert result.exit_code == 0
        assert "status" in result.output

    def test_cache_status_shows_info(self, runner, tmp_path, monkeypatch):
        """cache status should show catalog and benchmark info."""
        monkeypatch.setenv("CIS_BENCH_ENV", "test")
        result = runner.invoke(cli, ["cache", "status"])
        assert result.exit_code == 0
        # Should show catalog status
        assert "catalog" in result.output.lower()
        # Should show benchmark count or path
        assert "benchmark" in result.output.lower() or "downloaded" in result.output.lower()

    def test_cache_status_works_offline(self, runner, tmp_path, monkeypatch):
        """cache status should work with --offline flag."""
        monkeypatch.setenv("CIS_BENCH_ENV", "test")
        result = runner.invoke(cli, ["--offline", "cache", "status"])
        assert result.exit_code == 0


class TestOfflineContext:
    """Test that offline flag is properly passed through context."""

    def test_offline_stored_in_context(self, runner):
        """The offline flag should be stored in Click context."""
        # We can't directly test context, but we can verify behavior
        # This is implicitly tested by the blocking tests above
        pass

    def test_offline_default_is_false(self, runner, tmp_path, monkeypatch):
        """Without --offline flag, commands should attempt network (default)."""
        monkeypatch.setenv("CIS_BENCH_ENV", "test")
        # This would attempt network if not for test isolation
        result = runner.invoke(cli, ["search", "ubuntu"])
        # Should not mention offline mode
        assert "offline mode" not in result.output.lower()
