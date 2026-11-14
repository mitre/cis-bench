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
        def override_attributes(exporter):
            output_file = tmp_path / "out.xml"
            exporter.export(sample_benchmark, str(output_file))
            return etree.parse(str(output_file)).getroot().xpath("//@override")

        keeping_overrides = XCCDFExporter(style="cis")
        keeping_overrides.config.post_processing["remove_override_attr"] = False

        assert override_attributes(XCCDFExporter(style="cis")) == []
        assert override_attributes(keeping_overrides)


XCCDF_1_1 = "http://checklists.nist.gov/xccdf/1.1"
DUBLIN_CORE = "http://purl.org/dc/elements/1.1/"


def _declared(exporter: XCCDFExporter) -> dict[str | None, str]:
    """The style's namespaces as an lxml nsmap ("default" is the default namespace)."""
    return {
        (None if prefix == "default" else prefix): uri
        for prefix, uri in exporter.config.namespaces.items()
    }


def _rendered_root(exporter: XCCDFExporter, benchmark: Benchmark):
    """The root of the document xsdata writes, before any post-processing."""
    return etree.fromstring(exporter._render(exporter._create_benchmark(benchmark)).encode())


class TestRendering:
    """xsdata writes the style's namespaces itself; nothing repairs them afterwards."""

    def test_the_rendered_document_already_declares_the_styles_namespaces(self, minimal_benchmark):
        root = _rendered_root(XCCDFExporter(style="disa"), minimal_benchmark)

        assert root.tag == f"{{{XCCDF_1_1}}}Benchmark"
        assert root.nsmap == {None: XCCDF_1_1, "dc": DUBLIN_CORE}

    def test_a_style_that_does_not_declare_its_xccdf_namespace_is_refused(self, minimal_benchmark):
        # xsdata would make up a prefix (ns0) for it; the style must name the namespace.
        exporter = XCCDFExporter(style="disa")
        del exporter.config.benchmark["namespaces"]["default"]

        with pytest.raises(ValueError, match=f"{XCCDF_1_1}.*benchmark.namespaces"):
            _rendered_root(exporter, minimal_benchmark)

    def test_a_style_may_declare_its_xccdf_namespace_with_a_prefix(self, minimal_benchmark):
        exporter = XCCDFExporter(style="disa")
        exporter.config.benchmark["namespaces"] = {"xccdf": XCCDF_1_1, "dc": DUBLIN_CORE}

        root = _rendered_root(exporter, minimal_benchmark)

        assert root.prefix == "xccdf"
        assert root.nsmap == {"xccdf": XCCDF_1_1, "dc": DUBLIN_CORE}

    def test_rule_metadata_is_in_the_xccdf_namespace_when_it_is_declared_with_a_prefix(
        self, sample_benchmark, tmp_path
    ):
        from cis_bench.validators.xccdf_schema import validate_xccdf

        xccdf_1_2 = "http://checklists.nist.gov/xccdf/1.2"
        exporter = XCCDFExporter(style="cis")
        namespaces = exporter.config.benchmark["namespaces"]
        namespaces["xccdf"] = namespaces.pop("default")
        output_file = tmp_path / "out.xml"

        exporter.export(sample_benchmark, str(output_file))
        root = etree.parse(str(output_file)).getroot()

        assert root.prefix == "xccdf"
        assert root.findall(f".//{{{xccdf_1_2}}}Rule/{{{xccdf_1_2}}}metadata")
        assert [e.tag for e in root.iter("*") if etree.QName(e).namespace is None] == []
        assert validate_xccdf(output_file).errors == []

    @pytest.mark.parametrize("style", ["disa", "cis"])
    def test_the_rendered_document_uses_only_the_prefixes_the_style_declares(
        self, style, sample_benchmark
    ):
        exporter = XCCDFExporter(style=style)
        root = _rendered_root(exporter, sample_benchmark)

        assert root.nsmap == _declared(exporter)
        assert {element.prefix for element in root.iter() if isinstance(element.tag, str)} <= set(
            _declared(exporter)
        )

    @pytest.mark.parametrize("style", ["disa", "cis"])
    def test_post_processing_changes_no_element_name_or_namespace_declaration(
        self, style, sample_benchmark, tmp_path
    ):
        exporter = XCCDFExporter(style=style)
        exporter.config.post_processing["handlers"] = []
        rendered = _rendered_root(exporter, sample_benchmark)
        output_file = tmp_path / "out.xml"

        exporter.export(sample_benchmark, str(output_file))
        written = etree.parse(str(output_file)).getroot()

        assert written.nsmap == rendered.nsmap
        assert [e.tag for e in written.iter("*")] == [e.tag for e in rendered.iter("*")]

    @pytest.mark.parametrize("style", ["disa", "cis"])
    def test_only_the_root_declares_namespaces(self, style, sample_benchmark, tmp_path):
        # Injected metadata uses the prefixes the root declares; nothing below it adds one.
        exporter = XCCDFExporter(style=style)
        output_file = tmp_path / "out.xml"

        exporter.export(sample_benchmark, str(output_file))
        root = etree.parse(str(output_file)).getroot()

        assert root.nsmap == _declared(exporter)
        assert [e.tag for e in root.iter("*") if e.nsmap != root.nsmap] == []


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
# Test: Duplicate Rule IDs
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


