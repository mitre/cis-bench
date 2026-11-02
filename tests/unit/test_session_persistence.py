"""Unit tests for session persistence in AuthManager."""

import http.cookiejar
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from cis_bench.exceptions import AuthenticationError, TLSVerificationError
from cis_bench.fetcher.auth import AuthManager


def _workbench_cookie(
    name: str = "test_cookie", value: str = "test_value"
) -> http.cookiejar.Cookie:
    """A secure cookie scoped to the WorkBench host, as the browser would store it."""
    return http.cookiejar.Cookie(
        version=0,
        name=name,
        value=value,
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
        cj = http.cookiejar.MozillaCookieJar(str(temp_session_path))
        cj.set_cookie(_workbench_cookie())
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

    def test_load_saved_session_defaults_to_verified_tls(self, temp_session_path, monkeypatch):
        """With CIS_BENCH_VERIFY_SSL unset, a restored session verifies certificates."""
        monkeypatch.delenv("CIS_BENCH_VERIFY_SSL", raising=False)
        cj = http.cookiejar.MozillaCookieJar(str(temp_session_path))
        cj.set_cookie(_workbench_cookie())
        cj.save(ignore_discard=True, ignore_expires=True)

        with patch.object(AuthManager, "get_session_file_path", return_value=temp_session_path):
            session = AuthManager.load_saved_session()

        assert session is not None
        assert session.verify is True

    def test_load_saved_session_propagates_configuration_error(
        self, temp_session_path, monkeypatch
    ):
        """A bad CIS_BENCH_VERIFY_SSL value is a configuration error, not a missing session."""
        temp_session_path.write_text("# Netscape HTTP Cookie File\n")
        monkeypatch.setenv("CIS_BENCH_VERIFY_SSL", "bogus")

        with patch("cis_bench.fetcher.auth.AuthManager.get_session_file_path") as mock_path:
            mock_path.return_value = temp_session_path

            with pytest.raises(ValueError, match="CIS_BENCH_VERIFY_SSL"):
                AuthManager.load_saved_session()


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

        # Load synthetic login page HTML
        login_html_path = (
            Path(__file__).parent.parent / "fixtures" / "html" / "workbench_login_page.html"
        )
        login_html = login_html_path.read_text()
        assert "<script" not in login_html.lower()
        assert "csrf-token" not in login_html.lower()

        with patch.object(session, "get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200  # Returns 200 but with login page
            mock_response.text = login_html
            mock_get.return_value = mock_response

            result = AuthManager.validate_session(session, verify_ssl=False)

            assert result is False  # Should detect login page and return False

    def test_validate_session_completes_cis_portal_auth0_sso_handshake(self):
        """validate_session follows trusted Auth0 OIDC redirects hop-by-hop to mint WorkBench session."""
        session = requests.Session()
        session.cookies.set("auth0", "sso-cookie", domain="auth.portal.cisecurity.org")

        def _redirect(location: str) -> Mock:
            resp = Mock()
            resp.status_code = 302
            resp.headers = {"Location": location}
            return resp

        final_ok = Mock()
        final_ok.status_code = 200
        final_ok.headers = {}
        final_ok.text = "<html><body><h1>Benchmarks</h1><table></table></body></html>"

        with patch.object(session, "get") as mock_get:
            mock_get.side_effect = [
                _redirect("https://workbench.cisecurity.org"),
                _redirect("https://workbench.cisecurity.org/auth0/login"),
                _redirect("https://auth.portal.cisecurity.org/authorize?client_id=wb&state=s1"),
                _redirect("https://workbench.cisecurity.org/auth0/callback?code=c1&state=s1"),
                _redirect("/benchmarks"),
                final_ok,
            ]

            result = AuthManager.validate_session(session, verify_ssl=True)

        assert result is True
        requested_urls = [call.args[0] for call in mock_get.call_args_list]
        assert requested_urls == [
            "https://workbench.cisecurity.org/benchmarks",
            "https://workbench.cisecurity.org",
            "https://workbench.cisecurity.org/auth0/login",
            "https://auth.portal.cisecurity.org/authorize?client_id=wb&state=s1",
            "https://workbench.cisecurity.org/auth0/callback?code=c1&state=s1",
            "https://workbench.cisecurity.org/benchmarks",
        ]
        assert all(call.kwargs["allow_redirects"] is False for call in mock_get.call_args_list)
        assert all(call.kwargs["verify"] is True for call in mock_get.call_args_list)

    def test_validate_session_verifies_benchmarks_when_sso_lands_on_dashboard(self):
        """validate_session confirms /benchmarks access when OIDC callback lands on /dashboard."""
        session = requests.Session()
        session.cookies.set("auth0", "sso-cookie", domain="auth.portal.cisecurity.org")

        redirect_to_dashboard = Mock(
            status_code=302, headers={"Location": "https://workbench.cisecurity.org/dashboard"}
        )
        dashboard_ok = Mock(
            status_code=200, headers={}, text="<html><body><h1>Dashboard</h1></body></html>"
        )
        benchmarks_ok = Mock(
            status_code=200,
            headers={},
            text="<html><body><h1>Benchmarks</h1><table></table></body></html>",
        )

        with patch.object(
            session, "get", side_effect=[redirect_to_dashboard, dashboard_ok, benchmarks_ok]
        ) as mock_get:
            assert AuthManager.validate_session(session, verify_ssl=False) is True

        assert [c.args[0] for c in mock_get.call_args_list] == [
            "https://workbench.cisecurity.org/benchmarks",
            "https://workbench.cisecurity.org/dashboard",
            "https://workbench.cisecurity.org/benchmarks",
        ]

    @pytest.mark.parametrize(
        "bad_location",
        [
            "https://auth.portal.cisecurity.org/u/login?state=unauthenticated",
            "https://evil.example.com/callback",
            "https://workbench-staging.cisecurity.org/dashboard",
            "http://workbench.cisecurity.org/benchmarks",
            "",
        ],
    )
    def test_validate_session_rejects_login_untrusted_or_insecure_redirects(
        self, bad_location: str
    ):
        """validate_session stops immediately on Auth0 login, untrusted hosts, HTTP, or empty Location."""
        session = requests.Session()
        session.cookies.set("auth0", "sso-cookie", domain="auth.portal.cisecurity.org")

        first = Mock(status_code=302, headers={"Location": "https://workbench.cisecurity.org"})
        second = Mock(status_code=302, headers={"Location": bad_location})

        with patch.object(session, "get", side_effect=[first, second]) as mock_get:
            assert AuthManager.validate_session(session, verify_ssl=True) is False

        assert mock_get.call_count == 2

    def test_validate_session_rejects_200_on_auth_portal_host_or_excessive_redirects(self):
        """validate_session rejects 200 OK served on auth.portal.cisecurity.org and bounded redirect loops."""
        session = requests.Session()
        session.cookies.set("auth0", "sso-cookie", domain="auth.portal.cisecurity.org")

        to_auth = Mock(
            status_code=302,
            headers={"Location": "https://auth.portal.cisecurity.org/authorize?state=1"},
        )
        auth_html = Mock(status_code=200, headers={}, text="<html><body>Consent</body></html>")

        with patch.object(session, "get", side_effect=[to_auth, auth_html]) as auth_get:
            assert AuthManager.validate_session(session, verify_ssl=True) is False
        assert auth_get.call_count == 2

        alternating = [
            Mock(
                status_code=302,
                headers={
                    "Location": (
                        "https://auth.portal.cisecurity.org/authorize"
                        if i % 2 == 0
                        else "https://workbench.cisecurity.org/callback"
                    )
                },
            )
            for i in range(12)
        ]
        with patch.object(session, "get", side_effect=alternating) as loop_get:
            assert AuthManager.validate_session(session, verify_ssl=True) is False
        assert 2 <= loop_get.call_count <= 9

    def test_validate_session_honors_configured_workbench_base_url(self, monkeypatch):
        """validate_session targets CIS_BENCH_WORKBENCH_URL and allows QA Auth0 SSO onto that host."""
        monkeypatch.setenv("CIS_BENCH_WORKBENCH_URL", "https://workbench-staging.cisecurity.org/")
        session = requests.Session()
        session.cookies.set("auth0", "qa-sso", domain="auth.portal.qa.cisecurity.org")

        to_qa_auth = Mock(
            status_code=302,
            headers={"Location": "https://auth.portal.qa.cisecurity.org/authorize?state=s1"},
        )
        to_staging_cb = Mock(
            status_code=302,
            headers={
                "Location": "https://workbench-staging.cisecurity.org/auth0/callback?code=c1&state=s1"
            },
        )
        to_benchmarks = Mock(status_code=302, headers={"Location": "/benchmarks"})
        staging_ok = Mock(
            status_code=200,
            headers={},
            text="<html><body><h1>Benchmarks</h1><table></table></body></html>",
        )

        with patch.object(
            session,
            "get",
            side_effect=[to_qa_auth, to_staging_cb, to_benchmarks, staging_ok],
        ) as mock_get:
            assert AuthManager.validate_session(session, verify_ssl=False) is True

        assert [c.args[0] for c in mock_get.call_args_list] == [
            "https://workbench-staging.cisecurity.org/benchmarks",
            "https://auth.portal.qa.cisecurity.org/authorize?state=s1",
            "https://workbench-staging.cisecurity.org/auth0/callback?code=c1&state=s1",
            "https://workbench-staging.cisecurity.org/benchmarks",
        ]

        redirect_to_prod = Mock(
            status_code=302, headers={"Location": "https://workbench.cisecurity.org/benchmarks"}
        )
        with patch.object(session, "get", return_value=redirect_to_prod):
            assert AuthManager.validate_session(session, verify_ssl=False) is False

    # ============================================================================
    # Tests: Get or Create Session
    # ============================================================================

    def test_validate_session_raises_tls_error_when_certificate_verification_fails(self):
        """A TLS trust failure is reported as such, never as an expired session."""
        session = requests.Session()
        session.cookies.set("test", "value")

        with patch.object(session, "get") as mock_get:
            mock_get.side_effect = requests.exceptions.SSLError(
                "certificate verify failed: unable to get local issuer certificate"
            )

            with pytest.raises(TLSVerificationError) as exc_info:
                AuthManager.validate_session(session, verify_ssl=True)

        message = str(exc_info.value)
        assert "workbench.cisecurity.org" in message
        assert "unable to get local issuer certificate" in message
        assert "REQUESTS_CA_BUNDLE" in message
        assert "CIS_BENCH_VERIFY_SSL=false" in message
        assert isinstance(exc_info.value.__cause__, requests.exceptions.SSLError)

    def test_validate_session_still_returns_false_on_non_tls_connection_errors(self):
        """Network failures other than TLS trust keep the existing False contract."""
        session = requests.Session()
        session.cookies.set("test", "value")

        with patch.object(session, "get") as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError("connection refused")

            assert AuthManager.validate_session(session, verify_ssl=True) is False


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

    def test_get_or_create_session_preserves_saved_cookies_on_invalid_workbench_url(
        self, temp_session_path, monkeypatch
    ):
        """Invalid CIS_BENCH_WORKBENCH_URL raises ValueError without deleting saved session cookies."""
        with patch.object(AuthManager, "get_session_file_path", return_value=temp_session_path):
            seed = requests.Session()
            seed.cookies.set(
                "cis_workbench_session", "valid_token", domain="workbench.cisecurity.org"
            )
            AuthManager.save_session(seed)
            assert temp_session_path.exists()

            monkeypatch.setenv("CIS_BENCH_WORKBENCH_URL", "http://insecure.example.com")

            with pytest.raises(ValueError, match="CIS_BENCH_WORKBENCH_URL"):
                AuthManager.get_or_create_session()

            assert temp_session_path.exists()

    def test_get_or_create_session_raises_authentication_error_when_browser_session_invalid(
        self, temp_session_path
    ):
        """Fresh browser cookies that WorkBench rejects are an authentication failure, typed."""
        browser_session = requests.Session()
        browser_session.cookies.set("stale", "1", domain="workbench.cisecurity.org")
        with (
            patch.object(AuthManager, "get_session_file_path", return_value=temp_session_path),
            patch.object(AuthManager, "load_cookies_from_browser", return_value=browser_session),
            patch.object(AuthManager, "validate_session", return_value=False),
            patch.object(AuthManager, "save_session") as mock_save,
        ):
            with pytest.raises(AuthenticationError, match="workbench.cisecurity.org"):
                AuthManager.get_or_create_session(browser="chrome")

        mock_save.assert_not_called()

    @pytest.mark.parametrize(
        ("env_value", "expected_verify"),
        [
            pytest.param(None, True, id="unset-verifies"),
            pytest.param("false", False, id="opt-out"),
        ],
    )
    def test_get_or_create_and_validate_session_default_verify_ssl_from_config(
        self, temp_session_path, monkeypatch, env_value, expected_verify
    ):
        """get_or_create_session and validate_session take verify_ssl from Config when omitted."""
        if env_value is None:
            monkeypatch.delenv("CIS_BENCH_VERIFY_SSL", raising=False)
        else:
            monkeypatch.setenv("CIS_BENCH_VERIFY_SSL", env_value)
        with patch.object(AuthManager, "get_session_file_path", return_value=temp_session_path):
            seed = requests.Session()
            seed.cookies.set(
                "cis_workbench_session", "valid_token", domain="workbench.cisecurity.org"
            )
            AuthManager.save_session(seed)

            ok_resp = Mock(
                status_code=200,
                headers={},
                text="<html><body><h1>Benchmarks</h1><table></table></body></html>",
            )
            with patch("requests.Session.get", return_value=ok_resp) as mock_get:
                session = AuthManager.get_or_create_session()
                assert session.verify is expected_verify
                assert mock_get.call_args.kwargs["verify"] is expected_verify

            with patch.object(seed, "get", return_value=ok_resp) as default_get:
                assert AuthManager.validate_session(seed) is True
                assert default_get.call_args.kwargs["verify"] is expected_verify

            with patch.object(seed, "get", return_value=ok_resp) as explicit_get:
                assert AuthManager.validate_session(seed, verify_ssl=True) is True
                assert explicit_get.call_args.kwargs["verify"] is True


class TestCookieLoadersDefaultVerification:
    """Both cookie loaders verify certificates unless the environment opts out."""

    def test_load_cookies_from_file_defaults_to_verified_tls(self, temp_session_path, monkeypatch):
        monkeypatch.delenv("CIS_BENCH_VERIFY_SSL", raising=False)
        cj = http.cookiejar.MozillaCookieJar(str(temp_session_path))
        cj.set_cookie(_workbench_cookie())
        cj.save(ignore_discard=True, ignore_expires=True)

        session = AuthManager.load_cookies_from_file(str(temp_session_path))

        assert session.verify is True

    def test_load_cookies_from_browser_defaults_to_verified_tls(self, monkeypatch):
        monkeypatch.delenv("CIS_BENCH_VERIFY_SSL", raising=False)
        jar = http.cookiejar.CookieJar()
        jar.set_cookie(_workbench_cookie("workbench_session", "wb-1"))

        with patch("cis_bench.fetcher.auth.browser_cookie3.chrome", return_value=jar):
            session = AuthManager.load_cookies_from_browser("chrome")

        assert session.verify is True
        assert {c.name for c in session.cookies} == {"workbench_session"}
