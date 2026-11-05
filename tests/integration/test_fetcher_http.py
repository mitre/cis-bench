"""WorkBench request policy against a real local server: urllib3 retries and the per-host rate limit.

The session comes from fetcher.http.new_workbench_session, so each request goes through the
adapter cis-bench mounts for WorkBench: requests-ratelimiter's LimiterAdapter carrying a
urllib3 Retry.
"""

import logging
import threading
import time
from unittest.mock import patch

import pytest
import requests

from cis_bench.config import USER_AGENT
from cis_bench.exceptions import FetchError
from cis_bench.fetcher import http
from cis_bench.fetcher.auth import AuthManager
from cis_bench.fetcher.http import ThreadSessions, get_with_retry, new_workbench_session
from tests.conftest import LocalHTTPServer

TIMEOUT = (5, 5)
WORKBENCH_URL = "https://workbench.cisecurity.org"


class _ScriptedServer(LocalHTTPServer):
    """Answers GETs from a script of (status, headers, delay_seconds) and records arrival times."""

    def __init__(self, script):
        self.script = list(script)
        self.arrivals: list[float] = []
        self.user_agents: list[str] = []
        self._lock = threading.Lock()
        super().__init__(self._respond)

    def _respond(self, handler):
        with self._lock:
            self.arrivals.append(time.monotonic())
            self.user_agents.append(handler.headers.get("User-Agent", ""))
            status, headers, delay = self.script.pop(0) if self.script else (200, {}, 0)
        if delay:
            time.sleep(delay)
        body = b"ok"
        handler.send_response(status)
        for name, value in headers.items():
            handler.send_header(name, value)
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)


@pytest.fixture
def quick_backoff(monkeypatch):
    """Shrink urllib3's backoff for tests about how many attempts run, not how long they wait."""
    monkeypatch.setattr(http, "RETRY_BACKOFF_FACTOR", 0.01)
    monkeypatch.setattr(http, "RETRY_JITTER_SECONDS", 0.0)


class TestRetries:
    def test_a_503_with_retry_after_is_retried_after_the_requested_wait(self):
        with _ScriptedServer([(503, {"Retry-After": "1"}, 0), (200, {}, 0)]) as server:
            response = get_with_retry(
                new_workbench_session(), server.base_url + "/p", timeout=TIMEOUT
            )

        assert response.status_code == 200
        assert len(server.arrivals) == 2
        assert server.arrivals[1] - server.arrivals[0] >= 1.0

    def test_a_429_without_retry_after_is_retried(self):
        # urllib3 retries a 429 that carries Retry-After whatever the status list says;
        # one without the header is retried only because the list names 429.
        with _ScriptedServer([(429, {}, 0), (200, {}, 0)]) as server:
            response = get_with_retry(
                new_workbench_session(), server.base_url + "/p", timeout=TIMEOUT
            )

        assert response.status_code == 200
        assert len(server.arrivals) == 2

    def test_three_failed_attempts_raise_fetch_error_naming_the_url(self, quick_backoff):
        script = [(502, {}, 0), (503, {}, 0), (504, {}, 0)]
        with _ScriptedServer(script) as server:
            url = server.base_url + "/p"
            with pytest.raises(FetchError) as caught:
                get_with_retry(new_workbench_session(), url, timeout=TIMEOUT)

        assert len(server.arrivals) == 3
        assert url in str(caught.value)
        assert "3 attempts" in str(caught.value)

    def test_a_404_is_not_retried(self):
        with _ScriptedServer([(404, {}, 0)]) as server:
            with pytest.raises(requests.HTTPError):
                get_with_retry(new_workbench_session(), server.base_url + "/p", timeout=TIMEOUT)

        assert len(server.arrivals) == 1

    def test_a_read_timeout_is_retried(self):
        with _ScriptedServer([(200, {}, 1.0), (200, {}, 0)]) as server:
            response = get_with_retry(
                new_workbench_session(), server.base_url + "/p", timeout=(5, 0.3)
            )

        assert response.status_code == 200
        assert len(server.arrivals) == 2

    def test_a_refused_connection_is_retried_then_reported(self, quick_backoff):
        with _ScriptedServer([]) as server:
            closed_url = server.base_url + "/p"
        # the server is shut down: every attempt is refused
        with pytest.raises(FetchError) as caught:
            get_with_retry(new_workbench_session(), closed_url, timeout=(1, 1))

        assert closed_url in str(caught.value)

    def test_each_retry_logs_one_warning_with_the_url_attempt_and_wait(self, caplog):
        caplog.set_level(logging.WARNING, logger="cis_bench.fetcher.http")
        with _ScriptedServer([(503, {"Retry-After": "1"}, 0), (200, {}, 0)]) as server:
            url = server.base_url + "/p"
            get_with_retry(new_workbench_session(), url, timeout=TIMEOUT)

        retries = [r for r in caplog.records if r.name == "cis_bench.fetcher.http"]
        assert len(retries) == 1
        message = retries[0].getMessage()
        assert retries[0].levelno == logging.WARNING
        assert url in message
        assert "attempt 1/3" in message
        assert "retrying in 1.0s" in message

    def test_a_long_retry_after_is_capped(self, monkeypatch):
        monkeypatch.setattr(http, "RETRY_AFTER_MAX_SECONDS", 1)
        with _ScriptedServer([(503, {"Retry-After": "3600"}, 0), (200, {}, 0)]) as server:
            started = time.monotonic()
            response = get_with_retry(
                new_workbench_session(), server.base_url + "/p", timeout=TIMEOUT
            )

        assert response.status_code == 200
        assert time.monotonic() - started < 5


