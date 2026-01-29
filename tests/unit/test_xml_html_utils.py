"""Tests for XML and HTML utility modules.

Tests for:
- cis_bench.utils.xml_utils: XCCDF namespace handling, serialization, post-processing
- cis_bench.utils.html_parser: HTML cleaning, parsing, and validation
"""


# ============================================================================
# XML Utils Tests
# ============================================================================


class TestXCCDFNamespaceFixer:
    """Tests for XCCDFNamespaceFixer.fix_namespaces."""

    def test_fix_namespaces_basic(self):
        """Should add XCCDF namespace to unnamespaced elements."""
        from cis_bench.utils.xml_utils import XCCDFNamespaceFixer

        xml_input = "<Benchmark><title>Test</title></Benchmark>"
        xccdf_ns = "http://checklists.nist.gov/xccdf/1.1"

        result = XCCDFNamespaceFixer.fix_namespaces(xml_input, xccdf_ns)

        # Namespace should be added to both root and child elements
        assert xccdf_ns in result
        assert "Test" in result

    def test_fix_namespaces_already_namespaced(self):
        """Should not modify elements that already have namespaces."""
        from cis_bench.utils.xml_utils import XCCDFNamespaceFixer

        xccdf_ns = "http://checklists.nist.gov/xccdf/1.1"
        xml_input = f'<Benchmark xmlns="{xccdf_ns}"><title>Test</title></Benchmark>'

        result = XCCDFNamespaceFixer.fix_namespaces(xml_input, xccdf_ns)

        # Should still have the namespace
        assert xccdf_ns in result
        assert "Test" in result


class TestXCCDFSerializer:
    """Tests for XCCDFSerializer."""

    def test_serialize_to_string_basic(self):
        """Should serialize xsdata objects to XML string (lines 66-77)."""
        from dataclasses import dataclass

        from cis_bench.utils.xml_utils import XCCDFSerializer

        # Create a simple dataclass that xsdata can serialize
        @dataclass
        class SimpleElement:
            value: str = "test"

        obj = SimpleElement(value="hello")
        result = XCCDFSerializer.serialize_to_string(obj)

        assert "<?xml" in result
        assert "hello" in result

    def test_serialize_to_string_no_pretty(self):
        """Should serialize without indentation when pretty=False."""
        from dataclasses import dataclass

        from cis_bench.utils.xml_utils import XCCDFSerializer

        @dataclass
        class SimpleElement:
            value: str = "test"

        obj = SimpleElement(value="compact")
        result = XCCDFSerializer.serialize_to_string(obj, pretty=False)

        assert "<?xml" in result
        assert "compact" in result

    def test_serialize_to_string_custom_indent(self):
        """Should use custom indent string."""
        from dataclasses import dataclass

        from cis_bench.utils.xml_utils import XCCDFSerializer

        @dataclass
        class SimpleElement:
            value: str = "test"

        obj = SimpleElement(value="indented")
        result = XCCDFSerializer.serialize_to_string(obj, indent="    ")  # 4 spaces

        assert "indented" in result

    def test_tree_to_string_basic(self):
        """Should convert lxml Element to string."""
        from lxml import etree

        from cis_bench.utils.xml_utils import XCCDFSerializer

        root = etree.Element("root")
        child = etree.SubElement(root, "child")
        child.text = "content"

        result = XCCDFSerializer.tree_to_string(root, pretty=True)

        assert "<?xml" in result
        assert "<root>" in result
        assert "<child>content</child>" in result

    def test_tree_to_string_no_pretty(self):
        """Should serialize without pretty printing when disabled."""
        from lxml import etree

        from cis_bench.utils.xml_utils import XCCDFSerializer

        root = etree.Element("root")
        etree.SubElement(root, "child").text = "test"

        result = XCCDFSerializer.tree_to_string(root, pretty=False)

        assert "<?xml" in result
        assert "<root>" in result


