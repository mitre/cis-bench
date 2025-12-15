"""Tests for CIS WorkBench authentication and cookie management.

Tests AuthManager cookie extraction, session creation, and error handling.
"""

import http.cookiejar
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests

from cis_bench.fetcher.auth import AuthManager


class TestAuthManagerBrowserCookies:
    """Test browser cookie extraction."""

    @patch("cis_bench.fetcher.auth.browser_cookie3.chrome")
    def test_chrome_cookie_extraction(self, mock_chrome):
        """Test successful Chrome cookie extraction."""
        # Setup mock cookie jar
        mock_cj = MagicMock(spec=http.cookiejar.CookieJar)
        mock_cookie = Mock()
        mock_cookie.domain = "workbench.cisecurity.org"
        mock_cookie.name = "session_token"
        mock_cj.__iter__ = Mock(return_value=iter([mock_cookie]))
        mock_chrome.return_value = mock_cj

        # Execute
        session = AuthManager.load_cookies_from_browser("chrome")

        # Verify
        mock_chrome.assert_called_once_with(domain_name="workbench.cisecurity.org")
        assert isinstance(session, requests.Session)
        assert session.cookies == mock_cj

    @patch("cis_bench.fetcher.auth.browser_cookie3.firefox")
    def test_firefox_cookie_extraction(self, mock_firefox):
        """Test successful Firefox cookie extraction."""
        # Setup mock cookie jar
        mock_cj = MagicMock(spec=http.cookiejar.CookieJar)
        mock_cookie = Mock()
        mock_cookie.domain = "workbench.cisecurity.org"
        mock_cookie.name = "XSRF-TOKEN"
        mock_cj.__iter__ = Mock(return_value=iter([mock_cookie]))
        mock_firefox.return_value = mock_cj

        # Execute
        session = AuthManager.load_cookies_from_browser("firefox")

        # Verify
        mock_firefox.assert_called_once_with(domain_name="workbench.cisecurity.org")
        assert isinstance(session, requests.Session)
        assert session.cookies == mock_cj

    @patch("cis_bench.fetcher.auth.browser_cookie3.edge")
    def test_edge_cookie_extraction(self, mock_edge):
        """Test successful Edge cookie extraction."""
        # Setup mock cookie jar
        mock_cj = MagicMock(spec=http.cookiejar.CookieJar)
        mock_cookie = Mock()
        mock_cookie.domain = "workbench.cisecurity.org"
        mock_cj.__iter__ = Mock(return_value=iter([mock_cookie]))
        mock_edge.return_value = mock_cj

        # Execute
        session = AuthManager.load_cookies_from_browser("edge")

        # Verify
        mock_edge.assert_called_once_with(domain_name="workbench.cisecurity.org")
        assert isinstance(session, requests.Session)

    @patch("cis_bench.fetcher.auth.browser_cookie3.safari")
    def test_safari_cookie_extraction(self, mock_safari):
        """Test successful Safari cookie extraction."""
        # Setup mock cookie jar
        mock_cj = MagicMock(spec=http.cookiejar.CookieJar)
        mock_cookie = Mock()
        mock_cookie.domain = "workbench.cisecurity.org"
        mock_cj.__iter__ = Mock(return_value=iter([mock_cookie]))
        mock_safari.return_value = mock_cj

        # Execute
        session = AuthManager.load_cookies_from_browser("safari")

        # Verify
        mock_safari.assert_called_once_with(domain_name="workbench.cisecurity.org")
        assert isinstance(session, requests.Session)

    def test_unsupported_browser(self):
        """Test error handling for unsupported browser."""
        with pytest.raises(ValueError, match="Unsupported browser: opera"):
            AuthManager.load_cookies_from_browser("opera")

    @patch("cis_bench.fetcher.auth.browser_cookie3.chrome")
    def test_cookie_extraction_failure(self, mock_chrome):
        """Test error handling when cookie extraction fails."""
        # Simulate browser_cookie3 exception
        mock_chrome.side_effect = Exception("Browser database locked")

        # Execute and verify
        with pytest.raises(Exception, match="Failed to extract cookies from chrome"):
            AuthManager.load_cookies_from_browser("chrome")

    @patch("cis_bench.fetcher.auth.browser_cookie3.chrome")
    def test_cookie_count_logging(self, mock_chrome):
        """Test that cookie count is correctly calculated and logged."""
        # Setup multiple cookies
        cookies = []
        for i in range(5):
            cookie = Mock()
            cookie.domain = "workbench.cisecurity.org"
            cookie.name = f"cookie_{i}"
            cookies.append(cookie)

        mock_cj = MagicMock(spec=http.cookiejar.CookieJar)
        mock_cj.__iter__ = Mock(return_value=iter(cookies))
        mock_chrome.return_value = mock_cj

        # Execute
        session = AuthManager.load_cookies_from_browser("chrome")

        # Verify session created
        assert isinstance(session, requests.Session)
        assert session.cookies == mock_cj

    @patch("cis_bench.fetcher.auth.browser_cookie3.chrome")
    def test_empty_cookie_jar(self, mock_chrome):
        """Test handling of empty cookie jar (no CIS WorkBench cookies)."""
        # Setup empty cookie jar
        mock_cj = MagicMock(spec=http.cookiejar.CookieJar)
        mock_cj.__iter__ = Mock(return_value=iter([]))
        mock_chrome.return_value = mock_cj

        # Execute
        session = AuthManager.load_cookies_from_browser("chrome")

        # Verify session created (even with no cookies)
        assert isinstance(session, requests.Session)
        assert session.cookies == mock_cj

    @patch("cis_bench.fetcher.auth.browser_cookie3.chrome")
    def test_case_insensitive_browser_name(self, mock_chrome):
        """Test that browser name matching is case-insensitive."""
        mock_cj = MagicMock(spec=http.cookiejar.CookieJar)
        mock_cj.__iter__ = Mock(return_value=iter([]))
        mock_chrome.return_value = mock_cj

        # Test various cases
        for browser_name in ["chrome", "CHROME", "Chrome", "ChRoMe"]:
            session = AuthManager.load_cookies_from_browser(browser_name)
            assert isinstance(session, requests.Session)


