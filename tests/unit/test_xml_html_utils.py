"""Tests for XML and HTML utility modules.

Tests for:
- cis_bench.utils.xml_utils: XCCDF serialization with a namespace map, post-processing
- cis_bench.utils.html_parser: HTML cleaning, parsing, and validation
"""

import pytest
from lxml import etree

# ============================================================================
# XML Utils Tests
# ============================================================================


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


XCCDF_1_2 = "http://checklists.nist.gov/xccdf/1.2"


def _resolve(element, qname: str) -> str:
    """A QName value (prefix:local or local) resolved with the namespaces in scope."""
    prefix, _, local = qname.rpartition(":")
    return f"{{{element.nsmap[prefix or None]}}}{local}"


class TestXsiTypeValues:
    """An xsi:type value is a QName in the document: its prefix must be one in scope."""

    @pytest.mark.parametrize(
        "ns_map", [{None: XCCDF_1_2}, {"xccdf": XCCDF_1_2}], ids=["unprefixed", "prefixed"]
    )
    def test_an_xsi_type_value_resolves_to_its_type(self, ns_map):
        from xsdata.formats.dataclass.context import XmlContext

        from cis_bench.models.xccdf.xccdf_1_2 import Rule, WarningType
        from cis_bench.utils.xml_utils import XCCDFPostProcessor, XCCDFSerializer

        # A Rule description given a subtype: xsdata names the subtype in xsi:type
        rule = Rule(id="xccdf_org.example_rule_r", description=[WarningType(content=["d"])])

        # As the exporter writes it: serialized, then post-processed
        written = XCCDFPostProcessor.process(
            XCCDFSerializer.serialize_to_string(rule, ns_map=ns_map)
        )
        root = etree.fromstring(written.encode())
        description = root.find(f"{{{XCCDF_1_2}}}description")
        xsi_type = description.get("{http://www.w3.org/2001/XMLSchema-instance}type")

        assert _resolve(description, xsi_type) == XmlContext().build(WarningType).target_qname


class TestXCCDFPostProcessor:
    """Tests for XCCDFPostProcessor.process: attributes only, namespaces left as written."""

    DOCUMENT = (
        f'<Benchmark xmlns="{XCCDF_1_2}" xmlns:dc="http://purl.org/dc/elements/1.1/"'
        ' xmlns:controls="http://cisecurity.org/controls">'
        '<Rule id="r" override="true"><dc:title>T</dc:title>'
        "<metadata><controls:cis_controls/></metadata></Rule></Benchmark>"
    )

    def test_override_attributes_are_removed_by_default(self):
        from cis_bench.utils.xml_utils import XCCDFPostProcessor

        root = etree.fromstring(XCCDFPostProcessor.process(self.DOCUMENT).encode())

        assert {e.get("override") for e in root.iter("*")} == {None}

    def test_override_attributes_stay_when_the_style_keeps_them(self):
        from cis_bench.utils.xml_utils import XCCDFPostProcessor

        result = XCCDFPostProcessor.process(self.DOCUMENT, {"remove_override_attr": False})

        assert etree.fromstring(result.encode()).find(f"{{{XCCDF_1_2}}}Rule").get("override") == (
            "true"
        )

    def test_every_element_name_and_namespace_declaration_is_kept(self):
        from cis_bench.utils.xml_utils import XCCDFPostProcessor

        before = etree.fromstring(self.DOCUMENT.encode())
        after = etree.fromstring(XCCDFPostProcessor.process(self.DOCUMENT).encode())

        assert [(e.tag, e.prefix, e.nsmap) for e in after.iter("*")] == [
            (e.tag, e.prefix, e.nsmap) for e in before.iter("*")
        ]


# ============================================================================
# HTML Parser Tests
# ============================================================================


class TestNCNameSlug:
    """Tests for ncname_slug: text to an XML NCName-safe identifier segment."""

    def test_cis_title_becomes_underscored_segment(self):
        from cis_bench.utils.xml_utils import ncname_slug

        assert (
            ncname_slug("CIS Ubuntu Linux 22.04 LTS Benchmark")
            == "CIS_Ubuntu_Linux_22.04_LTS_Benchmark"
        )

    def test_ncname_safe_text_is_unchanged(self):
        from cis_bench.utils.xml_utils import ncname_slug

        assert ncname_slug("v1.0.0") == "v1.0.0"
        assert ncname_slug("Release-2_final") == "Release-2_final"

    def test_runs_of_unsafe_characters_collapse_to_one_underscore(self):
        from cis_bench.utils.xml_utils import ncname_slug

        assert ncname_slug("a  b\t/c:d") == "a_b_c_d"
        assert ncname_slug("v7.1.0 (vNext)") == "v7.1.0_vNext"

    def test_leading_and_trailing_separators_are_dropped(self):
        from cis_bench.utils.xml_utils import ncname_slug

        assert ncname_slug("  Title  ") == "Title"
        assert ncname_slug("(draft)") == "draft"

    def test_empty_text_gives_empty_slug(self):
        from cis_bench.utils.xml_utils import ncname_slug

        assert ncname_slug("") == ""
        assert ncname_slug(" / ") == ""


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


class TestAttributeText:
    """attribute_text reads one attribute of a tag as text, whatever bs4 stored it as."""

    @staticmethod
    def _tag(html):
        from bs4 import BeautifulSoup

        return BeautifulSoup(html, "html.parser").find("wb-x")

    def test_a_single_valued_attribute_is_returned_as_written(self):
        from cis_bench.utils.html_parser import attribute_text

        assert attribute_text(self._tag("<wb-x profiles='[{\"a\": 1}]'></wb-x>"), "profiles") == (
            '[{"a": 1}]'
        )

    def test_a_missing_attribute_is_none(self):
        from cis_bench.utils.html_parser import attribute_text

        assert attribute_text(self._tag("<wb-x></wb-x>"), "profiles") is None

    def test_an_empty_attribute_is_an_empty_string(self):
        from cis_bench.utils.html_parser import attribute_text

        assert attribute_text(self._tag('<wb-x id=""></wb-x>'), "id") == ""

    def test_a_multi_valued_attribute_is_joined_as_it_was_written(self):
        from cis_bench.utils.html_parser import attribute_text

        assert attribute_text(self._tag('<wb-x class="one  two"></wb-x>'), "class") == "one two"
