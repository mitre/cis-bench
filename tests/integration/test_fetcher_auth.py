"""Tests for CIS WorkBench authentication and cookie management.

Tests AuthManager cookie extraction, session creation, and error handling.
"""

import http.cookiejar
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests
from requests.cookies import RequestsCookieJar, create_cookie

from cis_bench.config import RequestPolicy
from cis_bench.fetcher.auth import AuthManager

POLICY = RequestPolicy(requests_per_second=3.0, retries=2, backoff_factor=1.0, jitter_seconds=0.5)


@pytest.fixture
def auth(tmp_path):
    """An AuthManager for production WorkBench that verifies TLS and saves to a temp file."""
    return AuthManager(
        workbench_url="https://workbench.cisecurity.org",
        verify_ssl=True,
        session_file=tmp_path / "session.cookies",
        request_policy=POLICY,
        timeout=(10.0, 30.0),
    )


def _jar_with(*cookies: http.cookiejar.Cookie) -> http.cookiejar.CookieJar:
    jar = http.cookiejar.CookieJar()
    for cookie in cookies:
        jar.set_cookie(cookie)
    return jar


class TestAuthManagerBrowserCookies:
    """Test browser cookie extraction."""

    @patch("cis_bench.fetcher.auth.browser_cookie3.chrome")
    def test_chrome_cookie_extraction_includes_cis_sso_and_filters_untrusted_domains(
        self, mock_chrome, auth
    ):
        """Chrome extraction loads workbench and CIS Portal Auth0 cookies while rejecting lookalike domains."""
        mock_chrome.return_value = _jar_with(
            create_cookie("workbench_session", "wb-1", domain="workbench.cisecurity.org"),
            create_cookie("auth0", "sso-1", domain="auth.portal.cisecurity.org"),
            create_cookie("org_pref", "cis-1", domain=".cisecurity.org"),
            create_cookie("phish", "leak", domain="evil-cisecurity.org"),
            create_cookie("suffix_phish", "leak2", domain="cisecurity.org.attacker.example"),
        )

        session = auth.load_cookies_from_browser("chrome")

        mock_chrome.assert_called_once_with(domain_name="cisecurity.org")
        assert isinstance(session, requests.Session)
        assert isinstance(session.cookies, RequestsCookieJar)
        extracted = {(c.domain, c.name): c.value for c in session.cookies}
        assert extracted == {
            ("workbench.cisecurity.org", "workbench_session"): "wb-1",
            ("auth.portal.cisecurity.org", "auth0"): "sso-1",
            (".cisecurity.org", "org_pref"): "cis-1",
        }

    @patch("cis_bench.fetcher.auth.browser_cookie3.firefox")
    def test_firefox_cookie_extraction(self, mock_firefox, auth):
        """Test successful Firefox cookie extraction."""
        mock_firefox.return_value = _jar_with(
            create_cookie("XSRF-TOKEN", "xsrf-1", domain="workbench.cisecurity.org")
        )

        session = auth.load_cookies_from_browser("firefox")

        mock_firefox.assert_called_once_with(domain_name="cisecurity.org")
        assert isinstance(session, requests.Session)
        assert [(c.domain, c.name) for c in session.cookies] == [
            ("workbench.cisecurity.org", "XSRF-TOKEN")
        ]

    @patch("cis_bench.fetcher.auth.browser_cookie3.edge")
    def test_edge_cookie_extraction(self, mock_edge, auth):
        """Test successful Edge cookie extraction."""
        mock_edge.return_value = _jar_with(
            create_cookie("auth0", "sso-edge", domain="auth.portal.cisecurity.org")
        )

        session = auth.load_cookies_from_browser("edge")

        mock_edge.assert_called_once_with(domain_name="cisecurity.org")
        assert [(c.domain, c.name) for c in session.cookies] == [
            ("auth.portal.cisecurity.org", "auth0")
        ]

    @patch("cis_bench.fetcher.auth.browser_cookie3.safari")
    def test_safari_cookie_extraction(self, mock_safari, auth):
        """Test successful Safari cookie extraction."""
        mock_safari.return_value = _jar_with(
            create_cookie("auth0", "sso-safari", domain="auth.portal.cisecurity.org")
        )

        session = auth.load_cookies_from_browser("safari")

        mock_safari.assert_called_once_with(domain_name="cisecurity.org")
        assert [(c.domain, c.name) for c in session.cookies] == [
            ("auth.portal.cisecurity.org", "auth0")
        ]

    def test_unsupported_browser(self, auth):
        """Test error handling for unsupported browser."""
        with pytest.raises(ValueError, match="Unsupported browser: opera"):
            auth.load_cookies_from_browser("opera")

    @patch("cis_bench.fetcher.auth.browser_cookie3.chrome")
    def test_cookie_extraction_failure(self, mock_chrome, auth):
        """Test error handling when cookie extraction fails."""
        # Simulate browser_cookie3 exception
        mock_chrome.side_effect = Exception("Browser database locked")

        # Execute and verify
        with pytest.raises(Exception, match="Failed to extract cookies from chrome"):
            auth.load_cookies_from_browser("chrome")

    @patch("cis_bench.fetcher.auth.browser_cookie3.chrome")
    def test_cookie_count_logging(self, mock_chrome, auth):
        """Test that cookie count is correctly calculated and logged."""
        cookies = [
            create_cookie(f"cookie_{i}", f"val_{i}", domain="workbench.cisecurity.org")
            for i in range(5)
        ]
        mock_chrome.return_value = _jar_with(*cookies)

        session = auth.load_cookies_from_browser("chrome")

        assert isinstance(session, requests.Session)
        assert isinstance(session.cookies, RequestsCookieJar)
        assert len(list(session.cookies)) == 5

    @patch("cis_bench.fetcher.auth.browser_cookie3.chrome")
    def test_empty_cookie_jar(self, mock_chrome, auth):
        """Test handling of empty cookie jar (no CIS WorkBench cookies)."""
        mock_chrome.return_value = _jar_with()

        session = auth.load_cookies_from_browser("chrome")

        assert isinstance(session, requests.Session)
        assert isinstance(session.cookies, RequestsCookieJar)
        assert len(list(session.cookies)) == 0

    @patch("cis_bench.fetcher.auth.browser_cookie3.chrome")
    def test_case_insensitive_browser_name(self, mock_chrome, auth):
        """Test that browser name matching is case-insensitive."""
        mock_chrome.return_value = _jar_with()

        for browser_name in ["chrome", "CHROME", "Chrome", "ChRoMe"]:
            session = auth.load_cookies_from_browser(browser_name)
            assert isinstance(session, requests.Session)