class TestRateLimit:
    def test_threads_sharing_a_session_stay_within_the_per_host_rate(self, monkeypatch):
        monkeypatch.setattr(http, "WORKBENCH_REQUESTS_PER_SECOND", 3)
        sessions = ThreadSessions(new_workbench_session())
        with _ScriptedServer([]) as server:

            def fetch():
                for _ in range(3):
                    get_with_retry(sessions.current(), server.base_url + "/p", timeout=TIMEOUT)

            workers = [threading.Thread(target=fetch) for _ in range(3)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join()

        arrivals = sorted(server.arrivals)
        assert len(arrivals) == 9
        # at most 3 requests in any one-second window
        for index in range(len(arrivals) - 3):
            assert arrivals[index + 3] - arrivals[index] >= 0.95

    def test_the_rate_can_be_lowered_for_a_session(self):
        with _ScriptedServer([]) as server:
            session = new_workbench_session(requests_per_second=1)
            started = time.monotonic()
            for _ in range(3):
                get_with_retry(session, server.base_url + "/p", timeout=TIMEOUT)

        assert time.monotonic() - started >= 1.9


class TestALoweredRateCoversTheSessionCheck:
    """A rate given to AuthManager paces the session check and every later request."""

    @pytest.mark.parametrize("source", ["saved-session", "browser"])
    def test_the_session_check_and_later_requests_follow_the_rate(self, tmp_path, source):
        session_file = tmp_path / "session.cookies"
        if source == "saved-session":
            session_file.write_text(
                "# Netscape HTTP Cookie File\n"
                ".cisecurity.org\tTRUE\t/\tTRUE\t0\tworkbench_session\tsaved\n"
            )
        browser_cookies = [
            requests.cookies.create_cookie("workbench_session", "fresh", domain=".cisecurity.org")
        ]
        with _ScriptedServer([]) as server:
            auth = AuthManager(
                workbench_url=server.base_url,
                verify_ssl=True,
                session_file=session_file,
                requests_per_second=1,
            )
            with patch(
                "cis_bench.fetcher.auth.browser_cookie3.firefox", return_value=browser_cookies
            ):
                session = auth.get_or_create_session(
                    browser="firefox", force_refresh=source == "browser"
                )
            for _ in range(2):
                get_with_retry(session, server.base_url + "/p", timeout=TIMEOUT)

        # the session check's GET, then two more: one per second
        assert len(server.arrivals) == 3
        assert server.arrivals[2] - server.arrivals[0] >= 1.9

    def test_the_windows_browser_fallback_keeps_the_rate(self, tmp_path):
        auth = AuthManager(
            workbench_url=WORKBENCH_URL,
            verify_ssl=True,
            session_file=tmp_path / "session.cookies",
            requests_per_second=1,
        )
        with (
            patch("platform.system", return_value="Windows"),
            patch(
                "cis_bench.fetcher.auth.browser_cookie3.chrome",
                side_effect=Exception("This operation requires admin. Please run as admin."),
            ),
            patch("cis_bench.fetcher.auth.browser_cookie3.firefox", return_value=[]),
        ):
            session = auth.load_cookies_from_browser("chrome", try_fallback=True)
        with _ScriptedServer([]) as server:
            started = time.monotonic()
            for _ in range(3):
                get_with_retry(session, server.base_url + "/p", timeout=TIMEOUT)

        assert time.monotonic() - started >= 1.9


def _auth(tmp_path):
    return AuthManager(
        workbench_url=WORKBENCH_URL, verify_ssl=True, session_file=tmp_path / "session.cookies"
    )


def _session_from_browser(tmp_path):
    with patch("cis_bench.fetcher.auth.browser_cookie3.firefox", return_value=[]):
        return _auth(tmp_path).load_cookies_from_browser("firefox")


def _session_from_cookie_file(tmp_path):
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text("# Netscape HTTP Cookie File\n")
    return _auth(tmp_path).load_cookies_from_file(str(cookie_file))


class TestSessionsAuthManagerCreates:
    """Every session the login paths create carries the WorkBench retry and rate policy."""

    @pytest.mark.parametrize(
        "make_session",
        [_session_from_browser, _session_from_cookie_file],
        ids=["browser", "cookie-file"],
    )
    def test_the_session_retries_a_503(self, tmp_path, make_session):
        session = make_session(tmp_path)
        with _ScriptedServer([(503, {"Retry-After": "0"}, 0), (200, {}, 0)]) as server:
            response = get_with_retry(session, server.base_url + "/p", timeout=TIMEOUT)

        assert response.status_code == 200
        assert len(server.arrivals) == 2


class TestUserAgent:
    def test_every_request_from_a_workbench_session_names_cis_bench(self):
        with _ScriptedServer([(503, {"Retry-After": "0"}, 0), (200, {}, 0)]) as server:
            get_with_retry(new_workbench_session(), server.base_url + "/p", timeout=TIMEOUT)

        assert server.user_agents == [USER_AGENT, USER_AGENT]
