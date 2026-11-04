"""CIS WorkBench scraper with strategy pattern support.

This scraper uses the Strategy pattern to adapt to HTML changes.
It produces validated Pydantic Benchmark models.
"""

import copy
import logging
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from datetime import datetime
from typing import Any

import requests
import urllib3
from bs4 import BeautifulSoup, Tag
from pydantic import HttpUrl
from requests.structures import CaseInsensitiveDict

from cis_bench.config import Config
from cis_bench.exceptions import AuthenticationError, FetchError
from cis_bench.fetcher.auth import is_workbench_login_page
from cis_bench.fetcher.strategies.base import ScraperStrategy
from cis_bench.fetcher.strategies.detector import StrategyDetector
from cis_bench.models.benchmark import Benchmark, Recommendation

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


def _session_for_worker(base: requests.Session) -> requests.Session:
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


class WorkbenchScraper:
    """Scraper for CIS WorkBench with auto-adapting HTML strategies.

    Uses Strategy pattern to handle HTML structure changes gracefully.
    Produces validated Pydantic models as output.

    Fetch methods may be called from several threads at once. The thread that created the
    scraper uses ``session`` itself; every other thread gets its own copy of it on first use,
    so concurrent responses never write to a cookie jar another thread is reading.
    """

    def __init__(self, session: requests.Session, strategy: ScraperStrategy | None = None):
        """Initialize scraper.

        Args:
            session: Authenticated requests session
            strategy: Optional specific strategy (auto-detected if not provided)
        """
        self.session = session
        self.strategy = strategy
        self._detected_strategy: ScraperStrategy | None = None
        self._strategy_lock = threading.Lock()
        self._owner_thread = threading.current_thread()
        self._worker_sessions = threading.local()
        self.timeout = Config.get_request_timeout()

    def _current_session(self) -> requests.Session:
        """The session this thread should send requests with."""
        if threading.current_thread() is self._owner_thread:
            return self.session
        worker: requests.Session | None = getattr(self._worker_sessions, "session", None)
        if worker is None:
            worker = _session_for_worker(self.session)
            self._worker_sessions.session = worker
        return worker

    def _get_strategy(self, html: str) -> ScraperStrategy:
        """Get strategy to use (override or auto-detect).

        Args:
            html: Sample HTML for detection

        Returns:
            Strategy instance to use
        """
        if self.strategy:
            logger.debug(f"Using manual strategy: {self.strategy.version}")
            return self.strategy

        detected = self._detected_strategy
        if detected is None:
            with self._strategy_lock:
                if self._detected_strategy is None:
                    self._detected_strategy = StrategyDetector.detect_strategy(html)
                detected = self._detected_strategy

        return detected

    # Pause before each retry, in seconds; one more attempt than there are pauses.
    _RETRY_BACKOFF_SECONDS = (1, 2)
    _MAX_ATTEMPTS = len(_RETRY_BACKOFF_SECONDS) + 1
    # Server-side conditions worth retrying; everything else is final.
    _RETRYABLE_STATUS_CODES = frozenset({502, 503, 504})

    def _request(self, url: str) -> requests.Response:
        """GET url with the configured timeout and a bounded retry.

        Timeouts, connection errors and 502/503/504 responses are retried with
        backoff; any other HTTP error is raised at once. When the last attempt
        still fails, FetchError names the url so the caller can skip or report
        the item instead of hanging on it.

        Raises:
            FetchError: After the final failed attempt.
            requests.HTTPError: For a non-retryable HTTP status.
        """
        for attempt in range(1, self._MAX_ATTEMPTS + 1):
            try:
                response = self._current_session().get(url, timeout=self.timeout)
                response.raise_for_status()
                return response
            except requests.HTTPError as e:
                status = e.response.status_code if e.response is not None else None
                if status not in self._RETRYABLE_STATUS_CODES:
                    raise
                failure: requests.RequestException = e
            except (requests.Timeout, requests.ConnectionError) as e:
                failure = e

            if attempt == self._MAX_ATTEMPTS:
                raise FetchError(url, attempt, str(failure)) from failure
            wait = self._RETRY_BACKOFF_SECONDS[attempt - 1]
            logger.warning(
                f"Request failed (attempt {attempt}/{self._MAX_ATTEMPTS}), "
                f"retrying in {wait}s: {url}: {failure}"
            )
            time.sleep(wait)
        raise AssertionError("unreachable: every attempt returns or raises")

    def fetch_html(self, url: str) -> str:
        """Fetch HTML from URL.

        Args:
            url: URL to fetch

        Returns:
            HTML content

        Raises:
            FetchError: If the request still fails after every retry
            AuthenticationError: If WorkBench answered with its login page (an
                expired session); that is final, never retried
            requests.HTTPError: For a non-retryable HTTP status
        """
        html = self._request(url).text
        if is_workbench_login_page(html):
            raise AuthenticationError(
                f"WorkBench returned the login page for {url}; the saved session has expired"
            )
        return html

    def fetch_json(self, url: str) -> dict[str, Any]:
        """Fetch JSON from URL.

        Args:
            url: URL to fetch

        Returns:
            Parsed JSON data

        Raises:
            FetchError: If the request still fails after every retry
            requests.HTTPError: For a non-retryable HTTP status
        """
        payload = self._request(url).json()
        if not isinstance(payload, dict):
            raise ValueError(f"Expected JSON object from {url}, got {type(payload).__name__}")
        return payload

    @staticmethod
    def get_benchmark_id(url: str) -> str:
        """Extract benchmark ID from URL.

        Args:
            url: Benchmark URL

        Returns:
            Benchmark ID

        Raises:
            ValueError: If ID cannot be extracted
        """
        match = re.search(r"\d+/*$", url)
        if not match:
            raise ValueError(f"Cannot extract benchmark ID from URL: {url}")
        return match.group().replace("/", "")

    def get_benchmark_title(self, benchmark_url: str) -> str:
        """Fetch benchmark title from page.

        Args:
            benchmark_url: URL to benchmark page

        Returns:
            Benchmark title
        """
        html = self.fetch_html(benchmark_url)
        soup = BeautifulSoup(html, "html.parser")
        title_elem = soup.find(name="wb-benchmark-title")
        if isinstance(title_elem, Tag):
            raw_title = title_elem.get("title")
            if isinstance(raw_title, str):
                return raw_title
            if isinstance(raw_title, list):
                return " ".join(raw_title)
        return "Unknown Benchmark"

    def fetch_navtree(self, benchmark_id: str) -> dict[str, Any]:
        """Fetch navigation tree for benchmark.

        Args:
            benchmark_id: CIS benchmark ID

        Returns:
            Navigation tree JSON data
        """
        base_url = Config.get_workbench_base_url()
        url = f"{base_url}/api/v1/benchmarks/{benchmark_id}/navtree"
        return self.fetch_json(url)

    def parse_navtree(self, navtree_data: dict[str, Any]) -> list[dict[str, str]]:
        """Parse navigation tree to extract recommendation URLs.

        Args:
            navtree_data: Navigation tree JSON

        Returns:
            List of dicts with url, title, ref
        """
        base_url = Config.get_workbench_base_url()

        def generate_urls(recommendations: list[dict[str, Any]]) -> list[dict[str, str]]:
            output: list[dict[str, str]] = []
            for rec in recommendations:
                rec_id = rec["id"]
                section_id = rec["section_id"]
                url = f"{base_url}/sections/{section_id}/recommendations/{rec_id}"
                output.append(
                    {"url": url, "title": str(rec["title"]), "ref": str(rec["view_level"])}
                )
            return output

        def parse_subsections(
            subsections: list[dict[str, Any]], result: list[dict[str, str]]
        ) -> None:
            for section in subsections:
                # Process recommendations at this level
                recommendations = section.get("recommendations_for_nav_tree", [])
                result.extend(generate_urls(recommendations))

                # Recursively process subsections
                sub_subsections = section.get("subsections_for_nav_tree")
                if sub_subsections:
                    parse_subsections(sub_subsections, result)

        parsed_data: list[dict[str, str]] = []
        navtree = navtree_data["navtree"]
        parse_subsections(navtree, parsed_data)
        return parsed_data

    def fetch_recommendation(self, rec_url: str) -> dict[str, Any]:
        """Fetch and parse a single recommendation page.

        Args:
            rec_url: URL to recommendation page

        Returns:
            Dictionary with all extracted fields
        """
        html = self.fetch_html(rec_url)
        strategy = self._get_strategy(html)
        return strategy.extract_recommendation(html)

    def download_benchmark(
        self, benchmark_url: str, progress_callback: Callable[[str], None] | None = None
    ) -> Benchmark:
        """Download complete benchmark with all recommendations.

        Args:
            benchmark_url: URL to benchmark page
            progress_callback: Optional callback for progress messages

        Returns:
            Validated Benchmark (Pydantic model)

        Raises:
            ValueError: If data validation fails
            AuthenticationError: If the session expires during the download
            FetchError: If the benchmark page or navigation tree cannot be fetched
            requests.HTTPError: For a non-retryable HTTP status on those requests
        """

        def log(msg: str, level: str = "info") -> None:
            # Send to progress callback (for progress bar)
            if progress_callback:
                progress_callback(msg)

            # Only log important messages (not individual fetches)
            if not msg.startswith("["):  # Skip "[1/322] Fetching..." messages
                if level == "debug":
                    logger.debug(msg)
                else:
                    logger.info(msg)

        # Extract benchmark ID
        benchmark_id = self.get_benchmark_id(benchmark_url)
        log(f"Fetching benchmark: {benchmark_url}", level="debug")

        # Get benchmark title
        title = self.get_benchmark_title(benchmark_url)
        log(f"Benchmark title: {title}", level="debug")

        # Extract version from title (simple heuristic)
        version_match = re.search(r"v[\d.]+|vNEXT", title, re.IGNORECASE)
        version = version_match.group() if version_match else "v1.0.0"

        # Fetch navigation tree
        navtree = self.fetch_navtree(benchmark_id)
        recommendations_list = self.parse_navtree(navtree)
        log(f"Found {len(recommendations_list)} recommendations", level="debug")

        # Fetch each recommendation
        recommendations = []
        for idx, rec_meta in enumerate(recommendations_list, 1):
            log(
                f"[{idx}/{len(recommendations_list)}] Fetching {rec_meta['ref']}: {rec_meta['title']}",
                level="debug",
            )

            try:
                rec_data = self.fetch_recommendation(rec_meta["url"])

                # Create Recommendation (Pydantic validates automatically)
                recommendation = Recommendation(
                    ref=rec_meta["ref"],
                    title=rec_meta["title"],
                    url=HttpUrl(rec_meta["url"]),
                    **rec_data,  # Spread extracted fields
                )

                recommendations.append(recommendation)

            except AuthenticationError:
                # Every further fetch would get the login page too; stop here.
                raise
            except Exception as e:
                logger.error(f"Failed to fetch {rec_meta['url']}: {e}")
                # Continue with other recommendations
                continue

        # Create Benchmark (Pydantic validates automatically)
        benchmark = Benchmark(
            title=title,
            benchmark_id=benchmark_id,
            url=HttpUrl(benchmark_url),
            version=version,
            scraper_version=(
                self._detected_strategy.version if self._detected_strategy else "manual"
            ),
            total_recommendations=len(recommendations),
            recommendations=recommendations,
            downloaded_at=datetime.now(),
        )

        log(f"✓ Successfully downloaded {len(recommendations)} recommendations", level="debug")

        return benchmark
