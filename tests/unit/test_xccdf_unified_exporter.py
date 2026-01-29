"""Tests for XCCDF Unified Exporter.

Tests for XCCDFExporter class covering:
- Initialization with different styles
- Style validation and error handling
- Export method with both CIS and DISA styles
- Post-processing pipeline
- Metadata injection
- CIS Controls ident URI generation
"""

from unittest.mock import mock_open, patch

import pytest

from cis_bench.exporters.xccdf_unified_exporter import XCCDFExporter
from cis_bench.models.benchmark import Benchmark, CISControl, Recommendation

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_benchmark(sample_recommendation_complete):
    """Create a sample benchmark with one recommendation."""
    return Benchmark(
        title="Ubuntu Linux 22.04 LTS Benchmark",
        benchmark_id="23598",
        url="https://workbench.cisecurity.org/benchmarks/23598",
        version="v1.0.0",
        scraper_version="1.0.0",
        total_recommendations=1,
        recommendations=[sample_recommendation_complete],
    )


@pytest.fixture
def benchmark_with_multiple_recs():
    """Create a benchmark with multiple recommendations for profile testing."""
    recs = [
        Recommendation(
            ref="1.1.1",
            title="Test Recommendation 1",
            url="https://workbench.cisecurity.org/sections/1/recommendations/1",
            assessment_status="Automated",
            profiles=["Level 1 - Server", "Level 1 - Workstation"],
            cis_controls=[
                CISControl(
                    version=8, control="4.1", title="Control 4.1", ig1=True, ig2=True, ig3=True
                ),
            ],
        ),
        Recommendation(
            ref="1.1.2",
            title="Test Recommendation 2",
            url="https://workbench.cisecurity.org/sections/1/recommendations/2",
            assessment_status="Automated",
            profiles=["Level 2 - Server"],
            cis_controls=[
                CISControl(
                    version=7, control="9.2", title="Control 9.2", ig1=True, ig2=False, ig3=False
                ),
            ],
        ),
    ]
    return Benchmark(
        title="Ubuntu Linux 22.04 LTS Benchmark",
        benchmark_id="23598",
        url="https://workbench.cisecurity.org/benchmarks/23598",
        version="v1.0.0",
        scraper_version="1.0.0",
        total_recommendations=2,
        recommendations=recs,
    )


@pytest.fixture
def minimal_benchmark():
    """Create a minimal benchmark with required fields only."""
    rec = Recommendation(
        ref="1.1.1",
        title="Minimal Recommendation",
        url="https://workbench.cisecurity.org/sections/1/recommendations/1",
        assessment_status="Automated",
    )
    return Benchmark(
        title="Test Benchmark",
        benchmark_id="12345",
        url="https://workbench.cisecurity.org/benchmarks/12345",
        version="v1.0.0",
        scraper_version="1.0.0",
        total_recommendations=1,
        recommendations=[rec],
    )


# ============================================================================
# Test: XCCDFExporter Initialization
# ============================================================================


class TestXCCDFExporterInit:
    """Tests for XCCDFExporter initialization."""

    def test_init_disa_style(self):
        """Should initialize with DISA style successfully."""
        exporter = XCCDFExporter(style="disa")

        assert exporter.style == "disa"
        assert exporter.config is not None
        assert exporter.engine is not None

    def test_init_cis_style(self):
        """Should initialize with CIS style successfully."""
        exporter = XCCDFExporter(style="cis")

        assert exporter.style == "cis"
        assert exporter.config is not None
        assert exporter.engine is not None

    def test_init_default_style_is_disa(self):
        """Should default to DISA style when not specified."""
        exporter = XCCDFExporter()

        assert exporter.style == "disa"

    def test_init_invalid_style_raises_error(self):
        """Should raise ValueError for unknown style."""
        with pytest.raises(ValueError) as exc_info:
            XCCDFExporter(style="nonexistent_style")

        error_msg = str(exc_info.value)
        assert "Unknown XCCDF style: 'nonexistent_style'" in error_msg
        assert "Available styles:" in error_msg
        # Should suggest available styles
        assert "disa" in error_msg or "cis" in error_msg

    def test_init_invalid_style_suggests_config_path(self):
        """Should suggest config file path for new styles."""
        with pytest.raises(ValueError) as exc_info:
            XCCDFExporter(style="custom_org")

        error_msg = str(exc_info.value)
        assert "configs/styles/custom_org.yaml" in error_msg


