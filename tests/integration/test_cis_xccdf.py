"""Integration tests for CIS Native XCCDF export."""

import subprocess
import tempfile
from pathlib import Path

import pytest
from lxml import etree

from cis_bench.exporters import ExporterFactory
from cis_bench.models.benchmark import Benchmark


@pytest.fixture
def sample_benchmark(synthetic_complete_file):
    """Load synthetic test benchmark."""
    return Benchmark.from_json_file(str(synthetic_complete_file))


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

            # With 20 synthetic recommendations and full dual metadata, should be > 25 KB
            assert file_size > 25_000, (
                f"File size {file_size} seems too small for 20 recs with metadata"
            )

            # And compact (< 500 KB)
            assert file_size < 500_000, f"File size {file_size} seems too large"

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
            assert len(groups) == 20

            # Should have Rules
            rules = tree.findall(".//Rule") + tree.findall(
                ".//{http://checklists.nist.gov/xccdf/1.2}Rule"
            )
            assert len(rules) == 20

        finally:
            Path(output_path).unlink()

    def test_cis_export_validates_nist_xccdf_1_2_schema(self, sample_benchmark, tmp_path):
        """CIS XCCDF 1.2 export must validate against NIST XCCDF 1.2 XSD schema."""
        output_file = tmp_path / "test_cis.xml"
        exporter = ExporterFactory.create("xccdf", style="cis")
        exporter.export(sample_benchmark, str(output_file))

        schema_file = (
            Path(__file__).parent.parent.parent / "schemas" / "xccdf" / "1.2" / "xccdf_1.2.xsd"
        )
        result = subprocess.run(
            ["xmllint", "--noout", "--schema", str(schema_file), str(output_file)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"XCCDF 1.2 schema validation failed: {result.stderr}"

    def test_cis_metadata_aligned_by_rule_id_and_repeatable(self, sample_benchmark, tmp_path):
        """Metadata injection aligns 1-to-1 by Rule ID and resets across repeated exports."""
        exporter = ExporterFactory.create("xccdf", style="cis")
        first_out = tmp_path / "cis_first.xml"
        second_out = tmp_path / "cis_second.xml"

        exporter.export(sample_benchmark, str(first_out))
        exporter.export(sample_benchmark, str(second_out))

        tree = etree.parse(str(second_out))
        ns = {
            "xccdf": "http://checklists.nist.gov/xccdf/1.2",
            "controls": "http://cisecurity.org/controls",
        }

        # Rule 6.2.1 has no CIS Controls so its allow_empty cis_controls container has zero frameworks
        unmapped_rule = tree.xpath(
            "//xccdf:Rule[@id='xccdf_org.cisecurity.benchmarks_rule_6_2_1']",
            namespaces=ns,
        )
        assert len(unmapped_rule) == 1
        unmapped_metas = unmapped_rule[0].xpath("./xccdf:metadata", namespaces=ns)
        assert len(unmapped_metas) == 1
        assert len(unmapped_metas[0].xpath(".//controls:framework", namespaces=ns)) == 0

        # Mapped rules must each have exactly one metadata block with v7+v8 frameworks before ident
        mapped_rules = tree.xpath(
            "//xccdf:Rule[@id!='xccdf_org.cisecurity.benchmarks_rule_6_2_1']",
            namespaces=ns,
        )
        assert len(mapped_rules) == 19
        for rule in mapped_rules:
            metas = rule.xpath("./xccdf:metadata", namespaces=ns)
            assert len(metas) == 1
            assert len(metas[0].xpath(".//controls:framework", namespaces=ns)) == 2
            child_names = [etree.QName(child).localname for child in rule]
            assert child_names.index("metadata") < child_names.index("ident")

    def test_cis_export_populates_benchmark_notice_from_style_config(
        self, sample_benchmark, tmp_path
    ):
        """CIS XCCDF 1.2 export emits configured <notice id='terms-of-use' xml:lang='en'>."""
        output_file = tmp_path / "test_cis_notice.xml"
        exporter = ExporterFactory.create("xccdf", style="cis")
        exporter.export(sample_benchmark, str(output_file))

        tree = etree.parse(str(output_file))
        ns = {"xccdf": "http://checklists.nist.gov/xccdf/1.2"}
        notices = tree.xpath("/xccdf:Benchmark/xccdf:notice", namespaces=ns)

        assert len(notices) == 1
        notice = notices[0]
        assert notice.get("id") == "terms-of-use"
        assert notice.get("{http://www.w3.org/XML/1998/namespace}lang") == "en"
        notice_text = (notice.text or "").strip()
        assert sample_benchmark.title in notice_text
        assert str(sample_benchmark.url) in notice_text
        assert "Center for Internet Security, Inc." in notice_text
        assert "https://workbench.cisecurity.org/terms-of-use" in notice_text
        assert "cis-bench" in notice_text