class TestDublinCoreInjector:
    """Tests for DublinCoreInjector."""

    def test_inject_dc_elements_basic(self):
        """Should inject DC elements into reference element."""
        from cis_bench.utils.xml_utils import DublinCoreInjector

        xccdf_ns = "http://checklists.nist.gov/xccdf/1.1"
        dc_ns = "http://purl.org/dc/elements/1.1/"

        xml_input = f"""<?xml version="1.0"?>
        <Benchmark xmlns="{xccdf_ns}">
            <reference/>
        </Benchmark>"""

        dc_elements = {"dc:publisher": "CIS Security", "dc:source": "https://cis.org"}

        result = DublinCoreInjector.inject_dc_elements(xml_input, dc_elements, xccdf_ns, dc_ns)

        assert "CIS Security" in result
        assert "https://cis.org" in result

    def test_inject_dc_elements_no_reference(self):
        """Should handle XML without reference element."""
        from cis_bench.utils.xml_utils import DublinCoreInjector

        xccdf_ns = "http://checklists.nist.gov/xccdf/1.1"

        xml_input = f"""<?xml version="1.0"?>
        <Benchmark xmlns="{xccdf_ns}">
            <title>Test</title>
        </Benchmark>"""

        dc_elements = {"dc:publisher": "CIS"}

        result = DublinCoreInjector.inject_dc_elements(xml_input, dc_elements, xccdf_ns)

        # Should not crash, just return XML without DC elements
        assert "Test" in result

    def test_inject_dc_into_all_references_with_markers(self):
        """Should parse DC markers and convert to proper DC elements (lines 227-283)."""
        from cis_bench.utils.xml_utils import DublinCoreInjector

        xccdf_ns = "http://checklists.nist.gov/xccdf/1.1"

        # XML with DC markers in reference text
        xml_input = f"""<?xml version="1.0"?>
        <Benchmark xmlns="{xccdf_ns}">
            <reference>DC:dc:title:NIST SP 800-53||DC:dc:identifier:CM-7</reference>
        </Benchmark>"""

        result = DublinCoreInjector.inject_dc_into_all_references(xml_input, xccdf_ns)

        # DC elements should be created
        assert "NIST SP 800-53" in result
        assert "CM-7" in result
        # Original marker text should be gone
        assert "DC:dc:" not in result

    def test_inject_dc_into_all_references_clears_existing_children(self):
        """Should clear existing children from reference element (line 185)."""
        from cis_bench.utils.xml_utils import DublinCoreInjector

        xccdf_ns = "http://checklists.nist.gov/xccdf/1.1"

        # XML with DC markers AND existing child elements
        xml_input = f"""<?xml version="1.0"?>
        <Benchmark xmlns="{xccdf_ns}">
            <reference>DC:dc:title:New Title<existingChild>old</existingChild></reference>
        </Benchmark>"""

        result = DublinCoreInjector.inject_dc_into_all_references(xml_input, xccdf_ns)

        # New DC element should be created
        assert "New Title" in result
        # Existing child should be removed
        assert "existingChild" not in result
        assert "old" not in result

    def test_inject_dc_into_all_references_no_markers(self):
        """Should not modify references without DC markers."""
        from cis_bench.utils.xml_utils import DublinCoreInjector

        xccdf_ns = "http://checklists.nist.gov/xccdf/1.1"

        xml_input = f"""<?xml version="1.0"?>
        <Benchmark xmlns="{xccdf_ns}">
            <reference>https://www.cisecurity.org/controls</reference>
        </Benchmark>"""

        result = DublinCoreInjector.inject_dc_into_all_references(xml_input, xccdf_ns)

        # Original content preserved
        assert "https://www.cisecurity.org/controls" in result

    def test_inject_cis_metadata_simple_element(self):
        """Should inject simple CIS metadata elements (lines 276-281)."""
        from cis_bench.utils.xml_utils import DublinCoreInjector

        xccdf_ns = "http://checklists.nist.gov/xccdf/1.1"

        xml_input = f"""<?xml version="1.0"?>
        <Benchmark xmlns="{xccdf_ns}">
            <metadata>META:cis-profile:Level 1</metadata>
        </Benchmark>"""

        result = DublinCoreInjector.inject_cis_metadata(xml_input, xccdf_ns)

        assert "Level 1" in result
        assert "META:" not in result

    def test_inject_cis_metadata_nested_structure(self):
        """Should inject nested CIS metadata with key=value pairs (lines 260-275)."""
        from cis_bench.utils.xml_utils import DublinCoreInjector

        xccdf_ns = "http://checklists.nist.gov/xccdf/1.1"

        xml_input = f"""<?xml version="1.0"?>
        <Benchmark xmlns="{xccdf_ns}">
            <metadata>META:cis-control:version=8:control-id=4.8:title=Uninstall Unnecessary Services</metadata>
        </Benchmark>"""

        result = DublinCoreInjector.inject_cis_metadata(xml_input, xccdf_ns)

        # Nested structure should be created
        assert "8" in result  # version
        assert "4.8" in result  # control-id
        assert "Uninstall Unnecessary Services" in result
        assert "META:" not in result

    def test_inject_cis_metadata_no_metadata_element(self):
        """Should handle XML without metadata elements."""
        from cis_bench.utils.xml_utils import DublinCoreInjector

        xccdf_ns = "http://checklists.nist.gov/xccdf/1.1"

        xml_input = f"""<?xml version="1.0"?>
        <Benchmark xmlns="{xccdf_ns}">
            <title>Test</title>
        </Benchmark>"""

        result = DublinCoreInjector.inject_cis_metadata(xml_input, xccdf_ns)

        # Should not crash
        assert "Test" in result

    def test_inject_cis_metadata_clears_existing_children(self):
        """Should clear existing children from metadata element (line 241)."""
        from cis_bench.utils.xml_utils import DublinCoreInjector

        xccdf_ns = "http://checklists.nist.gov/xccdf/1.1"

        # XML with META markers AND existing child elements
        xml_input = f"""<?xml version="1.0"?>
        <Benchmark xmlns="{xccdf_ns}">
            <metadata>META:cis-profile:Level 2<existingChild>old data</existingChild></metadata>
        </Benchmark>"""

        result = DublinCoreInjector.inject_cis_metadata(xml_input, xccdf_ns)

        # New CIS element should be created
        assert "Level 2" in result
        # Existing child should be removed
        assert "existingChild" not in result
        assert "old data" not in result


