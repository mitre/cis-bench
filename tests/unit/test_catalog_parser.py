"""Unit tests for catalog HTML parser."""

from pathlib import Path

import pytest

from cis_bench.catalog.parser import WorkBenchCatalogParser


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
        benchmarks = WorkBenchCatalogParser.parse_catalog_page(sample_catalog_html)

        assert isinstance(benchmarks, list)
        assert len(benchmarks) > 0

    def test_benchmark_has_required_fields(self, sample_catalog_html):
        """Test parsed benchmarks have all required fields."""
        benchmarks = WorkBenchCatalogParser.parse_catalog_page(sample_catalog_html)

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
        benchmarks = WorkBenchCatalogParser.parse_catalog_page(sample_catalog_html)

        # Check IDs are numeric strings
        for bench in benchmarks:
            assert bench["benchmark_id"].isdigit()
            assert len(bench["benchmark_id"]) > 0

    def test_title_cleaning(self, sample_catalog_html):
        """Test title is cleaned (removes org prefix, [imported] suffix)."""
        benchmarks = WorkBenchCatalogParser.parse_catalog_page(sample_catalog_html)

        for bench in benchmarks:
            # Should not have pipe prefix
            assert not bench["title"].startswith("|")
            # Should not have [imported] suffix
            assert "[imported]" not in bench["title"]

    def test_status_values(self, sample_catalog_html):
        """Test status values are valid."""
        benchmarks = WorkBenchCatalogParser.parse_catalog_page(sample_catalog_html)

        valid_statuses = {"Published", "Draft", "Archived", "Rejected", "Accepted"}

        for bench in benchmarks:
            assert bench["status"] in valid_statuses

    def test_collections_is_list(self, sample_catalog_html):
        """Test collections field is always a list."""
        benchmarks = WorkBenchCatalogParser.parse_catalog_page(sample_catalog_html)

        for bench in benchmarks:
            assert isinstance(bench["collections"], list)

    def test_url_format(self, sample_catalog_html):
        """Test URLs are properly formatted."""
        benchmarks = WorkBenchCatalogParser.parse_catalog_page(sample_catalog_html)

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


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_html(self):
        """Test parsing empty HTML returns empty list."""
        benchmarks = WorkBenchCatalogParser.parse_catalog_page("")
        assert benchmarks == []

    def test_html_without_table(self):
        """Test HTML without table returns empty list."""
        html = "<html><body><p>No table here</p></body></html>"
        benchmarks = WorkBenchCatalogParser.parse_catalog_page(html)
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

        benchmarks = WorkBenchCatalogParser.parse_catalog_page(html)

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

        benchmarks = WorkBenchCatalogParser.parse_catalog_page(html)

        assert len(benchmarks) == 1
        assert benchmarks[0]["community"] is None
        assert benchmarks[0]["owner"] is None
        assert benchmarks[0]["collections"] == []


class TestAuthenticationDetection:
    """Test detection of unauthenticated responses (login page)."""

    def test_is_login_page_with_login_html(self, login_page_html):
        """Test that login page HTML is correctly identified."""
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
        from cis_bench.exceptions import AuthenticationError

        with pytest.raises(AuthenticationError, match="Not authenticated.*login"):
            WorkBenchCatalogParser.parse_catalog_page(login_page_html)