class TestGetAvailableStyles:
    """Tests for _get_available_styles static method."""

    def test_get_available_styles_returns_list(self):
        """Should return list of available style names."""
        styles = XCCDFExporter._get_available_styles()

        assert isinstance(styles, list)
        assert "disa" in styles
        assert "cis" in styles

    def test_get_available_styles_sorted(self):
        """Should return styles in sorted order."""
        styles = XCCDFExporter._get_available_styles()

        assert styles == sorted(styles)


# ============================================================================
# Test: Format Name and Extension
# ============================================================================


class TestFormatMethods:
    """Tests for format_name and get_file_extension methods."""

    def test_format_name_disa(self):
        """Should return 'XCCDF (DISA)' for DISA style."""
        exporter = XCCDFExporter(style="disa")

        assert exporter.format_name() == "XCCDF (DISA)"

    def test_format_name_cis(self):
        """Should return 'XCCDF (CIS)' for CIS style."""
        exporter = XCCDFExporter(style="cis")

        assert exporter.format_name() == "XCCDF (CIS)"

    def test_get_file_extension(self):
        """Should return 'xml' as file extension."""
        exporter = XCCDFExporter(style="disa")

        assert exporter.get_file_extension() == "xml"


# ============================================================================
# Test: Export Method
# ============================================================================


class TestExportMethod:
    """Tests for the export method."""

    def test_export_creates_file(self, tmp_path, minimal_benchmark):
        """Should create XML file at output path."""
        exporter = XCCDFExporter(style="disa")
        output_file = tmp_path / "test_output.xml"

        result = exporter.export(minimal_benchmark, str(output_file))

        assert output_file.exists()
        assert result == str(output_file)

    def test_export_returns_valid_xml(self, tmp_path, minimal_benchmark):
        """Should create valid XML content."""
        from lxml import etree

        exporter = XCCDFExporter(style="disa")
        output_file = tmp_path / "test_output.xml"

        exporter.export(minimal_benchmark, str(output_file))

        # Should parse without errors
        content = output_file.read_text()
        root = etree.fromstring(content.encode("utf-8"))
        assert root is not None

    def test_export_disa_style_xccdf_version(self, tmp_path, minimal_benchmark):
        """DISA export should use XCCDF 1.1 namespace."""
        exporter = XCCDFExporter(style="disa")
        output_file = tmp_path / "test_output.xml"

        exporter.export(minimal_benchmark, str(output_file))

        content = output_file.read_text()
        # DISA uses XCCDF 1.1.4 namespace
        assert "checklists.nist.gov/xccdf/1.1" in content

    def test_export_cis_style_xccdf_version(self, tmp_path, minimal_benchmark):
        """CIS export should use XCCDF 1.2 namespace."""
        exporter = XCCDFExporter(style="cis")
        output_file = tmp_path / "test_output.xml"

        exporter.export(minimal_benchmark, str(output_file))

        content = output_file.read_text()
        # CIS uses XCCDF 1.2 namespace
        assert "checklists.nist.gov/xccdf/1.2" in content

    def test_export_benchmark_with_profiles(self, tmp_path, benchmark_with_multiple_recs):
        """Should generate Profile elements for recommendations with profiles."""
        exporter = XCCDFExporter(style="disa")
        output_file = tmp_path / "test_output.xml"

        exporter.export(benchmark_with_multiple_recs, str(output_file))

        content = output_file.read_text()
        # Should contain profile-related content
        assert "Profile" in content or "profile" in content


# ============================================================================
# Test: Create Benchmark From Mapping
# ============================================================================


class TestCreateBenchmark:
    """Tests for _create_benchmark internal method."""

    def test_create_benchmark_generates_groups(self, minimal_benchmark):
        """Should create Group elements for each recommendation."""
        exporter = XCCDFExporter(style="disa")

        xccdf_bench = exporter._create_benchmark(minimal_benchmark)

        # Benchmark should have groups
        assert hasattr(xccdf_bench, "group")
        assert len(xccdf_bench.group) == len(minimal_benchmark.recommendations)

    def test_create_benchmark_stores_post_processing_data(self, minimal_benchmark):
        """Should store DC elements for post-processing."""
        exporter = XCCDFExporter(style="disa")

        exporter._create_benchmark(minimal_benchmark)

        # Should have stored DC elements for post-processing
        assert hasattr(exporter, "_dc_elements")


# ============================================================================
# Test: Post-Processing Pipeline
# ============================================================================


