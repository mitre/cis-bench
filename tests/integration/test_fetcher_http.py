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

from cis_bench.config import USER_AGENT, RequestPolicy
from cis_bench.exceptions import FetchError
from cis_bench.fetcher import http
from cis_bench.fetcher.auth import AuthManager
from cis_bench.fetcher.http import ThreadSessions, get_with_retry, new_workbench_session
from tests.conftest import LocalHTTPServer

TIMEOUT = (5, 5)
WORKBENCH_URL = "https://workbench.cisecurity.org"
# The policy these tests send with, and a copy that barely waits between attempts.
POLICY = RequestPolicy(requests_per_second=3.0, retries=2, backoff_factor=1.0, jitter_seconds=0.5)
QUICK = RequestPolicy(requests_per_second=3.0, retries=2, backoff_factor=0.01, jitter_seconds=0.0)
ONE_PER_SECOND = RequestPolicy(
    requests_per_second=1.0, retries=2, backoff_factor=1.0, jitter_seconds=0.5
)


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


class TestRetries:
    def test_a_503_with_retry_after_is_retried_after_the_requested_wait(self):
        with _ScriptedServer([(503, {"Retry-After": "1"}, 0), (200, {}, 0)]) as server:
            response = get_with_retry(
                new_workbench_session(POLICY), server.base_url + "/p", timeout=TIMEOUT
            )

        assert response.status_code == 200
        assert len(server.arrivals) == 2
        assert server.arrivals[1] - server.arrivals[0] >= 1.0

    def test_a_429_without_retry_after_is_retried(self):
        # urllib3 retries a 429 that carries Retry-After whatever the status list says;
        # one without the header is retried only because the list names 429.
        with _ScriptedServer([(429, {}, 0), (200, {}, 0)]) as server:
            response = get_with_retry(
                new_workbench_session(POLICY), server.base_url + "/p", timeout=TIMEOUT
            )

        assert response.status_code == 200
        assert len(server.arrivals) == 2

    def test_three_failed_attempts_raise_fetch_error_naming_the_url(self):
        script = [(502, {}, 0), (503, {}, 0), (504, {}, 0)]
        with _ScriptedServer(script) as server:
            url = server.base_url + "/p"
            with pytest.raises(FetchError) as caught:
                get_with_retry(new_workbench_session(QUICK), url, timeout=TIMEOUT)

        assert len(server.arrivals) == 3
        assert url in str(caught.value)
        assert "3 attempts" in str(caught.value)

    def test_a_404_is_not_retried(self):
        with _ScriptedServer([(404, {}, 0)]) as server:
            with pytest.raises(requests.HTTPError):
                get_with_retry(
                    new_workbench_session(POLICY), server.base_url + "/p", timeout=TIMEOUT
                )

        assert len(server.arrivals) == 1

    def test_a_read_timeout_is_retried(self):
        with _ScriptedServer([(200, {}, 1.0), (200, {}, 0)]) as server:
            response = get_with_retry(
                new_workbench_session(POLICY), server.base_url + "/p", timeout=(5, 0.3)
            )

        assert response.status_code == 200
        assert len(server.arrivals) == 2

    def test_a_refused_connection_is_retried_then_reported(self):
        with _ScriptedServer([]) as server:
            closed_url = server.base_url + "/p"
        # the server is shut down: every attempt is refused
        with pytest.raises(FetchError) as caught:
            get_with_retry(new_workbench_session(POLICY), closed_url, timeout=(1, 1))

        assert closed_url in str(caught.value)

    def test_each_retry_logs_one_warning_with_the_url_attempt_and_wait(self, caplog):
        caplog.set_level(logging.WARNING, logger="cis_bench.fetcher.http")
        with _ScriptedServer([(503, {"Retry-After": "1"}, 0), (200, {}, 0)]) as server:
            url = server.base_url + "/p"
            get_with_retry(new_workbench_session(POLICY), url, timeout=TIMEOUT)

        retries = [r for r in caplog.records if r.name == "cis_bench.fetcher.http"]
        assert len(retries) == 1
        message = retries[0].getMessage()
        assert retries[0].levelno == logging.WARNING
        assert url in message
        assert "attempt 1/3" in message
        assert "retrying in 1.0s" in message

    def test_the_retry_warning_shows_the_page_number_but_no_other_query_parameter(self, caplog):
        caplog.set_level(logging.WARNING, logger="cis_bench.fetcher.http")
        with _ScriptedServer([(503, {}, 0), (200, {}, 0)]) as server:
            url = server.base_url + "/benchmarks?page=2&code=SECRET&state=NONCE"
            get_with_retry(new_workbench_session(QUICK), url, timeout=TIMEOUT)

        (warning,) = [r.getMessage() for r in caplog.records if r.name == "cis_bench.fetcher.http"]
        assert "/benchmarks?page=2:" in warning
        assert "SECRET" not in warning
        assert "NONCE" not in warning

    def test_a_request_that_fails_for_good_names_its_url_without_other_query_parameters(self):
        """The error for a refused connection quotes the URL and the library's message."""
        with _ScriptedServer([]) as server:
            dead = server.base_url
        url = dead + "/benchmarks?page=2&code=SECRET&state=NONCE"

        with pytest.raises(FetchError) as raised:
            get_with_retry(new_workbench_session(QUICK), url, timeout=TIMEOUT)

        assert raised.value.url == dead + "/benchmarks?page=2"
        assert "SECRET" not in str(raised.value)
        assert "NONCE" not in str(raised.value)

    def test_the_cli_logging_setup_leaves_no_second_retry_line_with_the_raw_url(self, capfd):
        """urllib3 logs each connection retry itself, with the path and query as sent."""
        from cis_bench.utils.logging_config import LoggingConfig

        with _ScriptedServer([]) as server:
            dead = server.base_url
        root = logging.getLogger()
        handlers, level = root.handlers[:], root.level
        pool_logger = logging.getLogger("urllib3.connectionpool")
        pool_level = pool_logger.level
        try:
            LoggingConfig.setup_from_flags(quiet=True)
            with pytest.raises(FetchError):
                get_with_retry(
                    new_workbench_session(QUICK),
                    dead + "/auth0/callback?code=SECRET&state=NONCE",
                    timeout=TIMEOUT,
                )
        finally:
            root.handlers[:] = handlers
            root.setLevel(level)
            pool_logger.setLevel(pool_level)

        printed = capfd.readouterr().err
        assert printed.count("Request failed (attempt") == 2  # our own line, once per retry
        assert "SECRET" not in printed
        assert "NONCE" not in printed

    def test_a_long_retry_after_is_capped(self, monkeypatch):
        monkeypatch.setattr(http, "RETRY_AFTER_MAX_SECONDS", 1)
        with _ScriptedServer([(503, {"Retry-After": "3600"}, 0), (200, {}, 0)]) as server:
            started = time.monotonic()
            response = get_with_retry(
                new_workbench_session(POLICY), server.base_url + "/p", timeout=TIMEOUT
            )

        assert response.status_code == 200
        assert time.monotonic() - started < 5


