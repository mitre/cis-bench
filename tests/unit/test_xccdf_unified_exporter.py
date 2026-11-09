"""Tests for XCCDF Unified Exporter.

Tests for XCCDFExporter class covering:
- Initialization with different styles
- Style validation and error handling
- Export method with both CIS and DISA styles
- Post-processing pipeline
- Metadata injection
"""

import pytest
from lxml import etree

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


# ============================================================================
# Test: Post-Processing Pipeline
# ============================================================================


class TestPostProcessing:
    """Tests for _apply_post_processing method."""

    def test_the_root_declares_the_namespaces_of_the_loaded_config(
        self, tmp_path, minimal_benchmark
    ):
        exporter = XCCDFExporter(style="cis")
        exporter.config.benchmark["namespaces"]["ex"] = "urn:example"
        output_file = tmp_path / "out.xml"

        exporter.export(minimal_benchmark, str(output_file))

        assert etree.parse(str(output_file)).getroot().nsmap.get("ex") == "urn:example"

    def test_post_processing_follows_the_loaded_config(self, tmp_path, sample_benchmark):
        def controls_metadata(exporter):
            output_file = tmp_path / "out.xml"
            exporter.export(sample_benchmark, str(output_file))
            return (
                etree.parse(str(output_file))
                .getroot()
                .xpath("//*[namespace-uri()='http://cisecurity.org/controls']")
            )

        without_injection = XCCDFExporter(style="cis")
        without_injection.config.post_processing["handlers"] = ["dublin_core_injection"]

        assert controls_metadata(XCCDFExporter(style="cis"))
        assert controls_metadata(without_injection) == []

    def test_post_processing_missing_xccdf_namespace_raises_error(self, minimal_benchmark):
        """Should raise ValueError if no XCCDF namespace in config."""
        exporter = XCCDFExporter(style="disa")

        # Create minimal XML to process
        test_xml = '<?xml version="1.0"?><Benchmark id="test"/>'

        exporter.config.benchmark["namespaces"] = {}  # No default or xccdf key
        exporter.config.post_processing = {"handlers": []}

        with pytest.raises(ValueError, match="No XCCDF namespace found"):
            exporter._apply_post_processing(test_xml, minimal_benchmark)


# ============================================================================
# Test: Metadata Injection
# ============================================================================


class TestMetadataInjection:
    """Tests for _inject_metadata_from_config method."""

    def test_inject_metadata_no_elements(self, minimal_benchmark):
        """Should return unchanged XML when no metadata elements."""
        exporter = XCCDFExporter(style="cis")

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

        exporter = XCCDFExporter(style="cis")

        # Create a simple metadata element to inject
        metadata_elem = etree.Element("test-metadata")
        metadata_elem.text = "Test content"

        # Store metadata for injection
        exporter.engine._metadata_for_post_processing = [metadata_elem]

        test_xml = '<?xml version="1.0"?><Benchmark xmlns="http://checklists.nist.gov/xccdf/1.2"><Rule id="test"/></Benchmark>'

        result = exporter._inject_metadata_from_config(test_xml)

        # Should have injected metadata
        assert "metadata" in result.lower() or "test-metadata" in result

    def test_inject_metadata_respects_rule_count(self, minimal_benchmark):
        """Should not inject more metadata than rules exist."""
        from lxml import etree

        exporter = XCCDFExporter(style="cis")

        # Create multiple metadata elements (more than rules)
        metadata_elems = [etree.Element(f"meta-{i}") for i in range(5)]
        exporter.engine._metadata_for_post_processing = metadata_elems

        # XML with only 2 rules
        test_xml = """<?xml version="1.0"?>
        <Benchmark xmlns="http://checklists.nist.gov/xccdf/1.2">
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

        exporter = XCCDFExporter(style="cis")

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

        # Create minimal XML to process
        test_xml = '<?xml version="1.0"?><Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1" id="test"/>'

        # A config naming the XCCDF namespace "xccdf" instead of "default"
        exporter.config.benchmark["namespaces"] = {"xccdf": "http://checklists.nist.gov/xccdf/1.1"}
        exporter.config.post_processing = {"handlers": []}

        # Should use xccdf key namespace and not raise
        result = exporter._apply_post_processing(test_xml, minimal_benchmark)
        assert result is not None

    def test_post_processing_unknown_handler_logs_warning(self, minimal_benchmark, caplog):
        """Should log warning for unknown handler (line 197)."""
        import logging

        exporter = XCCDFExporter(style="disa")

        test_xml = '<?xml version="1.0"?><Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1" id="test"/>'

        exporter.config.post_processing = {"handlers": ["unknown_handler_xyz"]}

        with caplog.at_level(logging.WARNING):
            exporter._apply_post_processing(test_xml, minimal_benchmark)

        assert "Unknown post-processing handler" in caplog.text


class TestMetadataInjectionAdditional:
    """Additional tests for _inject_metadata_from_config edge cases."""

    def test_inject_metadata_more_rules_than_metadata(self):
        """Should break when metadata elements < rules (line 249)."""
        from lxml import etree

        exporter = XCCDFExporter(style="cis")

        # Create only 1 metadata element
        metadata_elem = etree.Element("test-metadata")
        metadata_elem.text = "Test"
        exporter.engine._metadata_for_post_processing = [metadata_elem]

        # XML with 3 rules
        test_xml = """<?xml version="1.0"?>
        <Benchmark xmlns="http://checklists.nist.gov/xccdf/1.2">
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