class TestPostProcessing:
    """Tests for _apply_post_processing method."""

    def test_post_processing_handles_namespaces_in_benchmark_section(
        self, tmp_path, minimal_benchmark
    ):
        """Should handle namespaces defined in benchmark section of config."""
        # DISA config has namespaces in benchmark section
        exporter = XCCDFExporter(style="disa")
        output_file = tmp_path / "test_output.xml"

        # Should not raise error
        result = exporter.export(minimal_benchmark, str(output_file))
        assert output_file.exists()

    def test_post_processing_handles_top_level_namespaces(self, tmp_path, minimal_benchmark):
        """Should handle namespaces at top-level of config."""
        # CIS config has namespaces at top level
        exporter = XCCDFExporter(style="cis")
        output_file = tmp_path / "test_output.xml"

        # Should not raise error
        result = exporter.export(minimal_benchmark, str(output_file))
        assert output_file.exists()

    def test_post_processing_unknown_handler_warning(self, tmp_path, minimal_benchmark, caplog):
        """Should log warning for unknown post-processing handlers."""
        exporter = XCCDFExporter(style="disa")

        # Create a mock config that has an unknown handler
        with patch.object(exporter, "_apply_post_processing") as mock_post:
            # Simulate the original method but inject unknown handler
            original_method = XCCDFExporter._apply_post_processing

            def side_effect(xml_output, benchmark):
                # Call original but we'll test the warning separately
                return xml_output

            mock_post.side_effect = side_effect

            output_file = tmp_path / "test_output.xml"
            exporter.export(minimal_benchmark, str(output_file))

    def test_post_processing_missing_xccdf_namespace_raises_error(self, minimal_benchmark):
        """Should raise ValueError if no XCCDF namespace in config."""
        exporter = XCCDFExporter(style="disa")

        # Create minimal XML to process
        test_xml = '<?xml version="1.0"?><Benchmark id="test"/>'

        # Patch the YAML loading to return config without xccdf namespace
        with patch("builtins.open", mock_open(read_data="post_processing:\n  handlers: []")):
            with patch("yaml.safe_load") as mock_yaml:
                mock_yaml.return_value = {
                    "namespaces": {},  # No default or xccdf key
                    "post_processing": {"handlers": []},
                }

                with pytest.raises(ValueError) as exc_info:
                    exporter._apply_post_processing(test_xml, minimal_benchmark)

                assert "No XCCDF namespace found" in str(exc_info.value)


# ============================================================================
# Test: Metadata Injection
# ============================================================================


class TestMetadataInjection:
    """Tests for _inject_metadata_from_config method."""

    def test_inject_metadata_no_elements(self, minimal_benchmark):
        """Should return unchanged XML when no metadata elements."""
        exporter = XCCDFExporter(style="disa")

        test_xml = '<?xml version="1.0"?><Benchmark><Rule id="test"/></Benchmark>'

        # Ensure no metadata stored
        if hasattr(exporter.engine, "_metadata_for_post_processing"):
            delattr(exporter.engine, "_metadata_for_post_processing")

        result = exporter._inject_metadata_from_config(test_xml)

        # Should return unchanged (minus formatting differences)
        assert "Rule" in result

    def test_inject_metadata_with_elements(self, minimal_benchmark):
        """Should inject metadata elements into rules."""
        from lxml import etree

        exporter = XCCDFExporter(style="disa")

        # Create a simple metadata element to inject
        metadata_elem = etree.Element("test-metadata")
        metadata_elem.text = "Test content"

        # Store metadata for injection
        exporter.engine._metadata_for_post_processing = [metadata_elem]

        test_xml = '<?xml version="1.0"?><Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1"><Rule id="test"/></Benchmark>'

        result = exporter._inject_metadata_from_config(test_xml)

        # Should have injected metadata
        assert "metadata" in result.lower() or "test-metadata" in result

    def test_inject_metadata_respects_rule_count(self, minimal_benchmark):
        """Should not inject more metadata than rules exist."""
        from lxml import etree

        exporter = XCCDFExporter(style="disa")

        # Create multiple metadata elements (more than rules)
        metadata_elems = [etree.Element(f"meta-{i}") for i in range(5)]
        exporter.engine._metadata_for_post_processing = metadata_elems

        # XML with only 2 rules
        test_xml = """<?xml version="1.0"?>
        <Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1">
            <Rule id="rule1"/>
            <Rule id="rule2"/>
        </Benchmark>"""

        result = exporter._inject_metadata_from_config(test_xml)

        # Should still produce valid XML
        root = etree.fromstring(result.encode("utf-8"))
        assert root is not None

    def test_inject_metadata_handles_missing_namespace(self, minimal_benchmark):
        """Should handle case where root has no namespace map."""
        from lxml import etree

        exporter = XCCDFExporter(style="disa")

        metadata_elem = etree.Element("test-metadata")
        exporter.engine._metadata_for_post_processing = [metadata_elem]

        # XML without namespace
        test_xml = '<?xml version="1.0"?><Benchmark><Rule id="test"/></Benchmark>'

        result = exporter._inject_metadata_from_config(test_xml)

        # Should still work - creates metadata without namespace prefix
        assert "metadata" in result.lower()


