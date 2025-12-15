"""Unit tests for session persistence in AuthManager."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from cis_bench.fetcher.auth import AuthManager


@pytest.fixture
def temp_session_path(tmp_path):
    """Create temporary session file path."""
    return tmp_path / "session.cookies"


# ============================================================================
# Tests: Save Session
# ============================================================================


class TestSaveSession:
    """Test session saving functionality."""

    def test_save_session_creates_file(self, temp_session_path):
        """save_session creates cookie file."""
        session = requests.Session()
        session.cookies.set("test_cookie", "test_value", domain="example.com")

        with patch("cis_bench.fetcher.auth.AuthManager.get_session_file_path") as mock_path:
            mock_path.return_value = temp_session_path

            AuthManager.save_session(session)

            assert temp_session_path.exists()

    def test_save_session_creates_parent_directory(self, tmp_path):
        """save_session creates parent directories if needed."""
        session_path = tmp_path / "subdir" / "another" / "session.cookies"
        session = requests.Session()
        session.cookies.set("test", "value")

        with patch("cis_bench.fetcher.auth.AuthManager.get_session_file_path") as mock_path:
            mock_path.return_value = session_path

            AuthManager.save_session(session)

            assert session_path.exists()
            assert session_path.parent.exists()


# ============================================================================
# Tests: Load Saved Session
# ============================================================================


class TestLoadSavedSession:
    """Test loading saved sessions."""

    def test_load_saved_session_returns_none_if_no_file(self, temp_session_path):
        """load_saved_session returns None when file doesn't exist."""
        with patch("cis_bench.fetcher.auth.AuthManager.get_session_file_path") as mock_path:
            mock_path.return_value = temp_session_path

            result = AuthManager.load_saved_session()

            assert result is None

    def test_load_saved_session_returns_session_with_cookies(self, temp_session_path):
        """load_saved_session returns session with cookies."""
        # Create a valid cookie file
        import http.cookiejar

        cj = http.cookiejar.MozillaCookieJar(str(temp_session_path))
        cookie = http.cookiejar.Cookie(
            version=0,
            name="test_cookie",
            value="test_value",
            port=None,
            port_specified=False,
            domain="workbench.cisecurity.org",
            domain_specified=True,
            domain_initial_dot=False,
            path="/",
            path_specified=True,
            secure=True,
            expires=None,
            discard=False,
            comment=None,
            comment_url=None,
            rest={},
            rfc2109=False,
        )
        cj.set_cookie(cookie)
        cj.save(ignore_discard=True, ignore_expires=True)

        with patch("cis_bench.fetcher.auth.AuthManager.get_session_file_path") as mock_path:
            with patch("cis_bench.config.Config.get_verify_ssl") as mock_verify:
                mock_path.return_value = temp_session_path
                mock_verify.return_value = False

                session = AuthManager.load_saved_session()

                assert session is not None
                assert len(list(session.cookies)) > 0
                assert session.verify is False


# ============================================================================
# Tests: Clear Saved Session
# ============================================================================


class TestClearSavedSession:
    """Test clearing saved sessions."""

    def test_clear_saved_session_removes_file(self, temp_session_path):
        """clear_saved_session removes the session file."""
        temp_session_path.touch()

        with patch("cis_bench.fetcher.auth.AuthManager.get_session_file_path") as mock_path:
            mock_path.return_value = temp_session_path

            result = AuthManager.clear_saved_session()

            assert result is True
            assert not temp_session_path.exists()

    def test_clear_saved_session_returns_false_if_no_file(self, temp_session_path):
        """clear_saved_session returns False when no file exists."""
        with patch("cis_bench.fetcher.auth.AuthManager.get_session_file_path") as mock_path:
            mock_path.return_value = temp_session_path

            result = AuthManager.clear_saved_session()

            assert result is False


# ============================================================================
# Tests: Validate Session
# ============================================================================


