"""Unit tests for session persistence in AuthManager."""

import http.cookiejar
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from cis_bench.config import RequestPolicy
from cis_bench.exceptions import AuthenticationError, NoSavedSessionError, TLSVerificationError
from cis_bench.fetcher.auth import AuthManager

POLICY = RequestPolicy(requests_per_second=3.0, retries=2, backoff_factor=1.0, jitter_seconds=0.5)


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


WORKBENCH_URL = "https://workbench.cisecurity.org"


@pytest.fixture
def temp_session_path(tmp_path):
    """Create temporary session file path."""
    return tmp_path / "session.cookies"


@pytest.fixture
def auth(temp_session_path):
    """An AuthManager for production WorkBench that verifies TLS and saves to a temp file."""
    return AuthManager(
        workbench_url=WORKBENCH_URL,
        verify_ssl=True,
        session_file=temp_session_path,
        request_policy=POLICY,
        timeout=(10.0, 30.0),
    )


# ============================================================================
# Tests: Save Session
# ============================================================================


class TestSaveSession:
    """Test session saving functionality."""

    def test_save_session_creates_file(self, auth, temp_session_path):
        """save_session creates cookie file."""
        session = requests.Session()
        session.cookies.set("test_cookie", "test_value", domain="example.com")

        auth.save_session(session)

        assert temp_session_path.exists()

    def test_save_session_creates_parent_directory(self, tmp_path):
        """save_session creates parent directories if needed."""
        session_path = tmp_path / "subdir" / "another" / "session.cookies"
        session = requests.Session()
        session.cookies.set("test", "value")
        auth = AuthManager(
            workbench_url=WORKBENCH_URL,
            verify_ssl=True,
            session_file=session_path,
            request_policy=POLICY,
            timeout=(10.0, 30.0),
        )

        auth.save_session(session)

        assert session_path.exists()
        assert session_path.parent.exists()


# ============================================================================
# Tests: Load Saved Session
# ============================================================================


class TestLoadSavedSession:
    """Test loading saved sessions."""

    def test_load_saved_session_returns_none_if_no_file(self, auth):
        """load_saved_session returns None when file doesn't exist."""
        result = auth.load_saved_session()

        assert result is None

    def test_load_saved_session_returns_session_with_cookies(self, temp_session_path):
        """load_saved_session returns session with cookies."""
        cj = http.cookiejar.MozillaCookieJar(str(temp_session_path))
        cj.set_cookie(_workbench_cookie())
        cj.save(ignore_discard=True, ignore_expires=True)
        auth = AuthManager(
            workbench_url=WORKBENCH_URL,
            verify_ssl=False,
            session_file=temp_session_path,
            request_policy=POLICY,
            timeout=(10.0, 30.0),
        )

        session = auth.load_saved_session()

        assert session is not None
        assert len(list(session.cookies)) > 0
        assert session.verify is False


# ============================================================================
# Tests: Clear Saved Session
# ============================================================================


class TestClearSavedSession:
    """Test clearing saved sessions."""

    def test_clear_saved_session_removes_file(self, auth, temp_session_path):
        """clear_saved_session removes the session file."""
        temp_session_path.touch()

        result = auth.clear_saved_session()

        assert result is True
        assert not temp_session_path.exists()

    def test_clear_saved_session_returns_false_if_no_file(self, auth):
        """clear_saved_session returns False when no file exists."""
        result = auth.clear_saved_session()

        assert result is False


# ============================================================================
# Tests: Validate Session
# ============================================================================


