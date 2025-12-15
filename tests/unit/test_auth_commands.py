"""Unit tests for auth commands (login, status, logout)."""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from cis_bench.cli.app import cli


@pytest.fixture
def runner():
    """Create Click CLI test runner."""
    return CliRunner()


# ============================================================================
# Tests: Auth Login Command
# ============================================================================


class TestAuthLogin:
    """Test auth login command."""

    def test_login_extracts_and_saves_session(self, runner, tmp_path):
        """Login extracts cookies from browser and saves session."""
        session_path = tmp_path / "session.cookies"

        with patch("cis_bench.cli.commands.auth.AuthManager") as mock_auth_class:
            with patch("cis_bench.cli.commands.auth.Config") as mock_config:
                mock_config.get_verify_ssl.return_value = False

                # Mock session
                mock_session = Mock()
                mock_session.cookies = [Mock(), Mock(), Mock()]  # 3 cookies
                mock_auth_class.load_cookies_from_browser.return_value = mock_session
                mock_auth_class.validate_session.return_value = True
                mock_auth_class.get_session_file_path.return_value = session_path

                result = runner.invoke(cli, ["auth", "login", "--browser", "chrome"])

                assert result.exit_code == 0
                assert "Login successful" in result.output
                assert "Extracted 3 cookies" in result.output
                assert "Session is valid" in result.output
                assert mock_auth_class.save_session.called

    def test_login_fails_with_invalid_session(self, runner, tmp_path):
        """Login fails if session validation fails."""
        with patch("cis_bench.cli.commands.auth.AuthManager") as mock_auth_class:
            with patch("cis_bench.cli.commands.auth.Config") as mock_config:
                mock_config.get_verify_ssl.return_value = False

                mock_session = Mock()
                mock_session.cookies = [Mock()]
                mock_auth_class.load_cookies_from_browser.return_value = mock_session
                mock_auth_class.validate_session.return_value = False  # Invalid

                result = runner.invoke(cli, ["auth", "login", "--browser", "chrome"])

                assert result.exit_code == 1
                assert "Session validation failed" in result.output
                assert not mock_auth_class.save_session.called

    def test_login_with_no_verify_ssl_flag(self, runner, tmp_path):
        """Login with --no-verify-ssl flag."""
        session_path = tmp_path / "session.cookies"

        with patch("cis_bench.cli.commands.auth.AuthManager") as mock_auth_class:
            with patch("cis_bench.cli.commands.auth.Config") as mock_config:
                mock_config.get_verify_ssl.return_value = True  # Default

                mock_session = Mock()
                mock_session.cookies = [Mock()]
                mock_auth_class.load_cookies_from_browser.return_value = mock_session
                mock_auth_class.validate_session.return_value = True
                mock_auth_class.get_session_file_path.return_value = session_path

                result = runner.invoke(
                    cli, ["auth", "login", "--browser", "chrome", "--no-verify-ssl"]
                )

                assert result.exit_code == 0
                # Verify SSL was disabled (verify_ssl=False passed)
                call_args = mock_auth_class.load_cookies_from_browser.call_args
                assert call_args.kwargs["verify_ssl"] is False


# ============================================================================
# Tests: Auth Status Command
# ============================================================================


class TestAuthStatus:
    """Test auth status command."""

    def test_status_shows_logged_in(self, runner, tmp_path):
        """Status shows logged in when session is valid."""
        session_path = tmp_path / "session.cookies"
        session_path.touch()

        with patch("cis_bench.cli.commands.auth.AuthManager") as mock_auth_class:
            with patch("cis_bench.cli.commands.auth.Config") as mock_config:
                mock_config.get_verify_ssl.return_value = False

                mock_session = Mock()
                mock_session.cookies = [Mock(), Mock()]
                mock_auth_class.get_session_file_path.return_value = session_path
                mock_auth_class.load_saved_session.return_value = mock_session
                mock_auth_class.validate_session.return_value = True

                result = runner.invoke(cli, ["auth", "status"])

                assert result.exit_code == 0
                assert "Logged in" in result.output
                assert "Session is valid" in result.output

    def test_status_shows_not_logged_in(self, runner, tmp_path):
        """Status shows not logged in when no session file."""
        session_path = tmp_path / "nonexistent" / "session.cookies"

        with patch("cis_bench.cli.commands.auth.AuthManager") as mock_auth_class:
            mock_auth_class.get_session_file_path.return_value = session_path

            result = runner.invoke(cli, ["auth", "status"])

            assert result.exit_code == 1
            assert "Not logged in" in result.output
            assert "auth login" in result.output

    def test_status_json_output(self, runner, tmp_path):
        """Status outputs JSON format."""
        session_path = tmp_path / "session.cookies"
        session_path.touch()

        with patch("cis_bench.cli.commands.auth.AuthManager") as mock_auth_class:
            with patch("cis_bench.cli.commands.auth.Config") as mock_config:
                mock_config.get_verify_ssl.return_value = False

                mock_session = Mock()
                mock_session.cookies = [Mock(), Mock()]
                mock_auth_class.get_session_file_path.return_value = session_path
                mock_auth_class.load_saved_session.return_value = mock_session
                mock_auth_class.validate_session.return_value = True

                result = runner.invoke(cli, ["auth", "status", "--output-format", "json"])

                assert result.exit_code == 0
                assert '"logged_in": true' in result.output
                assert '"cookie_count": 2' in result.output


# ============================================================================
# Tests: Auth Logout Command
# ============================================================================


class TestAuthLogout:
    """Test auth logout command."""

    def test_logout_clears_session(self, runner, tmp_path):
        """Logout clears saved session."""
        session_path = tmp_path / "session.cookies"
        session_path.touch()

        with patch("cis_bench.cli.commands.auth.AuthManager") as mock_auth_class:
            mock_auth_class.get_session_file_path.return_value = session_path
            mock_auth_class.clear_saved_session.return_value = True

            result = runner.invoke(cli, ["auth", "logout"])

            assert result.exit_code == 0
            assert "Logged out successfully" in result.output
            assert mock_auth_class.clear_saved_session.called

    def test_logout_when_not_logged_in(self, runner, tmp_path):
        """Logout when no session exists."""
        session_path = tmp_path / "nonexistent.cookies"

        with patch("cis_bench.cli.commands.auth.AuthManager") as mock_auth_class:
            mock_auth_class.get_session_file_path.return_value = session_path

            result = runner.invoke(cli, ["auth", "logout"])

            assert result.exit_code == 0
            assert "No saved session" in result.output