class TestTheGivenPolicyDrivesTheSession:
    """Retries, backoff and jitter come from the RequestPolicy the session was built with."""

    def test_zero_retries_means_one_attempt(self):
        policy = RequestPolicy(
            requests_per_second=3.0, retries=0, backoff_factor=0.0, jitter_seconds=0.0
        )
        with _ScriptedServer([(503, {}, 0), (200, {}, 0)]) as server:
            url = server.base_url + "/p"
            with pytest.raises(FetchError) as caught:
                get_with_retry(new_workbench_session(policy), url, timeout=TIMEOUT)

        assert len(server.arrivals) == 1
        assert caught.value.attempts == 1

    def test_more_retries_mean_more_attempts(self):
        policy = RequestPolicy(
            requests_per_second=50.0, retries=4, backoff_factor=0.0, jitter_seconds=0.0
        )
        with _ScriptedServer([(503, {}, 0)] * 5) as server:
            with pytest.raises(FetchError) as caught:
                get_with_retry(
                    new_workbench_session(policy), server.base_url + "/p", timeout=TIMEOUT
                )

        assert len(server.arrivals) == 5
        assert caught.value.attempts == 5

    def test_the_backoff_factor_sets_the_wait_before_the_second_retry(self):
        # urllib3: the first retry is immediate, the second waits factor * 2 seconds.
        slow = RequestPolicy(
            requests_per_second=50.0, retries=2, backoff_factor=0.5, jitter_seconds=0.0
        )
        with _ScriptedServer([(503, {}, 0), (503, {}, 0), (200, {}, 0)]) as server:
            get_with_retry(new_workbench_session(slow), server.base_url + "/p", timeout=TIMEOUT)
        gap = server.arrivals[2] - server.arrivals[1]
        assert 0.9 <= gap < 1.6

        quick = RequestPolicy(
            requests_per_second=50.0, retries=2, backoff_factor=0.0, jitter_seconds=0.0
        )
        with _ScriptedServer([(503, {}, 0), (503, {}, 0), (200, {}, 0)]) as server:
            get_with_retry(new_workbench_session(quick), server.base_url + "/p", timeout=TIMEOUT)
        assert server.arrivals[2] - server.arrivals[0] < 0.5

    def test_the_retry_object_carries_every_value_of_the_policy(self):
        # urllib3 reads these names; the behaviour tests above show it acts on them.
        policy = RequestPolicy(
            requests_per_second=3.0, retries=7, backoff_factor=0.3, jitter_seconds=0.9
        )
        retry = http.workbench_retry(policy)
        assert (retry.total, retry.backoff_factor, retry.backoff_jitter) == (7, 0.3, 0.9)
        assert retry.status_forcelist == {429, 502, 503, 504}
        assert retry.respect_retry_after_header is True

    def test_jitter_adds_up_to_the_given_seconds(self):
        policy = RequestPolicy(
            requests_per_second=50.0, retries=2, backoff_factor=0.25, jitter_seconds=1.0
        )
        gaps = []
        for _ in range(3):
            with _ScriptedServer([(503, {}, 0), (503, {}, 0), (200, {}, 0)]) as server:
                get_with_retry(
                    new_workbench_session(policy), server.base_url + "/p", timeout=TIMEOUT
                )
            gaps.append(server.arrivals[2] - server.arrivals[1])
        # factor 0.25 -> 0.5 s, plus a random jitter in [0, 1.0)
        assert all(0.45 <= gap < 1.7 for gap in gaps)


