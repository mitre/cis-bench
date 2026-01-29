"""Tests for auth CLI commands (login, logout, status).

These tests cover the uncovered lines in cli/commands/auth.py:
- Lines 97-149: --open flag behavior (platform-specific browser opening)
- Lines 160-162: Cookie file loading error handling
- Lines 181: Windows permission error handling (re-raise path)
- Lines 205-208: SSL verification tip on validation failure
- Lines 224-225, 227-229: ValueError and Exception handlers in login
- Lines 305-307: Exception handler in status command
- Lines 341-344: Exception handler in logout command

DOES NOT duplicate tests from:
- test_auth_windows_fallback.py - Windows fallback behavior
- test_cli_structure.py - Flag presence verification
"""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from cis_bench.cli.app import cli


@pytest.fixture
def runner():
    """Create Click CLI test runner."""
    return CliRunner()


class TestAuthLoginCommand:
    """Tests for 'auth login' command."""

    def test_login_requires_browser_or_cookies(self, runner):
        """auth login should require either --browser or --cookies."""
        result = runner.invoke(cli, ["auth", "login"])

        assert result.exit_code == 1
        assert "Must specify either --browser or --cookies" in result.output

    def test_login_with_invalid_browser(self, runner):
        """auth login should reject invalid browser choice."""
        result = runner.invoke(cli, ["auth", "login", "--browser", "invalid"])

        assert result.exit_code != 0
        assert "Invalid value" in result.output

    @patch("cis_bench.cli.commands.auth.AuthManager")
    def test_login_with_browser_extracts_cookies(self, mock_auth_manager, runner):
        """auth login --browser should extract and save cookies."""
        mock_session = MagicMock()
        mock_session.cookies = [MagicMock()]  # Non-empty cookies
        mock_auth_manager.load_cookies_from_browser.return_value = mock_session
        mock_auth_manager.validate_session.return_value = True
        mock_auth_manager._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "firefox"])

        # Should have called load_cookies_from_browser
        mock_auth_manager.load_cookies_from_browser.assert_called()
        # Should have tried to validate
        mock_auth_manager.validate_session.assert_called()

    @patch("cis_bench.cli.commands.auth.AuthManager")
    def test_login_with_cookies_file(self, mock_auth_manager, runner, tmp_path):
        """auth login --cookies should load from file."""
        # Create a dummy cookie file
        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text("# Netscape HTTP Cookie File\n")

        mock_session = MagicMock()
        mock_session.cookies = [MagicMock()]
        mock_auth_manager.load_cookies_from_file.return_value = mock_session
        mock_auth_manager.validate_session.return_value = True

        result = runner.invoke(cli, ["auth", "login", "--cookies", str(cookie_file)])

        # Should have called load_cookies_from_file
        mock_auth_manager.load_cookies_from_file.assert_called()

    @patch("cis_bench.cli.commands.auth.AuthManager")
    def test_login_prefers_cookies_over_browser(self, mock_auth_manager, runner, tmp_path):
        """When both --browser and --cookies provided, prefer cookies."""
        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text("# Netscape HTTP Cookie File\n")

        mock_session = MagicMock()
        mock_session.cookies = [MagicMock()]
        mock_auth_manager.load_cookies_from_file.return_value = mock_session
        mock_auth_manager.validate_session.return_value = True

        result = runner.invoke(
            cli, ["auth", "login", "--browser", "chrome", "--cookies", str(cookie_file)]
        )

        # Should warn about both being specified
        assert "Warning" in result.output or result.exit_code == 0

        # Should use cookies file, not browser
        mock_auth_manager.load_cookies_from_file.assert_called()

    @patch("cis_bench.cli.commands.auth.AuthManager")
    def test_login_validation_failure(self, mock_auth_manager, runner):
        """auth login should fail if session validation fails."""
        mock_session = MagicMock()
        mock_session.cookies = [MagicMock()]
        mock_auth_manager.load_cookies_from_browser.return_value = mock_session
        mock_auth_manager.validate_session.return_value = False
        mock_auth_manager._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "firefox"])

        assert result.exit_code == 1
        assert "validation failed" in result.output.lower() or "invalid" in result.output.lower()

    @patch("cis_bench.cli.commands.auth.AuthManager")
    def test_login_no_cookies_found(self, mock_auth_manager, runner):
        """auth login should fail if no cookies extracted."""
        mock_session = MagicMock()
        mock_session.cookies = []  # Empty cookies
        mock_auth_manager.load_cookies_from_browser.return_value = mock_session
        mock_auth_manager._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "firefox"])

        assert result.exit_code == 1
        assert "No cookies found" in result.output

    @patch("cis_bench.cli.commands.auth.AuthManager")
    def test_login_saves_session_on_success(self, mock_auth_manager, runner):
        """auth login should save session after successful validation."""
        mock_session = MagicMock()
        mock_session.cookies = [MagicMock()]
        mock_auth_manager.load_cookies_from_browser.return_value = mock_session
        mock_auth_manager.validate_session.return_value = True
        mock_auth_manager._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "firefox"])

        # Should have saved session
        mock_auth_manager.save_session.assert_called_once_with(mock_session)

    @patch("cis_bench.cli.commands.auth.AuthManager")
    def test_login_windows_permission_error_shows_help(self, mock_auth_manager, runner):
        """auth login should show helpful message on Windows permission error."""
        mock_auth_manager.load_cookies_from_browser.side_effect = Exception(
            "This operation requires admin"
        )
        mock_auth_manager._is_windows_permission_error.return_value = True
        mock_auth_manager._format_windows_cookie_error.return_value = (
            "Use Firefox or --cookies option"
        )

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome"])

        assert result.exit_code == 1
        # Should show Windows-specific help
        assert "firefox" in result.output.lower() or "cookie" in result.output.lower()


