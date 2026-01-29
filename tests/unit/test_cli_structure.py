"""Tests for CLI command structure and flag organization.

These tests enforce the simplified CLI structure where:
- auth login = THE place for authentication setup
- download/get/export = use saved session only (no inline auth flags)

This prevents flag duplication and user confusion (Issue #3).
"""


class TestAuthCommandStructure:
    """Verify auth commands have correct flags."""

    def test_auth_login_has_browser_option(self):
        """auth login should have --browser flag."""
        from cis_bench.cli.commands.auth import login

        param_names = [p.name for p in login.params]
        assert "browser" in param_names

    def test_auth_login_has_cookies_option(self):
        """auth login should have --cookies flag."""
        from cis_bench.cli.commands.auth import login

        param_names = [p.name for p in login.params]
        assert "cookies" in param_names

    def test_auth_login_has_no_verify_ssl_option(self):
        """auth login should have --no-verify-ssl flag."""
        from cis_bench.cli.commands.auth import login

        param_names = [p.name for p in login.params]
        assert "no_verify_ssl" in param_names


class TestDownloadCommandStructure:
    """Verify download command does NOT have auth flags (DRY principle)."""

    def test_download_has_no_browser_option(self):
        """download should NOT have --browser flag (use auth login instead)."""
        from cis_bench.cli.commands.download import download

        param_names = [p.name for p in download.params]
        assert "browser" not in param_names, (
            "download should not have --browser flag. "
            "Users should use 'cis-bench auth login --browser X' instead."
        )

    def test_download_has_no_cookies_option(self):
        """download should NOT have --cookies flag (use auth login instead)."""
        from cis_bench.cli.commands.download import download

        param_names = [p.name for p in download.params]
        assert "cookies" not in param_names, (
            "download should not have --cookies flag. "
            "Users should use 'cis-bench auth login --cookies FILE' instead."
        )

    def test_download_has_no_verify_ssl_option(self):
        """download should NOT have --no-verify-ssl (use auth login instead)."""
        from cis_bench.cli.commands.download import download

        param_names = [p.name for p in download.params]
        assert "no_verify_ssl" not in param_names, (
            "download should not have --no-verify-ssl flag. "
            "Users should use 'cis-bench auth login --no-verify-ssl' instead."
        )

    def test_download_has_format_option(self):
        """download should still have --format flag."""
        from cis_bench.cli.commands.download import download

        param_names = [p.name for p in download.params]
        assert "export_formats" in param_names or "format" in param_names

    def test_download_has_force_option(self):
        """download should have --force flag."""
        from cis_bench.cli.commands.download import download

        param_names = [p.name for p in download.params]
        assert "force" in param_names


class TestGetCommandStructure:
    """Verify get command does NOT have auth flags (DRY principle)."""

    def test_get_has_no_browser_option(self):
        """get should NOT have --browser flag (use auth login instead)."""
        from cis_bench.cli.commands.get import get_cmd

        param_names = [p.name for p in get_cmd.params]
        assert "browser" not in param_names, (
            "get should not have --browser flag. "
            "Users should use 'cis-bench auth login --browser X' instead."
        )

    def test_get_has_format_option(self):
        """get should have --format flag."""
        from cis_bench.cli.commands.get import get_cmd

        param_names = [p.name for p in get_cmd.params]
        assert "format" in param_names or "export_format" in param_names

    def test_get_has_style_option(self):
        """get should have --style flag for XCCDF."""
        from cis_bench.cli.commands.get import get_cmd

        param_names = [p.name for p in get_cmd.params]
        assert "style" in param_names


class TestExportCommandStructure:
    """Verify export command structure (no auth needed - works on local files)."""

    def test_export_has_no_browser_option(self):
        """export should NOT have --browser flag (doesn't need auth)."""
        from cis_bench.cli.commands.export import export_cmd

        param_names = [p.name for p in export_cmd.params]
        assert "browser" not in param_names

    def test_export_has_format_option(self):
        """export should have --format flag."""
        from cis_bench.cli.commands.export import export_cmd

        param_names = [p.name for p in export_cmd.params]
        assert "export_format" in param_names or "format" in param_names

    def test_export_has_style_option(self):
        """export should have --style flag for XCCDF."""
        from cis_bench.cli.commands.export import export_cmd

        param_names = [p.name for p in export_cmd.params]
        assert "style" in param_names


class TestNoSessionErrorMessage:
    """Verify helpful error when no saved session exists."""

    def test_download_without_session_shows_auth_hint(self, cli_runner, mocker):
        """download without session should tell user to run auth login."""
        from cis_bench.cli.app import cli

        # Mock no saved session
        mocker.patch(
            "cis_bench.fetcher.auth.AuthManager.get_or_create_session",
            side_effect=ValueError("No saved session found"),
        )

        result = cli_runner.invoke(cli, ["download", "23598"])

        # Should mention auth login
        assert "auth login" in result.output.lower() or result.exit_code != 0
