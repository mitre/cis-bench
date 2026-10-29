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
from cis_bench.utils.parallel import parallel_execute

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
        metadata = self.get_benchmark_metadata(benchmark_url)
        return metadata.get("title", "Unknown Benchmark")

    def get_benchmark_metadata(self, benchmark_url: str) -> dict:
        """Fetch benchmark metadata from detail page.

        Extracts title, published_date, description, etc. from the
        benchmark's main page.

        Args:
            benchmark_url: URL to benchmark page

        Returns:
            Dictionary with title, published_date, description, etc.
        """
        from cis_bench.catalog.parser import WorkBenchCatalogParser

        html = self.fetch_html(benchmark_url)
        soup = BeautifulSoup(html, "html.parser")

        # Get title from custom element
        title_elem = soup.find(name="wb-benchmark-title")
        title = title_elem.get("title") if title_elem else "Unknown Benchmark"

        # Get additional metadata (published_date, description, etc.)
        metadata = WorkBenchCatalogParser.parse_benchmark_detail_page(html)
        metadata["title"] = title

        return metadata

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
        self,
        benchmark_url: str,
        progress_callback: Callable[[str], None] | None = None,
        max_workers: int = 10,
    ) -> Benchmark:
        """Download complete benchmark with all recommendations.

        Uses parallel fetching with ThreadPoolExecutor for 10x faster downloads.

        Args:
            benchmark_url: URL to benchmark page
            progress_callback: Optional callback for progress messages
            max_workers: Number of parallel threads (default: 10)

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

        def fetch_single_recommendation(rec_meta: dict) -> Recommendation | None:
            """Fetch a single recommendation (for parallel execution)."""
            rec_data = self.fetch_recommendation(rec_meta["url"])
            return Recommendation(
                ref=rec_meta["ref"],
                title=rec_meta["title"],
                url=rec_meta["url"],
                **rec_data,
            )

        # Extract benchmark ID
        benchmark_id = self.get_benchmark_id(benchmark_url)
        log(f"Fetching benchmark: {benchmark_url}", level="debug")

        # Get benchmark metadata (ALL fields from detail page)
        metadata = self.get_benchmark_metadata(benchmark_url)
        title = metadata.get("title", "Unknown Benchmark")
        log(f"Benchmark title: {title}", level="debug")
        if metadata.get("published_date"):
            log(f"Published: {metadata['published_date']}", level="debug")
        if metadata.get("release_type"):
            log(f"Release Type: {metadata['release_type']}", level="debug")

        # Extract version from title (simple heuristic)
        version_match = re.search(r"v[\d.]+|vNEXT", title, re.IGNORECASE)
        version = version_match.group() if version_match else "v1.0.0"

        # Fetch navigation tree
        navtree = self.fetch_navtree(benchmark_id)
        recommendations_list = self.parse_navtree(navtree)
        total = len(recommendations_list)
        log(f"Found {total} recommendations", level="debug")

        # Progress callback adapter for parallel_execute
        def on_progress(completed: int, total_count: int, rec_meta: dict):
            log(
                f"[{completed}/{total_count}] {rec_meta['ref']}: {rec_meta['title'][:40]}",
                level="debug",
            )

        # Fetch recommendations in parallel using centralized utility
        result = parallel_execute(
            recommendations_list,
            fetch_single_recommendation,
            max_workers=max_workers,
            progress_callback=on_progress,
        )

        # Log any failures
        for rec_meta, error in result.failed:
            logger.error(f"Failed to fetch {rec_meta['url']}: {error}")

        # Sort recommendations by ref to maintain consistent order
        recommendations = sorted(result.results, key=lambda r: r.ref)

        # Create Benchmark with ALL metadata (Pydantic validates automatically)
        benchmark = Benchmark(
            title=title,
            benchmark_id=benchmark_id,
            url=benchmark_url,
            version=version,
            # Core metadata
            published_date=metadata.get("published_date"),
            published_relative=metadata.get("published_relative"),
            description=metadata.get("description"),
            release_type=metadata.get("release_type"),
            # Attribution
            contributors=metadata.get("contributors", []),
            # Lineage
            parent_benchmark_url=metadata.get("parent_benchmark_url"),
            parent_benchmark_title=metadata.get("parent_benchmark_title"),
            # Organizational
            community_url=metadata.get("community_url"),
            milestone_name=metadata.get("milestone_name"),
            milestone_url=metadata.get("milestone_url"),
            # Documentation
            intended_audience=metadata.get("intended_audience"),
            acknowledgements=metadata.get("acknowledgements"),
            # Structured data
            assets=metadata.get("assets", []),
            revision_history=metadata.get("revision_history", []),
            # System metadata
            scraper_version=(
                self._detected_strategy.version if self._detected_strategy else "manual"
            ),
            total_recommendations=len(recommendations),
            recommendations=recommendations,
            downloaded_at=datetime.now(),
        )

        log(f"✓ Successfully downloaded {len(recommendations)} recommendations", level="debug")

        return benchmark