class TestAuthLogoutCommand:
    """Tests for 'auth logout' command."""

    @patch("cis_bench.cli.commands.auth.AuthManager")
    def test_logout_clears_session(self, mock_auth_manager, runner):
        """auth logout should clear saved session."""
        mock_auth_manager.clear_saved_session.return_value = True

        result = runner.invoke(cli, ["auth", "logout"])

        mock_auth_manager.clear_saved_session.assert_called_once()
        assert result.exit_code == 0

    @patch("cis_bench.cli.commands.auth.AuthManager")
    def test_logout_no_session(self, mock_auth_manager, runner):
        """auth logout should handle case when no session exists."""
        mock_auth_manager.clear_saved_session.return_value = False

        result = runner.invoke(cli, ["auth", "logout"])

        assert result.exit_code == 0
        assert "No session to clear" in result.output or "no session" in result.output.lower()


class TestAuthStatusCommand:
    """Tests for 'auth status' command."""

    @patch("cis_bench.cli.commands.auth.AuthManager")
    def test_status_with_valid_session(self, mock_auth_manager, runner):
        """auth status should show logged in when session valid."""
        mock_session = MagicMock()
        mock_session.cookies = [MagicMock()]
        mock_auth_manager.load_saved_session.return_value = mock_session
        mock_auth_manager.validate_session.return_value = True

        result = runner.invoke(cli, ["auth", "status"])

        assert result.exit_code == 0
        # Should indicate logged in
        assert (
            "logged in" in result.output.lower()
            or "valid" in result.output.lower()
            or "✓" in result.output
        )

    @patch("cis_bench.cli.commands.auth.AuthManager")
    def test_status_with_invalid_session(self, mock_auth_manager, runner):
        """auth status should show logged out when session invalid."""
        mock_session = MagicMock()
        mock_auth_manager.load_saved_session.return_value = mock_session
        mock_auth_manager.validate_session.return_value = False

        result = runner.invoke(cli, ["auth", "status"])

        # Should indicate not logged in or session expired
        assert (
            "not logged in" in result.output.lower()
            or "expired" in result.output.lower()
            or "invalid" in result.output.lower()
            or "✗" in result.output
        )

    @patch("cis_bench.cli.commands.auth.AuthManager")
    def test_status_no_session(self, mock_auth_manager, runner):
        """auth status should show not logged in when no saved session."""
        mock_auth_manager.load_saved_session.return_value = None

        result = runner.invoke(cli, ["auth", "status"])

        assert (
            "not logged in" in result.output.lower()
            or "no saved session" in result.output.lower()
            or "✗" in result.output
        )


