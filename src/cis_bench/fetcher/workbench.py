"""CIS WorkBench scraper with strategy pattern support.

This scraper uses the Strategy pattern to adapt to HTML changes.
It produces validated Pydantic Benchmark models.
"""

import json
import logging
import re
import threading
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

import requests
import urllib3
from bs4 import BeautifulSoup, Tag
from pydantic import HttpUrl, TypeAdapter, ValidationError

from cis_bench.exceptions import AuthenticationError, ParserError
from cis_bench.fetcher.auth import is_workbench_login_page
from cis_bench.fetcher.http import ThreadSessions, get_with_retry, workbench_page_text
from cis_bench.fetcher.strategies.base import ExtractedRecommendation, ScraperStrategy
from cis_bench.fetcher.strategies.detector import StrategyDetector
from cis_bench.models.benchmark import (
    HTML_ERA_SCRAPER_VERSIONS,
    Benchmark,
    BenchmarkPage,
    ProfileDefinition,
    ProfileDefinitions,
    Recommendation,
)
from cis_bench.utils.html_parser import attribute_text
from cis_bench.utils.markdown_text import html_to_markdown, unix_line_breaks
from cis_bench.utils.parallel import parallel_execute_batched
from cis_bench.utils.vue_payload import decode_vue_payload
from cis_bench.utils.workbench_urls import navtree_url, recommendation_url

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


# WorkBench renders a release's status as a label ("Published") followed by a bare text node
# such as "1 year ago on Aug 28th 2025".
_PUBLISHED_ON_RE = re.compile(r"\bago on ([A-Za-z]+) (\d+)(?:st|nd|rd|th) (\d{4})")
# Paragraphs of an Overview section written as a heading and paragraphs, as kept for a page
# without the overview component.
_OVERVIEW_PARAGRAPHS = 3
# The page's profile list, validated by the model's own rules for it.
_PROFILE_DEFINITIONS = TypeAdapter(ProfileDefinitions)


def parse_benchmark_page(html: str) -> BenchmarkPage:
    """What a benchmark's WorkBench page says: its title, publish date, description and
    profile definitions.

    The one parser for that page; every command that reads it goes through here.

    Raises:
        ParserError: The page's profile list does not decode to a list of titled profiles.
    """
    soup = BeautifulSoup(html, "html.parser")
    return BenchmarkPage(
        title=_benchmark_title(soup),
        published_date=_published_date(soup),
        description=_description(soup),
        profile_definitions=_profile_definitions(soup),
    )


def _profile_definitions(soup: BeautifulSoup) -> list[ProfileDefinition]:
    """The profiles in the page's wb-benchmark-profiles component: each one's title,
    description and the title of the profile it extends; none without the component.

    The component gives each description as HTML; it is stored as Markdown, the one form
    benchmark text takes (a description that is not text is left for validation to refuse).

    Raises:
        ParserError: The component has no payload, or the payload is not JSON, not a list
            of objects, or not valid profile definitions (a title each, text descriptions
            and parents, each title once).
    """
    component = soup.find(name="wb-benchmark-profiles")
    if not isinstance(component, Tag):
        return []
    payload = decode_vue_payload(attribute_text(component, ":profiles"))
    if payload is None:
        raise ParserError("wb-benchmark-profiles: the component has no profile list")
    try:
        profiles = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ParserError(
            f"wb-benchmark-profiles: the profile list is not JSON: {error}"
        ) from error
    if not isinstance(profiles, list):
        raise ParserError(
            f"wb-benchmark-profiles: expected a list of profiles, got {type(profiles).__name__}"
        )
    for profile in profiles:
        if not isinstance(profile, dict):
            raise ParserError(f"wb-benchmark-profiles: a profile is not an object: {profile!r}")
    try:
        return _PROFILE_DEFINITIONS.validate_python(
            [
                {
                    "title": profile.get("title"),
                    "description": (
                        html_to_markdown(description)
                        if isinstance(description := profile.get("description"), str)
                        else description
                    ),
                    "parent": profile.get("parent_title"),
                }
                for profile in profiles
            ]
        )
    except ValidationError as error:
        raise ParserError(f"wb-benchmark-profiles: {error}") from error


def _benchmark_title(soup: BeautifulSoup) -> str:
    """The title the page carries in its wb-benchmark-title element."""
    title_elem = soup.find(name="wb-benchmark-title")
    if isinstance(title_elem, Tag):
        raw_title = title_elem.get("title")
        if isinstance(raw_title, str):
            return raw_title
        if isinstance(raw_title, list):
            return " ".join(raw_title)
    return "Unknown Benchmark"


