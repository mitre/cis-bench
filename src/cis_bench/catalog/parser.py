"""Parser for CIS WorkBench catalog pages.

Extracts benchmark metadata from HTML catalog listing pages.
"""

import logging
import re
from gettext import ngettext

from bs4 import BeautifulSoup

from cis_bench.exceptions import AuthenticationError
from cis_bench.fetcher.auth import is_workbench_login_page
from cis_bench.utils.workbench_urls import normalize_benchmark_url

logger = logging.getLogger(__name__)


class WorkBenchCatalogParser:
    """Parse CIS WorkBench catalog HTML pages."""

    @staticmethod
    def is_login_page(html: str) -> bool:
        """Detect if HTML is the login page (unauthenticated response).

        Args:
            html: HTML content to check

        Returns:
            True if this is the login page, False otherwise

        Example:
            if WorkBenchCatalogParser.is_login_page(html):
                raise AuthenticationError("Not authenticated")
        """
        return is_workbench_login_page(html)

    @staticmethod
    def parse_catalog_page(html: str, *, base_url: str) -> list[dict]:
        """Extract benchmark list from catalog page.

        Args:
            html: HTML content from WorkBench catalog page
            base_url: The WorkBench origin the page came from; row links must be on it

        Returns:
            List of dictionaries with benchmark data

        Raises:
            AuthenticationError: If HTML is the login page (not authenticated)

        Example:
            benchmarks = WorkBenchCatalogParser.parse_catalog_page(html, base_url=origin)
            for b in benchmarks:
                print(f"{b['benchmark_id']}: {b['title']}")
        """
        # Check for login page first (defensive check)
        if WorkBenchCatalogParser.is_login_page(html):
            raise AuthenticationError(
                "Not authenticated. Session is invalid or expired. "
                "Please run: cis-bench auth login --browser chrome"
            )

        soup = BeautifulSoup(html, "html.parser")

        # Find the benchmarks table
        table = soup.find("table")

        if not table:
            logger.warning("No table found in catalog HTML")
            return []

        # Get all data rows (skip header)
        rows = table.find_all("tr")[1:]  # Skip header row

        benchmarks = []

        for row in rows:
            try:
                benchmark = WorkBenchCatalogParser._parse_table_row(row, base_url)
                if benchmark:
                    benchmarks.append(benchmark)
            except Exception as e:
                logger.warning(f"Failed to parse row: {e}")
                continue

        logger.debug(
            ngettext(
                "Parsed {count} benchmark from catalog page",
                "Parsed {count} benchmarks from catalog page",
                len(benchmarks),
            ).format(count=len(benchmarks))
        )
        return benchmarks

    @staticmethod
    def _parse_table_row(row, base_url: str) -> dict | None:
        """Parse single table row.

        Table columns:
        0: Title (with link containing benchmark ID)
        1: Version
        2: Status
        3: Community
        4: Collections
        5: Owner
        6: (empty/actions)
        """
        cells = row.find_all("td")

        if len(cells) < 6:
            return None

        # Extract title and benchmark ID from link
        title_cell = cells[0]
        link = title_cell.find("a")

        if not link:
            return None

        href = link.get("href", "")
        title = link.get_text(strip=True)

        try:
            benchmark_id, url = normalize_benchmark_url(href, base_url=base_url)
        except ValueError:
            return None

        # Clean title (remove leading pipe and org name)
        # Format: "|CIS AKS..." or "Center for Internet Security, New York |CIS AKS..."
        if "|" in title:
            title = title.split("|", 1)[1].strip()

        # Remove "[imported]" suffix if present
        title = title.replace("[imported]", "").strip()

        # Infer platform and platform type from title (high accuracy heuristic)
        platform_type, platform = WorkBenchCatalogParser._infer_platform(title)

        # Extract other fields
        version = cells[1].get_text(strip=True)
        status = cells[2].get_text(strip=True)
        community = cells[3].get_text(strip=True) or None
        collections_text = cells[4].get_text(strip=True)
        owner = cells[5].get_text(strip=True) or None

        # Parse collections (comma-separated or single, stripped and deduplicated)
        collections = (
            list(dict.fromkeys(c.strip() for c in collections_text.split(",") if c.strip()))
            if collections_text
            else []
        )

        return {
            "benchmark_id": benchmark_id,
            "title": title,
            "version": version if version else None,
            "status": status,
            "url": url,
            "platform_type": platform_type,
            "platform": platform,
            "community": community,
            "owner": owner,
            "collections": collections if collections else [],
        }

    # Platform mapping: (keywords, platform_type, platform_name).
    # Each keyword is a regex fragment matched case-insensitively on whole words only
    # (anchored with \b on both sides), so "aks" matches "(AKS)" but not "Oaks".
    # All keywords are literal text except "oracle.*container engine".
    PLATFORM_PATTERNS = [
        # Managed Kubernetes services that include cloud vendor names in title (check before cloud)
        (["aks"], "container", "azure-aks"),
        # Cloud Platforms (check before OS to catch "Oracle Cloud" before "Oracle")
        (["oracle cloud", "oci"], "cloud", "oracle-cloud"),
        (["amazon web services", "aws"], "cloud", "aws"),
        (["google cloud", "gcp"], "cloud", "google-cloud"),
        (["microsoft azure", "azure"], "cloud", "azure"),
        (["alibaba cloud"], "cloud", "alibaba-cloud"),
        (["ibm cloud"], "cloud", "ibm-cloud"),
        # Databases (check before OS to catch "Oracle Database" before "Oracle Linux")
        (["oracle database", "oracle db"], "database", "oracle-database"),
        (["mysql"], "database", "mysql"),
        (["postgresql", "postgres"], "database", "postgresql"),
        (["mongodb"], "database", "mongodb"),
        (["microsoft sql server", "mssql"], "database", "mssql"),
        # Operating Systems
        (["ubuntu"], "os", "ubuntu"),
        (["almalinux", "alma linux"], "os", "almalinux"),
        (["rocky linux", "rockylinux"], "os", "rocky-linux"),
        (["red hat", "rhel"], "os", "red-hat"),
        (["oracle linux"], "os", "oracle-linux"),
        (["debian"], "os", "debian"),
        (["suse", "sles"], "os", "suse"),
        (["windows server"], "os", "windows-server"),
        (["macos", "mac os"], "os", "macos"),
        # Containers & Kubernetes (specific services)
        (["eks"], "container", "aws-eks"),
        (["gke"], "container", "google-gke"),
        (["oke", "oracle.*container engine"], "container", "oracle-oke"),
        (["kubernetes", "k8s"], "container", "kubernetes"),
        (["docker"], "container", "docker"),
        # Applications
        (["nginx"], "application", "nginx"),
        (["tomcat"], "application", "tomcat"),
    ]

    _COMPILED_PLATFORM_PATTERNS = [
        (
            [re.compile(rf"\b(?:{keyword})\b", re.IGNORECASE) for keyword in keywords],
            platform_type,
            platform_name,
        )
        for keywords, platform_type, platform_name in PLATFORM_PATTERNS
    ]

    @staticmethod
    def _infer_platform(title: str) -> tuple[str | None, str | None]:
        """Infer platform type and name from benchmark title.

        Args:
            title: Benchmark title

        Returns:
            Tuple of (platform_type, platform_name) or (None, None)

        Example:
            "CIS Ubuntu Linux 20.04" → ("os", "ubuntu")
            "CIS Amazon Web Services" → ("cloud", "aws")
            "CIS Oracle Database 19c" → ("database", "oracle-database")
            "CIS Oracle Cloud Infrastructure" → ("cloud", "oracle-cloud")
        """
        # Check patterns in order (more specific first); every keyword is anchored on
        # word boundaries, so ordering only decides genuinely ambiguous titles.
        for (
            patterns,
            platform_type,
            platform_name,
        ) in WorkBenchCatalogParser._COMPILED_PLATFORM_PATTERNS:
            if any(pattern.search(title) for pattern in patterns):
                return (platform_type, platform_name)

        # No match
        return (None, None)

    @staticmethod
    def extract_pagination_info(html: str) -> dict:
        """Extract pagination information from catalog page.

        Args:
            html: HTML content

        Returns:
            Dictionary with current_page, total_pages, total_count
        """
        soup = BeautifulSoup(html, "html.parser")

        result = {"current_page": 1, "total_pages": None, "total_count": 0}

        # Look for nav element with pagination (current WorkBench format)
        nav = soup.find("nav")
        if nav:
            # Get all page number links
            # Format: <nav>‹ 1 2 3 4 5 6 7 8 9 10 ... 65 66 ›</nav>
            page_links = nav.find_all("a")
            page_numbers = []

            for link in page_links:
                text = link.get_text(strip=True)
                if text.isdigit():
                    page_numbers.append(int(text))

            if page_numbers:
                # Last page number is total pages
                total_pages = max(page_numbers)
                result["total_pages"] = total_pages
                logger.debug(
                    ngettext(
                        "Detected {count} page from nav element",
                        "Detected {count} pages from nav element",
                        total_pages,
                    ).format(count=total_pages)
                )

        # Fallback: Look for old format pagination
        if result["total_pages"] is None:
            pagination = soup.find("div", class_=re.compile(r"pagination|pager", re.I))
            if pagination:
                text = soup.get_text()
                page_match = re.search(r"Page (\d+) of (\d+)", text, re.I)
                if page_match:
                    result["current_page"] = int(page_match.group(1))
                    result["total_pages"] = int(page_match.group(2))

        logger.debug(f"Pagination info: {result}")
        return result