# =============================================================================
# Additional tests for uncovered lines
# =============================================================================


class TestAuthLoginOpenFlag:
    """Tests for 'auth login --open' flag behavior (lines 97-149).

    These tests cover platform-specific browser opening code paths.
    Note: platform module is imported inside the function, so we patch it globally.
    """

    @patch("cis_bench.cli.commands.auth.AuthManager")
    @patch("platform.system")
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_login_open_macos(
        self, mock_which, mock_subprocess, mock_platform, mock_auth, runner, tmp_path
    ):
        """Should use macOS 'open' command with --open flag on Darwin."""
        mock_platform.return_value = "Darwin"
        mock_which.return_value = "/usr/bin/open"
        mock_subprocess.return_value = MagicMock(returncode=0)

        mock_session = MagicMock()
        mock_session.cookies = [MagicMock()]
        mock_auth.load_cookies_from_browser.return_value = mock_session
        mock_auth.validate_session.return_value = True
        mock_auth.save_session.return_value = None
        mock_auth.get_session_file_path.return_value = tmp_path / "session.cookies"
        mock_auth._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome", "--open"], input="\n")

        # Should call subprocess with open command
        mock_subprocess.assert_called()
        call_args = mock_subprocess.call_args[0][0]
        assert "/usr/bin/open" in call_args
        assert "-a" in call_args
        assert "Google Chrome" in call_args
        assert "https://workbench.cisecurity.org/" in call_args

    @patch("cis_bench.cli.commands.auth.AuthManager")
    @patch("platform.system")
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_login_open_linux(
        self, mock_which, mock_subprocess, mock_platform, mock_auth, runner, tmp_path
    ):
        """Should use xdg-open on Linux with --open flag."""
        mock_platform.return_value = "Linux"
        mock_which.return_value = "/usr/bin/xdg-open"
        mock_subprocess.return_value = MagicMock(returncode=0)

        mock_session = MagicMock()
        mock_session.cookies = [MagicMock()]
        mock_auth.load_cookies_from_browser.return_value = mock_session
        mock_auth.validate_session.return_value = True
        mock_auth.save_session.return_value = None
        mock_auth.get_session_file_path.return_value = tmp_path / "session.cookies"
        mock_auth._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome", "--open"], input="\n")

        mock_subprocess.assert_called()
        call_args = mock_subprocess.call_args[0][0]
        assert "xdg-open" in str(call_args)

    @patch("cis_bench.cli.commands.auth.AuthManager")
    @patch("platform.system")
    @patch("webbrowser.open")
    def test_login_open_windows(self, mock_webbrowser, mock_platform, mock_auth, runner, tmp_path):
        """Should use webbrowser module on Windows with --open flag."""
        mock_platform.return_value = "Windows"

        mock_session = MagicMock()
        mock_session.cookies = [MagicMock()]
        mock_auth.load_cookies_from_browser.return_value = mock_session
        mock_auth.validate_session.return_value = True
        mock_auth.save_session.return_value = None
        mock_auth.get_session_file_path.return_value = tmp_path / "session.cookies"
        mock_auth._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome", "--open"], input="\n")

        mock_webbrowser.assert_called_once_with("https://workbench.cisecurity.org/")

    @patch("cis_bench.cli.commands.auth.AuthManager")
    @patch("platform.system")
    @patch("webbrowser.open")
    def test_login_open_unknown_os_fallback(
        self, mock_webbrowser, mock_platform, mock_auth, runner, tmp_path
    ):
        """Should fall back to webbrowser module on unknown OS."""
        mock_platform.return_value = "FreeBSD"  # Unknown OS

        mock_session = MagicMock()
        mock_session.cookies = [MagicMock()]
        mock_auth.load_cookies_from_browser.return_value = mock_session
        mock_auth.validate_session.return_value = True
        mock_auth.save_session.return_value = None
        mock_auth.get_session_file_path.return_value = tmp_path / "session.cookies"
        mock_auth._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome", "--open"], input="\n")

        mock_webbrowser.assert_called_once_with("https://workbench.cisecurity.org/")

    @patch("cis_bench.cli.commands.auth.AuthManager")
    @patch("platform.system")
    @patch("shutil.which")
    def test_login_open_macos_open_not_found(
        self, mock_which, mock_platform, mock_auth, runner, tmp_path
    ):
        """Should show helpful message if 'open' command not found on macOS."""
        mock_platform.return_value = "Darwin"
        mock_which.return_value = None  # 'open' not found

        mock_session = MagicMock()
        mock_session.cookies = [MagicMock()]
        mock_auth.load_cookies_from_browser.return_value = mock_session
        mock_auth.validate_session.return_value = True
        mock_auth.save_session.return_value = None
        mock_auth.get_session_file_path.return_value = tmp_path / "session.cookies"
        mock_auth._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome", "--open"], input="\n")

        # Should show error message but continue
        assert "Could not open browser" in result.output
        assert "Please open manually" in result.output

    @patch("cis_bench.cli.commands.auth.AuthManager")
    @patch("platform.system")
    @patch("shutil.which")
    def test_login_open_linux_xdg_not_found(
        self, mock_which, mock_platform, mock_auth, runner, tmp_path
    ):
        """Should show helpful message if xdg-open not found on Linux."""
        mock_platform.return_value = "Linux"
        mock_which.return_value = None  # xdg-open not found

        mock_session = MagicMock()
        mock_session.cookies = [MagicMock()]
        mock_auth.load_cookies_from_browser.return_value = mock_session
        mock_auth.validate_session.return_value = True
        mock_auth.save_session.return_value = None
        mock_auth.get_session_file_path.return_value = tmp_path / "session.cookies"
        mock_auth._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome", "--open"], input="\n")

        # Should show error message but continue
        assert "Could not open browser" in result.output
        assert "Please open manually" in result.output

    @patch("cis_bench.cli.commands.auth.AuthManager")
    @patch("platform.system")
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_login_open_subprocess_failure(
        self, mock_which, mock_subprocess, mock_platform, mock_auth, runner, tmp_path
    ):
        """Should handle subprocess failure gracefully."""
        mock_platform.return_value = "Darwin"
        mock_which.return_value = "/usr/bin/open"
        mock_subprocess.side_effect = Exception("Browser launch failed")

        mock_session = MagicMock()
        mock_session.cookies = [MagicMock()]
        mock_auth.load_cookies_from_browser.return_value = mock_session
        mock_auth.validate_session.return_value = True
        mock_auth.save_session.return_value = None
        mock_auth.get_session_file_path.return_value = tmp_path / "session.cookies"
        mock_auth._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome", "--open"], input="\n")

        # Should continue after browser open failure
        assert "Could not open browser" in result.output