def _published_date(soup: BeautifulSoup) -> date | None:
    """The date in the "<n> <units> ago on Aug 28th 2025" status text (abbreviated or full
    month name); anything that is not a real calendar date in that shape gives None."""
    text = soup.find(string=_PUBLISHED_ON_RE)
    if not isinstance(text, str):
        return None
    match = _PUBLISHED_ON_RE.search(text)
    if match is None:
        return None
    month, day, year = match.groups()
    for fmt in ("%b %d %Y", "%B %d %Y"):
        try:
            return datetime.strptime(f"{month} {day} {year}", fmt).date()
        except ValueError:
            continue
    return None


def _description(soup: BeautifulSoup) -> str | None:
    """The page's overview as the Markdown the page gives.

    WorkBench renders it as <wb-recommendation-data attribute="overview" text="...">, whose
    text is Markdown like a recommendation's text fields; it is kept as written (a
    placeholder such as <path> stays), with every line break as \\n. A page written with
    an "Overview" heading instead gives the text of its first paragraphs up to the next
    heading.
    """
    component = soup.find("wb-recommendation-data", attrs={"attribute": "overview"})
    if isinstance(component, Tag):
        text = unix_line_breaks(attribute_text(component, "text") or "").strip()
        return text or None

    heading = soup.find(
        lambda tag: isinstance(tag, Tag)
        and tag.name == "h2"
        and "overview" in tag.get_text().lower()
    )
    if not isinstance(heading, Tag):
        return None
    paragraphs = []
    for sibling in heading.find_next_siblings():
        if sibling.name and sibling.name.startswith("h"):
            break
        text = sibling.get_text(strip=True)
        if text:
            paragraphs.append(text)
    return " ".join(paragraphs[:_OVERVIEW_PARAGRAPHS]) or None


def _login_page_error(url: str) -> AuthenticationError:
    """The error for a request WorkBench answered with its login page: the session expired."""
    return AuthenticationError(
        f"WorkBench returned the login page for {url}; the saved session has expired"
    )


