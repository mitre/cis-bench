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

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from cis_bench.cli.app import cli
from cis_bench.exceptions import TLSVerificationError


@pytest.fixture
def runner():
    """Create Click CLI test runner."""
    return CliRunner()


@pytest.fixture(autouse=True)
def session_file(data_dir):
    """Where this test's saved session lives: session.cookies in its own data folder."""
    return data_dir / "session.cookies"


@pytest.fixture
def mock_auth(auth_manager_class):
    """The AuthManager instance the command builds; its methods are mocks."""
    return auth_manager_class.return_value


@pytest.fixture
def mock_auth_manager(mock_auth):
    """The AuthManager instance the command builds; its methods are mocks."""
    return mock_auth


class TestAuthLoginCommand:
    """Tests for 'auth login' command."""

    def test_login_without_flags_reads_cookies_from_the_browser_setting(
        self, mock_auth_manager, runner, monkeypatch
    ):
        """auth login alone uses CIS_BENCH_BROWSER (chrome unless set); --browser overrides it."""
        monkeypatch.setenv("CIS_BENCH_BROWSER", "firefox")
        mock_session = MagicMock()
        mock_session.cookies = [MagicMock()]
        mock_auth_manager.load_cookies_from_browser.return_value = mock_session
        mock_auth_manager.validate_session.return_value = True
        mock_auth_manager._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login"])

        assert result.exit_code == 0, result.output
        mock_auth_manager.load_cookies_from_browser.assert_called_once_with(
            "firefox", try_fallback=True
        )

    def test_login_with_invalid_browser(self, runner):
        """auth login should reject invalid browser choice."""
        result = runner.invoke(cli, ["auth", "login", "--browser", "invalid"])

        assert result.exit_code != 0
        assert "Invalid value" in result.output

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

    def test_login_no_cookies_found(self, mock_auth_manager, runner):
        """auth login should fail if no cookies extracted."""
        mock_session = MagicMock()
        mock_session.cookies = []  # Empty cookies
        mock_auth_manager.load_cookies_from_browser.return_value = mock_session
        mock_auth_manager._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "firefox"])

        assert result.exit_code == 1
        assert "No cookies found" in result.output

    def test_login_saves_session_on_success(self, mock_auth_manager, runner, tmp_path, monkeypatch):
        """auth login should save session after successful validation."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("CIS_BENCH_HOME", "s[/p]")
        mock_session = MagicMock()
        mock_session.cookies = [MagicMock()]
        mock_auth_manager.load_cookies_from_browser.return_value = mock_session
        mock_auth_manager.validate_session.return_value = True
        mock_auth_manager._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "firefox"])

        # Should have saved session
        mock_auth_manager.save_session.assert_called_once_with(mock_session)
        assert "Session saved to s[/p]/session.cookies" in result.output

    def test_login_windows_permission_error_shows_help(self, mock_auth_manager, runner):
        """auth login should show helpful message on Windows permission error."""
        mock_auth_manager.load_cookies_from_browser.side_effect = Exception(
            "This operation requires admin [/e]"
        )
        mock_auth_manager._is_windows_permission_error.return_value = True
        mock_auth_manager._format_windows_cookie_error.return_value = (
            "Use Firefox [/f] or --cookies option"
        )

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome"])

        assert result.exit_code == 1
        assert result.output.count("This operation requires admin [/e]") == 1
        assert result.output.count("Use Firefox [/f] or --cookies option") == 1
        # Should show Windows-specific help
        assert "firefox" in result.output.lower() or "cookie" in result.output.lower()


class TestAuthLogoutCommand:
    """Tests for 'auth logout' command."""

    def test_logout_clears_session(self, mock_auth_manager, runner, session_file):
        """auth logout should clear saved session."""
        session_file.touch()
        mock_auth_manager.clear_saved_session.return_value = True

        result = runner.invoke(cli, ["auth", "logout"])

        mock_auth_manager.clear_saved_session.assert_called_once()
        assert result.exit_code == 0

    def test_logout_no_session(self, mock_auth_manager, runner, session_file):
        """auth logout should handle case when no session exists."""
        session_file.touch()
        mock_auth_manager.clear_saved_session.return_value = False

        result = runner.invoke(cli, ["auth", "logout"])

        assert result.exit_code == 0
        assert "No session to clear" in result.output or "no session" in result.output.lower()


class TestAuthStatusCommand:
    """Tests for 'auth status' command."""

    def test_status_with_valid_session(self, mock_auth_manager, runner, session_file):
        """auth status should show logged in when session valid."""
        session_file.touch()
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

    def test_status_with_invalid_session(self, mock_auth_manager, runner, session_file):
        """auth status should show logged out when session invalid."""
        session_file.touch()
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

    def test_status_with_workbench_unreachable_does_not_say_expired(
        self, mock_auth_manager, runner, session_file
    ):
        """A network failure leaves the session's state unknown; status says so and exits 1."""
        from cis_bench.exceptions import FetchError

        session_file.touch()
        mock_auth_manager.load_saved_session.return_value = MagicMock()
        mock_auth_manager.validate_session.side_effect = FetchError(
            "https://workbench.cisecurity.org/benchmarks", 3, "Read timed out"
        )

        result = runner.invoke(cli, ["auth", "status"])

        assert result.exit_code == 1
        assert "Could not reach WorkBench" in result.output
        assert "saved session was kept" in result.output
        assert "expired" not in result.output.lower()
        assert "no longer valid" not in result.output

    def test_status_no_session(self, mock_auth_manager, runner, session_file):
        """auth status should show not logged in when no saved session."""
        session_file.touch()
        mock_auth_manager.load_saved_session.return_value = None

        result = runner.invoke(cli, ["auth", "status"])

        assert (
            "not logged in" in result.output.lower()
            or "no saved session" in result.output.lower()
            or "✗" in result.output
        )