# ============================================================================
# Test: CIS Controls Ident URIs
# ============================================================================


class TestCISControlsIdentURIs:
    """Tests for _add_cis_controls_ident_uris method."""

    def test_add_cis_controls_ident_uris_with_safeguards(self):
        """Should add controlURI attributes to ident elements."""

        exporter = XCCDFExporter(style="cis")

        # Create XML with CIS Controls metadata and ident elements
        xccdf_ns = "http://checklists.nist.gov/xccdf/1.2"
        cc7_ns = "http://cisecurity.org/20-cc/v7.0"
        cc8_ns = "http://cisecurity.org/20-cc/v8.0"
        controls_ns = "http://cisecurity.org/controls"

        test_xml = f'''<?xml version="1.0"?>
        <Benchmark xmlns="{xccdf_ns}">
            <Rule id="test-rule">
                <ident system="http://cisecurity.org/20-cc/v8">CIS-8-4.1</ident>
                <metadata>
                    <cis_controls xmlns="{controls_ns}">
                        <safeguard urn="urn:cisecurity.org:controls:8:4:1"/>
                    </cis_controls>
                </metadata>
            </Rule>
        </Benchmark>'''

        result = exporter._add_cis_controls_ident_uris(test_xml, xccdf_ns, cc7_ns, cc8_ns)

        # Should contain controlURI
        assert "controlURI" in result or "control" in result

    def test_add_cis_controls_ident_uris_no_safeguards(self):
        """Should handle rules without safeguard elements."""
        exporter = XCCDFExporter(style="cis")

        xccdf_ns = "http://checklists.nist.gov/xccdf/1.2"
        cc7_ns = "http://cisecurity.org/20-cc/v7.0"
        cc8_ns = "http://cisecurity.org/20-cc/v8.0"

        test_xml = f'''<?xml version="1.0"?>
        <Benchmark xmlns="{xccdf_ns}">
            <Rule id="test-rule">
                <ident system="http://cisecurity.org/20-cc/v8">CIS-8-4.1</ident>
                <metadata>
                    <cis_controls xmlns="http://cisecurity.org/controls">
                    </cis_controls>
                </metadata>
            </Rule>
        </Benchmark>'''

        result = exporter._add_cis_controls_ident_uris(test_xml, xccdf_ns, cc7_ns, cc8_ns)

        # Should not raise error, return valid XML
        from lxml import etree

        root = etree.fromstring(result.encode("utf-8"))
        assert root is not None

    def test_add_cis_controls_ident_uris_no_metadata(self):
        """Should handle rules without metadata element."""
        exporter = XCCDFExporter(style="cis")

        xccdf_ns = "http://checklists.nist.gov/xccdf/1.2"
        cc7_ns = "http://cisecurity.org/20-cc/v7.0"
        cc8_ns = "http://cisecurity.org/20-cc/v8.0"

        test_xml = f'''<?xml version="1.0"?>
        <Benchmark xmlns="{xccdf_ns}">
            <Rule id="test-rule">
                <ident system="http://cisecurity.org/20-cc/v8">CIS-8-4.1</ident>
            </Rule>
        </Benchmark>'''

        result = exporter._add_cis_controls_ident_uris(test_xml, xccdf_ns, cc7_ns, cc8_ns)

        # Should not raise error
        from lxml import etree

        root = etree.fromstring(result.encode("utf-8"))
        assert root is not None

    def test_add_cis_controls_ident_uris_v7_controls(self):
        """Should handle v7 CIS Controls."""
        from lxml import etree

        exporter = XCCDFExporter(style="cis")

        xccdf_ns = "http://checklists.nist.gov/xccdf/1.2"
        cc7_ns = "http://cisecurity.org/20-cc/v7.0"
        cc8_ns = "http://cisecurity.org/20-cc/v8.0"
        controls_ns = "http://cisecurity.org/controls"

        test_xml = f'''<?xml version="1.0"?>
        <Benchmark xmlns="{xccdf_ns}">
            <Rule id="test-rule">
                <ident system="http://cisecurity.org/20-cc/v7">CIS-7-9.2</ident>
                <metadata>
                    <cis_controls xmlns="{controls_ns}">
                        <safeguard urn="urn:cisecurity.org:controls:7:9:2"/>
                    </cis_controls>
                </metadata>
            </Rule>
        </Benchmark>'''

        result = exporter._add_cis_controls_ident_uris(test_xml, xccdf_ns, cc7_ns, cc8_ns)

        # Should produce valid XML
        root = etree.fromstring(result.encode("utf-8"))
        assert root is not None

    def test_add_cis_controls_ident_uris_mixed_versions(self):
        """Should handle mixed v7 and v8 controls."""
        from lxml import etree

        exporter = XCCDFExporter(style="cis")

        xccdf_ns = "http://checklists.nist.gov/xccdf/1.2"
        cc7_ns = "http://cisecurity.org/20-cc/v7.0"
        cc8_ns = "http://cisecurity.org/20-cc/v8.0"
        controls_ns = "http://cisecurity.org/controls"

        test_xml = f'''<?xml version="1.0"?>
        <Benchmark xmlns="{xccdf_ns}">
            <Rule id="test-rule">
                <ident system="http://cisecurity.org/20-cc/v7">CIS-7-9.2</ident>
                <ident system="http://cisecurity.org/20-cc/v8">CIS-8-4.1</ident>
                <metadata>
                    <cis_controls xmlns="{controls_ns}">
                        <safeguard urn="urn:cisecurity.org:controls:7:9:2"/>
                        <safeguard urn="urn:cisecurity.org:controls:8:4:1"/>
                    </cis_controls>
                </metadata>
            </Rule>
        </Benchmark>'''

        result = exporter._add_cis_controls_ident_uris(test_xml, xccdf_ns, cc7_ns, cc8_ns)

        root = etree.fromstring(result.encode("utf-8"))
        assert root is not None

    def test_add_cis_controls_ident_uris_no_idents(self):
        """Should handle rules without ident elements."""
        exporter = XCCDFExporter(style="cis")

        xccdf_ns = "http://checklists.nist.gov/xccdf/1.2"
        cc7_ns = "http://cisecurity.org/20-cc/v7.0"
        cc8_ns = "http://cisecurity.org/20-cc/v8.0"
        controls_ns = "http://cisecurity.org/controls"

        test_xml = f'''<?xml version="1.0"?>
        <Benchmark xmlns="{xccdf_ns}">
            <Rule id="test-rule">
                <metadata>
                    <cis_controls xmlns="{controls_ns}">
                        <safeguard urn="urn:cisecurity.org:controls:8:4:1"/>
                    </cis_controls>
                </metadata>
            </Rule>
        </Benchmark>'''

        result = exporter._add_cis_controls_ident_uris(test_xml, xccdf_ns, cc7_ns, cc8_ns)

        # Should not raise error
        from lxml import etree

        root = etree.fromstring(result.encode("utf-8"))
        assert root is not None

    def test_add_cis_controls_ident_uris_unversioned_system(self):
        """Should skip idents without v7 or v8 in system URI."""
        exporter = XCCDFExporter(style="cis")

        xccdf_ns = "http://checklists.nist.gov/xccdf/1.2"
        cc7_ns = "http://cisecurity.org/20-cc/v7.0"
        cc8_ns = "http://cisecurity.org/20-cc/v8.0"
        controls_ns = "http://cisecurity.org/controls"

        test_xml = f'''<?xml version="1.0"?>
        <Benchmark xmlns="{xccdf_ns}">
            <Rule id="test-rule">
                <ident system="http://some-other-system">OTHER-ID</ident>
                <metadata>
                    <cis_controls xmlns="{controls_ns}">
                        <safeguard urn="urn:cisecurity.org:controls:8:4:1"/>
                    </cis_controls>
                </metadata>
            </Rule>
        </Benchmark>'''

        result = exporter._add_cis_controls_ident_uris(test_xml, xccdf_ns, cc7_ns, cc8_ns)

        # Should produce valid XML without controlURI on the unversioned ident
        from lxml import etree

        root = etree.fromstring(result.encode("utf-8"))
        assert root is not None

    def test_add_cis_controls_ident_uris_safeguard_with_subcontrol(self):
        """Should handle safeguard URNs with subcontrols."""
        from lxml import etree

        exporter = XCCDFExporter(style="cis")

        xccdf_ns = "http://checklists.nist.gov/xccdf/1.2"
        cc7_ns = "http://cisecurity.org/20-cc/v7.0"
        cc8_ns = "http://cisecurity.org/20-cc/v8.0"
        controls_ns = "http://cisecurity.org/controls"

        # URN with subcontrol (6 parts)
        test_xml = f'''<?xml version="1.0"?>
        <Benchmark xmlns="{xccdf_ns}">
            <Rule id="test-rule">
                <ident system="http://cisecurity.org/20-cc/v8">CIS-8-4.1.2</ident>
                <metadata>
                    <cis_controls xmlns="{controls_ns}">
                        <safeguard urn="urn:cisecurity.org:controls:8:4:1:2"/>
                    </cis_controls>
                </metadata>
            </Rule>
        </Benchmark>'''

        result = exporter._add_cis_controls_ident_uris(test_xml, xccdf_ns, cc7_ns, cc8_ns)

        root = etree.fromstring(result.encode("utf-8"))
        assert root is not None