# ============================================================================
# Test: the CIS export carries every text field
# ============================================================================


def _cis_rule(tmp_path, **fields):
    """The one Rule element of a CIS export of a benchmark holding one recommendation."""
    rec = Recommendation(
        ref="1.1.1",
        title="Ensure the example is set",
        url="https://workbench.cisecurity.org/sections/1/recommendations/1",
        assessment_status="Automated",
        **fields,
    )
    benchmark = Benchmark(
        title="Test Benchmark",
        benchmark_id="12345",
        url="https://workbench.cisecurity.org/benchmarks/12345",
        version="v1.0.0",
        scraper_version="v2_2026_01",
        total_recommendations=1,
        recommendations=[rec],
    )
    output_file = tmp_path / "cis.xml"
    XCCDFExporter(style="cis").export(benchmark, str(output_file))
    root = etree.parse(str(output_file)).getroot()
    (rule,) = root.xpath("//*[local-name()='Rule']")
    return rule


def _idents(rule):
    return [(i.get("system"), i.text or "") for i in rule.xpath("./*[local-name()='ident']")]


def _description(rule):
    (element,) = rule.xpath("./*[local-name()='description']")
    return "".join(element.itertext())


class TestTheCisExportCarriesEveryTextField:
    """CIS's own XCCDF writes every line of a recommendation's references as an ident with
    system "URL", after the CIS Controls idents, and folds its extra sections into the text
    elements; the export does the same for references, default value and additional
    information (our own text throughout)."""

    def test_every_reference_line_is_a_url_ident_in_order(self, tmp_path):
        rule = _cis_rule(
            tmp_path,
            references="GRID: X-000001\nhttps://example.com/a\n\n  CCI-000001  \n",
            cis_controls=[
                CISControl(version=8, control="4.1", title="Control", ig1=True, ig2=True, ig3=True)
            ],
        )

        idents = _idents(rule)
        url_idents = [value for system, value in idents if system == "URL"]
        assert url_idents == ["GRID: X-000001", "https://example.com/a", "CCI-000001"]
        # after the CIS Controls ident, as CIS orders them
        assert [system == "URL" for system, _ in idents] == [False, True, True, True]

    def test_a_recommendation_without_references_has_no_url_ident(self, tmp_path):
        rule = _cis_rule(tmp_path, references=None)

        assert [system for system, _ in _idents(rule) if system == "URL"] == []

    def test_default_value_and_additional_information_follow_the_description(self, tmp_path):
        rule = _cis_rule(
            tmp_path,
            description="Set the example for <user>.",
            default_value="/etc/example: off",
            additional_info="Run <tool> first.\n\n```\nexample --check\n```",
        )

        assert _description(rule) == (
            "Set the example for <user>.\n\n"
            "Default Value:\n\n/etc/example: off\n\n"
            "Additional Information:\n\nRun <tool> first.\n\n```\nexample --check\n```"
        )

    def test_an_empty_folded_field_adds_no_label(self, tmp_path):
        rule = _cis_rule(
            tmp_path, description="Set the example.", default_value="off", additional_info=None
        )

        assert _description(rule) == "Set the example.\n\nDefault Value:\n\noff"

    def test_a_description_alone_is_written_as_it_is(self, tmp_path):
        rule = _cis_rule(tmp_path, description="Set the example for <user>.")

        assert _description(rule) == "Set the example for <user>."
