"""Unit tests for catalog HTML parser."""

from pathlib import Path

import pytest

from cis_bench.catalog.parser import WorkBenchCatalogParser
from cis_bench.exceptions import AuthenticationError

BASE = "https://workbench.cisecurity.org"


@pytest.fixture
def sample_catalog_html():
    """Load sample catalog HTML."""
    fixture_path = (
        Path(__file__).parent.parent / "fixtures" / "html" / "workbench_catalog_page1_sample.html"
    )
    return fixture_path.read_text()


@pytest.fixture
def login_page_html():
    """Load login page HTML."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "html" / "workbench_login_page.html"
    return fixture_path.read_text()


class TestCatalogPageParsing:
    """Test parsing catalog listing pages."""

    def test_parse_catalog_page(self, sample_catalog_html):
        """Test parsing returns list of benchmarks."""
        benchmarks = WorkBenchCatalogParser.parse_catalog_page(sample_catalog_html, base_url=BASE)

        assert isinstance(benchmarks, list)
        assert len(benchmarks) > 0

    def test_benchmark_has_required_fields(self, sample_catalog_html):
        """Test parsed benchmarks have all required fields."""
        benchmarks = WorkBenchCatalogParser.parse_catalog_page(sample_catalog_html, base_url=BASE)

        bench = benchmarks[0]

        assert "benchmark_id" in bench
        assert "title" in bench
        assert "version" in bench
        assert "status" in bench
        assert "url" in bench
        assert "community" in bench
        assert "owner" in bench
        assert "collections" in bench

    def test_benchmark_id_extraction(self, sample_catalog_html):
        """Test benchmark ID is correctly extracted from URL."""
        benchmarks = WorkBenchCatalogParser.parse_catalog_page(sample_catalog_html, base_url=BASE)

        # Check IDs are numeric strings
        for bench in benchmarks:
            assert bench["benchmark_id"].isdigit()
            assert len(bench["benchmark_id"]) > 0

    def test_title_cleaning(self, sample_catalog_html):
        """Test title is cleaned (removes org prefix, [imported] suffix)."""
        benchmarks = WorkBenchCatalogParser.parse_catalog_page(sample_catalog_html, base_url=BASE)

        for bench in benchmarks:
            # Should not have pipe prefix
            assert not bench["title"].startswith("|")
            # Should not have [imported] suffix
            assert "[imported]" not in bench["title"]

    def test_status_values(self, sample_catalog_html):
        """Test all five WorkBench status values are exercised by the catalog fixture."""
        benchmarks = WorkBenchCatalogParser.parse_catalog_page(sample_catalog_html, base_url=BASE)

        valid_statuses = {"Published", "Draft", "Archived", "Rejected", "Accepted"}

        assert {bench["status"] for bench in benchmarks} == valid_statuses

    def test_sample_catalog_fixture_is_compact_synthetic_html(self, sample_catalog_html):
        """Catalog HTML fixture must be clean synthetic markup covering parser edge cases."""
        lowered = sample_catalog_html.lower()
        assert "<script" not in lowered
        assert "googletagmanager" not in lowered
        assert "csrf-token" not in lowered
        assert "livewirescriptconfig" not in lowered

        benchmarks = WorkBenchCatalogParser.parse_catalog_page(sample_catalog_html, base_url=BASE)
        assert len(benchmarks) == 6
        assert any(len(b["collections"]) >= 2 for b in benchmarks)
        assert any(b["collections"] == [] for b in benchmarks)
        assert any(b["community"] is not None for b in benchmarks)
        assert any(b["owner"] is not None for b in benchmarks)

        pagination = WorkBenchCatalogParser.extract_pagination_info(sample_catalog_html)
        assert pagination["current_page"] == 1
        assert pagination["total_pages"] == 66

    def test_collections_is_list(self, sample_catalog_html):
        """Test collections field is always a list."""
        benchmarks = WorkBenchCatalogParser.parse_catalog_page(sample_catalog_html, base_url=BASE)

        for bench in benchmarks:
            assert isinstance(bench["collections"], list)

    def test_url_format(self, sample_catalog_html):
        """Test URLs are properly formatted."""
        benchmarks = WorkBenchCatalogParser.parse_catalog_page(sample_catalog_html, base_url=BASE)

        for bench in benchmarks:
            assert bench["url"].startswith("https://workbench.cisecurity.org")
            assert "/benchmarks/" in bench["url"]


class TestPaginationParsing:
    """Test pagination information extraction."""

    def test_extract_pagination_info(self, sample_catalog_html):
        """Test extracting pagination data."""
        pagination = WorkBenchCatalogParser.extract_pagination_info(sample_catalog_html)

        assert isinstance(pagination, dict)
        assert "current_page" in pagination
        assert "total_pages" in pagination
        assert "total_count" in pagination

    def test_pagination_with_nav_element(self):
        """Test pagination extraction from nav element with page links."""
        html = """
        <html>
        <body>
            <nav>
                <a href="?page=1">1</a>
                <a href="?page=2">2</a>
                <a href="?page=3">3</a>
                <span>...</span>
                <a href="?page=66">66</a>
            </nav>
        </body>
        </html>
        """
        pagination = WorkBenchCatalogParser.extract_pagination_info(html)

        assert pagination["total_pages"] == 66
        assert pagination["current_page"] == 1

    def test_pagination_with_nav_but_no_page_numbers(self):
        """Test pagination when nav element exists but has no numeric page links."""
        html = """
        <html>
        <body>
            <nav>
                <a href="?page=prev">Previous</a>
                <a href="?page=next">Next</a>
            </nav>
        </body>
        </html>
        """
        pagination = WorkBenchCatalogParser.extract_pagination_info(html)

        # Should fall through to fallback, total_pages remains None
        assert pagination["total_pages"] is None
        assert pagination["current_page"] == 1

    def test_pagination_old_format_with_page_of_text(self):
        """Test pagination extraction from old format 'Page X of Y' text."""
        html = """
        <html>
        <body>
            <div class="pagination">
                Page 3 of 15
            </div>
        </body>
        </html>
        """
        pagination = WorkBenchCatalogParser.extract_pagination_info(html)

        assert pagination["current_page"] == 3
        assert pagination["total_pages"] == 15

    def test_pagination_old_format_pager_class(self):
        """Test pagination extraction from div with 'pager' class."""
        html = """
        <html>
        <body>
            <div class="pager">
                Showing Page 7 of 25
            </div>
        </body>
        </html>
        """
        pagination = WorkBenchCatalogParser.extract_pagination_info(html)

        assert pagination["current_page"] == 7
        assert pagination["total_pages"] == 25

    def test_pagination_no_pagination_element(self):
        """Test pagination when no pagination elements exist."""
        html = "<html><body><p>No pagination</p></body></html>"
        pagination = WorkBenchCatalogParser.extract_pagination_info(html)

        assert pagination["current_page"] == 1
        assert pagination["total_pages"] is None
        assert pagination["total_count"] == 0

    def test_pagination_div_exists_but_no_page_text(self):
        """Test pagination when div exists but no 'Page X of Y' text (coverage: branch 295->299)."""
        html = """
        <html>
        <body>
            <div class="pagination">
                <span>Previous</span>
                <span>Next</span>
            </div>
        </body>
        </html>
        """
        pagination = WorkBenchCatalogParser.extract_pagination_info(html)

        # Pagination div exists but no "Page X of Y" text, so no pages extracted
        assert pagination["current_page"] == 1
        assert pagination["total_pages"] is None


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_html(self):
        """Test parsing empty HTML returns empty list."""
        benchmarks = WorkBenchCatalogParser.parse_catalog_page("", base_url=BASE)
        assert benchmarks == []

    def test_html_without_table(self):
        """Test HTML without table returns empty list."""
        html = "<html><body><p>No table here</p></body></html>"
        benchmarks = WorkBenchCatalogParser.parse_catalog_page(html, base_url=BASE)
        assert benchmarks == []

    def test_malformed_row(self):
        """Test malformed rows are skipped."""
        html = """
        <table>
            <tr><th>Header</th></tr>
            <tr><td>Only one cell</td></tr>
            <tr>
                <td><a href="/benchmarks/123">Valid Benchmark</a></td>
                <td>v1.0.0</td>
                <td>Published</td>
                <td>Community</td>
                <td>Collection</td>
                <td>Owner</td>
            </tr>
        </table>
        """

        benchmarks = WorkBenchCatalogParser.parse_catalog_page(html, base_url=BASE)

        # Should parse the valid row, skip the malformed one
        assert len(benchmarks) == 1
        assert benchmarks[0]["benchmark_id"] == "123"

    def test_missing_optional_fields(self):
        """Test handles missing community/owner/collections."""
        html = """
        <table>
            <tr><th>Title</th><th>Version</th><th>Status</th><th>Community</th><th>Collections</th><th>Owner</th></tr>
            <tr>
                <td><a href="/benchmarks/123">Test Benchmark</a></td>
                <td>v1.0.0</td>
                <td>Published</td>
                <td></td>
                <td></td>
                <td></td>
            </tr>
        </table>
        """

        benchmarks = WorkBenchCatalogParser.parse_catalog_page(html, base_url=BASE)

        assert len(benchmarks) == 1
        assert benchmarks[0]["community"] is None
        assert benchmarks[0]["owner"] is None
        assert benchmarks[0]["collections"] == []

    def test_row_without_link_in_title_cell(self):
        """Test rows without link in title cell are skipped (coverage: line 124)."""
        html = """
        <table>
            <tr><th>Header</th></tr>
            <tr>
                <td>Title without link</td>
                <td>v1.0.0</td>
                <td>Published</td>
                <td>Community</td>
                <td>Collection</td>
                <td>Owner</td>
            </tr>
        </table>
        """
        benchmarks = WorkBenchCatalogParser.parse_catalog_page(html, base_url=BASE)
        assert benchmarks == []

    def test_link_without_benchmarks_path(self):
        """Test links without /benchmarks/ path are skipped (coverage: line 132->141, 142)."""
        html = """
        <table>
            <tr><th>Header</th></tr>
            <tr>
                <td><a href="/other/123">Some Link</a></td>
                <td>v1.0.0</td>
                <td>Published</td>
                <td>Community</td>
                <td>Collection</td>
                <td>Owner</td>
            </tr>
        </table>
        """
        benchmarks = WorkBenchCatalogParser.parse_catalog_page(html, base_url=BASE)
        assert benchmarks == []

    def test_malformed_benchmark_url_extraction(self):
        """Test handles malformed URL with /benchmarks/ but no ID after (coverage: lines 137-139)."""
        html = """
        <table>
            <tr><th>Header</th></tr>
            <tr>
                <td><a href="/benchmarks/">Malformed URL no ID</a></td>
                <td>v1.0.0</td>
                <td>Published</td>
                <td>Community</td>
                <td>Collection</td>
                <td>Owner</td>
            </tr>
        </table>
        """
        benchmarks = WorkBenchCatalogParser.parse_catalog_page(html, base_url=BASE)
        # Empty string ID would be falsy, so row is skipped
        assert benchmarks == []

    def test_title_with_pipe_but_no_content_after(self):
        """Test title cleaning when pipe exists but nothing follows (coverage: line 147)."""
        html = """
        <table>
            <tr><th>Header</th></tr>
            <tr>
                <td><a href="/benchmarks/123">Organization Name |</a></td>
                <td>v1.0.0</td>
                <td>Published</td>
                <td>Community</td>
                <td>Collection</td>
                <td>Owner</td>
            </tr>
        </table>
        """
        benchmarks = WorkBenchCatalogParser.parse_catalog_page(html, base_url=BASE)

        assert len(benchmarks) == 1
        # After split and strip, should be empty string
        assert benchmarks[0]["title"] == ""

    def test_collections_with_comma_separated_values(self):
        """Test collections parsing with comma-separated values (coverage: line 167)."""
        html = """
        <table>
            <tr><th>Header</th></tr>
            <tr>
                <td><a href="/benchmarks/123">Test Benchmark</a></td>
                <td>v1.0.0</td>
                <td>Published</td>
                <td>Community</td>
                <td>Collection A, Collection B, Collection C</td>
                <td>Owner</td>
            </tr>
        </table>
        """
        benchmarks = WorkBenchCatalogParser.parse_catalog_page(html, base_url=BASE)

        assert len(benchmarks) == 1
        assert benchmarks[0]["collections"] == ["Collection A", "Collection B", "Collection C"]

    def test_collections_deduplicates_and_strips_empty_entries(self):
        """Comma-separated collections strip empty items and preserve unique order."""
        html = """
        <table>
            <tr><th>Header</th></tr>
            <tr>
                <td><a href="/benchmarks/123">Test Benchmark</a></td>
                <td>v1.0.0</td>
                <td>Published</td>
                <td>Community</td>
                <td>Collection A, , Collection B, Collection A,   </td>
                <td>Owner</td>
            </tr>
        </table>
        """
        benchmarks = WorkBenchCatalogParser.parse_catalog_page(html, base_url=BASE)

        assert len(benchmarks) == 1
        assert benchmarks[0]["collections"] == ["Collection A", "Collection B"]

    def test_absolute_url_in_href(self):
        """Test handling of absolute URLs in href (coverage: line 172-173)."""
        html = """
        <table>
            <tr><th>Header</th></tr>
            <tr>
                <td><a href="https://workbench.cisecurity.org/benchmarks/456">Absolute URL</a></td>
                <td>v1.0.0</td>
                <td>Published</td>
                <td>Community</td>
                <td>Collection</td>
                <td>Owner</td>
            </tr>
        </table>
        """
        benchmarks = WorkBenchCatalogParser.parse_catalog_page(html, base_url=BASE)

        assert len(benchmarks) == 1
        assert benchmarks[0]["url"] == "https://workbench.cisecurity.org/benchmarks/456"
        assert benchmarks[0]["benchmark_id"] == "456"

    def test_url_with_query_params(self):
        """Test URL parsing handles query parameters and fragments by stripping them cleanly."""
        html = """
        <table>
            <tr><th>Header</th></tr>
            <tr>
                <td><a href="/benchmarks/789?version=1&sort=asc#overview">With Query Params</a></td>
                <td>v1.0.0</td>
                <td>Published</td>
                <td>Community</td>
                <td>Collection</td>
                <td>Owner</td>
            </tr>
        </table>
        """
        benchmarks = WorkBenchCatalogParser.parse_catalog_page(html, base_url=BASE)

        assert len(benchmarks) == 1
        assert benchmarks[0]["benchmark_id"] == "789"
        assert benchmarks[0]["url"] == "https://workbench.cisecurity.org/benchmarks/789"

    @pytest.mark.parametrize(
        "malicious_href",
        [
            "@attacker.example/benchmarks/23598",
            "https://workbench.cisecurity.org@attacker.example/benchmarks/23598",
            "//attacker.example/benchmarks/23598",
            "https://attacker.example/benchmarks/23598",
            "https://portal.cisecurity.org/benchmarks/23598",
            "http://workbench.cisecurity.org/benchmarks/23598",
            "/\\attacker.example/benchmarks/23598",
            "/benchmarks/23598/../../admin",
            "https://workbench.cisecurity.org/benchmarks/23598/../../admin",
            "/benchmarks/not-numeric",
            "/benchmarks/٢٣٥٩٨",
        ],
    )
    def test_rejects_off_origin_userinfo_and_non_numeric_benchmark_urls(self, malicious_href):
        """Catalog parser rejects @attacker userinfo tricks, off-origin hosts, HTTP, traversal, and non-ASCII IDs."""
        html = f"""
        <table>
            <tr><th>Title</th><th>Version</th><th>Status</th><th>Community</th><th>Collections</th><th>Owner</th></tr>
            <tr>
                <td><a href="{malicious_href}">Malicious Benchmark</a></td>
                <td>v1.0.0</td>
                <td>Published</td>
                <td>Community</td>
                <td>Collection</td>
                <td>Owner</td>
            </tr>
        </table>
        """
        benchmarks = WorkBenchCatalogParser.parse_catalog_page(html, base_url=BASE)

        assert benchmarks == []

    def test_url_with_trailing_path(self):
        """Test URL parsing handles trailing path segments correctly."""
        html = """
        <table>
            <tr><th>Header</th></tr>
            <tr>
                <td><a href="/benchmarks/555/details/sections">With Trailing Path</a></td>
                <td>v1.0.0</td>
                <td>Published</td>
                <td>Community</td>
                <td>Collection</td>
                <td>Owner</td>
            </tr>
        </table>
        """
        benchmarks = WorkBenchCatalogParser.parse_catalog_page(html, base_url=BASE)

        assert len(benchmarks) == 1
        assert benchmarks[0]["benchmark_id"] == "555"

    def test_parse_row_exception_handling(self):
        """Test exception handling during row parsing (coverage: lines 94-96)."""
        # Create HTML that will cause _parse_table_row to raise
        # We need to mock _parse_table_row to raise an exception
        from unittest.mock import patch

        html = """
        <table>
            <tr><th>Header</th></tr>
            <tr>
                <td><a href="/benchmarks/111">Benchmark 1</a></td>
                <td>v1.0.0</td>
                <td>Published</td>
                <td>Community</td>
                <td>Collection</td>
                <td>Owner</td>
            </tr>
            <tr>
                <td><a href="/benchmarks/222">Benchmark 2</a></td>
                <td>v2.0.0</td>
                <td>Draft</td>
                <td>Community</td>
                <td>Collection</td>
                <td>Owner</td>
            </tr>
        </table>
        """

        call_count = [0]
        original_parse_row = WorkBenchCatalogParser._parse_table_row

        def mock_parse_row(row, base_url):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ValueError("Test exception on first row")
            return original_parse_row(row, base_url)

        with patch.object(WorkBenchCatalogParser, "_parse_table_row", side_effect=mock_parse_row):
            benchmarks = WorkBenchCatalogParser.parse_catalog_page(html, base_url=BASE)

        # First row fails, second succeeds
        assert len(benchmarks) == 1
        assert benchmarks[0]["benchmark_id"] == "222"

    def test_url_id_extraction_attribute_error(self):
        """Test handling of AttributeError during URL ID extraction (coverage: lines 137-139).

        This tests the except block that catches IndexError/AttributeError.
        We mock the split method to raise AttributeError.
        """
        from unittest.mock import MagicMock, patch

        html = """
        <table>
            <tr><th>Header</th></tr>
            <tr>
                <td><a href="/benchmarks/123">Benchmark</a></td>
                <td>v1.0.0</td>
                <td>Published</td>
                <td>Community</td>
                <td>Collection</td>
                <td>Owner</td>
            </tr>
        </table>
        """

        # Create a mock href that will cause AttributeError on split
        original_parse_row = WorkBenchCatalogParser._parse_table_row

        def mock_parse_row_with_broken_href(row):
            """Parse row but with a href that raises on split."""

            cells = row.find_all("td")
            if len(cells) < 6:
                return None

            title_cell = cells[0]
            link = title_cell.find("a")
            if not link:
                return None

            # Create a mock href object that raises AttributeError on split
            mock_href = MagicMock()
            mock_href.__contains__ = lambda self, x: True  # "/benchmarks/" in href
            mock_href.split = MagicMock(side_effect=AttributeError("Test AttributeError"))

            # Temporarily replace get method
            original_get = link.get

            def mock_get(attr, default=""):
                if attr == "href":
                    return mock_href
                return original_get(attr, default)

            link.get = mock_get

            # Now call the original method which should hit the except block
            result = original_parse_row(row)
            return result

        with patch.object(
            WorkBenchCatalogParser, "_parse_table_row", side_effect=mock_parse_row_with_broken_href
        ):
            benchmarks = WorkBenchCatalogParser.parse_catalog_page(html, base_url=BASE)

        # Row should be skipped due to exception
        assert benchmarks == []


class TestAuthenticationDetection:
    """Test detection of unauthenticated responses (login page)."""

    def test_is_login_page_with_login_html(self, login_page_html):
        """Test that compact synthetic login page HTML is correctly identified."""
        lowered = login_page_html.lower()
        assert "<script" not in lowered
        assert "googletagmanager" not in lowered
        assert "csrf-token" not in lowered
        assert 'name="_token"' not in lowered

        is_login = WorkBenchCatalogParser.is_login_page(login_page_html)
        assert is_login is True

    def test_is_login_page_with_catalog_html(self, sample_catalog_html):
        """Test that catalog page HTML is not identified as login page."""
        is_login = WorkBenchCatalogParser.is_login_page(sample_catalog_html)
        assert is_login is False

    def test_is_login_page_with_empty_html(self):
        """Test empty HTML is not identified as login page."""
        is_login = WorkBenchCatalogParser.is_login_page("")
        assert is_login is False

    def test_parse_catalog_page_raises_on_login_page(self, login_page_html):
        """Test parsing login page raises AuthenticationError."""
        with pytest.raises(AuthenticationError, match="Not authenticated.*login"):
            WorkBenchCatalogParser.parse_catalog_page(login_page_html, base_url=BASE)

    def test_is_login_page_with_login_form(self):
        """Test detection of login form indicator."""
        html = """
        <html>
        <body>
            <form action="/login" method="POST">
                <input name="login" type="text" />
                <input name="password" type="password" />
            </form>
        </body>
        </html>
        """
        assert WorkBenchCatalogParser.is_login_page(html) is True

    def test_is_login_page_with_signin_wrapper(self):
        """Test detection of login wrapper class."""
        html = """
        <html>
        <body>
            <div class="index-signin-wrapper">
                <p>Please sign in</p>
            </div>
        </body>
        </html>
        """
        assert WorkBenchCatalogParser.is_login_page(html) is True

    def test_is_login_page_with_email_label(self):
        """Test detection of email/username label text."""
        html = """
        <html>
        <body>
            <label>E-Mail or Username</label>
            <input type="text" />
        </body>
        </html>
        """
        assert WorkBenchCatalogParser.is_login_page(html) is True


class TestPlatformInference:
    """Test platform type and name inference from benchmark titles."""

    @pytest.mark.parametrize(
        "title,expected_type,expected_platform",
        [
            # Operating Systems
            ("CIS Ubuntu Linux 20.04 LTS Benchmark", "os", "ubuntu"),
            ("CIS Red Hat Enterprise Linux 8 Benchmark", "os", "red-hat"),
            ("CIS AlmaLinux OS 8 Benchmark", "os", "almalinux"),
            ("CIS Rocky Linux 8 Benchmark", "os", "rocky-linux"),
            ("CIS Oracle Linux 8 Benchmark", "os", "oracle-linux"),
            ("CIS Debian Linux 11 Benchmark", "os", "debian"),
            ("CIS SUSE Linux Enterprise 15 Benchmark", "os", "suse"),
            ("CIS Microsoft Windows Server 2022 Benchmark", "os", "windows-server"),
            ("CIS Apple macOS 14.0 Sonoma Benchmark", "os", "macos"),
            # Cloud Platforms
            ("CIS Amazon Web Services Foundations Benchmark", "cloud", "aws"),
            ("CIS Microsoft Azure Foundations Benchmark", "cloud", "azure"),
            ("CIS Google Cloud Platform Foundation Benchmark", "cloud", "google-cloud"),
            ("CIS Oracle Cloud Infrastructure Foundations Benchmark", "cloud", "oracle-cloud"),
            ("CIS Alibaba Cloud Foundation Benchmark", "cloud", "alibaba-cloud"),
            ("CIS IBM Cloud Foundations Benchmark", "cloud", "ibm-cloud"),
            # Databases
            ("CIS Oracle Database 19c Benchmark", "database", "oracle-database"),
            ("CIS MySQL 8.0 Enterprise Benchmark", "database", "mysql"),
            ("CIS PostgreSQL 14 Benchmark", "database", "postgresql"),
            ("CIS MongoDB 6.0 Benchmark", "database", "mongodb"),
            ("CIS Microsoft SQL Server 2022 Benchmark", "database", "mssql"),
            # Containers & Kubernetes
            ("CIS Amazon Elastic Kubernetes Service (EKS) Benchmark", "container", "aws-eks"),
            ("CIS Azure Kubernetes Service (AKS) Benchmark", "container", "azure-aks"),
            ("CIS AKS Optimized Azure Linux Benchmark", "container", "azure-aks"),
            ("CIS Google Kubernetes Engine (GKE) Benchmark", "container", "google-gke"),
            ("CIS Kubernetes V1.27 Benchmark", "container", "kubernetes"),
            ("CIS Docker Benchmark", "container", "docker"),
            # Applications
            ("CIS NGINX Benchmark", "application", "nginx"),
            ("CIS Apache Tomcat 10 Benchmark", "application", "tomcat"),
            # No match
            ("CIS Some Unknown Platform Benchmark", None, None),
            ("Completely unrelated title", None, None),
        ],
    )
    def test_platform_inference(self, title, expected_type, expected_platform):
        """Test platform inference from various benchmark titles."""
        platform_type, platform = WorkBenchCatalogParser._infer_platform(title)
        assert platform_type == expected_type
        assert platform == expected_platform

    def test_platform_inference_case_insensitive(self):
        """Test platform inference is case-insensitive."""
        platform_type, platform = WorkBenchCatalogParser._infer_platform(
            "cis UBUNTU linux benchmark"
        )
        assert platform_type == "os"
        assert platform == "ubuntu"

    def test_oracle_cloud_vs_oracle_linux_disambiguation(self):
        """Test that Oracle Cloud is distinguished from Oracle Linux."""
        # Oracle Cloud should match cloud pattern
        platform_type, platform = WorkBenchCatalogParser._infer_platform(
            "CIS Oracle Cloud Infrastructure Benchmark"
        )
        assert platform_type == "cloud"
        assert platform == "oracle-cloud"

        # Oracle Linux should match OS pattern
        platform_type, platform = WorkBenchCatalogParser._infer_platform(
            "CIS Oracle Linux 8 Benchmark"
        )
        assert platform_type == "os"
        assert platform == "oracle-linux"

    def test_oracle_database_vs_oracle_linux_disambiguation(self):
        """Test that Oracle Database is distinguished from Oracle Linux."""
        platform_type, platform = WorkBenchCatalogParser._infer_platform(
            "CIS Oracle Database 19c Benchmark"
        )
        assert platform_type == "database"
        assert platform == "oracle-database"

    def test_oke_container_engine(self):
        """Test Oracle Container Engine for Kubernetes (OKE) detection."""
        platform_type, platform = WorkBenchCatalogParser._infer_platform(
            "CIS Oracle Container Engine for Kubernetes (OKE) Benchmark"
        )
        assert platform_type == "container"
        assert platform == "oracle-oke"


class TestCatalogRowHrefs:
    """Catalog row links resolve against the WorkBench origin the caller passes."""

    def test_relative_href_resolves_against_the_given_origin(self):
        """Relative catalog row hrefs resolve against the origin the caller passes."""
        html = """
        <table>
            <tr><th>Title</th><th>Version</th><th>Status</th><th>Community</th><th>Collections</th><th>Owner</th></tr>
            <tr>
                <td><a href="/benchmarks/61">CIS Ubuntu Benchmark</a></td>
                <td>v1.0.0</td>
                <td>Published</td>
                <td>Ubuntu</td>
                <td>OS</td>
                <td>cis</td>
            </tr>
        </table>
        """
        rows = WorkBenchCatalogParser.parse_catalog_page(
            html, base_url="https://workbench-staging.cisecurity.org"
        )

        assert len(rows) == 1
        assert rows[0]["url"] == "https://workbench-staging.cisecurity.org/benchmarks/61"


class TestParsingLogsPerPageDetailAtDebug:
    """Per-page detail is DEBUG; the default INFO output stays free of it."""

    def test_parsing_a_page_logs_at_debug_not_info(self, sample_catalog_html, caplog):
        with caplog.at_level("INFO", logger="cis_bench.catalog.parser"):
            WorkBenchCatalogParser.parse_catalog_page(sample_catalog_html, base_url=BASE)
        assert [r.getMessage() for r in caplog.records if r.levelname == "INFO"] == []

        caplog.clear()
        with caplog.at_level("DEBUG", logger="cis_bench.catalog.parser"):
            benchmarks = WorkBenchCatalogParser.parse_catalog_page(
                sample_catalog_html, base_url=BASE
            )
        assert f"Parsed {len(benchmarks)} benchmarks from catalog page" in [
            r.getMessage() for r in caplog.records if r.levelname == "DEBUG"
        ]