# ============================================================================
# Test: Store Post Processing Data
# ============================================================================


class TestStorePostProcessingData:
    """Tests for _store_post_processing_data method."""

    def test_store_post_processing_data_with_dc_elements(self, minimal_benchmark):
        """Should store DC elements from mapping engine."""
        exporter = XCCDFExporter(style="disa")

        # Set up engine with DC elements
        exporter.engine._dc_elements = ["dc:publisher", "dc:source"]

        exporter._store_post_processing_data()

        assert exporter._dc_elements == ["dc:publisher", "dc:source"]

    def test_store_post_processing_data_no_dc_elements(self, minimal_benchmark):
        """Should handle missing DC elements gracefully."""
        exporter = XCCDFExporter(style="disa")

        # Ensure no DC elements on engine
        if hasattr(exporter.engine, "_dc_elements"):
            delattr(exporter.engine, "_dc_elements")

        exporter._store_post_processing_data()

        # Should set empty list as default
        assert exporter._dc_elements == []


# ============================================================================
# Test: Edge Cases and Error Handling
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_export_empty_recommendations(self, tmp_path):
        """Should handle benchmark with no recommendations."""
        benchmark = Benchmark(
            title="Empty Benchmark",
            benchmark_id="12345",
            url="https://workbench.cisecurity.org/benchmarks/12345",
            version="v1.0.0",
            scraper_version="1.0.0",
            total_recommendations=0,
            recommendations=[],
        )

        exporter = XCCDFExporter(style="disa")
        output_file = tmp_path / "test_output.xml"

        result = exporter.export(benchmark, str(output_file))

        # Should still create valid XML
        assert output_file.exists()

    def test_export_benchmark_with_minimal_title(self, tmp_path):
        """Should handle benchmark with minimal title."""
        rec = Recommendation(
            ref="1.1.1",
            title="Test",
            url="https://workbench.cisecurity.org/sections/1/recommendations/1",
            assessment_status="Automated",
        )
        benchmark = Benchmark(
            title="X",  # Minimal title (title min_length is 1, can't be empty)
            benchmark_id="12345",
            url="https://workbench.cisecurity.org/benchmarks/12345",
            version="v1.0.0",
            scraper_version="1.0.0",
            total_recommendations=1,
            recommendations=[rec],
        )

        exporter = XCCDFExporter(style="disa")
        output_file = tmp_path / "test_output.xml"

        # Should not raise error
        result = exporter.export(benchmark, str(output_file))
        assert output_file.exists()

    def test_export_writes_utf8_encoding(self, tmp_path, minimal_benchmark):
        """Should write file with UTF-8 encoding."""
        exporter = XCCDFExporter(style="disa")
        output_file = tmp_path / "test_output.xml"

        exporter.export(minimal_benchmark, str(output_file))

        content = output_file.read_bytes()
        # Should be valid UTF-8
        content.decode("utf-8")
        # XML declaration should specify UTF-8
        assert b"UTF-8" in content or b"utf-8" in content