class TestAuthManagerFileBasedCookies:
    """Test cookie loading from Netscape format files."""

    @patch("cis_bench.fetcher.auth.http.cookiejar.MozillaCookieJar")
    def test_load_cookies_from_file_success(self, mock_mozilla_jar, auth):
        """Test successful loading of cookies from file into RequestsCookieJar."""
        cookie = create_cookie("workbench_session", "file-val", domain="workbench.cisecurity.org")
        mock_jar_instance = MagicMock()
        mock_jar_instance.__iter__ = Mock(return_value=iter([cookie]))
        mock_mozilla_jar.return_value = mock_jar_instance

        session = auth.load_cookies_from_file("/path/to/cookies.txt")

        mock_mozilla_jar.assert_called_once_with("/path/to/cookies.txt")
        mock_jar_instance.load.assert_called_once_with(ignore_discard=True, ignore_expires=True)
        assert isinstance(session, requests.Session)
        assert isinstance(session.cookies, RequestsCookieJar)
        assert session.cookies.get("workbench_session") == "file-val"

    @patch("cis_bench.fetcher.auth.http.cookiejar.MozillaCookieJar")
    def test_load_cookies_file_not_found(self, mock_mozilla_jar, auth):
        """Test error handling when cookie file doesn't exist."""
        mock_jar_instance = MagicMock()
        mock_jar_instance.load.side_effect = FileNotFoundError()
        mock_mozilla_jar.return_value = mock_jar_instance

        with pytest.raises(FileNotFoundError, match="Cookies file not found"):
            auth.load_cookies_from_file("/nonexistent/cookies.txt")

    @patch("cis_bench.fetcher.auth.http.cookiejar.MozillaCookieJar")
    def test_load_cookies_invalid_format(self, mock_mozilla_jar, auth):
        """Test error handling for invalid cookie file format."""
        mock_jar_instance = MagicMock()
        mock_jar_instance.load.side_effect = Exception("Invalid cookie file format")
        mock_mozilla_jar.return_value = mock_jar_instance

        with pytest.raises(Exception, match="Failed to load cookies from file"):
            auth.load_cookies_from_file("/path/to/bad_cookies.txt")

    @patch("cis_bench.fetcher.auth.http.cookiejar.MozillaCookieJar")
    def test_load_cookies_multiple_cookies(self, mock_mozilla_jar, auth):
        """Test loading file with multiple cookies."""
        cookies = [
            create_cookie(f"c_{i}", f"v_{i}", domain="workbench.cisecurity.org") for i in range(10)
        ]
        mock_jar_instance = MagicMock()
        mock_jar_instance.__iter__ = Mock(return_value=iter(cookies))
        mock_mozilla_jar.return_value = mock_jar_instance

        session = auth.load_cookies_from_file("/path/to/cookies.txt")

        assert isinstance(session, requests.Session)
        assert isinstance(session.cookies, RequestsCookieJar)
        assert len(list(session.cookies)) == 10
