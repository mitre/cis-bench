"""HTTP plumbing shared by every WorkBench scraper.

Two pieces: per-thread copies of the logged-in session, and a GET with a timeout and a bounded
retry. Both scrapers (benchmark download and catalog refresh) use them, so the session
arrangement and the request policy exist in one place.
"""

import copy
import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Mapping

import requests
from requests.structures import CaseInsensitiveDict

from cis_bench.exceptions import FetchError

logger = logging.getLogger(__name__)

# Pause before each retry, in seconds; one more attempt than there are pauses.
RETRY_BACKOFF_SECONDS = (1, 2)
MAX_ATTEMPTS = len(RETRY_BACKOFF_SECONDS) + 1
# Server-side conditions worth retrying; every other HTTP status is final.
RETRYABLE_STATUS_CODES = frozenset({502, 503, 504})


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
    headers: Mapping[str, str] | None = None,
) -> requests.Response:
    """GET url with a timeout and a bounded retry.

    Timeouts, connection errors and 502/503/504 responses are retried after 1 s and then 2 s;
    any other HTTP error is raised at once. When the last attempt still fails, FetchError names
    the url so the caller can skip or report the item instead of hanging on it.

    Raises:
        FetchError: After the final failed attempt.
        requests.HTTPError: For a non-retryable HTTP status.
    """
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            if headers is None:
                response = session.get(url, timeout=timeout)
            else:
                response = session.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            if status not in RETRYABLE_STATUS_CODES:
                raise
            failure: requests.RequestException = e
        except (requests.Timeout, requests.ConnectionError) as e:
            failure = e

        if attempt == MAX_ATTEMPTS:
            raise FetchError(url, attempt, str(failure)) from failure
        wait = RETRY_BACKOFF_SECONDS[attempt - 1]
        logger.warning(
            f"Request failed (attempt {attempt}/{MAX_ATTEMPTS}), retrying in {wait}s: {url}: {failure}"
        )
        time.sleep(wait)
    raise AssertionError("unreachable: every attempt returns or raises")