class TestRateLimit:
    def test_threads_sharing_a_session_stay_within_the_per_host_rate(self):
        sessions = ThreadSessions(new_workbench_session(POLICY))
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
            session = new_workbench_session(ONE_PER_SECOND)
            started = time.monotonic()
            for _ in range(3):
                get_with_retry(session, server.base_url + "/p", timeout=TIMEOUT)

        assert time.monotonic() - started >= 1.9


class TestRetriesCountAgainstTheRate:
    """A retry is a request like any other: it takes a slot of its host's rate limit.

    The limit is a number of requests in any one second (they may go out together); with no
    backoff, only the rate limit can hold a retry back.
    """

    TWO_PER_SECOND = RequestPolicy(
        requests_per_second=2.0, retries=2, backoff_factor=0.0, jitter_seconds=0.0
    )

    def test_retries_after_a_retryable_status_are_held_to_the_rate(self):
        with _ScriptedServer([(503, {}, 0), (503, {}, 0), (200, {}, 0)]) as server:
            get_with_retry(
                new_workbench_session(self.TWO_PER_SECOND), server.base_url + "/p", timeout=TIMEOUT
            )

        first, second, third = server.arrivals
        assert second - first < 0.5  # two requests fit in the second
        assert third - first >= 0.9  # the third waits for the next one

    def test_retries_after_a_read_failure_are_held_to_the_rate(self):
        # The first two answers come later than the 0.1 s read timeout, so each is retried.
        with _ScriptedServer([(200, {}, 0.3), (200, {}, 0.3), (200, {}, 0)]) as server:
            get_with_retry(
                new_workbench_session(self.TWO_PER_SECOND),
                server.base_url + "/p",
                timeout=(5, 0.1),
            )

        first, _, third = server.arrivals
        assert third - first >= 0.9

    def test_the_slot_is_taken_when_the_retry_is_sent_not_before_its_wait(self):
        """A retry that waited for Retry-After counts in the second it is sent in."""
        session = new_workbench_session(self.TWO_PER_SECOND)
        with _ScriptedServer([(503, {"Retry-After": "1"}, 0)]) as server:
            url = server.base_url + "/p"
            get_with_retry(session, url, timeout=TIMEOUT)  # 503, a second's wait, then 200
            get_with_retry(session, url, timeout=TIMEOUT)
            get_with_retry(session, url, timeout=TIMEOUT)

        _, retry, second, third = server.arrivals
        assert second - retry < 0.5  # the retry and one more request fit in that second
        assert third - retry >= 0.9  # so the next one waits

    def test_threads_whose_first_attempts_all_fail_stay_within_the_rate(self):
        four_per_second = RequestPolicy(
            requests_per_second=4.0, retries=2, backoff_factor=0.0, jitter_seconds=0.0
        )
        arrivals: list[float] = []
        seen: set[str] = set()
        lock = threading.Lock()

        def fail_the_first_request_for_each_path(handler):
            with lock:
                arrivals.append(time.monotonic())
                first_time = handler.path not in seen
                seen.add(handler.path)
            body = b"ok"
            handler.send_response(503 if first_time else 200)
            handler.send_header("Content-Length", str(len(body)))
            handler.end_headers()
            handler.wfile.write(body)

        errors: list[Exception] = []

        def fetch(sessions, url):
            try:
                get_with_retry(sessions.current(), url, timeout=TIMEOUT)
            except Exception as error:  # reported by the assertion below
                errors.append(error)

        with LocalHTTPServer(fail_the_first_request_for_each_path) as server:
            sessions = ThreadSessions(new_workbench_session(four_per_second))
            threads = [
                threading.Thread(target=fetch, args=(sessions, f"{server.base_url}/p/{number}"))
                for number in range(3)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        assert errors == []
        arrivals.sort()
        assert len(arrivals) == 6  # each thread: one failed first attempt, one retry
        # Four requests fit in the first second; the fifth and sixth wait for the next.
        assert arrivals[4] - arrivals[0] >= 0.9, [round(t - arrivals[0], 2) for t in arrivals]

    def test_one_hosts_retry_does_not_delay_a_request_to_another_host(self):
        one_per_second = RequestPolicy(
            requests_per_second=1.0, retries=2, backoff_factor=0.0, jitter_seconds=0.0
        )
        session = new_workbench_session(one_per_second)
        with (
            _ScriptedServer([(503, {}, 0), (200, {}, 0)]) as retried_host,
            _ScriptedServer([]) as other_host,
        ):
            sessions = ThreadSessions(session)
            retrying = threading.Thread(
                target=lambda: get_with_retry(
                    sessions.current(), retried_host.base_url + "/p", timeout=TIMEOUT
                )
            )
            retrying.start()
            time.sleep(0.2)  # the first host's retry is now waiting for its slot
            started = time.monotonic()
            get_with_retry(session, other_host.base_url + "/p", timeout=TIMEOUT)
            took = time.monotonic() - started
            retrying.join()

        assert took < 0.5
        assert retried_host.arrivals[1] - retried_host.arrivals[0] >= 0.9


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
                request_policy=ONE_PER_SECOND,
                timeout=(10.0, 30.0),
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
            request_policy=ONE_PER_SECOND,
            timeout=(10.0, 30.0),
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
        workbench_url=WORKBENCH_URL,
        verify_ssl=True,
        session_file=tmp_path / "session.cookies",
        request_policy=POLICY,
        timeout=(10.0, 30.0),
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
            get_with_retry(new_workbench_session(POLICY), server.base_url + "/p", timeout=TIMEOUT)

        assert server.user_agents == [USER_AGENT, USER_AGENT]