class TestValidateSession:
    """Test session validation."""

    def test_validate_session_returns_false_for_none(self):
        """validate_session returns False for None session."""
        result = AuthManager.validate_session(None)
        assert result is False

    def test_validate_session_returns_false_for_empty_cookies(self):
        """validate_session returns False when no cookies."""
        session = requests.Session()
        result = AuthManager.validate_session(session)
        assert result is False

    def test_validate_session_makes_test_request(self):
        """validate_session makes request to WorkBench."""
        session = requests.Session()
        session.cookies.set("test", "value")

        with patch.object(session, "get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = (
                "<html><body><h1>Benchmarks</h1><table></table></body></html>"  # Not login page
            )
            mock_get.return_value = mock_response

            result = AuthManager.validate_session(session, verify_ssl=False)

            assert result is True
            mock_get.assert_called_once()
            assert "workbench.cisecurity.org" in mock_get.call_args[0][0]

    def test_validate_session_detects_login_redirect(self):
        """validate_session returns False on login redirect to /login."""
        session = requests.Session()
        session.cookies.set("test", "value")

        with patch.object(session, "get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 302
            mock_response.headers = {"Location": "https://workbench.cisecurity.org/login"}
            mock_get.return_value = mock_response

            result = AuthManager.validate_session(session, verify_ssl=False)

            assert result is False

    def test_validate_session_detects_homepage_redirect(self):
        """validate_session returns False on redirect to homepage (unauthenticated)."""
        session = requests.Session()
        session.cookies.set("test", "value")

        with patch.object(session, "get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 302
            mock_response.headers = {"Location": "https://workbench.cisecurity.org"}
            mock_get.return_value = mock_response

            result = AuthManager.validate_session(session, verify_ssl=False)

            assert result is False  # Any redirect means invalid session

    def test_validate_session_detects_login_page_html(self):
        """validate_session returns False when receiving login page HTML."""
        session = requests.Session()
        session.cookies.set("test", "value")

        # Load actual login page HTML
        login_html_path = (
            Path(__file__).parent.parent / "fixtures" / "html" / "workbench_login_page.html"
        )
        login_html = login_html_path.read_text()

        with patch.object(session, "get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200  # Returns 200 but with login page
            mock_response.text = login_html
            mock_get.return_value = mock_response

            result = AuthManager.validate_session(session, verify_ssl=False)

            assert result is False  # Should detect login page and return False


# ============================================================================
# Tests: Get or Create Session
# ============================================================================


class TestGetOrCreateSession:
    """Test get_or_create_session logic."""

    def test_get_or_create_uses_saved_session_when_valid(self, temp_session_path):
        """get_or_create_session uses saved session when valid."""
        with patch("cis_bench.fetcher.auth.AuthManager.load_saved_session") as mock_load:
            with patch("cis_bench.fetcher.auth.AuthManager.validate_session") as mock_validate:
                mock_session = Mock()
                mock_load.return_value = mock_session
                mock_validate.return_value = True

                result = AuthManager.get_or_create_session()

                assert result == mock_session
                mock_load.assert_called_once()
                mock_validate.assert_called_once()

    def test_get_or_create_raises_error_when_no_session_and_no_browser(self):
        """get_or_create_session raises ValueError when no session and no browser."""
        with patch("cis_bench.fetcher.auth.AuthManager.load_saved_session") as mock_load:
            mock_load.return_value = None

            with pytest.raises(ValueError) as exc_info:
                AuthManager.get_or_create_session()

            assert "No saved session" in str(exc_info.value)
            assert "auth login" in str(exc_info.value)

    def test_get_or_create_creates_new_session_when_saved_invalid(self):
        """get_or_create_session creates new session when saved one is invalid."""
        with patch("cis_bench.fetcher.auth.AuthManager.load_saved_session") as mock_load:
            with patch("cis_bench.fetcher.auth.AuthManager.validate_session") as mock_validate:
                with patch("cis_bench.fetcher.auth.AuthManager.clear_saved_session") as mock_clear:
                    with patch(
                        "cis_bench.fetcher.auth.AuthManager.load_cookies_from_browser"
                    ) as mock_browser:
                        with patch("cis_bench.fetcher.auth.AuthManager.save_session") as mock_save:
                            old_session = Mock()
                            new_session = Mock()
                            new_session.cookies = [Mock()]

                            mock_load.return_value = old_session
                            mock_validate.side_effect = [False, True]  # Old invalid, new valid
                            mock_browser.return_value = new_session

                            result = AuthManager.get_or_create_session(browser="chrome")

                            assert result == new_session
                            mock_clear.assert_called_once()
                            mock_browser.assert_called_once()
                            mock_save.assert_called_once()

    def test_get_or_create_force_refresh_skips_saved_session(self):
        """get_or_create_session with force_refresh ignores saved session."""
        with patch("cis_bench.fetcher.auth.AuthManager.load_saved_session") as mock_load:
            with patch(
                "cis_bench.fetcher.auth.AuthManager.load_cookies_from_browser"
            ) as mock_browser:
                with patch("cis_bench.fetcher.auth.AuthManager.validate_session") as mock_validate:
                    with patch("cis_bench.fetcher.auth.AuthManager.save_session") as mock_save:
                        new_session = Mock()
                        new_session.cookies = [Mock()]
                        mock_browser.return_value = new_session
                        mock_validate.return_value = True

                        result = AuthManager.get_or_create_session(
                            browser="chrome", force_refresh=True
                        )

                        # Should NOT call load_saved_session
                        mock_load.assert_not_called()
                        # Should create new session
                        mock_browser.assert_called_once()