class TestAuthManagerFileBasedCookies:
    """Test cookie loading from Netscape format files."""

    @patch("cis_bench.fetcher.auth.http.cookiejar.MozillaCookieJar")
    def test_load_cookies_from_file_success(self, mock_mozilla_jar):
        """Test successful loading of cookies from file."""
        # Setup mock
        mock_jar_instance = MagicMock()
        mock_jar_instance.__iter__ = Mock(return_value=iter([Mock()]))
        mock_mozilla_jar.return_value = mock_jar_instance

        # Execute
        session = AuthManager.load_cookies_from_file("/path/to/cookies.txt")

        # Verify
        mock_mozilla_jar.assert_called_once_with("/path/to/cookies.txt")
        mock_jar_instance.load.assert_called_once_with(ignore_discard=True, ignore_expires=True)
        assert isinstance(session, requests.Session)
        assert session.cookies == mock_jar_instance

    @patch("cis_bench.fetcher.auth.http.cookiejar.MozillaCookieJar")
    def test_load_cookies_file_not_found(self, mock_mozilla_jar):
        """Test error handling when cookie file doesn't exist."""
        # Setup mock to raise FileNotFoundError
        mock_jar_instance = MagicMock()
        mock_jar_instance.load.side_effect = FileNotFoundError()
        mock_mozilla_jar.return_value = mock_jar_instance

        # Execute and verify
        with pytest.raises(FileNotFoundError, match="Cookies file not found"):
            AuthManager.load_cookies_from_file("/nonexistent/cookies.txt")

    @patch("cis_bench.fetcher.auth.http.cookiejar.MozillaCookieJar")
    def test_load_cookies_invalid_format(self, mock_mozilla_jar):
        """Test error handling for invalid cookie file format."""
        # Setup mock to raise exception on load
        mock_jar_instance = MagicMock()
        mock_jar_instance.load.side_effect = Exception("Invalid cookie file format")
        mock_mozilla_jar.return_value = mock_jar_instance

        # Execute and verify
        with pytest.raises(Exception, match="Failed to load cookies from file"):
            AuthManager.load_cookies_from_file("/path/to/bad_cookies.txt")

    @patch("cis_bench.fetcher.auth.http.cookiejar.MozillaCookieJar")
    def test_load_cookies_multiple_cookies(self, mock_mozilla_jar):
        """Test loading file with multiple cookies."""
        # Setup multiple cookies
        cookies = [Mock() for _ in range(10)]
        mock_jar_instance = MagicMock()
        mock_jar_instance.__iter__ = Mock(return_value=iter(cookies))
        mock_mozilla_jar.return_value = mock_jar_instance

        # Execute
        session = AuthManager.load_cookies_from_file("/path/to/cookies.txt")

        # Verify
        assert isinstance(session, requests.Session)
        assert session.cookies == mock_jar_instance


