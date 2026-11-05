"""HTTP plumbing shared by every WorkBench request.

Retries and pacing come from established libraries instead of hand-written loops and sleeps:
urllib3's Retry (exponential backoff with jitter, Retry-After) and requests-ratelimiter's
per-host limiter, both on one adapter that new_workbench_session mounts. Per-thread copies of
a session share that adapter, so one limiter covers every worker thread. The policy values
(rate, retries, statuses, backoff, User-Agent) are constants in cis_bench.config, imported
here and never copied.
"""

import copy
import logging
import threading
from collections import OrderedDict

import requests
from requests.structures import CaseInsensitiveDict
from requests_ratelimiter import LimiterAdapter
from urllib3.util.retry import Retry

from cis_bench.config import (
    REQUEST_RETRIES,
    RETRY_AFTER_MAX_SECONDS,
    RETRY_BACKOFF_FACTOR,
    RETRY_JITTER_SECONDS,
    RETRYABLE_STATUS_CODES,
    USER_AGENT,
    WORKBENCH_REQUESTS_PER_SECOND,
)
from cis_bench.exceptions import FetchError

logger = logging.getLogger(__name__)


def _max_attempts() -> int:
    return REQUEST_RETRIES + 1


class WorkBenchRetry(Retry):
    """urllib3 Retry that logs each retry and caps the server's Retry-After.

    One WARNING per retry names the URL, the attempt and the wait about to be slept. The wait
    is computed once per attempt and cached, so the logged figure is the one urllib3 sleeps.
    """

    _backoff_time: float | None = None

    def get_backoff_time(self) -> float:
        if self._backoff_time is None:
            self._backoff_time = super().get_backoff_time()
        return self._backoff_time

    def get_retry_after(self, response):
        seconds = super().get_retry_after(response)
        return None if seconds is None else min(seconds, RETRY_AFTER_MAX_SECONDS)

    def increment(
        self, method=None, url=None, response=None, error=None, _pool=None, _stacktrace=None
    ):
        retry = super().increment(method, url, response, error, _pool, _stacktrace)
        retry_after = (
            retry.get_retry_after(response)
            if retry.respect_retry_after_header and response is not None
            else None
        )
        wait = retry_after if retry_after else retry.get_backoff_time()
        where = f"{_pool.scheme}://{_pool.host}:{_pool.port}{url}" if _pool is not None else url
        cause = error if error is not None else f"HTTP {response.status}"
        logger.warning(
            f"Request failed (attempt {len(retry.history)}/{_max_attempts()}), "
            f"retrying in {wait:.1f}s: {where}: {cause}"
        )
        return retry


def workbench_retry() -> WorkBenchRetry:
    """The retry policy for WorkBench GETs: connect, read and 429/502/503/504 failures."""
    return WorkBenchRetry(
        total=REQUEST_RETRIES,
        status_forcelist=RETRYABLE_STATUS_CODES,
        allowed_methods=frozenset({"GET", "HEAD"}),
        backoff_factor=RETRY_BACKOFF_FACTOR,
        backoff_jitter=RETRY_JITTER_SECONDS,
        respect_retry_after_header=True,
        raise_on_status=False,
    )


def mount_workbench_adapter(
    session: requests.Session, requests_per_second: float | None = None
) -> None:
    """Mount the WorkBench adapter (rate limit per host, then retries) on session.

    requests_per_second defaults to WORKBENCH_REQUESTS_PER_SECOND.
    """
    rate = WORKBENCH_REQUESTS_PER_SECOND if requests_per_second is None else requests_per_second
    adapter = LimiterAdapter(per_second=rate, burst=1, per_host=True, max_retries=workbench_retry())
    for prefix in ("https://", "http://"):
        session.mount(prefix, adapter)


def new_workbench_session(requests_per_second: float | None = None) -> requests.Session:
    """A requests.Session for WorkBench: the shared rate limit and retry policy mounted, and the
    cis-bench User-Agent on every request."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    mount_workbench_adapter(session, requests_per_second)
    return session


def session_for_worker(base: requests.Session) -> requests.Session:
    """Return a Session that carries base's login and settings but owns its cookie jar.

    requests does not make Session safe to share between threads, and WorkBench rotates its
    session cookies on every response, so each worker thread works on its own copy. The copy
    reuses base's mounted adapters: urllib3 connection pools are thread-safe, so workers share
    one pool of keep-alive connections. Because the adapters are shared, a worker copy must
    never be closed; closing it would close base's connections.
    """
    worker = requests.Session()
    for adapter in worker.adapters.values():
        adapter.close()  # the fresh default adapters are replaced by base's below
    worker.adapters = OrderedDict(base.adapters)
    worker.cookies = base.cookies.copy()
    worker.headers = CaseInsensitiveDict(base.headers)
    worker.auth = base.auth
    worker.proxies = dict(base.proxies)
    worker.hooks = {event: list(hooks) for event, hooks in base.hooks.items()}
    worker.params = copy.copy(base.params)
    worker.stream = base.stream
    worker.verify = base.verify
    worker.cert = base.cert
    worker.max_redirects = base.max_redirects
    worker.trust_env = base.trust_env
    return worker


class ThreadSessions:
    """The session each thread should send requests with.

    The thread that creates this keeps using ``session`` itself; every other thread gets its own
    copy of it on first use (see ``session_for_worker``), so concurrent responses never write to
    a cookie jar another thread is reading. The owner is tracked by Thread object, not thread
    ident, because idents can be reused after a thread exits.
    """

    def __init__(self, session: requests.Session):
        self.session = session
        self._owner_thread = threading.current_thread()
        self._local = threading.local()

    def current(self) -> requests.Session:
        if threading.current_thread() is self._owner_thread:
            return self.session
        worker: requests.Session | None = getattr(self._local, "session", None)
        if worker is None:
            worker = session_for_worker(self.session)
            self._local.session = worker
        return worker


def get_with_retry(
    session: requests.Session,
    url: str,
    *,
    timeout: tuple[float, float],
) -> requests.Response:
    """GET url through the session's WorkBench adapter, which paces and retries it.

    Retries happen inside the adapter (see workbench_retry). When they are used up, a timeout,
    a connection failure or a still-retryable status becomes FetchError naming the url, so the
    caller can skip or report the item instead of hanging on it; any other HTTP error is raised
    as it is.

    Raises:
        FetchError: After the final failed attempt.
        requests.HTTPError: For a non-retryable HTTP status.
    """
    try:
        response = session.get(url, timeout=timeout)
    except (requests.Timeout, requests.ConnectionError) as e:
        raise FetchError(url, _max_attempts(), str(e)) from e
    if response.status_code in RETRYABLE_STATUS_CODES:
        raise FetchError(url, _max_attempts(), f"HTTP {response.status_code}")
    response.raise_for_status()
    return response