class TestAuthLoginCookieFileErrors:
    """Tests for cookie file loading error handling (lines 160-162)."""

    @patch("cis_bench.cli.commands.auth.AuthManager")
    def test_login_cookie_file_load_failure(self, mock_auth, runner, tmp_path):
        """Should handle cookie file loading errors gracefully."""
        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text("invalid content\n")

        mock_auth.load_cookies_from_file.side_effect = Exception("Invalid cookie format")

        result = runner.invoke(cli, ["auth", "login", "--cookies", str(cookie_file)])

        assert result.exit_code == 1
        assert "Failed to load cookies" in result.output

    @patch("cis_bench.cli.commands.auth.AuthManager")
    def test_login_cookie_file_permission_error(self, mock_auth, runner, tmp_path):
        """Should handle cookie file permission errors."""
        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text("content\n")

        mock_auth.load_cookies_from_file.side_effect = PermissionError("Access denied")

        result = runner.invoke(cli, ["auth", "login", "--cookies", str(cookie_file)])

        assert result.exit_code == 1
        assert "Failed to load cookies" in result.output


class TestAuthLoginSSLVerificationTip:
    """Tests for SSL verification tip on validation failure (lines 205-208)."""

    @patch("cis_bench.cli.commands.auth.AuthManager")
    @patch("cis_bench.cli.commands.auth.Config.get_verify_ssl")
    def test_login_shows_ssl_tip_when_ssl_enabled(self, mock_get_ssl, mock_auth, runner):
        """Should show SSL tip when validation fails with SSL verification enabled."""
        mock_get_ssl.return_value = True

        mock_session = MagicMock()
        mock_session.cookies = [MagicMock()]
        mock_auth.load_cookies_from_browser.return_value = mock_session
        mock_auth.validate_session.return_value = False
        mock_auth._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome"])

        assert result.exit_code == 1
        assert "Session validation failed" in result.output
        assert "--no-verify-ssl" in result.output
        assert "CIS_BENCH_VERIFY_SSL=false" in result.output

    @patch("cis_bench.cli.commands.auth.AuthManager")
    @patch("cis_bench.cli.commands.auth.Config.get_verify_ssl")
    def test_login_no_ssl_tip_when_ssl_disabled(self, mock_get_ssl, mock_auth, runner):
        """Should NOT show SSL tip when SSL verification is already disabled."""
        mock_get_ssl.return_value = False

        mock_session = MagicMock()
        mock_session.cookies = [MagicMock()]
        mock_auth.load_cookies_from_browser.return_value = mock_session
        mock_auth.validate_session.return_value = False
        mock_auth._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome"])

        assert result.exit_code == 1
        assert "Session validation failed" in result.output
        # Should NOT show SSL tip when already disabled
        assert "--no-verify-ssl" not in result.output