class TestAuthStatusMachineOutput:
    """-o json and -o yaml put only the status document on stdout, and the exit code says
    whether the saved session is valid, as in table output."""

    def _saved_session(self, mock_auth, session_file, *, valid: bool):
        session_file.touch()
        session = MagicMock()
        session.cookies = [MagicMock(), MagicMock()]
        mock_auth.load_saved_session.return_value = session
        mock_auth.validate_session.return_value = valid

    @pytest.mark.parametrize(("valid", "exit_code"), [(True, 0), (False, 1)])
    def test_json_is_the_whole_stdout_and_the_exit_code_follows_the_session(
        self, mock_auth, runner, session_file, valid, exit_code
    ):
        import json

        self._saved_session(mock_auth, session_file, valid=valid)

        result = runner.invoke(cli, ["auth", "status", "--output-format", "json"])

        assert result.exit_code == exit_code, result.output
        assert json.loads(result.stdout) == {
            "logged_in": valid,
            "session_file": str(session_file),
            "cookie_count": 2,
            "ssl_verify": True,
        }

    def test_yaml_is_the_whole_stdout(self, mock_auth, runner, session_file):
        import yaml

        self._saved_session(mock_auth, session_file, valid=False)

        result = runner.invoke(cli, ["auth", "status", "-o", "yaml"])

        assert result.exit_code == 1, result.output
        assert yaml.safe_load(result.stdout)["logged_in"] is False


# =============================================================================
# Additional tests for uncovered lines
# =============================================================================


class TestAuthLoginOpenFlag:
    """Tests for 'auth login --open' flag behavior (lines 97-149).

    These tests cover platform-specific browser opening code paths.
    Note: platform module is imported inside the function, so we patch it globally.
    """

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
        mock_auth._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome", "--open"], input="\n")

        # Should call subprocess with open command
        mock_subprocess.assert_called()
        call_args = mock_subprocess.call_args[0][0]
        assert "/usr/bin/open" in call_args
        assert "-a" in call_args
        assert "Google Chrome" in call_args
        assert "https://workbench.cisecurity.org/" in call_args

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
        mock_auth._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome", "--open"], input="\n")

        mock_subprocess.assert_called()
        call_args = mock_subprocess.call_args[0][0]
        assert "xdg-open" in str(call_args)

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
        mock_auth._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome", "--open"], input="\n")

        mock_webbrowser.assert_called_once_with("https://workbench.cisecurity.org/")

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
        mock_auth._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome", "--open"], input="\n")

        mock_webbrowser.assert_called_once_with("https://workbench.cisecurity.org/")

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
        mock_auth._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome", "--open"], input="\n")

        # Should show error message but continue
        assert "Could not open browser" in result.output
        assert "Please open manually" in result.output

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
        mock_auth._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome", "--open"], input="\n")

        # Should show error message but continue
        assert "Could not open browser" in result.output
        assert "Please open manually" in result.output

    @patch("platform.system")
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_login_open_subprocess_failure(
        self, mock_which, mock_subprocess, mock_platform, mock_auth, runner, tmp_path
    ):
        """Should handle subprocess failure gracefully."""
        mock_platform.return_value = "Darwin"
        mock_which.return_value = "/usr/bin/open"
        mock_subprocess.side_effect = Exception("Browser launch failed [/e]")

        mock_session = MagicMock()
        mock_session.cookies = [MagicMock()]
        mock_auth.load_cookies_from_browser.return_value = mock_session
        mock_auth.validate_session.return_value = True
        mock_auth.save_session.return_value = None
        mock_auth._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome", "--open"], input="\n")

        # Should continue after browser open failure
        assert result.output.count("Could not open browser: Browser launch failed [/e]") == 1

    @patch("platform.system", return_value="Windows")
    @patch("webbrowser.open")
    def test_login_open_uses_configured_workbench_base_url(
        self, mock_webbrowser, mock_platform, mock_auth, runner, tmp_path, monkeypatch
    ):
        """auth login --open opens CIS_BENCH_WORKBENCH_URL when configured."""
        monkeypatch.setenv("CIS_BENCH_WORKBENCH_URL", "https://workbench-staging.cisecurity.org")
        mock_session = MagicMock()
        mock_session.cookies = [MagicMock()]
        mock_auth.load_cookies_from_browser.return_value = mock_session
        mock_auth.validate_session.return_value = True
        mock_auth._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome", "--open"], input="\n")

        assert result.exit_code == 0
        mock_webbrowser.assert_called_once_with("https://workbench-staging.cisecurity.org/")