class TestXCCDFPostProcessor:
    """Tests for XCCDFPostProcessor.process."""

    def test_process_default_config(self):
        """Should use default config when none provided (line 323)."""
        from cis_bench.utils.xml_utils import XCCDFPostProcessor

        xccdf_ns = "http://checklists.nist.gov/xccdf/1.1"
        xml_input = f'<Benchmark xmlns="{xccdf_ns}"><title>Test</title></Benchmark>'

        # Call with post_processing_config=None (triggers line 323)
        result = XCCDFPostProcessor.process(xml_input, xccdf_ns)

        assert "Test" in result
        assert "<?xml" in result

    def test_process_removes_override_attr(self):
        """Should remove override attribute by default."""
        from cis_bench.utils.xml_utils import XCCDFPostProcessor

        xccdf_ns = "http://checklists.nist.gov/xccdf/1.1"
        xml_input = f'<Benchmark xmlns="{xccdf_ns}"><Rule override="true">Test</Rule></Benchmark>'

        result = XCCDFPostProcessor.process(xml_input, xccdf_ns)

        assert 'override="true"' not in result
        assert "Test" in result

    def test_process_preserve_namespaces_default_key(self):
        """Should handle 'default' key in preserve_namespaces (lines 371-372)."""
        from cis_bench.utils.xml_utils import XCCDFPostProcessor

        xccdf_ns = "http://checklists.nist.gov/xccdf/1.1"
        dc_ns = "http://purl.org/dc/elements/1.1/"

        xml_input = f'<Benchmark xmlns="{xccdf_ns}"><title>Test</title></Benchmark>'

        # Use namespace_map with None key (lxml convention)
        namespace_map = {None: xccdf_ns, "dc": dc_ns}

        config = {"preserve_namespaces": ["default", "dc"]}

        result = XCCDFPostProcessor.process(
            xml_input, xccdf_ns, namespace_map=namespace_map, post_processing_config=config
        )

        assert "Test" in result
        assert xccdf_ns in result

    def test_process_preserve_namespaces_from_default_string(self):
        """Should handle 'default' in namespace_map directly (line 372 branch)."""
        from cis_bench.utils.xml_utils import XCCDFPostProcessor

        xccdf_ns = "http://checklists.nist.gov/xccdf/1.1"

        xml_input = f'<Benchmark xmlns="{xccdf_ns}"><title>Test</title></Benchmark>'

        # Use namespace_map with 'default' string key instead of None
        namespace_map = {"default": xccdf_ns}

        config = {"preserve_namespaces": ["default"]}

        result = XCCDFPostProcessor.process(
            xml_input, xccdf_ns, namespace_map=namespace_map, post_processing_config=config
        )

        assert "Test" in result

    def test_process_with_dc_elements(self):
        """Should inject DC elements when provided."""
        from cis_bench.utils.xml_utils import XCCDFPostProcessor

        xccdf_ns = "http://checklists.nist.gov/xccdf/1.1"

        xml_input = f"""<?xml version="1.0"?>
        <Benchmark xmlns="{xccdf_ns}">
            <reference/>
        </Benchmark>"""

        dc_elements = {"dc:publisher": "Test Publisher"}

        result = XCCDFPostProcessor.process(xml_input, xccdf_ns, dc_elements=dc_elements)

        assert "Test Publisher" in result

    def test_process_strip_namespace_prefixes(self):
        """Should strip namespace prefixes when configured."""
        from cis_bench.utils.xml_utils import XCCDFPostProcessor

        xccdf_ns = "http://checklists.nist.gov/xccdf/1.1"

        xml_input = f'<Benchmark xmlns="{xccdf_ns}"><title>Test</title></Benchmark>'

        config = {"strip_namespace_prefixes": True}

        result = XCCDFPostProcessor.process(xml_input, xccdf_ns, post_processing_config=config)

        # Still valid XML
        assert "Test" in result
        assert "<?xml" in result

    def test_process_use_all_namespaces(self):
        """Should use all namespaces when preserve_namespaces not specified (lines 378-379)."""
        from cis_bench.utils.xml_utils import XCCDFPostProcessor

        xccdf_ns = "http://checklists.nist.gov/xccdf/1.1"
        dc_ns = "http://purl.org/dc/elements/1.1/"
        cis_ns = "http://cisecurity.org/xccdf/metadata/1.0"

        xml_input = f'<Benchmark xmlns="{xccdf_ns}"><title>Test</title></Benchmark>'

        # Provide namespace_map but NO preserve_namespaces config
        namespace_map = {None: xccdf_ns, "dc": dc_ns, "cis": cis_ns}

        # Empty config - preserve_namespaces will be None, triggering lines 378-379
        config = {}

        result = XCCDFPostProcessor.process(
            xml_input, xccdf_ns, namespace_map=namespace_map, post_processing_config=config
        )

        # All namespaces should be included
        assert xccdf_ns in result
        assert "Test" in result


