"""Tests for web component data extraction utility."""

from bs4 import BeautifulSoup

from cis_bench.utils.web_component_parser import WebComponentDataExtractor


class TestWebComponentJSONExtraction:
    """Test extracting JSON from web component attributes."""

    def test_extract_json_attribute_basic(self):
        """Test extracting JSON from web component attribute."""
        html = """
        <html>
            <wb-benchmark-assets assets-json='[{"title":"Test","cpe_id":"cpe:2.3:o:test:test:1"}]'>
            </wb-benchmark-assets>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")

        result = WebComponentDataExtractor.extract_json_attribute(
            soup, "wb-benchmark-assets", "assets-json"
        )

        assert result is not None
        assert len(result) == 1
        assert result[0]["title"] == "Test"
        assert result[0]["cpe_id"] == "cpe:2.3:o:test:test:1"

    def test_extract_json_attribute_html_encoded(self):
        """Test extracting HTML-encoded JSON."""
        html = """
        <wb-data data-json='[{&quot;key&quot;:&quot;value&quot;}]'></wb-data>
        """
        soup = BeautifulSoup(html, "html.parser")

        result = WebComponentDataExtractor.extract_json_attribute(soup, "wb-data", "data-json")

        assert result is not None
        assert result[0]["key"] == "value"

    def test_extract_json_attribute_not_found(self):
        """Test when component doesn't exist."""
        html = "<html><body>No component here</body></html>"
        soup = BeautifulSoup(html, "html.parser")

        result = WebComponentDataExtractor.extract_json_attribute(soup, "wb-missing", "data")

        assert result is None

    def test_extract_json_attribute_missing_attribute(self):
        """Test when component exists but attribute is missing."""
        html = "<wb-component></wb-component>"
        soup = BeautifulSoup(html, "html.parser")

        result = WebComponentDataExtractor.extract_json_attribute(
            soup, "wb-component", "missing-attr"
        )

        assert result is None

    def test_extract_json_attribute_invalid_json(self):
        """Test handling of invalid JSON."""
        html = '<wb-data data-json="not valid json"></wb-data>'
        soup = BeautifulSoup(html, "html.parser")

        result = WebComponentDataExtractor.extract_json_attribute(soup, "wb-data", "data-json")

        assert result is None


class TestWebComponentHTMLExtraction:
    """Test extracting HTML-encoded content from web components."""

    def test_extract_html_attribute(self):
        """Test extracting HTML-encoded attribute."""
        html = '<wb-section text="&lt;p&gt;Test content&lt;/p&gt;"></wb-section>'
        soup = BeautifulSoup(html, "html.parser")

        result = WebComponentDataExtractor.extract_html_attribute(soup, "wb-section", "text")

        assert result == "<p>Test content</p>"

    def test_extract_text_from_html_attribute(self):
        """Test extracting plain text from HTML-encoded attribute."""
        html = '<wb-section text="&lt;p&gt;Overview text here&lt;/p&gt;"></wb-section>'
        soup = BeautifulSoup(html, "html.parser")

        result = WebComponentDataExtractor.extract_text_from_html_attribute(
            soup, "wb-section", "text"
        )

        assert result == "Overview text here"

    def test_extract_html_attribute_not_found(self):
        """Test when HTML attribute not found."""
        html = "<html></html>"
        soup = BeautifulSoup(html, "html.parser")

        result = WebComponentDataExtractor.extract_html_attribute(soup, "wb-missing", "text")

        assert result is None


class TestRealWorldWebComponents:
    """Test with real CIS WorkBench web component patterns."""

    def test_real_assets_component(self):
        """Test extraction from actual wb-benchmark-assets structure."""
        # Real HTML from CIS WorkBench
        html = """
        <wb-benchmark-assets
            assets-json='[{"title":"AlmaLinux OS 9","cpe_id":"cpe:2.3:o:almalinux:almalinux:9:*:*:*:*:*:*:*"}]'
        ></wb-benchmark-assets>
        """
        soup = BeautifulSoup(html, "html.parser")

        result = WebComponentDataExtractor.extract_json_attribute(
            soup, "wb-benchmark-assets", "assets-json"
        )

        assert result is not None
        assert len(result) == 1
        assert result[0]["title"] == "AlmaLinux OS 9"
        assert "cpe:2.3:o:almalinux" in result[0]["cpe_id"]

    def test_real_profiles_component(self):
        """Test extraction from actual wb-benchmark-profiles structure."""
        # Simplified real HTML
        html = """
        <wb-benchmark-profiles
            profiles-json='[{"title":"Level 1 - Server","description":"<p>Items in this profile...</p>"}]'
        ></wb-benchmark-profiles>
        """
        soup = BeautifulSoup(html, "html.parser")

        result = WebComponentDataExtractor.extract_json_attribute(
            soup, "wb-benchmark-profiles", "profiles-json"
        )

        assert result is not None
        assert len(result) >= 1
        assert result[0]["title"] == "Level 1 - Server"