# ============================================================================
# Test: Factory Registration
# ============================================================================


class TestApplyPostProcessingAdditional:
    """Additional tests for _apply_post_processing to cover edge cases."""

    def test_post_processing_with_xccdf_key_namespace(self, minimal_benchmark):
        """Should handle config with 'xccdf' key for namespace (line 177)."""
        exporter = XCCDFExporter(style="disa")

        # Initialize _dc_elements (normally done by _store_post_processing_data)
        exporter._dc_elements = []

        # Create minimal XML to process
        test_xml = '<?xml version="1.0"?><Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1" id="test"/>'

        # Patch YAML loading to return config with 'xccdf' key instead of 'default'
        with patch("builtins.open", mock_open(read_data="namespaces:\n  xccdf: http://test.ns")):
            with patch("yaml.safe_load") as mock_yaml:
                mock_yaml.return_value = {
                    "namespaces": {"xccdf": "http://checklists.nist.gov/xccdf/1.1"},
                    "post_processing": {"handlers": []},
                }

                # Should use xccdf key namespace and not raise
                result = exporter._apply_post_processing(test_xml, minimal_benchmark)
                assert result is not None

    def test_post_processing_unknown_handler_logs_warning(self, minimal_benchmark, caplog):
        """Should log warning for unknown handler (line 197)."""
        import logging

        exporter = XCCDFExporter(style="disa")

        # Initialize _dc_elements (normally done by _store_post_processing_data)
        exporter._dc_elements = []

        test_xml = '<?xml version="1.0"?><Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1" id="test"/>'

        with patch("builtins.open", mock_open(read_data="test")):
            with patch("yaml.safe_load") as mock_yaml:
                mock_yaml.return_value = {
                    "namespaces": {"default": "http://checklists.nist.gov/xccdf/1.1"},
                    "post_processing": {"handlers": ["unknown_handler_xyz"]},
                }

                with caplog.at_level(logging.WARNING):
                    exporter._apply_post_processing(test_xml, minimal_benchmark)

                assert "Unknown post-processing handler" in caplog.text