# ============================================================================
# HTML Parser Tests
# ============================================================================


class TestHTMLCleanerStripHtml:
    """Tests for HTMLCleaner.strip_html."""

    def test_strip_html_basic(self):
        """Should remove HTML tags and return plain text."""
        from cis_bench.utils.html_parser import HTMLCleaner

        html = "<p>Hello <strong>world</strong></p>"
        result = HTMLCleaner.strip_html(html)

        assert result == "Hello world"

    def test_strip_html_none_input(self):
        """Should return empty string for None (already covered but verify)."""
        from cis_bench.utils.html_parser import HTMLCleaner

        assert HTMLCleaner.strip_html(None) == ""

    def test_strip_html_no_tags(self):
        """Should handle text without HTML tags."""
        from cis_bench.utils.html_parser import HTMLCleaner

        text = "Plain text without any tags"
        result = HTMLCleaner.strip_html(text)

        assert result == text


class TestHTMLCleanerHtmlToMarkdown:
    """Tests for HTMLCleaner.html_to_markdown."""

    def test_html_to_markdown_none(self):
        """Should return empty string for None (line 50)."""
        from cis_bench.utils.html_parser import HTMLCleaner

        result = HTMLCleaner.html_to_markdown(None)
        assert result == ""

    def test_html_to_markdown_paragraph(self):
        """Should convert <p> tags to newlines."""
        from cis_bench.utils.html_parser import HTMLCleaner

        html = "<p>First paragraph</p><p>Second paragraph</p>"
        result = HTMLCleaner.html_to_markdown(html)

        assert "First paragraph" in result
        assert "Second paragraph" in result

    def test_html_to_markdown_code(self):
        """Should convert <code> to backticks."""
        from cis_bench.utils.html_parser import HTMLCleaner

        html = "Run <code>ls -la</code> command"
        result = HTMLCleaner.html_to_markdown(html)

        assert "`ls -la`" in result

    def test_html_to_markdown_list(self):
        """Should convert <li> to markdown list items."""
        from cis_bench.utils.html_parser import HTMLCleaner

        html = "<ul><li>Item 1</li><li>Item 2</li></ul>"
        result = HTMLCleaner.html_to_markdown(html)

        assert "- Item 1" in result
        assert "- Item 2" in result

    def test_html_to_markdown_strong(self):
        """Should convert <strong> to bold markdown."""
        from cis_bench.utils.html_parser import HTMLCleaner

        html = "<strong>Important</strong>"
        result = HTMLCleaner.html_to_markdown(html)

        assert "**Important**" in result

    def test_html_to_markdown_emphasis(self):
        """Should convert <em> to italic markdown."""
        from cis_bench.utils.html_parser import HTMLCleaner

        html = "<em>Emphasized</em>"
        result = HTMLCleaner.html_to_markdown(html)

        assert "*Emphasized*" in result