class TestAuthLoginExceptionHandlers:
    """Tests for ValueError and Exception handlers in login (lines 224-229)."""

    @patch("cis_bench.cli.commands.auth.AuthManager")
    def test_login_value_error_handling(self, mock_auth, runner):
        """Should handle ValueError gracefully (line 224-225)."""
        mock_auth.load_cookies_from_browser.side_effect = ValueError("Invalid browser type")
        mock_auth._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome"])

        assert result.exit_code == 1
        assert "Invalid browser type" in result.output

    @patch("cis_bench.cli.commands.auth.AuthManager")
    def test_login_generic_exception_handling(self, mock_auth, runner):
        """Should handle unexpected exceptions gracefully (lines 227-229)."""
        mock_auth.load_cookies_from_browser.side_effect = RuntimeError("Unexpected error")
        mock_auth._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome"])

        assert result.exit_code == 1
        assert "Login failed" in result.output
        assert "Unexpected error" in result.output


class TestAuthLoginWindowsPermissionReRaise:
    """Tests for Windows permission error re-raise path (line 181)."""

    @patch("cis_bench.cli.commands.auth.AuthManager")
    def test_login_non_windows_error_reraises(self, mock_auth, runner):
        """Should re-raise non-Windows permission errors."""
        # When _is_windows_permission_error returns False, should re-raise
        mock_auth.load_cookies_from_browser.side_effect = Exception("Network timeout")
        mock_auth._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome"])

        assert result.exit_code == 1
        # Should show generic login failed error
        assert "Login failed" in result.output