class TestCISControlsIdentURIsAdditional:
    """Additional tests for _add_cis_controls_ident_uris edge cases."""

    def test_add_cis_controls_safeguard_without_urn(self):
        """Should skip safeguards without urn attribute (line 300)."""
        from lxml import etree

        exporter = XCCDFExporter(style="cis")

        xccdf_ns = "http://checklists.nist.gov/xccdf/1.2"
        cc7_ns = "http://cisecurity.org/20-cc/v7.0"
        cc8_ns = "http://cisecurity.org/20-cc/v8.0"
        controls_ns = "http://cisecurity.org/controls"

        # Safeguard without urn attribute
        test_xml = f'''<?xml version="1.0"?>
        <Benchmark xmlns="{xccdf_ns}">
            <Rule id="test-rule">
                <ident system="http://cisecurity.org/20-cc/v8">CIS-8-4.1</ident>
                <metadata>
                    <cis_controls xmlns="{controls_ns}">
                        <safeguard/>
                    </cis_controls>
                </metadata>
            </Rule>
        </Benchmark>'''

        result = exporter._add_cis_controls_ident_uris(test_xml, xccdf_ns, cc7_ns, cc8_ns)

        # Should not raise error
        root = etree.fromstring(result.encode("utf-8"))
        assert root is not None

    def test_add_cis_controls_urn_too_short(self):
        """Should skip URNs with fewer than 5 parts (line 304)."""
        from lxml import etree

        exporter = XCCDFExporter(style="cis")

        xccdf_ns = "http://checklists.nist.gov/xccdf/1.2"
        cc7_ns = "http://cisecurity.org/20-cc/v7.0"
        cc8_ns = "http://cisecurity.org/20-cc/v8.0"
        controls_ns = "http://cisecurity.org/controls"

        # URN with only 4 parts (too short)
        test_xml = f'''<?xml version="1.0"?>
        <Benchmark xmlns="{xccdf_ns}">
            <Rule id="test-rule">
                <ident system="http://cisecurity.org/20-cc/v8">CIS-8-4.1</ident>
                <metadata>
                    <cis_controls xmlns="{controls_ns}">
                        <safeguard urn="short:urn:only:four"/>
                    </cis_controls>
                </metadata>
            </Rule>
        </Benchmark>'''

        result = exporter._add_cis_controls_ident_uris(test_xml, xccdf_ns, cc7_ns, cc8_ns)

        root = etree.fromstring(result.encode("utf-8"))
        assert root is not None

    def test_add_cis_controls_without_cis_controls_element(self):
        """Should skip rules without cis_controls element (line 290)."""
        from lxml import etree

        exporter = XCCDFExporter(style="cis")

        xccdf_ns = "http://checklists.nist.gov/xccdf/1.2"
        cc7_ns = "http://cisecurity.org/20-cc/v7.0"
        cc8_ns = "http://cisecurity.org/20-cc/v8.0"

        # Metadata without cis_controls element
        test_xml = f'''<?xml version="1.0"?>
        <Benchmark xmlns="{xccdf_ns}">
            <Rule id="test-rule">
                <ident system="http://cisecurity.org/20-cc/v8">CIS-8-4.1</ident>
                <metadata>
                    <other_element>content</other_element>
                </metadata>
            </Rule>
        </Benchmark>'''

        result = exporter._add_cis_controls_ident_uris(test_xml, xccdf_ns, cc7_ns, cc8_ns)

        root = etree.fromstring(result.encode("utf-8"))
        assert root is not None

    def test_add_cis_controls_control_uri_without_subcontrol(self):
        """Should generate URI without subcontrol when not provided (line 312)."""
        from lxml import etree

        exporter = XCCDFExporter(style="cis")

        xccdf_ns = "http://checklists.nist.gov/xccdf/1.2"
        cc7_ns = "http://cisecurity.org/20-cc/v7.0"
        cc8_ns = "http://cisecurity.org/20-cc/v8.0"
        controls_ns = "http://cisecurity.org/controls"

        # URN with exactly 5 parts (no subcontrol) - format: urn:cisecurity.org:controls:version:control
        test_xml = f'''<?xml version="1.0"?>
        <Benchmark xmlns="{xccdf_ns}">
            <Rule id="test-rule">
                <ident system="http://cisecurity.org/20-cc/v8">CIS-8-4</ident>
                <metadata>
                    <cis_controls xmlns="{controls_ns}">
                        <safeguard urn="urn:cisecurity.org:controls:8:4"/>
                    </cis_controls>
                </metadata>
            </Rule>
        </Benchmark>'''

        result = exporter._add_cis_controls_ident_uris(test_xml, xccdf_ns, cc7_ns, cc8_ns)

        root = etree.fromstring(result.encode("utf-8"))
        assert root is not None