class TestHTMLCleanerParseMitreTable:
    """Tests for HTMLCleaner.parse_mitre_table."""

    def test_parse_mitre_table_null_string(self):
        """Should return None for 'null' string (line 78)."""
        from cis_bench.utils.html_parser import HTMLCleaner

        result = HTMLCleaner.parse_mitre_table("null")
        assert result is None

    def test_parse_mitre_table_no_table(self):
        """Should return None when no table found (lines 86-87)."""
        from cis_bench.utils.html_parser import HTMLCleaner

        html = "<div>No table here</div>"
        result = HTMLCleaner.parse_mitre_table(html)

        assert result is None

    def test_parse_mitre_table_empty_rows(self):
        """Should skip rows without cells (line 98)."""
        from cis_bench.utils.html_parser import HTMLCleaner

        html = """
        <table>
            <tr></tr>
            <tr><th>Technique</th></tr>
            <tr><td>T1059</td></tr>
        </table>
        """
        result = HTMLCleaner.parse_mitre_table(html)

        assert result is not None
        assert "T1059" in result.get("techniques", [])

    def test_parse_mitre_table_with_techniques(self):
        """Should parse techniques section."""
        from cis_bench.utils.html_parser import HTMLCleaner

        html = """
        <table>
            <tr><th>Technique</th></tr>
            <tr><td>T1059, T1053</td></tr>
        </table>
        """
        result = HTMLCleaner.parse_mitre_table(html)

        assert result is not None
        assert "techniques" in result
        assert "T1059" in result["techniques"]
        assert "T1053" in result["techniques"]

    def test_parse_mitre_table_with_tactics(self):
        """Should parse tactics section."""
        from cis_bench.utils.html_parser import HTMLCleaner

        html = """
        <table>
            <tr><th>Tactic</th></tr>
            <tr><td>Execution, Persistence</td></tr>
        </table>
        """
        result = HTMLCleaner.parse_mitre_table(html)

        assert result is not None
        assert "Execution" in result["tactics"]
        assert "Persistence" in result["tactics"]

    def test_parse_mitre_table_with_mitigations(self):
        """Should parse mitigations section."""
        from cis_bench.utils.html_parser import HTMLCleaner

        html = """
        <table>
            <tr><th>Mitigation</th></tr>
            <tr><td>M1038, M1026</td></tr>
        </table>
        """
        result = HTMLCleaner.parse_mitre_table(html)

        assert result is not None
        assert "M1038" in result["mitigations"]

    def test_parse_mitre_table_no_data(self):
        """Should return None when table has no data."""
        from cis_bench.utils.html_parser import HTMLCleaner

        html = """
        <table>
            <tr><th>Header</th></tr>
        </table>
        """
        result = HTMLCleaner.parse_mitre_table(html)

        # Table exists but no matching data
        assert result is None


