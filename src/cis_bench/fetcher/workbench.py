"""CIS WorkBench scraper with strategy pattern support.

This scraper uses the Strategy pattern to adapt to HTML changes.
It produces validated Pydantic Benchmark models.
"""

import logging
import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

import requests
import urllib3
from bs4 import BeautifulSoup

from cis_bench.fetcher.strategies.base import ScraperStrategy
from cis_bench.fetcher.strategies.detector import StrategyDetector
from cis_bench.models.benchmark import Benchmark, Recommendation

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


class WorkbenchScraper:
    """Scraper for CIS WorkBench with auto-adapting HTML strategies.

    Uses Strategy pattern to handle HTML structure changes gracefully.
    Produces validated Pydantic models as output.
    """

    def __init__(self, session: requests.Session, strategy: ScraperStrategy | None = None):
        """Initialize scraper.

        Args:
            session: Authenticated requests session
            strategy: Optional specific strategy (auto-detected if not provided)
        """
        self.session = session
        self.strategy = strategy
        self._detected_strategy = None

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

        if not self._detected_strategy:
            self._detected_strategy = StrategyDetector.detect_strategy(html)

        return self._detected_strategy

    def fetch_html(self, url: str) -> str:
        """Fetch HTML from URL.

        Args:
            url: URL to fetch

        Returns:
            HTML content

        Raises:
            requests.HTTPError: If request fails
        """
        response = self.session.get(url)
        response.raise_for_status()
        return response.text

    def fetch_json(self, url: str) -> dict[str, Any]:
        """Fetch JSON from URL.

        Args:
            url: URL to fetch

        Returns:
            Parsed JSON data

        Raises:
            requests.HTTPError: If request fails
        """
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

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
        return title_elem.get("title") if title_elem else "Unknown Benchmark"

    def fetch_navtree(self, benchmark_id: str) -> dict[str, Any]:
        """Fetch navigation tree for benchmark.

        Args:
            benchmark_id: CIS benchmark ID

        Returns:
            Navigation tree JSON data
        """
        url = f"https://workbench.cisecurity.org/api/v1/benchmarks/{benchmark_id}/navtree"
        return self.fetch_json(url)

    def parse_navtree(self, navtree_data: dict[str, Any]) -> list[dict[str, str]]:
        """Parse navigation tree to extract recommendation URLs.

        Args:
            navtree_data: Navigation tree JSON

        Returns:
            List of dicts with url, title, ref
        """

        def generate_urls(recommendations: list[dict]) -> list[dict]:
            output = []
            for rec in recommendations:
                rec_id = rec["id"]
                section_id = rec["section_id"]
                url = f"https://workbench.cisecurity.org/sections/{section_id}/recommendations/{rec_id}"
                output.append({"url": url, "title": rec["title"], "ref": rec["view_level"]})
            return output

        def parse_subsections(subsections: list[dict], result: list[dict]):
            for section in subsections:
                # Process recommendations at this level
                recommendations = section.get("recommendations_for_nav_tree", [])
                result.extend(generate_urls(recommendations))

                # Recursively process subsections
                sub_subsections = section.get("subsections_for_nav_tree")
                if sub_subsections:
                    parse_subsections(sub_subsections, result)

        parsed_data = []
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
            requests.HTTPError: If HTTP request fails
        """

        def log(msg: str, level="info"):
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
                    url=rec_meta["url"],
                    **rec_data,  # Spread extracted fields
                )

                recommendations.append(recommendation)

            except Exception as e:
                logger.error(f"Failed to fetch {rec_meta['url']}: {e}")
                # Continue with other recommendations
                continue

        # Create Benchmark (Pydantic validates automatically)
        benchmark = Benchmark(
            title=title,
            benchmark_id=benchmark_id,
            url=benchmark_url,
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