class TestAuthManagerCookieDictionary:
    """Test session creation from cookie dictionary."""

    def test_create_session_with_cookies(self):
        """Test session creation from dictionary."""
        cookies = {"XSRF-TOKEN": "abc123", "workbench_session": "xyz789", "_ga": "analytics_id"}

        # Execute
        session = AuthManager.create_session_with_cookies(cookies)

        # Verify
        assert isinstance(session, requests.Session)
        assert "XSRF-TOKEN" in session.cookies
        assert session.cookies["XSRF-TOKEN"] == "abc123"

    def test_create_session_empty_dictionary(self):
        """Test session creation with empty cookie dictionary."""
        session = AuthManager.create_session_with_cookies({})

        # Verify
        assert isinstance(session, requests.Session)
        assert len(session.cookies) == 0

    def test_create_session_special_characters(self):
        """Test cookie values with special characters."""
        cookies = {"token": "value=with=equals", "session": "value;with;semicolons"}

        # Execute
        session = AuthManager.create_session_with_cookies(cookies)

        # Verify
        assert isinstance(session, requests.Session)
        assert session.cookies["token"] == "value=with=equals"


class TestAuthManagerGetAuthenticatedSession:
    """Test the unified authentication method."""

    @patch("cis_bench.fetcher.auth.AuthManager.load_cookies_from_browser")
    def test_prioritize_browser_cookies(self, mock_load_browser):
        """Test that browser cookies are prioritized when all methods specified."""
        mock_session = Mock(spec=requests.Session)
        mock_load_browser.return_value = mock_session

        # Execute with all three methods
        session = AuthManager.get_authenticated_session(
            browser="chrome", cookies_file="/path/to/cookies.txt", cookies_dict={"key": "value"}
        )

        # Verify browser method was called (highest priority)
        mock_load_browser.assert_called_once_with("chrome")
        assert session == mock_session

    @patch("cis_bench.fetcher.auth.AuthManager.load_cookies_from_file")
    def test_fallback_to_file(self, mock_load_file):
        """Test fallback to cookies file when browser not specified."""
        mock_session = Mock(spec=requests.Session)
        mock_load_file.return_value = mock_session

        # Execute with file and dict only
        session = AuthManager.get_authenticated_session(
            browser=None, cookies_file="/path/to/cookies.txt", cookies_dict={"key": "value"}
        )

        # Verify file method was called
        mock_load_file.assert_called_once_with("/path/to/cookies.txt")
        assert session == mock_session

    @patch("cis_bench.fetcher.auth.AuthManager.create_session_with_cookies")
    def test_fallback_to_dict(self, mock_create_session):
        """Test fallback to cookie dictionary when browser and file not specified."""
        mock_session = Mock(spec=requests.Session)
        mock_create_session.return_value = mock_session

        cookies = {"key": "value"}
        # Execute with dict only
        session = AuthManager.get_authenticated_session(
            browser=None, cookies_file=None, cookies_dict=cookies
        )

        # Verify dict method was called
        mock_create_session.assert_called_once_with(cookies)
        assert session == mock_session

    def test_no_cookie_source_provided(self):
        """Test error when no cookie source provided."""
        with pytest.raises(ValueError, match="No cookie source provided"):
            AuthManager.get_authenticated_session(
                browser=None, cookies_file=None, cookies_dict=None
            )

    @patch("cis_bench.fetcher.auth.AuthManager.load_cookies_from_browser")
    def test_browser_failure_doesnt_fallback(self, mock_load_browser):
        """Test that browser failure doesn't silently fall back to other methods."""
        # Simulate browser extraction failure
        mock_load_browser.side_effect = Exception("Browser extraction failed")

        # Execute and verify exception propagates
        with pytest.raises(Exception, match="Browser extraction failed"):
            AuthManager.get_authenticated_session(
                browser="chrome", cookies_file="/path/to/cookies.txt", cookies_dict={"key": "value"}
            )
