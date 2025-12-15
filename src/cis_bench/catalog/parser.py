"""Parser for CIS WorkBench catalog pages.

Extracts benchmark metadata from HTML catalog listing pages.
"""

import logging
import re

from bs4 import BeautifulSoup

from cis_bench.exceptions import AuthenticationError

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
        if not html:
            return False

        soup = BeautifulSoup(html, "html.parser")

        # Check for login form indicators
        login_indicators = [
            soup.find("form", action=re.compile(r"/login")),  # Login form
            soup.find("input", {"name": "login"}),  # E-Mail/Username field
            soup.find("input", {"name": "password"}),  # Password field
            soup.find("div", class_="index-signin-wrapper"),  # Login wrapper
            soup.find(string=re.compile(r"E-Mail or Username", re.I)),  # Label text
        ]

        # If any login indicator is found, it's the login page
        return any(indicator is not None for indicator in login_indicators)

    @staticmethod
    def parse_catalog_page(html: str) -> list[dict]:
        """Extract benchmark list from catalog page.

        Args:
            html: HTML content from WorkBench catalog page

        Returns:
            List of dictionaries with benchmark data

        Raises:
            AuthenticationError: If HTML is the login page (not authenticated)

        Example:
            benchmarks = WorkBenchCatalogParser.parse_catalog_page(html)
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
                benchmark = WorkBenchCatalogParser._parse_table_row(row)
                if benchmark:
                    benchmarks.append(benchmark)
            except Exception as e:
                logger.warning(f"Failed to parse row: {e}")
                continue

        logger.info(f"Parsed {len(benchmarks)} benchmarks from catalog page")
        return benchmarks

    @staticmethod
    def _parse_table_row(row) -> dict | None:
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

        # Extract benchmark ID from URL
        # Format: https://workbench.cisecurity.org/benchmarks/23598
        benchmark_id = None
        if "/benchmarks/" in href:
            try:
                # Extract ID from URL
                id_part = href.split("/benchmarks/")[1]
                benchmark_id = id_part.split("/")[0].split("?")[0]
            except (IndexError, AttributeError):
                logger.warning(f"Could not extract ID from URL: {href}")
                return None

        if not benchmark_id:
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

        # Parse collections (might be comma-separated or single)
        collections = []
        if collections_text:
            # Split by comma or use as single
            if "," in collections_text:
                collections = [c.strip() for c in collections_text.split(",")]
            else:
                collections = [collections_text]

        # Build full URL
        if href.startswith("http"):
            url = href
        else:
            url = f"https://workbench.cisecurity.org{href}"

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

    # Platform mapping: (keywords, platform_type, platform_name)
    PLATFORM_PATTERNS = [
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
        (["aks"], "container", "azure-aks"),
        (["gke"], "container", "google-gke"),
        (["oke", "oracle.*container engine"], "container", "oracle-oke"),
        (["kubernetes", "k8s"], "container", "kubernetes"),
        (["docker"], "container", "docker"),
        # Applications
        (["nginx"], "application", "nginx"),
        (["tomcat"], "application", "tomcat"),
    ]

    @staticmethod
    def _infer_platform(title: str) -> tuple:
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
        title_lower = title.lower()

        # Check patterns in order (more specific first)
        for keywords, platform_type, platform_name in WorkBenchCatalogParser.PLATFORM_PATTERNS:
            for keyword in keywords:
                # Use regex for patterns like "oracle.*container"
                import re

                if re.search(keyword, title_lower):
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
                result["total_pages"] = max(page_numbers)
                logger.debug(f"Detected {result['total_pages']} pages from nav element")

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

    @staticmethod
    def parse_benchmark_detail_page(html: str) -> dict:
        """Parse individual benchmark page for additional metadata.

        This is for Phase 2 enhancement - get published date, description, etc.
        from the benchmark detail page (not the catalog listing).

        Args:
            html: HTML from benchmark detail page

        Returns:
            Dictionary with published_date, description, etc.
        """
        soup = BeautifulSoup(html, "html.parser")

        metadata = {}

        # Extract published date
        # Format: "Published 3 months ago on Aug 1st 2025"
        published_text = soup.find(text=re.compile(r"Published.*ago"))
        if published_text:
            # Try to extract actual date
            date_match = re.search(r"on ([A-Za-z]+ \d+(?:st|nd|rd|th) \d{4})", published_text)
            if date_match:
                metadata["published_date"] = date_match.group(1)
                metadata["published_relative"] = published_text.strip()

        # Extract description from Overview section
        overview = soup.find("h2", text=re.compile(r"Overview", re.I))
        if overview:
            # Get text after Overview heading
            desc_parts = []
            for sibling in overview.find_next_siblings():
                if sibling.name and sibling.name.startswith("h"):
                    break  # Stop at next heading
                text = sibling.get_text(strip=True)
                if text:
                    desc_parts.append(text)

            if desc_parts:
                metadata["description"] = " ".join(desc_parts[:3])  # First 3 paragraphs

        logger.debug(f"Extracted metadata: {metadata}")
        return metadata
