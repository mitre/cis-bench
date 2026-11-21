"""HTTP plumbing shared by every WorkBench request.

Retries and pacing come from established libraries instead of hand-written loops and sleeps:
urllib3's Retry (exponential backoff with jitter, Retry-After) and requests-ratelimiter's
per-host limiter, both on one adapter that new_workbench_session mounts. Per-thread copies of
a session share that adapter, so one limiter covers every worker thread. The limiter takes a
slot for each request the adapter sends and, through WorkBenchRetry, for each retry urllib3
makes inside it, so retries count against the rate too. The tunable policy
(rate, retries, backoff, jitter) arrives as a RequestPolicy from the caller; the fixed part
(retryable statuses, Retry-After cap, User-Agent) is constants in cis_bench.config.
"""

import copy
import html
import logging
import re
import threading
from collections import OrderedDict
from collections.abc import Callable, Mapping
from typing import Any, Self

import requests
from requests.structures import CaseInsensitiveDict
from requests_ratelimiter import LimiterAdapter
from urllib3.util.retry import Retry

from cis_bench.config import (
    RETRY_AFTER_MAX_SECONDS,
    RETRYABLE_STATUS_CODES,
    USER_AGENT,
    RequestPolicy,
)
from cis_bench.exceptions import FetchError
from cis_bench.utils.workbench_urls import printable_url, without_query_strings

logger = logging.getLogger(__name__)


def _attempts_allowed(retry: Retry) -> int:
    """How many attempts this retry object allows in all: its remaining total plus those made."""
    return int(retry.total or 0) + len(retry.history) + 1


def attempts_allowed(session: requests.Session, url: str) -> int:
    """The attempts the session's adapter makes for url before giving up.

    An adapter without a urllib3 Retry (requests' default, or a test double) makes one.
    """
    retry = getattr(session.get_adapter(url), "max_retries", None)
    return _attempts_allowed(retry) if isinstance(retry, Retry) else 1