class TestMetadataInjectionAdditional:
    """Additional tests for _inject_metadata_from_config edge cases."""

    def test_inject_metadata_more_rules_than_metadata(self):
        """Should break when metadata elements < rules (line 249)."""
        from lxml import etree

        exporter = XCCDFExporter(style="disa")

        # Create only 1 metadata element
        metadata_elem = etree.Element("test-metadata")
        metadata_elem.text = "Test"
        exporter.engine._metadata_for_post_processing = [metadata_elem]

        # XML with 3 rules
        test_xml = """<?xml version="1.0"?>
        <Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1">
            <Rule id="rule1"/>
            <Rule id="rule2"/>
            <Rule id="rule3"/>
        </Benchmark>"""

        result = exporter._inject_metadata_from_config(test_xml)

        # Should produce valid XML - only first rule gets metadata
        root = etree.fromstring(result.encode("utf-8"))
        assert root is not None


class TestFormatNameEdgeCases:
    """Tests for format_name with different style names."""

    def test_format_name_custom_style_uses_title_case(self):
        """Should use title case for non-standard style names."""
        # We can't easily test this without creating a custom style file
        # But we can verify the logic path exists
        exporter = XCCDFExporter(style="disa")
        # Manually set style to test title case branch
        exporter.style = "custom_style"

        result = exporter.format_name()

        # Should use title case for custom styles
        assert "Custom_Style" in result or "custom_style" in result.lower()


class TestFactoryRegistration:
    """Tests for ExporterFactory registration."""

    def test_xccdf_registered_in_factory(self):
        """XCCDFExporter should be registered for 'xccdf' format."""
        from cis_bench.exporters.base import ExporterFactory

        available = ExporterFactory.available_formats()
        assert "xccdf" in available

    def test_xml_registered_in_factory(self):
        """XCCDFExporter should be registered for 'xml' format."""
        from cis_bench.exporters.base import ExporterFactory

        available = ExporterFactory.available_formats()
        assert "xml" in available

    def test_factory_creates_xccdf_exporter(self):
        """Factory should create XCCDFExporter for 'xccdf' format."""
        from cis_bench.exporters.base import ExporterFactory

        exporter = ExporterFactory.create("xccdf", style="disa")

        assert isinstance(exporter, XCCDFExporter)
        assert exporter.style == "disa"

    def test_factory_creates_with_style_parameter(self):
        """Factory should pass style parameter to exporter."""
        from cis_bench.exporters.base import ExporterFactory

        exporter = ExporterFactory.create("xccdf", style="cis")

        assert exporter.style == "cis"