class TestAuthStatusExceptionHandler:
    """Tests for exception handler in status command (lines 305-307)."""

    @patch("cis_bench.cli.commands.auth.AuthManager")
    def test_status_exception_handling(self, mock_auth, runner):
        """Should handle unexpected exceptions gracefully."""
        mock_auth.get_session_file_path.side_effect = RuntimeError("Unexpected filesystem error")

        result = runner.invoke(cli, ["auth", "status"])

        assert result.exit_code == 1
        assert "Status check failed" in result.output
        assert "Unexpected filesystem error" in result.output

    @patch("cis_bench.cli.commands.auth.AuthManager")
    def test_status_no_session_file(self, mock_auth, runner):
        """Should report not logged in when no session file exists."""
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_auth.get_session_file_path.return_value = mock_path

        result = runner.invoke(cli, ["auth", "status"])

        assert result.exit_code == 1
        assert "Not logged in" in result.output
        assert "cis-bench auth login" in result.output

    @patch("cis_bench.cli.commands.auth.AuthManager")
    def test_status_failed_to_load_session(self, mock_auth, runner, tmp_path):
        """Should report error when session file exists but can't be loaded."""
        mock_path = tmp_path / "session.cookies"
        mock_path.touch()

        mock_auth.get_session_file_path.return_value = mock_path
        mock_auth.load_saved_session.return_value = None

        result = runner.invoke(cli, ["auth", "status"])

        assert result.exit_code == 1
        assert "Could not load saved session" in result.output

    @patch("cis_bench.cli.commands.auth.AuthManager")
    @patch("cis_bench.cli.commands.auth.Config.get_verify_ssl")
    def test_status_json_output(self, mock_get_ssl, mock_auth, runner, tmp_path):
        """Should output JSON when --output-format json specified."""
        mock_get_ssl.return_value = True
        mock_path = tmp_path / "session.cookies"
        mock_path.touch()

        mock_session = MagicMock()
        mock_session.cookies = [MagicMock()]

        mock_auth.get_session_file_path.return_value = mock_path
        mock_auth.load_saved_session.return_value = mock_session
        mock_auth.validate_session.return_value = True

        result = runner.invoke(cli, ["auth", "status", "--output-format", "json"])

        # JSON output includes logged_in field
        assert "logged_in" in result.output


class TestAuthLogoutExceptionHandler:
    """Tests for exception handler in logout command (lines 341-344)."""

    @patch("cis_bench.cli.commands.auth.AuthManager")
    def test_logout_exception_handling(self, mock_auth, runner, tmp_path):
        """Should handle unexpected exceptions gracefully."""
        mock_path = tmp_path / "session.cookies"
        mock_path.touch()

        mock_auth.get_session_file_path.return_value = mock_path
        mock_auth.clear_saved_session.side_effect = RuntimeError("Permission denied")

        result = runner.invoke(cli, ["auth", "logout"])

        assert result.exit_code == 1
        assert "Logout failed" in result.output
        assert "Permission denied" in result.output

    @patch("cis_bench.cli.commands.auth.AuthManager")
    def test_logout_no_session_file(self, mock_auth, runner):
        """Should report no session to clear when none exists."""
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_auth.get_session_file_path.return_value = mock_path

        result = runner.invoke(cli, ["auth", "logout"])

        assert result.exit_code == 0
        assert "No saved session to clear" in result.output

    @patch("cis_bench.cli.commands.auth.AuthManager")
    def test_logout_clear_returns_false(self, mock_auth, runner, tmp_path):
        """Should handle case where clear_saved_session returns False."""
        mock_path = tmp_path / "session.cookies"
        mock_path.touch()

        mock_auth.get_session_file_path.return_value = mock_path
        mock_auth.clear_saved_session.return_value = False

        result = runner.invoke(cli, ["auth", "logout"])

        assert result.exit_code == 0
        assert "No session to clear" in result.output


class TestAuthHelpMessages:
    """Tests for auth command help messages."""

    def test_auth_group_help(self, runner):
        """Should show auth group help."""
        result = runner.invoke(cli, ["auth", "--help"])

        assert result.exit_code == 0
        assert "Manage authentication for CIS WorkBench" in result.output
        assert "login" in result.output
        assert "logout" in result.output
        assert "status" in result.output

    def test_auth_login_help(self, runner):
        """Should show auth login help."""
        result = runner.invoke(cli, ["auth", "login", "--help"])

        assert result.exit_code == 0
        assert "--browser" in result.output
        assert "--cookies" in result.output
        assert "--open" in result.output
        assert "--no-verify-ssl" in result.output

    def test_auth_status_help(self, runner):
        """Should show auth status help."""
        result = runner.invoke(cli, ["auth", "status", "--help"])

        assert result.exit_code == 0
        assert "--output-format" in result.output

    def test_auth_logout_help(self, runner):
        """Should show auth logout help."""
        result = runner.invoke(cli, ["auth", "logout", "--help"])

        assert result.exit_code == 0
        assert "Log out and clear saved session" in result.output
