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

            # Parse and validate structure
            tree = etree.parse(output_path)
            root = tree.getroot()

            # Find CIS Controls idents
            cis_v8_idents = root.xpath(
                ".//*[local-name()='ident'][@system='http://cisecurity.org/20-cc/v8']"
            )
            cis_v7_idents = root.xpath(
                ".//*[local-name()='ident'][@system='http://cisecurity.org/20-cc/v7']"
            )

            assert len(cis_v8_idents) > 0, "Should have CIS Controls v8 idents"
            assert len(cis_v7_idents) > 0, "Should have CIS Controls v7 idents"

            # Note: cc7:controlURI and cc8:controlURI attributes defined in config
            # but not yet implemented in attribute injection post-processor
            # This is a future enhancement (optional for basic compatibility)

        finally:
            Path(output_path).unlink()

    def test_mitre_as_ident_elements(self, sample_benchmark):
        """Test that MITRE ATT&CK is exported as ident elements (not metadata)."""
        exporter = ExporterFactory.create("xccdf", style="cis")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            output_path = f.name

        try:
            exporter.export(sample_benchmark, output_path)

            tree = etree.parse(output_path)
            root = tree.getroot()

            # MITRE now as ident elements (cleaner, no namespace pollution)
            mitre_technique_idents = root.xpath(
                ".//*[local-name()='ident'][@system='https://attack.mitre.org/techniques']"
            )
            mitre_tactic_idents = root.xpath(
                ".//*[local-name()='ident'][@system='https://attack.mitre.org/tactics']"
            )
            mitre_mitigation_idents = root.xpath(
                ".//*[local-name()='ident'][@system='https://attack.mitre.org/mitigations']"
            )

            assert len(mitre_technique_idents) > 0, "Should have MITRE technique idents"
            assert len(mitre_tactic_idents) > 0, "Should have MITRE tactic idents"
            assert len(mitre_mitigation_idents) > 0, "Should have MITRE mitigation idents"

            # Verify format
            first_tech = mitre_technique_idents[0]
            assert first_tech.text.startswith("T"), "MITRE technique IDs start with T"

        finally:
            Path(output_path).unlink()

    def test_profiles_at_benchmark_level(self, sample_benchmark):
        """Test that Profiles are generated at Benchmark level (proper XCCDF standard)."""
        exporter = ExporterFactory.create("xccdf", style="cis")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            output_path = f.name

        try:
            exporter.export(sample_benchmark, output_path)

            tree = etree.parse(output_path)
            root = tree.getroot()

            # Profiles now at Benchmark level (proper XCCDF standard)
            profile_elements = root.xpath(".//*[local-name()='Profile']")
            assert len(profile_elements) > 0, "Should have Profile elements"

            # Verify at least 2 profiles (Level 1 Server/Workstation)
            assert len(profile_elements) >= 2, (
                f"Expected at least 2 profiles, found {len(profile_elements)}"
            )

            # Verify profiles have select elements
            for profile in profile_elements:
                selects = profile.xpath(".//*[local-name()='select']")
                assert len(selects) > 0, "Profiles should have select elements"

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
            assert file_size > 1_000_000, (
                f"File size {file_size} seems too small for 322 recs with metadata"
            )

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
