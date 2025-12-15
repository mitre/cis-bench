"""Integration tests for CIS Native XCCDF export."""

import tempfile
from pathlib import Path

import pytest
from lxml import etree

from cis_bench.exporters import ExporterFactory
from cis_bench.models.benchmark import Benchmark


@pytest.fixture
def sample_benchmark():
    """Load test benchmark."""
    fixture_path = (
        Path(__file__).parent.parent / "fixtures" / "benchmarks" / "almalinux_complete.json"
    )
    return Benchmark.from_json_file(str(fixture_path))


class TestCISXCCDFExport:
    """Test CIS Native XCCDF export functionality."""

    def test_cis_exporter_creation(self):
        """Test that CIS exporter can be created."""
        exporter = ExporterFactory.create("xccdf", style="cis")
        assert exporter is not None
        assert exporter.format_name() == "XCCDF (CIS)"

    def test_cis_xccdf_export_basic(self, sample_benchmark):
        """Test basic CIS XCCDF export."""
        exporter = ExporterFactory.create("xccdf", style="cis")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            output_path = f.name

        try:
            exporter.export(sample_benchmark, output_path)

            # Verify file was created
            assert Path(output_path).exists()

            # Verify it's valid XML
            tree = etree.parse(output_path)
            root = tree.getroot()

            assert root.tag.endswith("Benchmark")

        finally:
            Path(output_path).unlink()

    def test_cis_xccdf_namespaces(self, sample_benchmark):
        """Test that all required namespaces are declared."""
        exporter = ExporterFactory.create("xccdf", style="cis")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            output_path = f.name

        try:
            exporter.export(sample_benchmark, output_path)

            tree = etree.parse(output_path)
            root = tree.getroot()

            # Check all required namespaces are present
            nsmap = root.nsmap

            assert "http://checklists.nist.gov/xccdf/1.2" in nsmap.values()
            assert "http://www.w3.org/1999/xhtml" in nsmap.values()
            assert "http://cisecurity.org/controls" in nsmap.values()
            assert "http://cisecurity.org/20-cc/v7.0" in nsmap.values()
            assert "http://cisecurity.org/20-cc/v8.0" in nsmap.values()
            assert "http://purl.org/dc/elements/1.1/" in nsmap.values()
            assert "http://cisecurity.org/xccdf/enhanced/1.0" in nsmap.values()

        finally:
            Path(output_path).unlink()

    def test_cis_controls_metadata_structure(self, sample_benchmark):
        """Test that CIS Controls have the correct nested structure."""
        exporter = ExporterFactory.create("xccdf", style="cis")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            output_path = f.name

        try:
            exporter.export(sample_benchmark, output_path)

            tree = etree.parse(output_path)

            # Find CIS Controls elements
            ns = {
                "xccdf": "http://checklists.nist.gov/xccdf/1.2",
                "controls": "http://cisecurity.org/controls",
            }

            cis_controls = tree.xpath("//controls:cis_controls", namespaces=ns)
            assert len(cis_controls) > 0, "Should have CIS Controls metadata"

            # Check nested structure: cis_controls > framework > safeguard
            frameworks = tree.xpath("//controls:framework", namespaces=ns)
            assert len(frameworks) > 0, "Should have framework elements"

            safeguards = tree.xpath("//controls:safeguard", namespaces=ns)
            assert len(safeguards) > 0, "Should have safeguard elements"

            # Check first safeguard has required attributes and elements
            first_safeguard = safeguards[0]
            assert first_safeguard.get("title") is not None
            assert first_safeguard.get("urn") is not None

            # Check safeguard has required child elements
            ig = first_safeguard.find(".//{http://cisecurity.org/controls}implementation_groups")
            assert ig is not None
            assert ig.get("ig3") is not None

            asset_type = first_safeguard.find(".//{http://cisecurity.org/controls}asset_type")
            assert asset_type is not None

            sec_func = first_safeguard.find(".//{http://cisecurity.org/controls}security_function")
            assert sec_func is not None

        finally:
            Path(output_path).unlink()

    def test_cis_controls_ident_elements(self, sample_benchmark):
        """Test that ident elements have cc7/cc8 controlURI attributes."""
        exporter = ExporterFactory.create("xccdf", style="cis")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            output_path = f.name

        try:
            exporter.export(sample_benchmark, output_path)

            # Read raw XML to check attributes
            with open(output_path) as f:
                xml_content = f.read()

            # Check for cc7 and cc8 controlURI attributes
            assert "cc7:controlURI" in xml_content, "Should have cc7 controlURI attributes"
            assert "cc8:controlURI" in xml_content, "Should have cc8 controlURI attributes"

            # Parse and validate structure
            tree = etree.parse(output_path)
            ns = {
                "xccdf": "http://checklists.nist.gov/xccdf/1.2",
                "cc7": "http://cisecurity.org/20-cc/v7.0",
                "cc8": "http://cisecurity.org/20-cc/v8.0",
            }

            # Count idents with controlURI (check raw XML since XPath with namespaced attributes is tricky)
            assert xml_content.count("cc7:controlURI") > 0, "Should have cc7 controlURI attributes"
            assert xml_content.count("cc8:controlURI") > 0, "Should have cc8 controlURI attributes"

            # Verify at least one ident has the correct structure
            # Parse with namespace-aware approach
            root = tree.getroot()
            all_idents = root.findall(".//ident") + root.findall(
                ".//{http://checklists.nist.gov/xccdf/1.2}ident"
            )

            # Find first ident with cc8 controlURI
            found_cc8 = False
            for ident in all_idents:
                cc8_uri = ident.get("{http://cisecurity.org/20-cc/v8.0}controlURI")
                if cc8_uri:
                    found_cc8 = True
                    assert cc8_uri.startswith("http://cisecurity.org/20-cc/v8.0/control/")
                    break

            assert found_cc8, "Should find at least one ident with cc8:controlURI attribute"

        finally:
            Path(output_path).unlink()

    def test_enhanced_metadata_mitre(self, sample_benchmark):
        """Test that enhanced metadata includes MITRE ATT&CK."""
        exporter = ExporterFactory.create("xccdf", style="cis")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            output_path = f.name

        try:
            exporter.export(sample_benchmark, output_path)

            tree = etree.parse(output_path)
            ns = {"enhanced": "http://cisecurity.org/xccdf/enhanced/1.0"}

            # Check for MITRE elements
            mitre_blocks = tree.xpath("//enhanced:mitre", namespaces=ns)
            assert len(mitre_blocks) > 0, "Should have MITRE metadata blocks"

            techniques = tree.xpath("//enhanced:technique", namespaces=ns)
            assert len(techniques) > 0, "Should have MITRE techniques"

            # Verify technique has id attribute and text
            first_tech = techniques[0]
            assert first_tech.get("id") is not None
            assert first_tech.get("id").startswith("T")  # MITRE technique IDs start with T
            assert first_tech.text is not None

        finally:
            Path(output_path).unlink()

    def test_enhanced_metadata_profiles(self, sample_benchmark):
        """Test that enhanced metadata includes CIS Profiles."""
        exporter = ExporterFactory.create("xccdf", style="cis")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            output_path = f.name

        try:
            exporter.export(sample_benchmark, output_path)

            tree = etree.parse(output_path)
            ns = {"enhanced": "http://cisecurity.org/xccdf/enhanced/1.0"}

            # Check for profile elements
            profiles = tree.xpath("//enhanced:profile", namespaces=ns)
            assert len(profiles) > 0, "Should have profile entries"

            # Verify profile content
            profile_texts = [p.text for p in profiles if p.text]
            assert any("Level 1" in text for text in profile_texts), "Should have Level 1 profiles"

        finally:
            Path(output_path).unlink()

    def test_nist_references_dublin_core(self, sample_benchmark):
        """Test that NIST references use Dublin Core."""
        exporter = ExporterFactory.create("xccdf", style="cis")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            output_path = f.name

        try:
            exporter.export(sample_benchmark, output_path)

            tree = etree.parse(output_path)
            ns = {
                "xccdf": "http://checklists.nist.gov/xccdf/1.2",
                "dc": "http://purl.org/dc/elements/1.1/",
            }

            # Find references with Dublin Core (namespace-agnostic)
            dc_titles = tree.xpath(
                '//*[local-name()="title" and namespace-uri()="http://purl.org/dc/elements/1.1/"]'
            )
            assert len(dc_titles) > 0, "Should have Dublin Core titles"

            dc_identifiers = tree.xpath(
                '//*[local-name()="identifier" and namespace-uri()="http://purl.org/dc/elements/1.1/"]'
            )
            assert len(dc_identifiers) > 0, "Should have Dublin Core identifiers"

            # Verify content
            assert any("NIST" in title.text for title in dc_titles if title.text)

        finally:
            Path(output_path).unlink()

    def test_output_file_size_reasonable(self, sample_benchmark):
        """Test that output file size is reasonable (includes metadata)."""
        exporter = ExporterFactory.create("xccdf", style="cis")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            output_path = f.name

        try:
            exporter.export(sample_benchmark, output_path)

            file_size = Path(output_path).stat().st_size

            # With 322 recommendations and full metadata, should be > 1 MB
            assert (
                file_size > 1_000_000
            ), f"File size {file_size} seems too small for 322 recs with metadata"

            # But not unreasonably large (< 5 MB)
            assert file_size < 5_000_000, f"File size {file_size} seems too large"

        finally:
            Path(output_path).unlink()

    def test_xml_well_formed(self, sample_benchmark):
        """Test that generated XML is well-formed."""
        exporter = ExporterFactory.create("xccdf", style="cis")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            output_path = f.name

        try:
            exporter.export(sample_benchmark, output_path)

            # Parse should succeed without errors
            tree = etree.parse(output_path)
            root = tree.getroot()

            assert root is not None

            # Verify basic structure
            assert root.tag.endswith("Benchmark")

            # Should have Groups
            groups = tree.findall(".//Group") + tree.findall(
                ".//{http://checklists.nist.gov/xccdf/1.2}Group"
            )
            assert len(groups) > 0

            # Should have Rules
            rules = tree.findall(".//Rule") + tree.findall(
                ".//{http://checklists.nist.gov/xccdf/1.2}Rule"
            )
            assert len(rules) == 322

        finally:
            Path(output_path).unlink()