class WorkBenchRetry(Retry):
    """urllib3 Retry that logs each retry, caps the server's Retry-After and paces retries.

    One WARNING per retry names the URL, the attempt and the wait about to be slept. The wait
    is computed once per attempt and cached, so the logged figure is the one urllib3 sleeps.
    After that wait, take_slot (the adapter's rate limiter) is asked for a slot, so a retry is
    counted against the request rate like a first attempt.
    """

    _backoff_time: float | None = None

    def __init__(
        self, *args: Any, take_slot: Callable[[], None] | None = None, **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self.take_slot = take_slot

    def new(self, **kw: Any) -> Self:
        # urllib3 builds a fresh Retry for every attempt; keep the limiter with it.
        kw.setdefault("take_slot", self.take_slot)
        return super().new(**kw)

    def sleep(self, response: Any = None) -> None:
        super().sleep(response)
        if self.take_slot is not None:
            self.take_slot()

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
        where = printable_url(
            f"{_pool.scheme}://{_pool.host}:{_pool.port}{url}" if _pool is not None else (url or "")
        )
        cause = error if error is not None else f"HTTP {response.status}"
        logger.warning(
            f"Request failed (attempt {len(retry.history)}/{_attempts_allowed(retry)}), "
            f"retrying in {wait:.1f}s: {where}: {cause}"
        )
        return retry


def workbench_retry(
    policy: RequestPolicy, *, take_slot: Callable[[], None] | None = None
) -> WorkBenchRetry:
    """The retry behaviour for WorkBench GETs: connect, read and 429/502/503/504 failures.

    take_slot is called before each retry is sent, after its backoff or Retry-After wait.
    """
    return WorkBenchRetry(
        take_slot=take_slot,
        total=policy.retries,
        status_forcelist=RETRYABLE_STATUS_CODES,
        allowed_methods=frozenset({"GET", "HEAD"}),
        backoff_factor=policy.backoff_factor,
        backoff_jitter=policy.jitter_seconds,
        respect_retry_after_header=True,
        raise_on_status=False,
    )


class WorkBenchAdapter(LimiterAdapter):
    """The rate-limited adapter for WorkBench, whose limit also covers retries.

    LimiterAdapter takes one slot of the host's limit per send, and urllib3 then makes its
    retries inside that send. This adapter remembers the request each thread is sending, and
    its WorkBenchRetry calls take_retry_slot before every retry, so a retry waits for a slot
    of the same host as the first attempt did.
    """

    def __init__(self, policy: RequestPolicy) -> None:
        super().__init__(per_second=policy.requests_per_second, burst=1, per_host=True)
        self.max_retries = workbench_retry(policy, take_slot=self.take_retry_slot)
        self._sending = threading.local()

    def send(
        self,
        request: requests.PreparedRequest,
        stream: bool | None = False,
        timeout: None | float | tuple[float | None, float | None] = None,
        verify: bool | str | None = True,
        cert: None | bytes | str | tuple[bytes | str, bytes | str] = None,
        proxies: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> requests.Response:
        # The parameters are HTTPAdapter.send's. Their types and **kwargs are widened to what
        # LimiterMixin.send declares (the library types its mixin as a requests.Session).
        self._sending.request = request
        try:
            return super().send(
                request,
                stream=stream,
                timeout=timeout,
                verify=verify,
                cert=cert,
                proxies=proxies,
                **kwargs,
            )
        finally:
            self._sending.request = None

    def take_retry_slot(self) -> None:
        """Wait for a slot of the rate limit for the request this thread is sending."""
        request = getattr(self._sending, "request", None)
        if request is not None:
            # The library names a host's bucket in _bucket_name; using it keeps retries in
            # the bucket its own send() used for the first attempt.
            self.limiter.try_acquire(self._bucket_name(request), weight=1, blocking=True)


def mount_workbench_adapter(session: requests.Session, policy: RequestPolicy) -> None:
    """Mount the WorkBench adapter (rate limit per host, covering retries) on session."""
    adapter = WorkBenchAdapter(policy)
    for prefix in ("https://", "http://"):
        session.mount(prefix, adapter)


def new_workbench_session(policy: RequestPolicy) -> requests.Session:
    """A requests.Session for WorkBench: the given rate limit and retry policy mounted, and the
    cis-bench User-Agent on every request."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    mount_workbench_adapter(session, policy)
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


# Cloudflare's Email Address Obfuscation rewrites each address on a page it serves, differently
# on every fetch: an element carrying the address in data-cfemail, and a link whose href ends in
# /cdn-cgi/l/email-protection#<hex>. The hex is a key byte followed by the address's UTF-8 bytes,
# each XOR the key (as Cloudflare's email-decode script reverses it).
_CF_EMAIL_ELEMENT_RE = re.compile(
    r"<(a|span)\b[^>]*?\sdata-cfemail=\"([0-9A-Fa-f]*)\"[^>]*>.*?</\1>", re.DOTALL
)
# The whole href value, as Cloudflare writes it (a path on the same origin): a value with
# anything else in it is not Cloudflare's and is left alone.
_CF_EMAIL_LINK_RE = re.compile(r'href="/cdn-cgi/l/email-protection#([^"]*)"')


def _cloudflare_address(hex_text: str) -> str | None:
    """The address a Cloudflare hex string encodes, or None when it is not a valid encoding."""
    try:
        data = bytes.fromhex(hex_text)
        address = bytes(byte ^ data[0] for byte in data[1:]).decode("utf-8")
    except ValueError:  # not hex, or not UTF-8
        return None
    return address or None  # empty, or a key with no address


def decode_cloudflare_emails(text: str) -> str:
    """text with every Cloudflare-obfuscated address written out as the address itself.

    An obfuscated element becomes the address; an obfuscated link becomes a mailto: link.
    Only Cloudflare's own markup is rewritten: a data-cfemail attribute, and an href whose whole
    value is /cdn-cgi/l/email-protection#<hex>.
    Markup whose hex is not a valid encoding is left as it was.
    """

    def element(match: re.Match[str]) -> str:
        address = _cloudflare_address(match.group(2))
        return match.group(0) if address is None else html.escape(address, quote=False)

    def link(match: re.Match[str]) -> str:
        address = _cloudflare_address(match.group(1))
        return match.group(0) if address is None else f'href="mailto:{html.escape(address)}"'

    return _CF_EMAIL_LINK_RE.sub(link, _CF_EMAIL_ELEMENT_RE.sub(element, text))


def workbench_page_text(response: requests.Response) -> str:
    """The text of a WorkBench page response, with Cloudflare-obfuscated addresses decoded.

    The one way page text is taken from a WorkBench response, so every parser, the stored
    benchmark and every export see real addresses.
    """
    return decode_cloudflare_emails(response.text)


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
    # A request may have been redirected into the SSO handshake, whose URLs carry a state or
    # a code: the error names the URL and quotes the library's message without those.
    try:
        response = session.get(url, timeout=timeout)
    except (requests.Timeout, requests.ConnectionError) as e:
        raise FetchError(
            printable_url(url), attempts_allowed(session, url), without_query_strings(str(e))
        ) from e
    if response.status_code in RETRYABLE_STATUS_CODES:
        raise FetchError(
            printable_url(url), attempts_allowed(session, url), f"HTTP {response.status_code}"
        )
    response.raise_for_status()
    return response