class WorkbenchScraper:
    """Scraper for CIS WorkBench with auto-adapting HTML strategies.

    Uses Strategy pattern to handle HTML structure changes gracefully.
    Produces validated Pydantic models as output.

    Fetch methods may be called from several threads at once. The thread that created the
    scraper uses ``session`` itself; every other thread gets its own copy of it on first use,
    so concurrent responses never write to a cookie jar another thread is reading.
    """

    def __init__(
        self,
        session: requests.Session,
        *,
        base_url: str,
        timeout: tuple[float, float],
        max_workers: int,
        batch_size: int,
        strategy: ScraperStrategy | None = None,
    ):
        """Initialize scraper.

        Args:
            session: Authenticated requests session
            base_url: The WorkBench origin (already validated) every URL is built on
            timeout: (connect, read) seconds for every request
            max_workers: Recommendation pages fetched at once
            batch_size: Recommendations per batch of parallel work
            strategy: Optional specific strategy (auto-detected if not provided)
        """
        self.session = session
        self.strategy = strategy
        self._detected_strategy: ScraperStrategy | None = None
        self._strategy_lock = threading.Lock()
        self._sessions = ThreadSessions(session)
        self.base_url = base_url
        self.timeout = timeout
        self.max_workers = max_workers
        self.batch_size = batch_size

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

    def _request(self, url: str) -> requests.Response:
        """GET url on this thread's session with the shared timeout and retry policy.

        Raises:
            FetchError: After the final failed attempt.
            requests.HTTPError: For a non-retryable HTTP status.
        """
        return get_with_retry(self._sessions.current(), url, timeout=self.timeout)

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
        html = workbench_page_text(self._request(url))
        if is_workbench_login_page(html):
            raise _login_page_error(url)
        return html

    def fetch_json(self, url: str) -> dict[str, Any]:
        """Fetch JSON from URL.

        Args:
            url: URL to fetch

        Returns:
            Parsed JSON data

        Raises:
            FetchError: If the request still fails after every retry
            AuthenticationError: If WorkBench answered with its login page (an
                expired session)
            ValueError: If the answer is not JSON, or not a JSON object
            requests.HTTPError: For a non-retryable HTTP status
        """
        response = self._request(url)
        try:
            payload = response.json()
        except requests.JSONDecodeError as error:
            # An expired session is answered with the HTML login page, status 200.
            if is_workbench_login_page(response.text):
                raise _login_page_error(url) from None
            raise ValueError(
                f"Expected JSON from {url}, got a response that is not JSON"
            ) from error
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
        return self.fetch_benchmark_page(benchmark_url).title

    def fetch_benchmark_page(self, benchmark_url: str) -> BenchmarkPage:
        """Fetch a benchmark's own page and read it (parse_benchmark_page)."""
        return parse_benchmark_page(self.fetch_html(benchmark_url))

    def fetch_navtree(self, benchmark_id: str) -> dict[str, Any]:
        """Fetch navigation tree for benchmark.

        Args:
            benchmark_id: CIS benchmark ID

        Returns:
            Navigation tree JSON data
        """
        url = navtree_url(benchmark_id, base_url=self.base_url)
        return self.fetch_json(url)

    def parse_navtree(self, navtree_data: dict[str, Any]) -> list[dict[str, str]]:
        """Parse navigation tree to extract recommendation URLs.

        Args:
            navtree_data: Navigation tree JSON

        Returns:
            List of dicts with url, title, ref
        """

        def generate_urls(recommendations: list[dict[str, Any]]) -> list[dict[str, str]]:
            output: list[dict[str, str]] = []
            for rec in recommendations:
                rec_id = rec["id"]
                section_id = rec["section_id"]
                url = recommendation_url(section_id, rec_id, base_url=self.base_url)
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

    def fetch_recommendation(self, rec_url: str) -> ExtractedRecommendation:
        """Fetch and parse a single recommendation page.

        Args:
            rec_url: URL to recommendation page

        Returns:
            The fields the page supplies, as the strategy extracted them
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

        # The benchmark's own page: its title, publish date and description
        page = self.fetch_benchmark_page(benchmark_url)
        title = page.title
        log(f"Benchmark title: {title}", level="debug")

        # Extract version from title (simple heuristic)
        version_match = re.search(r"v[\d.]+|vNEXT", title, re.IGNORECASE)
        version = version_match.group() if version_match else "v1.0.0"

        # Fetch navigation tree
        navtree = self.fetch_navtree(benchmark_id)
        recommendations_list = self.parse_navtree(navtree)
        log(f"Found {len(recommendations_list)} recommendations", level="debug")

        def build_recommendation(rec_meta: dict[str, str]) -> Recommendation:
            rec_data = self.fetch_recommendation(rec_meta["url"])
            # Pydantic validates the extracted fields
            return Recommendation(
                ref=rec_meta["ref"],
                title=rec_meta["title"],
                url=HttpUrl(rec_meta["url"]),
                **rec_data,
            )

        def report_completion(completed: int, total: int, rec_meta: dict[str, str]) -> None:
            log(
                f"[{completed}/{total}] Fetching {rec_meta['ref']}: {rec_meta['title']}",
                level="debug",
            )

        # Fetch recommendations concurrently; the session's adapter paces the requests and
        # results come back in navtree order. An expired session stops the run after the
        # batch that saw it.
        fetched = parallel_execute_batched(
            recommendations_list,
            build_recommendation,
            batch_size=self.batch_size,
            max_workers=self.max_workers,
            progress_callback=report_completion,
            stop_on=(AuthenticationError,),
        )
        for _, error in fetched.failed:
            if isinstance(error, AuthenticationError):
                # Every further fetch would get the login page too.
                raise error
        for rec_meta, error in fetched.failed:
            # Several errors already name the URL (FetchError, requests.HTTPError): say it once.
            detail = str(error)
            where = "" if rec_meta["url"] in detail else f"{rec_meta['url']}: "
            logger.error(f"Failed to fetch {where}{detail}")
        recommendations = fetched.results

        # Create Benchmark (Pydantic validates automatically). A strategy that copied the
        # page's HTML says so, and the model turns that text into Markdown.
        scraper_version = self._detected_strategy.version if self._detected_strategy else "manual"
        benchmark = Benchmark(
            title=title,
            benchmark_id=benchmark_id,
            url=HttpUrl(benchmark_url),
            version=version,
            published_date=page.published_date,
            description=page.description,
            profile_definitions=page.profile_definitions,
            scraper_version=scraper_version,
            text_format="html" if scraper_version in HTML_ERA_SCRAPER_VERSIONS else "markdown",
            total_recommendations=len(recommendations),
            recommendations=recommendations,
            downloaded_at=datetime.now(UTC),
        )

        log(f"✓ Successfully downloaded {len(recommendations)} recommendations", level="debug")

        return benchmark