# ============================================================================
# Test: Duplicate Rule IDs and schema-ordered metadata insertion
# ============================================================================


def _recommendation(ref: str, title: str) -> Recommendation:
    return Recommendation(
        ref=ref,
        title=title,
        url=f"https://workbench.cisecurity.org/sections/1/recommendations/{ref}",
        assessment_status="Automated",
    )


class TestDuplicateRuleIds:
    """Two recommendations that map to one Rule ID are invalid XCCDF and must not export."""

    def test_export_raises_on_duplicate_rule_ids(self, tmp_path):
        from cis_bench.exceptions import ExportError

        benchmark = Benchmark(
            title="Test Benchmark",
            benchmark_id="12345",
            url="https://workbench.cisecurity.org/benchmarks/12345",
            version="v1.0.0",
            scraper_version="1.0.0",
            total_recommendations=3,
            recommendations=[
                _recommendation("1.1.1", "First"),
                _recommendation("1.1.2", "Unrelated"),
                _recommendation("1.1.1", "Second with the same ref"),
            ],
        )
        output = tmp_path / "dup.xml"

        with pytest.raises(ExportError) as exc_info:
            XCCDFExporter(style="cis").export(benchmark, str(output))

        message = str(exc_info.value)
        assert "xccdf_org.cisecurity.benchmarks_rule_1_1_1" in message
        assert "1.1.1" in message and "First" in message and "Second with the same ref" in message
        assert "1.1.2" not in message
        assert not output.exists(), "no file may be written for an invalid document"

    def test_export_with_unique_rule_ids_still_writes(self, tmp_path):
        benchmark = Benchmark(
            title="Test Benchmark",
            benchmark_id="12345",
            url="https://workbench.cisecurity.org/benchmarks/12345",
            version="v1.0.0",
            scraper_version="1.0.0",
            total_recommendations=2,
            recommendations=[_recommendation("1.1.1", "First"), _recommendation("1.1.2", "Second")],
        )
        output = tmp_path / "ok.xml"
        XCCDFExporter(style="cis").export(benchmark, str(output))
        assert output.exists()


class TestMetadataInsertionFollowsSchemaOrder:
    """Metadata is placed where the XCCDF schema of the style's version puts it."""

    def test_metadata_goes_after_the_last_item_element_present(self):
        """XCCDF 1.2 Rule: ...reference, metadata, rationale, platform, ..., signature.

        Order from src/cis_bench/schemas/xccdf/1.2/xccdf_1.2.xsd itemType -> selectableItemType -> ruleType.
        """
        from lxml import etree

        exporter = XCCDFExporter(style="cis")
        exporter.engine._metadata_for_post_processing = [etree.Element("extra")]
        exporter._rule_metadata_by_id = {"r": [etree.Element("extra")]}
        xml = (
            '<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.2">'
            '<Rule id="r"><title/><description/><reference/><rationale/><fixtext/><check/></Rule>'
            "</Benchmark>"
        )

        root = etree.fromstring(exporter._inject_metadata_from_config(xml).encode())
        children = [etree.QName(c).localname for c in root[0]]
        assert children == [
            "title",
            "description",
            "reference",
            "metadata",
            "rationale",
            "fixtext",
            "check",
        ]

    def test_metadata_is_appended_when_no_later_element_is_present(self):
        from lxml import etree

        exporter = XCCDFExporter(style="cis")
        exporter._rule_metadata_by_id = {"r": [etree.Element("extra")]}
        xml = (
            '<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.2">'
            '<Rule id="r"><title/><description/></Rule></Benchmark>'
        )

        root = etree.fromstring(exporter._inject_metadata_from_config(xml).encode())
        assert [etree.QName(c).localname for c in root[0]] == ["title", "description", "metadata"]

    def test_injection_is_refused_for_a_version_whose_rule_has_no_metadata(self):
        """XCCDF 1.1.4 Rules carry no metadata element (src/cis_bench/schemas/xccdf/1.1/xccdf-schema.xsd itemType, 717-745).

        Enabling the handler on such a style is a configuration error whether or
        not anything happens to be queued for injection.
        """
        from cis_bench.exceptions import ExportError

        exporter = XCCDFExporter(style="disa")
        xml = '<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1"><Rule id="r"><title/></Rule></Benchmark>'

        with pytest.raises(ExportError, match="1.1.4"):
            exporter._inject_metadata_from_config(xml)