class TestAuthLoginCookieFileErrors:
    """Tests for cookie file loading error handling (lines 160-162)."""

    def test_login_cookie_file_load_failure(self, mock_auth, runner, working_dir):
        """Should handle cookie file loading errors gracefully."""
        cookie_file = Path("c[/p]") / "cookies.txt"
        cookie_file.parent.mkdir(parents=True)  # "c[" / "p]"
        cookie_file.write_text("invalid content\n")

        mock_auth.load_cookies_from_file.side_effect = Exception("Invalid cookie format [/e]")

        result = runner.invoke(cli, ["auth", "login", "--cookies", str(cookie_file)])

        assert result.exit_code == 1
        assert "Loading cookies from c[/p]/cookies.txt" in result.output
        assert result.output.count("Failed to load cookies: Invalid cookie format [/e]") == 1

    def test_login_cookie_file_permission_error(self, mock_auth, runner, tmp_path):
        """Should handle cookie file permission errors."""
        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text("content\n")

        mock_auth.load_cookies_from_file.side_effect = PermissionError("Access denied")

        result = runner.invoke(cli, ["auth", "login", "--cookies", str(cookie_file)])

        assert result.exit_code == 1
        assert "Failed to load cookies" in result.output


class TestAuthLoginTLSFailureReporting:
    """An invalid session and a TLS trust failure are different problems and get different output."""

    def test_login_invalid_session_does_not_suggest_disabling_tls(
        self, mock_auth, runner, monkeypatch
    ):
        """A session WorkBench rejected is a login problem; TLS was fine, so no TLS tip."""
        monkeypatch.setenv("CIS_BENCH_VERIFY_SSL", "true")

        mock_session = MagicMock()
        mock_session.cookies = [MagicMock()]
        mock_auth.load_cookies_from_browser.return_value = mock_session
        mock_auth.validate_session.return_value = False
        mock_auth._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome"])

        assert result.exit_code == 1
        assert "Session validation failed" in result.output
        assert "--no-verify-ssl" not in result.output
        assert "CIS_BENCH_VERIFY_SSL=false" not in result.output

    def test_login_reports_an_unreachable_workbench_as_such(self, mock_auth, runner):
        from cis_bench.exceptions import FetchError

        mock_session = MagicMock()
        mock_session.cookies = [MagicMock()]
        mock_auth.load_cookies_from_browser.return_value = mock_session
        mock_auth.validate_session.side_effect = FetchError(
            "https://workbench.cisecurity.org/benchmarks", 3, "Read timed out"
        )
        mock_auth._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome"])

        assert result.exit_code == 1
        assert "Could not reach WorkBench" in result.output
        assert "Login failed" not in result.output
        mock_auth.save_session.assert_not_called()

    def test_login_reports_tls_failure_with_remediation(self, mock_auth, runner, monkeypatch):
        """A certificate trust failure surfaces its own message and remediation, exit 1."""
        monkeypatch.setenv("CIS_BENCH_VERIFY_SSL", "true")

        mock_session = MagicMock()
        mock_session.cookies = [MagicMock()]
        mock_auth.load_cookies_from_browser.return_value = mock_session
        mock_auth.validate_session.side_effect = TLSVerificationError(
            "TLS certificate verification failed for workbench.cisecurity.org: "
            "unable to get local issuer certificate. If a proxy re-signs HTTPS traffic, "
            "point REQUESTS_CA_BUNDLE at its CA bundle; to skip verification entirely "
            "set CIS_BENCH_VERIFY_SSL=false."
        )
        mock_auth._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome"])

        assert result.exit_code == 1
        assert "TLS certificate verification failed for workbench.cisecurity.org" in result.output
        assert "REQUESTS_CA_BUNDLE" in result.output
        assert "Session validation failed" not in result.output
        assert "Login failed" not in result.output


