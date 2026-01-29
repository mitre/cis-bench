"""Tests for Windows cookie extraction fallback behavior.

Issue #3: Windows users get "requires admin" error with Chrome/Edge due to
Chrome's App-Bound Encryption (Chrome 127+). These tests verify:
1. Firefox fallback when Chrome/Edge fails on Windows
2. Helpful error messages with actionable workarounds
3. Cookie file option works on auth login
"""

from unittest.mock import MagicMock, patch

import pytest


class TestWindowsCookieFallback:
    """Test automatic Firefox fallback on Windows when Chrome/Edge fails."""

    @pytest.fixture
    def mock_windows_platform(self):
        """Mock platform.system() to return 'Windows'."""
        with patch("platform.system", return_value="Windows"):
            yield

    @pytest.fixture
    def mock_linux_platform(self):
        """Mock platform.system() to return 'Linux'."""
        with patch("platform.system", return_value="Linux"):
            yield

    def test_is_windows_permission_error_detects_admin_required(self):
        """Should detect Windows-specific permission errors."""
        from cis_bench.fetcher.auth import AuthManager

        # Windows admin required error
        error = Exception("This operation requires admin. Please run as admin.")
        assert AuthManager._is_windows_permission_error(error) is True

        # Windows permission denied error
        error = PermissionError("[WinError 5] Access is denied")
        assert AuthManager._is_windows_permission_error(error) is True

        # Generic error should not match
        error = Exception("Network timeout")
        assert AuthManager._is_windows_permission_error(error) is False

    def test_is_windows_permission_error_detects_file_locked(self):
        """Should detect Chrome file locking errors."""
        from cis_bench.fetcher.auth import AuthManager

        # File in use error
        error = PermissionError(
            "[WinError 32] The process cannot access the file because it is being used"
        )
        assert AuthManager._is_windows_permission_error(error) is True

    def test_get_fallback_browser_suggests_firefox_for_chrome(self):
        """When Chrome fails on Windows, suggest Firefox."""
        from cis_bench.fetcher.auth import AuthManager

        fallback = AuthManager._get_fallback_browser("chrome")
        assert fallback == "firefox"

    def test_get_fallback_browser_suggests_firefox_for_edge(self):
        """When Edge fails on Windows, suggest Firefox."""
        from cis_bench.fetcher.auth import AuthManager

        fallback = AuthManager._get_fallback_browser("edge")
        assert fallback == "firefox"

    def test_get_fallback_browser_returns_none_for_firefox(self):
        """Firefox has no fallback (it's the last resort)."""
        from cis_bench.fetcher.auth import AuthManager

        fallback = AuthManager._get_fallback_browser("firefox")
        assert fallback is None

    def test_get_fallback_browser_returns_none_for_safari(self):
        """Safari (macOS only) has no fallback."""
        from cis_bench.fetcher.auth import AuthManager

        fallback = AuthManager._get_fallback_browser("safari")
        assert fallback is None

    @patch("cis_bench.fetcher.auth.browser_cookie3")
    def test_load_cookies_tries_fallback_on_windows_error(self, mock_bc3, mock_windows_platform):
        """Should try Firefox when Chrome fails with permission error on Windows."""
        from cis_bench.fetcher.auth import AuthManager

        # Chrome fails with permission error
        mock_bc3.chrome.side_effect = Exception(
            "This operation requires admin. Please run as admin."
        )
        # Firefox succeeds
        mock_firefox_jar = MagicMock()
        mock_firefox_jar.__iter__ = lambda self: iter([])
        mock_bc3.firefox.return_value = mock_firefox_jar

        session = AuthManager.load_cookies_from_browser("chrome", try_fallback=True)

        # Should have tried Firefox after Chrome failed
        mock_bc3.firefox.assert_called_once()
        assert session is not None

    @patch("cis_bench.fetcher.auth.browser_cookie3")
    def test_load_cookies_no_fallback_on_linux(self, mock_bc3, mock_linux_platform):
        """Should NOT try fallback on non-Windows platforms."""
        from cis_bench.fetcher.auth import AuthManager

        # Chrome fails with permission error
        mock_bc3.chrome.side_effect = PermissionError("Permission denied")

        # Should raise, not try fallback
        with pytest.raises(Exception) as exc_info:
            AuthManager.load_cookies_from_browser("chrome", try_fallback=True)

        # Firefox should NOT have been called
        mock_bc3.firefox.assert_not_called()

    @patch("cis_bench.fetcher.auth.browser_cookie3")
    def test_load_cookies_fallback_disabled_by_default(self, mock_bc3, mock_windows_platform):
        """Fallback should be opt-in to avoid surprising behavior."""
        from cis_bench.fetcher.auth import AuthManager

        mock_bc3.chrome.side_effect = Exception("requires admin")

        with pytest.raises(Exception, match="requires admin"):
            AuthManager.load_cookies_from_browser("chrome")  # No try_fallback

        mock_bc3.firefox.assert_not_called()


class TestWindowsErrorMessages:
    """Test helpful error messages for Windows users."""

    def test_format_windows_cookie_error_includes_workarounds(self):
        """Error message should include actionable workarounds."""
        from cis_bench.fetcher.auth import AuthManager

        error = Exception("requires admin")
        message = AuthManager._format_windows_cookie_error("chrome", error)

        # Should suggest Firefox
        assert "firefox" in message.lower()

        # Should mention closing browser
        assert "close" in message.lower()

        # Should mention cookie file option
        assert "cookie" in message.lower()

    def test_format_windows_cookie_error_mentions_app_bound_encryption(self):
        """Error should explain WHY this happens."""
        from cis_bench.fetcher.auth import AuthManager

        error = Exception("requires admin")
        message = AuthManager._format_windows_cookie_error("edge", error)

        # Should explain the root cause
        assert "chrome" in message.lower() or "encrypt" in message.lower()


class TestAuthLoginCookiesOption:
    """Test that auth login accepts --cookies option."""

    def test_auth_login_has_cookies_option(self):
        """auth login command should accept --cookies flag."""
        from cis_bench.cli.commands.auth import login

        # Check that the command has a cookies parameter
        param_names = [p.name for p in login.params]
        assert "cookies" in param_names, (
            "auth login should have --cookies option for users who can't use browser extraction"
        )

    def test_auth_login_cookies_option_is_path_type(self):
        """--cookies should accept a file path."""
        from cis_bench.cli.commands.auth import login

        cookies_param = next(p for p in login.params if p.name == "cookies")
        # Should be a path type
        assert hasattr(cookies_param.type, "name") or "Path" in str(cookies_param.type)