class TestValidateSession:
    """Test session validation."""

    def test_validate_session_returns_false_for_none(self, auth):
        """validate_session returns False for None session."""
        result = auth.validate_session(None)
        assert result is False

    def test_validate_session_returns_false_for_empty_cookies(self, auth):
        """validate_session returns False when no cookies."""
        session = requests.Session()
        result = auth.validate_session(session)
        assert result is False

    def test_validate_session_makes_test_request(self, temp_session_path):
        """validate_session makes request to WorkBench."""
        auth = AuthManager(
            workbench_url=WORKBENCH_URL,
            verify_ssl=False,
            session_file=temp_session_path,
            request_policy=POLICY,
            timeout=(10.0, 30.0),
        )
        session = requests.Session()
        session.cookies.set("test", "value")

        with patch.object(session, "get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = (
                "<html><body><h1>Benchmarks</h1><table></table></body></html>"  # Not login page
            )
            mock_get.return_value = mock_response

            result = auth.validate_session(session)

            assert result is True
            mock_get.assert_called_once()
            assert "workbench.cisecurity.org" in mock_get.call_args[0][0]

    def test_validate_session_detects_login_redirect(self, temp_session_path):
        """validate_session returns False on login redirect to /login."""
        auth = AuthManager(
            workbench_url=WORKBENCH_URL,
            verify_ssl=False,
            session_file=temp_session_path,
            request_policy=POLICY,
            timeout=(10.0, 30.0),
        )
        session = requests.Session()
        session.cookies.set("test", "value")

        with patch.object(session, "get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 302
            mock_response.headers = {"Location": "https://workbench.cisecurity.org/login"}
            mock_get.return_value = mock_response

            result = auth.validate_session(session)

            assert result is False

    def test_validate_session_detects_homepage_redirect(self, temp_session_path):
        """validate_session returns False on redirect to homepage (unauthenticated)."""
        auth = AuthManager(
            workbench_url=WORKBENCH_URL,
            verify_ssl=False,
            session_file=temp_session_path,
            request_policy=POLICY,
            timeout=(10.0, 30.0),
        )
        session = requests.Session()
        session.cookies.set("test", "value")

        with patch.object(session, "get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 302
            mock_response.headers = {"Location": "https://workbench.cisecurity.org"}
            mock_get.return_value = mock_response

            result = auth.validate_session(session)

            assert result is False  # Any redirect means invalid session

    def test_validate_session_detects_login_page_html(self, temp_session_path):
        """validate_session returns False when receiving login page HTML."""
        auth = AuthManager(
            workbench_url=WORKBENCH_URL,
            verify_ssl=False,
            session_file=temp_session_path,
            request_policy=POLICY,
            timeout=(10.0, 30.0),
        )
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

            result = auth.validate_session(session)

            assert result is False  # Should detect login page and return False

    def test_validate_session_completes_cis_portal_auth0_sso_handshake(self, auth):
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

            result = auth.validate_session(session)

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

    def test_validate_session_verifies_benchmarks_when_sso_lands_on_dashboard(
        self, temp_session_path
    ):
        """validate_session confirms /benchmarks access when OIDC callback lands on /dashboard."""
        auth = AuthManager(
            workbench_url=WORKBENCH_URL,
            verify_ssl=False,
            session_file=temp_session_path,
            request_policy=POLICY,
            timeout=(10.0, 30.0),
        )
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
            assert auth.validate_session(session) is True

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
        self, auth, bad_location: str
    ):
        """validate_session stops immediately on Auth0 login, untrusted hosts, HTTP, or empty Location."""
        session = requests.Session()
        session.cookies.set("auth0", "sso-cookie", domain="auth.portal.cisecurity.org")

        first = Mock(status_code=302, headers={"Location": "https://workbench.cisecurity.org"})
        second = Mock(status_code=302, headers={"Location": bad_location})

        with patch.object(session, "get", side_effect=[first, second]) as mock_get:
            assert auth.validate_session(session) is False

        assert mock_get.call_count == 2

    def test_validate_session_rejects_200_on_auth_portal_host_or_excessive_redirects(self, auth):
        """validate_session rejects 200 OK served on auth.portal.cisecurity.org and bounded redirect loops."""
        session = requests.Session()
        session.cookies.set("auth0", "sso-cookie", domain="auth.portal.cisecurity.org")

        to_auth = Mock(
            status_code=302,
            headers={"Location": "https://auth.portal.cisecurity.org/authorize?state=1"},
        )
        auth_html = Mock(status_code=200, headers={}, text="<html><body>Consent</body></html>")

        with patch.object(session, "get", side_effect=[to_auth, auth_html]) as auth_get:
            assert auth.validate_session(session) is False
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
            assert auth.validate_session(session) is False
        assert 2 <= loop_get.call_count <= 9

    def test_validate_session_honors_configured_workbench_base_url(self, temp_session_path):
        """validate_session targets the WorkBench URL it was built with and allows QA Auth0 SSO onto that host."""
        auth = AuthManager(
            workbench_url="https://workbench-staging.cisecurity.org",
            verify_ssl=False,
            session_file=temp_session_path,
            request_policy=POLICY,
            timeout=(10.0, 30.0),
        )
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
            assert auth.validate_session(session) is True

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
            assert auth.validate_session(session) is False

    # ============================================================================
    # Tests: Get or Create Session
    # ============================================================================

    def test_validate_session_raises_tls_error_when_certificate_verification_fails(self, auth):
        """A TLS trust failure is reported as such, never as an expired session."""
        session = requests.Session()
        session.cookies.set("test", "value")

        with patch.object(session, "get") as mock_get:
            mock_get.side_effect = requests.exceptions.SSLError(
                "certificate verify failed: unable to get local issuer certificate"
            )

            with pytest.raises(TLSVerificationError) as exc_info:
                auth.validate_session(session)

        message = str(exc_info.value)
        assert "workbench.cisecurity.org" in message
        assert "unable to get local issuer certificate" in message
        assert "REQUESTS_CA_BUNDLE" in message
        assert "CIS_BENCH_VERIFY_SSL=false" in message
        assert isinstance(exc_info.value.__cause__, requests.exceptions.SSLError)

    @pytest.mark.parametrize(
        "failure",
        [
            requests.exceptions.ConnectionError("connection refused"),
            requests.exceptions.Timeout("Read timed out"),
            requests.exceptions.ChunkedEncodingError("connection broken"),
        ],
        ids=["connection", "timeout", "broken-body"],
    )
    def test_a_network_failure_is_a_fetch_error_naming_the_url_not_a_rejection(self, auth, failure):
        """WorkBench could not be asked, so nothing is known about the session."""
        from cis_bench.exceptions import FetchError

        session = requests.Session()
        session.cookies.set("test", "value")

        with patch.object(session, "get", side_effect=failure):
            with pytest.raises(FetchError) as raised:
                auth.validate_session(session)

        assert raised.value.url == f"{WORKBENCH_URL}/benchmarks"
        assert raised.value.__cause__ is failure
        assert not isinstance(raised.value, AuthenticationError)

    @pytest.mark.parametrize("status", [429, 500, 502, 503, 504, 404])
    def test_an_error_status_is_a_fetch_error_not_a_rejection(self, auth, status):
        """A server error says nothing about whether the session is still accepted."""
        from cis_bench.exceptions import FetchError

        session = requests.Session()
        session.cookies.set("test", "value")
        answer = Mock(status_code=status, headers={}, text="")

        with patch.object(session, "get", return_value=answer):
            with pytest.raises(FetchError) as raised:
                auth.validate_session(session)

        assert raised.value.url == f"{WORKBENCH_URL}/benchmarks"
        assert f"HTTP {status}" in str(raised.value)

    @pytest.mark.parametrize(("status", "attempts"), [(503, 3), (429, 3), (500, 1), (404, 1)])
    def test_the_error_counts_the_attempts_the_sessions_adapter_made(self, auth, status, attempts):
        """A status the adapter retries was tried retries + 1 times; any other status once."""
        from cis_bench.exceptions import FetchError
        from cis_bench.fetcher.http import new_workbench_session

        session = new_workbench_session(POLICY)  # POLICY retries twice
        session.cookies.set("test", "value")
        answer = Mock(status_code=status, headers={}, text="")

        with patch.object(session, "get", return_value=answer):
            with pytest.raises(FetchError) as raised:
                auth.validate_session(session)

        assert raised.value.attempts == attempts

    @pytest.mark.parametrize("status", [401, 403])
    def test_a_401_or_403_is_a_rejection(self, auth, status):
        session = requests.Session()
        session.cookies.set("test", "value")
        answer = Mock(status_code=status, headers={}, text="")

        with patch.object(session, "get", return_value=answer):
            assert auth.validate_session(session) is False

    @pytest.mark.parametrize(
        ("status", "outcome"),
        [(503, "unanswered"), (500, "unanswered"), (302, "rejected"), (403, "rejected")],
    )
    def test_the_benchmarks_request_after_the_sso_handshake_is_judged_the_same_way(
        self, auth, status, outcome
    ):
        """After SSO lands on the dashboard, /benchmarks is asked once more."""
        from cis_bench.exceptions import FetchError

        session = requests.Session()
        session.cookies.set("test", "value")
        answers = [
            Mock(status_code=302, headers={"Location": f"{WORKBENCH_URL}/dashboard"}, text=""),
            Mock(status_code=200, headers={}, text="<html>dashboard</html>"),
            Mock(status_code=status, headers={"Location": "/login"}, text=""),
        ]

        with patch.object(session, "get", side_effect=answers):
            if outcome == "rejected":
                assert auth.validate_session(session) is False
            else:
                with pytest.raises(FetchError) as raised:
                    auth.validate_session(session)
                assert raised.value.url == f"{WORKBENCH_URL}/benchmarks"
                assert f"HTTP {status}" in str(raised.value)

    def test_a_failure_part_way_through_the_sso_walk_names_the_url_that_failed(self, auth):
        from cis_bench.exceptions import FetchError

        session = requests.Session()
        session.cookies.set("test", "value")
        dashboard = f"{WORKBENCH_URL}/dashboard"
        to_dashboard = Mock(status_code=302, headers={"Location": dashboard}, text="")

        with patch.object(
            session,
            "get",
            side_effect=[to_dashboard, requests.exceptions.Timeout("Read timed out")],
        ):
            with pytest.raises(FetchError) as at_the_second_hop:
                auth.validate_session(session)
        assert at_the_second_hop.value.url == dashboard

        landed = Mock(status_code=200, headers={}, text="<html>dashboard</html>")
        with patch.object(
            session,
            "get",
            side_effect=[to_dashboard, landed, requests.exceptions.ConnectionError("reset")],
        ):
            with pytest.raises(FetchError) as at_the_last_request:
                auth.validate_session(session)
        assert at_the_last_request.value.url == f"{WORKBENCH_URL}/benchmarks"

    def test_every_request_of_the_check_uses_the_given_timeout(self, temp_session_path):
        """The SSO walk and the final /benchmarks request all wait as long as the caller says."""
        auth = AuthManager(
            workbench_url=WORKBENCH_URL,
            verify_ssl=True,
            session_file=temp_session_path,
            request_policy=POLICY,
            timeout=(4.0, 7.0),
        )
        session = requests.Session()
        session.cookies.set("test", "value")
        answers = [
            Mock(status_code=302, headers={"Location": f"{WORKBENCH_URL}/dashboard"}, text=""),
            Mock(status_code=200, headers={}, text="<html>dashboard</html>"),
            Mock(status_code=200, headers={}, text="<html>benchmarks</html>"),
        ]

        with patch.object(session, "get", side_effect=answers) as mock_get:
            assert auth.validate_session(session) is True

        assert mock_get.call_count == 3
        assert [call.kwargs["timeout"] for call in mock_get.call_args_list] == [(4.0, 7.0)] * 3


class TestGetOrCreateSession:
    """Test get_or_create_session logic."""

    def test_get_or_create_uses_saved_session_when_valid(self, auth):
        """get_or_create_session uses saved session when valid."""
        with patch("cis_bench.fetcher.auth.AuthManager.load_saved_session") as mock_load:
            with patch("cis_bench.fetcher.auth.AuthManager.validate_session") as mock_validate:
                mock_session = Mock()
                mock_load.return_value = mock_session
                mock_validate.return_value = True

                result = auth.get_or_create_session()

                assert result == mock_session
                mock_load.assert_called_once()
                mock_validate.assert_called_once()

    def test_get_or_create_raises_typed_error_when_no_session_and_no_browser(self, auth):
        """No saved session and no browser is a typed authentication condition, not a ValueError."""
        with patch("cis_bench.fetcher.auth.AuthManager.load_saved_session") as mock_load:
            mock_load.return_value = None

            with pytest.raises(NoSavedSessionError) as exc_info:
                auth.get_or_create_session()

            assert isinstance(exc_info.value, AuthenticationError)
            assert not isinstance(exc_info.value, ValueError)

            assert "No saved session" in str(exc_info.value)
            assert "auth login" in str(exc_info.value)

    def test_get_or_create_creates_new_session_when_saved_invalid(self, auth):
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

                            result = auth.get_or_create_session(browser="chrome")

                            assert result == new_session
                            mock_clear.assert_called_once()
                            mock_browser.assert_called_once()
                            mock_save.assert_called_once()

    def test_get_or_create_force_refresh_skips_saved_session(self, auth):
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

                        result = auth.get_or_create_session(browser="chrome", force_refresh=True)

                        # Should NOT call load_saved_session
                        mock_load.assert_not_called()
                        # Should create new session
                        mock_browser.assert_called_once()

    def test_get_or_create_session_raises_authentication_error_when_browser_session_invalid(
        self, auth
    ):
        """Fresh browser cookies that WorkBench rejects are an authentication failure, typed."""
        browser_session = requests.Session()
        browser_session.cookies.set("stale", "1", domain="workbench.cisecurity.org")
        with (
            patch.object(AuthManager, "load_cookies_from_browser", return_value=browser_session),
            patch.object(AuthManager, "validate_session", return_value=False),
            patch.object(AuthManager, "save_session") as mock_save,
        ):
            with pytest.raises(AuthenticationError, match="workbench.cisecurity.org"):
                auth.get_or_create_session(browser="chrome")

        mock_save.assert_not_called()


class TestTheSavedSessionSurvivesAnUnreachableWorkBench:
    """Only WorkBench rejecting the session deletes it; a failure to ask leaves the file alone."""

    @staticmethod
    def _save_a_session(auth):
        saved = requests.Session()
        saved.cookies.set("sid", "value", domain="workbench.cisecurity.org")
        auth.save_session(saved)

    def test_a_network_failure_raises_and_keeps_the_session_file(self, auth, temp_session_path):
        from cis_bench.exceptions import FetchError

        self._save_a_session(auth)

        with patch(
            "requests.Session.get", side_effect=requests.exceptions.ConnectionError("no route")
        ):
            with pytest.raises(FetchError):
                auth.get_or_create_session()

        assert temp_session_path.exists()

    def test_a_server_error_raises_and_keeps_the_session_file(self, auth, temp_session_path):
        from cis_bench.exceptions import FetchError

        self._save_a_session(auth)

        with patch("requests.Session.get", return_value=Mock(status_code=503, headers={}, text="")):
            with pytest.raises(FetchError):
                auth.get_or_create_session()

        assert temp_session_path.exists()

    def test_a_rejected_session_is_deleted(self, auth, temp_session_path):
        self._save_a_session(auth)
        to_login = Mock(status_code=302, headers={"Location": "/login"}, text="")

        with patch("requests.Session.get", return_value=to_login):
            with pytest.raises(NoSavedSessionError):
                auth.get_or_create_session()

        assert not temp_session_path.exists()


class TestSessionsCarryTheGivenVerifySsl:
    """Every session an AuthManager makes carries the verify_ssl it was built with."""

    @pytest.mark.parametrize("verify_ssl", [True, False], ids=["verifies", "opt-out"])
    def test_every_session_carries_the_verify_ssl_it_was_built_with(
        self, temp_session_path, verify_ssl
    ):
        auth = AuthManager(
            workbench_url=WORKBENCH_URL,
            verify_ssl=verify_ssl,
            session_file=temp_session_path,
            request_policy=POLICY,
            timeout=(10.0, 30.0),
        )
        cj = http.cookiejar.MozillaCookieJar(str(temp_session_path))
        cj.set_cookie(_workbench_cookie())
        cj.save(ignore_discard=True, ignore_expires=True)

        from_file = auth.load_cookies_from_file(str(temp_session_path))
        assert from_file.verify is verify_ssl

        saved = auth.load_saved_session()
        assert saved is not None
        assert saved.verify is verify_ssl

        jar = http.cookiejar.CookieJar()
        jar.set_cookie(_workbench_cookie("workbench_session", "wb-1"))
        with patch("cis_bench.fetcher.auth.browser_cookie3.chrome", return_value=jar):
            from_browser = auth.load_cookies_from_browser("chrome")
        assert from_browser.verify is verify_ssl
        assert {c.name for c in from_browser.cookies} == {"workbench_session"}

        ok_resp = Mock(
            status_code=200,
            headers={},
            text="<html><body><h1>Benchmarks</h1><table></table></body></html>",
        )
        with patch("requests.Session.get", return_value=ok_resp) as mock_get:
            session = auth.get_or_create_session()
        assert session.verify is verify_ssl
        assert mock_get.call_args.kwargs["verify"] is verify_ssl