class TestAuthLoginExceptionHandlers:
    """Tests for ValueError and Exception handlers in login (lines 224-229)."""

    def test_login_value_error_handling(self, mock_auth, runner):
        """Should handle ValueError gracefully (line 224-225)."""
        mock_auth.load_cookies_from_browser.side_effect = ValueError("Invalid browser type [/e]")
        mock_auth._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome"])

        assert result.exit_code == 1
        assert result.output.count("Invalid browser type [/e]") == 1

    def test_login_generic_exception_handling(self, mock_auth, runner):
        """An unexpected login failure prints one line, verbatim, without a traceback."""
        mock_auth.load_cookies_from_browser.side_effect = RuntimeError("Unexpected error [/e]")
        mock_auth._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome"])

        assert result.exit_code == 1
        assert result.output.count("Login failed: Unexpected error [/e]") == 1
        assert "Traceback" not in result.output

    def test_login_failure_traceback_is_written_with_verbose(self, mock_auth, runner):
        mock_auth.load_cookies_from_browser.side_effect = RuntimeError("Unexpected error")
        mock_auth._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["--verbose", "auth", "login", "--browser", "chrome"])

        assert result.exit_code == 1
        assert "Traceback" in result.output


class TestAuthLoginWindowsPermissionReRaise:
    """Tests for Windows permission error re-raise path (line 181)."""

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

    def test_status_exception_handling(self, auth_manager_class, runner):
        """Should handle unexpected exceptions gracefully."""
        auth_manager_class.side_effect = RuntimeError("Unexpected filesystem error [/e]")

        result = runner.invoke(cli, ["auth", "status"])

        assert result.exit_code == 1
        assert result.output.count("Status check failed: Unexpected filesystem error [/e]") == 1
        assert "Traceback" not in result.output

    def test_status_no_session_file(self, mock_auth, runner, tmp_path, monkeypatch):
        """Should report not logged in when no session file exists."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("CIS_BENCH_HOME", "s[/p]")

        result = runner.invoke(cli, ["auth", "status"])

        assert result.exit_code == 1
        assert "Not logged in" in result.output
        assert "No saved session found at s[/p]/session.cookies" in result.output
        assert "cis-bench auth login" in result.output

    def test_status_failed_to_load_session(self, mock_auth, runner, session_file):
        """Should report error when session file exists but can't be loaded."""
        session_file.touch()

        mock_auth.load_saved_session.return_value = None

        result = runner.invoke(cli, ["auth", "status"])

        assert result.exit_code == 1
        assert "Could not load saved session" in result.output

    def test_status_json_output(self, mock_auth, runner, session_file, monkeypatch):
        """Should output JSON when --output-format json specified."""
        monkeypatch.setenv("CIS_BENCH_VERIFY_SSL", "true")
        session_file.touch()

        mock_session = MagicMock()
        mock_session.cookies = [MagicMock()]

        mock_auth.load_saved_session.return_value = mock_session
        mock_auth.validate_session.return_value = True

        result = runner.invoke(cli, ["auth", "status", "--output-format", "json"])

        # JSON output includes logged_in field
        assert "logged_in" in result.output


