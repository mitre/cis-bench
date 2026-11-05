"""Unit tests for auth commands (login, status, logout)."""

from unittest.mock import Mock

import pytest
from click.testing import CliRunner

from cis_bench.cli.app import cli


@pytest.fixture
def runner():
    """Create Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def session_path(data_dir):
    """The saved session's file in this test's data folder (CIS_BENCH_DATA_DIR)."""
    return data_dir / "session.cookies"


@pytest.fixture
def mock_auth(auth_manager_class):
    """The AuthManager instance the command builds; its methods are mocks."""
    return auth_manager_class.return_value


# ============================================================================
# Tests: Auth Login Command
# ============================================================================


class TestAuthLogin:
    """Test auth login command."""

    def test_login_extracts_and_saves_session(self, runner, mock_auth, monkeypatch):
        """Login extracts cookies from browser and saves session."""
        monkeypatch.setenv("CIS_BENCH_VERIFY_SSL", "false")

        # Mock session
        mock_session = Mock()
        mock_session.cookies = [Mock(), Mock(), Mock()]  # 3 cookies
        mock_auth.load_cookies_from_browser.return_value = mock_session
        mock_auth.validate_session.return_value = True

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome"])

        assert result.exit_code == 0
        assert "Login successful" in result.output
        assert "Extracted 3 cookies" in result.output
        assert "Session is valid" in result.output
        assert mock_auth.save_session.called

    def test_login_fails_with_invalid_session(self, runner, mock_auth, monkeypatch):
        """Login fails if session validation fails."""
        monkeypatch.setenv("CIS_BENCH_VERIFY_SSL", "false")

        mock_session = Mock()
        mock_session.cookies = [Mock()]
        mock_auth.load_cookies_from_browser.return_value = mock_session
        mock_auth.validate_session.return_value = False  # Invalid

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome"])

        assert result.exit_code == 1
        assert "Session validation failed" in result.output
        assert not mock_auth.save_session.called

    def test_login_with_no_verify_ssl_flag(
        self, runner, auth_manager_class, mock_auth, monkeypatch
    ):
        """Login with --no-verify-ssl flag."""
        monkeypatch.setenv("CIS_BENCH_VERIFY_SSL", "true")  # Default

        mock_session = Mock()
        mock_session.cookies = [Mock()]
        mock_auth.load_cookies_from_browser.return_value = mock_session
        mock_auth.validate_session.return_value = True

        result = runner.invoke(cli, ["auth", "login", "--browser", "chrome", "--no-verify-ssl"])

        assert result.exit_code == 0
        # Verify SSL was disabled (verify_ssl=False reaches the manager that loads the cookies)
        assert auth_manager_class.call_args.kwargs["verify_ssl"] is False
        mock_auth.load_cookies_from_browser.assert_called_once_with("chrome", try_fallback=True)


# ============================================================================
# Tests: Auth Status Command
# ============================================================================


class TestAuthStatus:
    """Test auth status command."""

    def test_status_shows_logged_in(self, runner, mock_auth, session_path, monkeypatch):
        """Status shows logged in when session is valid."""
        session_path.touch()
        monkeypatch.setenv("CIS_BENCH_VERIFY_SSL", "false")

        mock_session = Mock()
        mock_session.cookies = [Mock(), Mock()]
        mock_auth.load_saved_session.return_value = mock_session
        mock_auth.validate_session.return_value = True

        result = runner.invoke(cli, ["auth", "status"])

        assert result.exit_code == 0
        assert "Logged in" in result.output
        assert "Session is valid" in result.output

    def test_status_shows_not_logged_in(self, runner, mock_auth, tmp_path, monkeypatch):
        """Status shows not logged in when no session file."""
        monkeypatch.setenv("CIS_BENCH_DATA_DIR", str(tmp_path / "nonexistent"))

        result = runner.invoke(cli, ["auth", "status"])

        assert result.exit_code == 1
        assert "Not logged in" in result.output
        assert "auth login" in result.output

    def test_status_json_output(self, runner, mock_auth, session_path, monkeypatch):
        """Status outputs JSON format."""
        session_path.touch()
        monkeypatch.setenv("CIS_BENCH_VERIFY_SSL", "false")

        mock_session = Mock()
        mock_session.cookies = [Mock(), Mock()]
        mock_auth.load_saved_session.return_value = mock_session
        mock_auth.validate_session.return_value = True

        result = runner.invoke(cli, ["auth", "status", "--output-format", "json"])

        assert result.exit_code == 0
        assert '"logged_in": true' in result.output
        assert '"cookie_count": 2' in result.output


# ============================================================================
# Tests: Auth Logout Command
# ============================================================================


class TestAuthLogout:
    """Test auth logout command."""

    def test_logout_clears_session(self, runner, mock_auth, session_path):
        """Logout clears saved session."""
        session_path.touch()
        mock_auth.clear_saved_session.return_value = True

        result = runner.invoke(cli, ["auth", "logout"])

        assert result.exit_code == 0
        assert "Logged out successfully" in result.output
        assert mock_auth.clear_saved_session.called

    def test_logout_when_not_logged_in(self, runner, mock_auth, session_path):
        """Logout when no session exists."""
        assert not session_path.exists()

        result = runner.invoke(cli, ["auth", "logout"])

        assert result.exit_code == 0
        assert "No saved session" in result.output