class TestHTMLCleanerParseCisControlsTable:
    """Tests for HTMLCleaner.parse_cis_controls_table."""

    def test_parse_cis_controls_empty(self):
        """Should return empty list for empty input (line 142)."""
        from cis_bench.utils.html_parser import HTMLCleaner

        result = HTMLCleaner.parse_cis_controls_table("")
        assert result == []

    def test_parse_cis_controls_none(self):
        """Should return empty list for None input."""
        from cis_bench.utils.html_parser import HTMLCleaner

        result = HTMLCleaner.parse_cis_controls_table(None)
        assert result == []

    def test_parse_cis_controls_version_8(self):
        """Should parse Version 8 controls (lines 155-165)."""
        from cis_bench.utils.html_parser import HTMLCleaner

        html = """
        <div>
            Version 8 10.3
            IG1 IG2 IG3
        </div>
        """
        result = HTMLCleaner.parse_cis_controls_table(html)

        assert len(result) >= 1
        v8_control = next((c for c in result if c["version"] == "8"), None)
        assert v8_control is not None
        assert v8_control["control_id"] == "10.3"

    def test_parse_cis_controls_version_7(self):
        """Should parse Version 7 controls (lines 168-178)."""
        from cis_bench.utils.html_parser import HTMLCleaner

        html = """
        <div>
            Version 7 8.5
            IG1 IG2
        </div>
        """
        result = HTMLCleaner.parse_cis_controls_table(html)

        assert len(result) >= 1
        v7_control = next((c for c in result if c["version"] == "7"), None)
        assert v7_control is not None
        assert v7_control["control_id"] == "8.5"

    def test_parse_cis_controls_both_versions(self):
        """Should parse both Version 7 and Version 8 controls."""
        from cis_bench.utils.html_parser import HTMLCleaner

        html = """
        <div>
            Version 8 4.8
            IG1 IG2 IG3
            Version 7 9.2
            IG1 IG2
        </div>
        """
        result = HTMLCleaner.parse_cis_controls_table(html)

        assert len(result) == 2


class TestHTMLCleanerParseNistReferences:
    """Tests for HTMLCleaner.parse_nist_references."""

    def test_parse_nist_references_empty(self):
        """Should return empty list for empty input (line 193)."""
        from cis_bench.utils.html_parser import HTMLCleaner

        result = HTMLCleaner.parse_nist_references("")
        assert result == []

    def test_parse_nist_references_none(self):
        """Should return empty list for None input."""
        from cis_bench.utils.html_parser import HTMLCleaner

        result = HTMLCleaner.parse_nist_references(None)
        assert result == []

    def test_parse_nist_references_single(self):
        """Should parse single NIST control."""
        from cis_bench.utils.html_parser import HTMLCleaner

        html = "NIST SP 800-53 Rev. 5: CM-7"
        result = HTMLCleaner.parse_nist_references(html)

        assert "CM-7" in result

    def test_parse_nist_references_multiple(self):
        """Should parse multiple NIST controls."""
        from cis_bench.utils.html_parser import HTMLCleaner

        html = "NIST SP 800-53 Rev. 5: SI-3, MP-7, AU-2"
        result = HTMLCleaner.parse_nist_references(html)

        assert "SI-3" in result
        assert "MP-7" in result
        assert "AU-2" in result

    def test_parse_nist_references_with_enhancements(self):
        """Should parse controls with enhancement numbers."""
        from cis_bench.utils.html_parser import HTMLCleaner

        html = "NIST SP 800-53: CM-7(2), SI-4(5)"
        result = HTMLCleaner.parse_nist_references(html)

        assert "CM-7(2)" in result
        assert "SI-4(5)" in result