class TestAuthLogoutExceptionHandler:
    """Tests for exception handler in logout command (lines 341-344)."""

    def test_logout_exception_handling(self, mock_auth, runner, session_file):
        """Should handle unexpected exceptions gracefully."""
        session_file.touch()

        mock_auth.clear_saved_session.side_effect = RuntimeError("Permission denied [/e]")

        result = runner.invoke(cli, ["auth", "logout"])

        assert result.exit_code == 1
        assert result.output.count("Logout failed: Permission denied [/e]") == 1
        assert "Traceback" not in result.output

    def test_logout_no_session_file(self, mock_auth, runner, tmp_path, monkeypatch):
        """Should report no session to clear when none exists."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("CIS_BENCH_HOME", "s[/p]")

        result = runner.invoke(cli, ["auth", "logout"])

        assert result.exit_code == 0
        assert "No saved session to clear" in result.output
        assert "No session file at s[/p]/session.cookies" in result.output

    def test_logout_clear_returns_false(self, mock_auth, runner, session_file):
        """Should handle case where clear_saved_session returns False."""
        session_file.touch()

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


class TestVerifiedTLSByDefault:
    """auth login and auth status verify certificates unless CIS_BENCH_VERIFY_SSL opts out."""

    def test_login_defaults_to_verified_tls(
        self, auth_manager_class, mock_auth, runner, monkeypatch
    ):
        monkeypatch.delenv("CIS_BENCH_VERIFY_SSL", raising=False)
        mock_session = MagicMock()
        mock_session.cookies = [MagicMock()]
        mock_auth.load_cookies_from_browser.return_value = mock_session
        mock_auth.validate_session.return_value = True

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome"])

        assert result.exit_code == 0, result.output
        assert auth_manager_class.call_args.kwargs["verify_ssl"] is True
        mock_auth.load_cookies_from_browser.assert_called_once_with("chrome", try_fallback=True)
        mock_auth.validate_session.assert_called_once_with(mock_session)

    def test_login_no_verify_ssl_flag_overrides_default(
        self, auth_manager_class, mock_auth, runner, monkeypatch
    ):
        monkeypatch.delenv("CIS_BENCH_VERIFY_SSL", raising=False)
        mock_session = MagicMock()
        mock_session.cookies = [MagicMock()]
        mock_auth.load_cookies_from_browser.return_value = mock_session
        mock_auth.validate_session.return_value = True

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome", "--no-verify-ssl"])

        assert result.exit_code == 0, result.output
        assert auth_manager_class.call_args.kwargs["verify_ssl"] is False
        mock_auth.load_cookies_from_browser.assert_called_once_with("chrome", try_fallback=True)
        mock_auth.validate_session.assert_called_once_with(mock_session)

    def test_status_defaults_to_verified_tls(
        self, auth_manager_class, mock_auth, runner, session_file, monkeypatch
    ):
        monkeypatch.delenv("CIS_BENCH_VERIFY_SSL", raising=False)
        session_file.touch()
        mock_session = MagicMock()
        mock_session.cookies = [MagicMock()]
        mock_auth.load_saved_session.return_value = mock_session
        mock_auth.validate_session.return_value = True

        result = runner.invoke(cli, ["auth", "status", "--output-format", "json"])

        assert result.exit_code == 0, result.output
        assert auth_manager_class.call_args.kwargs["verify_ssl"] is True
        mock_auth.validate_session.assert_called_once_with(mock_session)
        assert '"ssl_verify": true' in result.output


class TestCookieCountsAgreeWithTheNumber:
    """Every message that counts cookies reads "1 cookie" or "N cookies"."""

    @pytest.fixture
    def session_with(self):
        def make(count):
            session = MagicMock()
            session.cookies = [MagicMock() for _ in range(count)]
            return session

        return make

    @pytest.mark.parametrize(("count", "noun"), [(1, "cookie"), (2, "cookies")])
    def test_loading_a_cookie_file(self, mock_auth, runner, tmp_path, session_with, count, noun):
        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text("# Netscape HTTP Cookie File\n")
        mock_auth.load_cookies_from_file.return_value = session_with(count)
        mock_auth.validate_session.return_value = True

        result = runner.invoke(cli, ["auth", "login", "--cookies", str(cookie_file)])

        assert f"Loaded {count} {noun} from file\n" in result.output

    @pytest.mark.parametrize(("count", "noun"), [(1, "cookie"), (2, "cookies")])
    def test_extracting_from_a_browser(self, mock_auth, runner, session_with, count, noun):
        mock_auth.load_cookies_from_browser.return_value = session_with(count)
        mock_auth.validate_session.return_value = True
        mock_auth._is_windows_permission_error.return_value = False

        result = runner.invoke(cli, ["auth", "login", "--browser", "firefox"])

        assert f"Extracted {count} {noun} from firefox\n" in result.output

    @pytest.mark.parametrize(("count", "noun"), [(1, "cookie"), (2, "cookies")])
    def test_status_of_a_saved_session(
        self, mock_auth, runner, session_file, session_with, count, noun
    ):
        session_file.touch()
        mock_auth.load_saved_session.return_value = session_with(count)
        mock_auth.validate_session.return_value = True

        result = runner.invoke(cli, ["auth", "status"])

        assert f"Found saved session with {count} {noun}\n" in result.output