class TestHTMLCleanerExtractProfilesFromTitle:
    """Tests for HTMLCleaner.extract_profiles_from_title."""

    def test_extract_profiles_level_1(self):
        """Should extract Level 1 profile (lines 218-222)."""
        from cis_bench.utils.html_parser import HTMLCleaner

        title = "1.1.1 Ensure filesystem integrity is checked (L1)"
        result = HTMLCleaner.extract_profiles_from_title(title)

        assert "Level 1" in result

    def test_extract_profiles_level_2(self):
        """Should extract Level 2 profile (lines 223-224)."""
        from cis_bench.utils.html_parser import HTMLCleaner

        title = "1.2.3 Configure advanced auditing (L2)"
        result = HTMLCleaner.extract_profiles_from_title(title)

        assert "Level 2" in result

    def test_extract_profiles_no_level(self):
        """Should return empty list when no level present (lines 228-229)."""
        from cis_bench.utils.html_parser import HTMLCleaner

        title = "1.1.1 Ensure something"
        result = HTMLCleaner.extract_profiles_from_title(title)

        assert result == []


class TestHTMLValidatorHasTable:
    """Tests for HTMLValidator.has_table."""

    def test_has_table_true(self):
        """Should return True when table exists."""
        from cis_bench.utils.html_parser import HTMLValidator

        html = "<div><table><tr><td>Data</td></tr></table></div>"
        assert HTMLValidator.has_table(html) is True

    def test_has_table_false(self):
        """Should return False when no table."""
        from cis_bench.utils.html_parser import HTMLValidator

        html = "<div>No table here</div>"
        assert HTMLValidator.has_table(html) is False

    def test_has_table_empty(self):
        """Should return False for empty input (lines 238-239)."""
        from cis_bench.utils.html_parser import HTMLValidator

        assert HTMLValidator.has_table("") is False

    def test_has_table_none(self):
        """Should return False for None input (line 240)."""
        from cis_bench.utils.html_parser import HTMLValidator

        assert HTMLValidator.has_table(None) is False

    def test_has_table_case_insensitive(self):
        """Should match table tag case-insensitively."""
        from cis_bench.utils.html_parser import HTMLValidator

        html = "<TABLE><TR><TD>Data</TD></TR></TABLE>"
        assert HTMLValidator.has_table(html) is True


class TestHTMLValidatorExtractAllIds:
    """Tests for HTMLValidator.extract_all_ids."""

    def test_extract_all_ids_basic(self):
        """Should extract all element IDs (lines 252-253)."""
        from cis_bench.utils.html_parser import HTMLValidator

        html = """
        <div id="container">
            <p id="intro">Text</p>
            <span id="highlight">More</span>
        </div>
        """
        result = HTMLValidator.extract_all_ids(html)

        assert "container" in result
        assert "intro" in result
        assert "highlight" in result
        assert len(result) == 3

    def test_extract_all_ids_empty(self):
        """Should return empty list when no IDs present."""
        from cis_bench.utils.html_parser import HTMLValidator

        html = "<div><p>No IDs here</p></div>"
        result = HTMLValidator.extract_all_ids(html)

        assert result == []

    def test_extract_all_ids_nested(self):
        """Should find IDs at any nesting level."""
        from cis_bench.utils.html_parser import HTMLValidator

        html = """
        <div>
            <div>
                <div id="deeply-nested">Content</div>
            </div>
        </div>
        """
        result = HTMLValidator.extract_all_ids(html)

        assert "deeply-nested" in result
