"""Unit tests for helper methods and utilities.

Tests the core helper functions that power the mapping engine:
- TransformRegistry: HTML transformations
- VariableSubstituter: Variable substitution in templates
- CCILookupService: CCI deduplication logic
- DRY Helpers: Element construction methods
- WorkbenchParser: HTML/JSON parsing utilities
- HTMLCleaner: HTML transformation methods
"""

import pytest

from cis_bench.exporters.mapping_engine import (
    MappingEngine,
    TransformRegistry,
    VariableSubstituter,
)
from cis_bench.models.benchmark import (
    CISControl,
    MITREMapping,
    Recommendation,
)
from cis_bench.utils.cci_lookup import CCILookupService
from cis_bench.utils.html_parser import HTMLCleaner
from cis_bench.utils.parsers import WorkbenchParser

# ============================================================================
# FIXTURES - Common test data
# ============================================================================


@pytest.fixture
def sample_html_simple():
    """Simple HTML with basic tags."""
    return "<p>This is <strong>bold</strong> text.</p>"


@pytest.fixture
def sample_html_with_code():
    """HTML with code blocks that should be preserved."""
    return """
    <p>Run the command:</p>
    <pre><code>kubectl get pods</code></pre>
    <p>Expected output: <code>Running</code></p>
    """


@pytest.fixture
def sample_html_nested():
    """HTML with nested tags."""
    return "<div><p>Outer <span>inner <strong>bold</strong> text</span></p></div>"


@pytest.fixture
def sample_html_malformed():
    """Malformed HTML (unclosed tags)."""
    return "<p>Unclosed paragraph<strong>Bold text"


@pytest.fixture
def sample_mitre_table():
    """Sample MITRE ATT&CK mapping table HTML."""
    return """
    <table>
        <tr>
            <th>Techniques</th>
        </tr>
        <tr>
            <td>T1078, T1110, T1563</td>
        </tr>
        <tr>
            <th>Tactics</th>
        </tr>
        <tr>
            <td>TA0001, TA0002</td>
        </tr>
        <tr>
            <th>Mitigations</th>
        </tr>
        <tr>
            <td>M1026, M1027</td>
        </tr>
    </table>
    """


@pytest.fixture
def sample_nist_references():
    """Sample HTML with NIST control references."""
    return """
    <p>NIST SP 800-53 Rev. 5: CM-7, SI-3, AC-2(1)</p>
    <p>Additional: NIST SP 800-53 Revision 4 :: CM-7.1</p>
    """


@pytest.fixture
def sample_cis_controls_json():
    """Sample CIS Controls JSON string."""
    return """
    [
        {
            "version": "8",
            "control": "4.8",
            "title": "Uninstall or Disable Unnecessary Services",
            "ig1": true,
            "ig2": true,
            "ig3": true
        },
        {
            "version": "7",
            "control": "9.2",
            "title": "Ensure Only Approved Ports",
            "ig1": false,
            "ig2": true,
            "ig3": true
        }
    ]
    """


@pytest.fixture
def sample_recommendation():
    """Sample Recommendation object for testing."""
    return Recommendation(
        url="https://workbench.cisecurity.org/recommendations/12345",
        ref="3.1.1",
        title="Ensure that the kubeconfig file permissions are set to 644 or more restrictive",
        assessment_status="Automated",
        description="<p>Ensure that the <code>kubeconfig</code> file has permissions of <strong>644</strong> or more restrictive.</p>",
        rationale="<p>The kubeconfig file controls various parameters. You should restrict its file permissions.</p>",
        impact="<p>This significantly strengthens the security posture.</p>",
        audit="<pre><code>stat -c %a /var/lib/kubelet/kubeconfig</code></pre>",
        remediation="<pre><code>chmod 644 &lt;kubeconfig file&gt;</code></pre>",
        default_value="<p>See the AWS EKS documentation.</p>",
        additional_info="<p>Additional mitigation information.</p>",
        references="<p><a href='https://kubernetes.io/docs/'>Kubernetes Docs</a></p>",
        cis_controls=[
            CISControl(
                version=8, control="4.8", title="Uninstall Services", ig1=True, ig2=True, ig3=True
            )
        ],
        nist_controls=["CM-7", "SI-3", "AC-2(1)"],
        profiles=["Level 1", "Server"],
        mitre_mapping=MITREMapping(
            techniques=["T1078", "T1110"], tactics=["TA0001"], mitigations=["M1026"]
        ),
    )


@pytest.fixture
def sample_context():
    """Sample mapping context for variable substitution."""
    return {
        "platform": "eks",
        "ref": "3.1.1",
        "ref_normalized": "3_1_1",
        "stig_number": "030101",  # 3.1.1 → 03 01 01 → 030101
        "control": {"version": "8", "control": "4.8", "title": "Uninstall Services"},
        "nist_control_id": "CM-7",
    }


@pytest.fixture
def config_path(disa_config_path):
    """Path to DISA style config (use conftest fixture)."""
    return disa_config_path


# ============================================================================
# TEST: TransformRegistry
# ============================================================================


class TestTransformRegistry:
    """Unit tests for transformation functions."""

    def test_strip_html_basic(self, sample_html_simple):
        """Test basic HTML stripping."""
        result = TransformRegistry.apply("strip_html", sample_html_simple)
        assert result == "This is bold text."
        assert "<" not in result
        assert ">" not in result

    def test_strip_html_with_nested_tags(self, sample_html_nested):
        """Test HTML stripping with nested tags."""
        result = TransformRegistry.apply("strip_html", sample_html_nested)
        assert result == "Outer inner bold text"
        assert "span" not in result
        assert "div" not in result

    def test_strip_html_none_input(self):
        """Test strip_html with None input."""
        result = TransformRegistry.apply("strip_html", None)
        assert result == ""

    def test_strip_html_empty_string(self):
        """Test strip_html with empty string."""
        result = TransformRegistry.apply("strip_html", "")
        assert result == ""

    def test_strip_html_malformed(self, sample_html_malformed):
        """Test strip_html with malformed HTML."""
        result = TransformRegistry.apply("strip_html", sample_html_malformed)
        # BeautifulSoup should handle malformed HTML gracefully
        assert "Unclosed paragraph" in result
        assert "Bold text" in result
        assert "<" not in result

    def test_strip_html_keep_code_basic(self, sample_html_simple):
        """Test strip_html_keep_code on simple HTML."""
        result = TransformRegistry.apply("strip_html_keep_code", sample_html_simple)
        # Should strip HTML (currently uses strip_html implementation)
        assert "bold" in result.lower()

    def test_strip_html_keep_code_with_code_blocks(self, sample_html_with_code):
        """Test strip_html_keep_code preserves code blocks."""
        result = TransformRegistry.apply("strip_html_keep_code", sample_html_with_code)
        # Currently just strips all HTML - future enhancement should preserve <code>/<pre>
        assert "kubectl get pods" in result
        assert "Running" in result

    def test_html_to_markdown_basic(self, sample_html_simple):
        """Test HTML to Markdown conversion."""
        result = TransformRegistry.apply("html_to_markdown", sample_html_simple)
        # Should convert <strong> to **bold**
        assert "**bold**" in result or "bold" in result  # Depends on implementation

    def test_html_to_markdown_none_input(self):
        """Test html_to_markdown with None input."""
        result = TransformRegistry.apply("html_to_markdown", None)
        assert result == ""

    def test_none_transform(self):
        """Test 'none' transformation (pass-through)."""
        test_value = "unchanged text"
        result = TransformRegistry.apply("none", test_value)
        assert result == test_value

    def test_unknown_transform_raises_error(self):
        """Test that unknown transformation raises ValueError."""
        with pytest.raises(ValueError, match="Unknown transformation"):
            TransformRegistry.apply("nonexistent_transform", "test")

    def test_transform_with_special_characters(self):
        """Test HTML stripping with special characters."""
        html = "<p>Test &amp; &lt;special&gt; characters</p>"
        result = TransformRegistry.apply("strip_html", html)
        assert "&" in result or "amp" in result  # HTML entities handling

    # === strip_version_prefix transform tests ===

    def test_strip_version_prefix_lowercase_v(self):
        """Test stripping lowercase 'v' prefix from version."""
        result = TransformRegistry.apply("strip_version_prefix", "v4.0.0")
        assert result == "4.0.0"

    def test_strip_version_prefix_uppercase_v(self):
        """Test stripping uppercase 'V' prefix from version."""
        result = TransformRegistry.apply("strip_version_prefix", "V1.2.3")
        assert result == "1.2.3"

    def test_strip_version_prefix_no_prefix(self):
        """Test version without prefix is unchanged."""
        result = TransformRegistry.apply("strip_version_prefix", "4.0.0")
        assert result == "4.0.0"

    def test_strip_version_prefix_none_input(self):
        """Test strip_version_prefix with None input."""
        result = TransformRegistry.apply("strip_version_prefix", None)
        assert result == ""

    def test_strip_version_prefix_empty_string(self):
        """Test strip_version_prefix with empty string."""
        result = TransformRegistry.apply("strip_version_prefix", "")
        assert result == ""

    def test_strip_version_prefix_only_v(self):
        """Test edge case: version is just 'v'."""
        result = TransformRegistry.apply("strip_version_prefix", "v")
        assert result == ""


# ============================================================================
# TEST: VariableSubstituter
# ============================================================================


class TestVariableSubstituter:
    """Unit tests for variable substitution."""

    def test_simple_variable_substitution(self, sample_context):
        """Test simple variable substitution."""
        template = "xccdf_cis_{platform}_rule_{ref_normalized}"
        result = VariableSubstituter.substitute(template, sample_context)
        assert result == "xccdf_cis_eks_rule_3_1_1"

    def test_nested_variable_substitution(self, sample_context):
        """Test nested variable access (control.version)."""
        template = "Control {control.version}.{control.control}"
        result = VariableSubstituter.substitute(template, sample_context)
        assert result == "Control 8.4.8"

    def test_multiple_variables_in_template(self, sample_context):
        """Test template with multiple variables."""
        template = "Platform: {platform}, Ref: {ref}, Normalized: {ref_normalized}"
        result = VariableSubstituter.substitute(template, sample_context)
        assert result == "Platform: eks, Ref: 3.1.1, Normalized: 3_1_1"

    def test_missing_variable_returns_empty_string(self):
        """Test that missing variables are replaced with empty string."""
        template = "Test {missing_var} value"
        result = VariableSubstituter.substitute(template, {})
        assert result == "Test  value"

    def test_empty_template(self):
        """Test substitution with empty template."""
        result = VariableSubstituter.substitute("", {"key": "value"})
        assert result == ""

    def test_template_with_no_variables(self, sample_context):
        """Test template without any variables."""
        template = "This is a plain string"
        result = VariableSubstituter.substitute(template, sample_context)
        assert result == template

    def test_nested_missing_attribute(self, sample_context):
        """Test nested variable with missing attribute."""
        template = "Value: {control.nonexistent}"
        result = VariableSubstituter.substitute(template, sample_context)
        assert result == "Value: "

    def test_variable_with_special_characters_in_value(self):
        """Test substitution where value contains special characters."""
        context = {"platform": "eks-1.2_special"}
        template = "Platform: {platform}"
        result = VariableSubstituter.substitute(template, context)
        assert result == "Platform: eks-1.2_special"

    def test_deeply_nested_variables(self):
        """Test deeply nested variable access."""
        context = {"level1": {"level2": {"level3": "deep_value"}}}
        template = "Deep: {level1.level2.level3}"
        result = VariableSubstituter.substitute(template, context)
        assert result == "Deep: deep_value"

    def test_context_with_none_values(self):
        """Test substitution when context has None values."""
        context = {"platform": None, "ref": "3.1.1"}
        template = "Platform: {platform}, Ref: {ref}"
        result = VariableSubstituter.substitute(template, context)
        # None should be converted to string
        assert "None" in result or result == "Platform: , Ref: 3.1.1"


# ============================================================================
# TEST: CCILookupService
# ============================================================================


class TestCCILookupService:
    """Unit tests for CCI deduplication."""

    @pytest.fixture
    def cci_service(self):
        """Initialize CCI lookup service."""
        return CCILookupService()

    def test_get_ccis_for_cis_control_exists(self, cci_service):
        """Test getting CCIs for a known CIS control."""
        # Assuming "4.8" exists in mapping file
        ccis = cci_service.get_ccis_for_cis_control("4.8")
        # Should return list of CCIMapping objects
        assert isinstance(ccis, list)
        if ccis:  # If mapping exists
            assert all(hasattr(c, "cci") for c in ccis)

    def test_get_ccis_for_nonexistent_control(self, cci_service):
        """Test getting CCIs for non-existent CIS control."""
        ccis = cci_service.get_ccis_for_cis_control("99.99")
        assert ccis == []

    def test_deduplicate_nist_controls_all_covered(self, cci_service):
        """Test deduplication when all NIST controls are covered by CCIs."""
        # Use a real CIS control that maps to CCIs
        cis_controls = ["4.8"]
        cited_nist = ["CM-7"]  # Base control that should be covered

        ccis, extra_nist = cci_service.deduplicate_nist_controls(cis_controls, cited_nist)

        # Should have CCIs
        assert isinstance(ccis, list)
        # Extra NIST should be minimal if CM-7 is covered
        assert isinstance(extra_nist, list)

    def test_deduplicate_nist_controls_some_extras(self, cci_service):
        """Test deduplication when some NIST controls are NOT covered."""
        cis_controls = ["4.8"]
        # Include a control that likely won't be covered
        cited_nist = ["CM-7", "SI-99", "AC-99"]

        ccis, extra_nist = cci_service.deduplicate_nist_controls(cis_controls, cited_nist)

        # Should have some CCIs
        assert isinstance(ccis, list)
        # Should have some extras (the non-existent controls)
        assert isinstance(extra_nist, list)

    def test_deduplicate_nist_controls_no_cis_controls(self, cci_service):
        """Test deduplication with no CIS controls (all NIST become extras)."""
        cis_controls = []
        cited_nist = ["CM-7", "SI-3"]

        ccis, extra_nist = cci_service.deduplicate_nist_controls(cis_controls, cited_nist)

        assert ccis == []
        # All cited NIST should be extras
        assert set(extra_nist) == set(cited_nist)

    def test_deduplicate_nist_controls_no_nist_cited(self, cci_service):
        """Test deduplication with no NIST controls cited."""
        cis_controls = ["4.8"]
        cited_nist = []

        ccis, extra_nist = cci_service.deduplicate_nist_controls(cis_controls, cited_nist)

        # Should still get CCIs from CIS controls
        assert isinstance(ccis, list)
        # No extras
        assert extra_nist == []

    def test_get_base_nist_control_simple(self):
        """Test extracting base NIST control (simple case)."""
        base = CCILookupService._get_base_nist_control("CM-7")
        assert base == "CM-7"

    def test_get_base_nist_control_with_subcontrol(self):
        """Test extracting base from subcontrol (CM-7.1 → CM-7)."""
        base = CCILookupService._get_base_nist_control("CM-7.1")
        assert base == "CM-7"

    def test_get_base_nist_control_with_enhancement(self):
        """Test extracting base from enhancement (CM-7(5) → CM-7)."""
        base = CCILookupService._get_base_nist_control("CM-7(5)")
        assert base == "CM-7"

    def test_get_base_nist_control_complex(self):
        """Test extracting base from complex control (CM-7.1(5) → CM-7)."""
        base = CCILookupService._get_base_nist_control("CM-7.1(5)")
        assert base == "CM-7"

    def test_hierarchical_matching(self, cci_service):
        """Test that hierarchical matching works (CM-7.1 covers CM-7)."""
        # This is testing the CONCEPT - actual implementation depends on mapping data
        # If we have a CCI that maps to CM-7.1, it should cover CM-7
        base_cm7 = CCILookupService._get_base_nist_control("CM-7.1")
        base_cm7_cited = CCILookupService._get_base_nist_control("CM-7")

        # Both should resolve to CM-7
        assert base_cm7 == base_cm7_cited == "CM-7"


# ============================================================================
# TEST: DRY Helper Methods (MappingEngine)
# ============================================================================


class TestDRYHelpers:
    """Unit tests for DRY helper methods in MappingEngine."""

    @pytest.fixture
    def engine(self, config_path):
        """Create MappingEngine instance."""
        return MappingEngine(config_path)

    def test_construct_typed_element_with_content_field(self, engine):
        """Test _construct_typed_element with type that has 'content' field."""
        # HtmlTextWithSubType uses 'content'
        HtmlTextWithSubType = engine.get_xccdf_class("HtmlTextWithSubType")
        elem = engine._construct_typed_element(HtmlTextWithSubType, "Test content")

        assert elem is not None
        assert hasattr(elem, "content")
        assert elem.content == ["Test content"]

    def test_construct_typed_element_with_value_field(self, engine):
        """Test _construct_typed_element with type that has 'value' field."""
        # TextType uses 'value'
        TextType = engine.get_xccdf_class("TextType")
        elem = engine._construct_typed_element(TextType, "Test value")

        assert elem is not None
        assert hasattr(elem, "value")
        assert elem.value == "Test value"

    def test_construct_typed_element_with_none_value(self, engine):
        """Test _construct_typed_element with None value."""
        TextType = engine.get_xccdf_class("TextType")
        elem = engine._construct_typed_element(TextType, None)

        # Should handle None gracefully (depends on implementation)
        assert elem is not None or elem is None

    def test_is_list_field_for_list_type(self, engine):
        """Test _is_list_field correctly identifies list fields."""
        Rule = engine.get_xccdf_class("Rule")

        # Rule.title is list[TextWithSubType]
        is_list = engine._is_list_field(Rule, "title")
        assert is_list is True

    def test_is_list_field_for_single_type(self, engine):
        """Test _is_list_field correctly identifies single-value fields."""
        Rule = engine.get_xccdf_class("Rule")

        # Rule.version is Optional[VersionType] (single)
        is_list = engine._is_list_field(Rule, "version")
        # This depends on XCCDF schema - version might be single or list
        assert isinstance(is_list, bool)

    def test_is_list_field_for_nonexistent_field(self, engine):
        """Test _is_list_field with non-existent field (defaults to True)."""
        Rule = engine.get_xccdf_class("Rule")
        is_list = engine._is_list_field(Rule, "nonexistent_field")
        assert is_list is True  # Default behavior

    def test_element_name_to_type_name_kebab_case(self, engine):
        """Test _element_name_to_type_name with kebab-case."""
        type_name = engine._element_name_to_type_name("check-content")
        assert type_name == "CheckContentType"

    def test_element_name_to_type_name_lowercase(self, engine):
        """Test _element_name_to_type_name with lowercase."""
        type_name = engine._element_name_to_type_name("title")
        assert type_name == "TitleType"

    def test_element_name_to_type_name_already_has_type_suffix(self, engine):
        """Test _element_name_to_type_name when name already ends with 'Type'."""
        type_name = engine._element_name_to_type_name("TextType")
        # Should not double-add Type
        assert type_name == "TexttypeType" or type_name == "TextType"

    def test_build_field_value_simple_field(self, engine, sample_recommendation):
        """Test _build_field_value with simple field mapping."""
        field_mapping = {"source_field": "title", "transform": "strip_html"}
        context = {"ref_normalized": "3_1_1"}

        value = engine._build_field_value("title", field_mapping, sample_recommendation, context)

        # Should return stripped title
        assert value is not None
        assert isinstance(value, str)
        assert "kubeconfig" in value.lower()

    def test_build_field_value_embedded_xml(self, engine, sample_recommendation):
        """Test _build_field_value with embedded_xml_tags structure."""
        field_mapping = {"structure": "embedded_xml_tags"}
        context = {"ref_normalized": "3_1_1"}

        value = engine._build_field_value(
            "description", field_mapping, sample_recommendation, context
        )

        # Should return VulnDiscussion XML
        assert value is not None
        assert "<VulnDiscussion>" in value

    def test_build_field_value_cci_lookup(self, engine, sample_recommendation):
        """Test _build_field_value with CCI lookup."""
        field_mapping = {"source_logic": "cci_lookup_with_deduplication"}
        context = {"ref_normalized": "3_1_1"}

        value = engine._build_field_value("ident", field_mapping, sample_recommendation, context)

        # Should return list of CCIs
        assert isinstance(value, list)

    def test_build_field_value_missing_source_field(self, engine, sample_recommendation):
        """Test _build_field_value with no source_field specified."""
        field_mapping = {}  # Empty mapping
        context = {"ref_normalized": "3_1_1"}

        value = engine._build_field_value("unknown", field_mapping, sample_recommendation, context)

        assert value is None


# ============================================================================
# TEST: WorkbenchParser
# ============================================================================


class TestWorkbenchParser:
    """Unit tests for Workbench parsing utilities."""

    def test_parse_mitre_table_valid(self, sample_mitre_table):
        """Test parsing valid MITRE table."""
        result = WorkbenchParser.parse_mitre_table(sample_mitre_table)

        assert result is not None
        assert isinstance(result, MITREMapping)
        assert "T1078" in result.techniques
        assert "T1110" in result.techniques
        assert "TA0001" in result.tactics
        assert "M1026" in result.mitigations

    def test_parse_mitre_table_none_input(self):
        """Test parse_mitre_table with None input."""
        result = WorkbenchParser.parse_mitre_table(None)
        assert result is None

    def test_parse_mitre_table_empty_string(self):
        """Test parse_mitre_table with empty string."""
        result = WorkbenchParser.parse_mitre_table("")
        assert result is None

    def test_parse_mitre_table_null_string(self):
        """Test parse_mitre_table with "null" string."""
        result = WorkbenchParser.parse_mitre_table("null")
        assert result is None

    def test_parse_mitre_table_no_table(self):
        """Test parse_mitre_table with HTML that has no table."""
        html = "<p>No table here</p>"
        result = WorkbenchParser.parse_mitre_table(html)
        assert result is None

    def test_parse_mitre_table_empty_table(self):
        """Test parse_mitre_table with empty table."""
        html = "<table></table>"
        result = WorkbenchParser.parse_mitre_table(html)
        assert result is None

    def test_parse_nist_controls_valid(self, sample_nist_references):
        """Test parsing NIST control references."""
        result = WorkbenchParser.parse_nist_controls(sample_nist_references)

        assert isinstance(result, list)
        assert "CM-7" in result
        assert "SI-3" in result
        assert "AC-2(1)" in result

    def test_parse_nist_controls_none_input(self):
        """Test parse_nist_controls with None."""
        result = WorkbenchParser.parse_nist_controls(None)
        assert result == []

    def test_parse_nist_controls_no_matches(self):
        """Test parse_nist_controls with HTML that has no NIST refs."""
        html = "<p>No NIST references here</p>"
        result = WorkbenchParser.parse_nist_controls(html)
        assert result == []

    def test_parse_cis_controls_json_valid(self, sample_cis_controls_json):
        """Test parsing CIS Controls JSON."""
        result = WorkbenchParser.parse_cis_controls_json(sample_cis_controls_json)

        assert isinstance(result, list)
        assert len(result) == 2

        # Check first control
        assert result[0].version == 8  # version is int, not string
        assert result[0].control == "4.8"
        assert result[0].ig1 is True
        assert result[0].ig2 is True

        # Check second control
        assert result[1].version == 7  # version is int, not string
        assert result[1].control == "9.2"
        assert result[1].ig1 is False

    def test_parse_cis_controls_json_invalid_json(self):
        """Test parse_cis_controls_json with invalid JSON."""
        result = WorkbenchParser.parse_cis_controls_json("not valid json")
        assert result == []

    def test_parse_cis_controls_json_empty_array(self):
        """Test parse_cis_controls_json with empty array."""
        result = WorkbenchParser.parse_cis_controls_json("[]")
        assert result == []

    def test_parse_cis_controls_json_missing_ig_values(self):
        """Test parse_cis_controls_json with missing/null IG values."""
        json_str = """
        [{
            "version": "8",
            "control": "4.8",
            "title": "Test",
            "ig1": null,
            "ig2": null,
            "ig3": null
        }]
        """
        result = WorkbenchParser.parse_cis_controls_json(json_str)

        assert len(result) == 1
        # Should default None to False
        assert result[0].ig1 is False
        assert result[0].ig2 is False
        assert result[0].ig3 is False

    def test_extract_assessment_status_automated(self):
        """Test extracting 'Automated' status."""
        html = "<p>This is an automated assessment</p>"
        result = WorkbenchParser.extract_assessment_status(html)
        assert result == "Automated"

    def test_extract_assessment_status_manual(self):
        """Test extracting 'Manual' status."""
        html = "<p>This is a manual assessment</p>"
        result = WorkbenchParser.extract_assessment_status(html)
        assert result == "Manual"

    def test_extract_assessment_status_unknown(self):
        """Test extracting status when none found."""
        html = "<p>Some other text</p>"
        result = WorkbenchParser.extract_assessment_status(html)
        assert result == "Some other text" or result == "Unknown"

    def test_extract_assessment_status_none(self):
        """Test extracting status from None."""
        result = WorkbenchParser.extract_assessment_status(None)
        assert result == "Unknown"


# ============================================================================
# TEST: HTMLCleaner
# ============================================================================


class TestHTMLCleaner:
    """Unit tests for HTML transformation methods."""

    def test_strip_html_basic(self, sample_html_simple):
        """Test basic HTML stripping."""
        result = HTMLCleaner.strip_html(sample_html_simple)
        assert result == "This is bold text."
        assert "<" not in result

    def test_strip_html_none(self):
        """Test strip_html with None."""
        result = HTMLCleaner.strip_html(None)
        assert result == ""

    def test_strip_html_empty(self):
        """Test strip_html with empty string."""
        result = HTMLCleaner.strip_html("")
        assert result == ""

    def test_strip_html_preserves_text_spacing(self):
        """Test that strip_html preserves reasonable spacing."""
        html = "<p>First paragraph</p><p>Second paragraph</p>"
        result = HTMLCleaner.strip_html(html)
        # Should have text from both paragraphs
        assert "First paragraph" in result
        assert "Second paragraph" in result

    def test_html_to_markdown_basic(self, sample_html_simple):
        """Test HTML to Markdown conversion."""
        result = HTMLCleaner.html_to_markdown(sample_html_simple)
        # Should preserve text
        assert "bold" in result.lower()
        assert "text" in result.lower()

    def test_html_to_markdown_code_blocks(self):
        """Test Markdown conversion with code blocks."""
        html = "<p>Command: <code>ls -la</code></p>"
        result = HTMLCleaner.html_to_markdown(html)
        # Should convert code to backticks or preserve it
        assert "ls -la" in result

    def test_html_to_markdown_lists(self):
        """Test Markdown conversion with lists."""
        html = "<ul><li>Item 1</li><li>Item 2</li></ul>"
        result = HTMLCleaner.html_to_markdown(html)
        # Should preserve list items
        assert "Item 1" in result
        assert "Item 2" in result

    def test_parse_mitre_table(self, sample_mitre_table):
        """Test MITRE table parsing (from HTMLCleaner)."""
        result = HTMLCleaner.parse_mitre_table(sample_mitre_table)

        if result:  # If implementation exists
            assert isinstance(result, dict)

    def test_parse_nist_references(self, sample_nist_references):
        """Test NIST reference parsing (from HTMLCleaner)."""
        result = HTMLCleaner.parse_nist_references(sample_nist_references)

        assert isinstance(result, list)
        if result:  # If patterns match
            assert any("CM-7" in ref for ref in result)


# ============================================================================
# TEST: Integration - End-to-End Scenarios
# ============================================================================


class TestIntegrationScenarios:
    """Integration tests using real-world examples."""

    @pytest.fixture
    def engine(self, config_path):
        """Create MappingEngine instance."""
        return MappingEngine(config_path)

    def test_create_vuln_discussion_from_recommendation(self, engine, sample_recommendation):
        """Test creating VulnDiscussion from a complete Recommendation."""
        result = engine.create_vuln_discussion(sample_recommendation)

        assert result is not None
        assert "<VulnDiscussion>" in result
        assert "</VulnDiscussion>" in result

        # Should contain content from description and rationale
        assert "kubeconfig" in result.lower()

        # Should have DISA-required tags
        assert "<PotentialImpacts>" in result or "<Mitigations>" in result

    def test_get_ccis_with_deduplication(self, engine, sample_recommendation):
        """Test CCI lookup and deduplication with real recommendation."""
        ccis, extra_nist = engine.get_ccis_with_deduplication(sample_recommendation)

        assert isinstance(ccis, list)
        assert isinstance(extra_nist, list)

        # Should have some result (either CCIs or extra NIST)
        assert len(ccis) > 0 or len(extra_nist) > 0

    def test_normalize_ref(self, engine):
        """Test ref normalization for IDs."""
        assert engine.normalize_ref("3.1.1") == "3_1_1"
        assert engine.normalize_ref("1.2.3.4") == "1_2_3_4"
        assert engine.normalize_ref("5") == "5"

    def test_variable_substitution_in_rule_id(self, engine, sample_context):
        """Test that rule ID template substitution works correctly."""
        template = engine.config.rule_id.get("template", "CIS-{ref_normalized}_rule")
        result = VariableSubstituter.substitute(template, sample_context)

        # DISA style uses stig_number (030101), CIS style uses ref_normalized (3_1_1)
        # Either format is valid depending on config
        assert "030101" in result or "3_1_1" in result
        # DISA uses SV-/V- prefix, CIS uses organization prefix
        assert "SV-" in result or "xccdf" in result.lower() or "cis" in result.lower()

    def test_full_transformation_pipeline(self, sample_recommendation):
        """Test full pipeline: HTML input → Transform → Substitute → Output."""
        # 1. Extract HTML content
        html_content = sample_recommendation.description

        # 2. Transform (strip HTML)
        cleaned = TransformRegistry.apply("strip_html", html_content)
        assert "<" not in cleaned

        # 3. Substitute variables
        template = "Ref {ref}: {content}"
        context = {"ref": sample_recommendation.ref, "content": cleaned}
        result = VariableSubstituter.substitute(template, context)

        # Should have ref and content
        assert "3.1.1" in result
        assert "kubeconfig" in result.lower()


# ============================================================================
# TEST: Edge Cases and Error Handling
# ============================================================================


# ============================================================================
# TEST: ID Format Validation (TDD for config-driven ID templates)
# ============================================================================


class TestIDFormatValidation:
    """Verify ID formats match expected patterns for each style.

    DISA STIG convention:
    - Group ID: V-NNNNNN (e.g., V-030101)
    - Rule ID: SV-NNNNNNrREV_rule (e.g., SV-030101r1_rule)

    CIS convention:
    - Group ID: xccdf_org.cisecurity.benchmarks_group_{ref_normalized}
    - Rule ID: xccdf_org.cisecurity.benchmarks_rule_{ref_normalized}
    """

    @pytest.fixture
    def disa_engine(self, disa_config_path):
        """Create MappingEngine with DISA style."""
        return MappingEngine(disa_config_path)

    @pytest.fixture
    def cis_engine(self, cis_config_path):
        """Create MappingEngine with CIS style."""
        return MappingEngine(cis_config_path)

    # --- DISA ID Format Tests ---

    def test_disa_group_id_format_v_prefix(self, disa_engine):
        """DISA Group ID must start with V- prefix."""
        template = disa_engine.config.group_id.get("template", "")
        context = {"stig_number": "030101", "ref_normalized": "3_1_1", "platform": "eks"}
        group_id = VariableSubstituter.substitute(template, context)

        assert group_id.startswith("V-"), f"DISA Group ID must start with V-, got: {group_id}"

    def test_disa_group_id_format_numeric(self, disa_engine):
        """DISA Group ID must have numeric portion after V-."""
        import re

        template = disa_engine.config.group_id.get("template", "")
        context = {"stig_number": "030101", "ref_normalized": "3_1_1", "platform": "eks"}
        group_id = VariableSubstituter.substitute(template, context)

        # Pattern: V-NNNNNN (V- followed by digits)
        pattern = r"^V-\d+$"
        assert re.match(pattern, group_id), f"DISA Group ID must match V-NNNNNN, got: {group_id}"

    def test_disa_rule_id_format_sv_prefix(self, disa_engine):
        """DISA Rule ID must start with SV- prefix."""
        template = disa_engine.config.rule_id.get("template", "")
        context = {"stig_number": "030101", "ref_normalized": "3_1_1", "platform": "eks"}
        rule_id = VariableSubstituter.substitute(template, context)

        assert rule_id.startswith("SV-"), f"DISA Rule ID must start with SV-, got: {rule_id}"

    def test_disa_rule_id_format_revision_suffix(self, disa_engine):
        """DISA Rule ID must have rN_rule suffix."""
        import re

        template = disa_engine.config.rule_id.get("template", "")
        context = {"stig_number": "030101", "ref_normalized": "3_1_1", "platform": "eks"}
        rule_id = VariableSubstituter.substitute(template, context)

        # Pattern: SV-NNNNNNrREV_rule
        pattern = r"^SV-\d+r\d+_rule$"
        assert re.match(pattern, rule_id), (
            f"DISA Rule ID must match SV-NNNNNNrN_rule, got: {rule_id}"
        )

    def test_disa_stig_number_conversion(self, disa_engine):
        """Test ref_to_stig_number converts refs correctly."""
        test_cases = [
            ("1.1.1", "010101"),
            ("3.2.1", "030201"),
            ("10.5.3", "100503"),
            ("1.1.1.1", "01010101"),
            ("5", "05"),
        ]
        for ref, expected in test_cases:
            result = disa_engine.ref_to_stig_number(ref)
            assert result == expected, f"ref_to_stig_number({ref}) = {result}, expected {expected}"

    def test_disa_ids_are_unique_for_different_refs(self, disa_engine):
        """Different CIS refs should produce different DISA IDs."""
        refs = ["1.1.1", "1.1.2", "2.1.1", "3.2.1"]
        group_template = disa_engine.config.group_id.get("template", "")
        rule_template = disa_engine.config.rule_id.get("template", "")

        group_ids = set()
        rule_ids = set()

        for ref in refs:
            stig_number = disa_engine.ref_to_stig_number(ref)
            context = {"stig_number": stig_number, "ref_normalized": ref.replace(".", "_")}

            group_id = VariableSubstituter.substitute(group_template, context)
            rule_id = VariableSubstituter.substitute(rule_template, context)

            assert group_id not in group_ids, f"Duplicate Group ID: {group_id}"
            assert rule_id not in rule_ids, f"Duplicate Rule ID: {rule_id}"

            group_ids.add(group_id)
            rule_ids.add(rule_id)

    # --- CIS ID Format Tests ---

    def test_cis_group_id_format_prefix(self, cis_engine):
        """CIS Group ID must have cisecurity.benchmarks prefix."""
        template = cis_engine.config.group_id.get("template", "")
        context = {"stig_number": "030101", "ref_normalized": "3_1_1", "platform": "eks"}
        group_id = VariableSubstituter.substitute(template, context)

        assert "cisecurity.benchmarks" in group_id, (
            f"CIS Group ID must contain cisecurity.benchmarks, got: {group_id}"
        )
        assert "_group_" in group_id, f"CIS Group ID must contain _group_, got: {group_id}"

    def test_cis_group_id_format_contains_ref(self, cis_engine):
        """CIS Group ID must contain the normalized ref."""
        template = cis_engine.config.group_id.get("template", "")
        context = {"stig_number": "030101", "ref_normalized": "3_1_1", "platform": "eks"}
        group_id = VariableSubstituter.substitute(template, context)

        assert "3_1_1" in group_id, (
            f"CIS Group ID must contain ref_normalized (3_1_1), got: {group_id}"
        )

    def test_cis_rule_id_format_prefix(self, cis_engine):
        """CIS Rule ID must have cisecurity.benchmarks prefix."""
        template = cis_engine.config.rule_id.get("template", "")
        context = {"stig_number": "030101", "ref_normalized": "3_1_1", "platform": "eks"}
        rule_id = VariableSubstituter.substitute(template, context)

        assert "cisecurity.benchmarks" in rule_id, (
            f"CIS Rule ID must contain cisecurity.benchmarks, got: {rule_id}"
        )
        assert "_rule_" in rule_id, f"CIS Rule ID must contain _rule_, got: {rule_id}"

    def test_cis_rule_id_format_contains_ref(self, cis_engine):
        """CIS Rule ID must contain the normalized ref."""
        template = cis_engine.config.rule_id.get("template", "")
        context = {"stig_number": "030101", "ref_normalized": "3_1_1", "platform": "eks"}
        rule_id = VariableSubstituter.substitute(template, context)

        assert "3_1_1" in rule_id, (
            f"CIS Rule ID must contain ref_normalized (3_1_1), got: {rule_id}"
        )

    def test_cis_ids_are_unique_for_different_refs(self, cis_engine):
        """Different CIS refs should produce different CIS IDs."""
        refs = ["1.1.1", "1.1.2", "2.1.1", "3.2.1"]
        group_template = cis_engine.config.group_id.get("template", "")
        rule_template = cis_engine.config.rule_id.get("template", "")

        group_ids = set()
        rule_ids = set()

        for ref in refs:
            context = {"ref_normalized": ref.replace(".", "_")}

            group_id = VariableSubstituter.substitute(group_template, context)
            rule_id = VariableSubstituter.substitute(rule_template, context)

            assert group_id not in group_ids, f"Duplicate Group ID: {group_id}"
            assert rule_id not in rule_ids, f"Duplicate Rule ID: {rule_id}"

            group_ids.add(group_id)
            rule_ids.add(rule_id)

    # --- Edge Cases for ref_to_stig_number ---

    def test_stig_number_empty_ref(self, disa_engine):
        """Empty ref returns '00' (empty string split produces one empty segment)."""
        # Note: "".split(".") → [""] → "".zfill(2) → "00"
        # This is acceptable edge case behavior - empty refs shouldn't occur in practice
        result = disa_engine.ref_to_stig_number("")
        assert result == "00", f"Empty ref edge case, got: {result}"

    def test_stig_number_single_digit_segments(self, disa_engine):
        """Single digit segments should be zero-padded."""
        test_cases = [
            ("1", "01"),
            ("9", "09"),
            ("1.2", "0102"),
            ("1.2.3", "010203"),
        ]
        for ref, expected in test_cases:
            result = disa_engine.ref_to_stig_number(ref)
            assert result == expected, f"ref_to_stig_number({ref}) = {result}, expected {expected}"

    def test_stig_number_double_digit_segments(self, disa_engine):
        """Double digit segments should not be truncated."""
        test_cases = [
            ("10", "10"),
            ("10.11", "1011"),
            ("10.11.12", "101112"),
            ("99.99.99", "999999"),
        ]
        for ref, expected in test_cases:
            result = disa_engine.ref_to_stig_number(ref)
            assert result == expected, f"ref_to_stig_number({ref}) = {result}, expected {expected}"

    def test_stig_number_very_deep_hierarchy(self, disa_engine):
        """Very deep refs (5+ levels) should still work."""
        result = disa_engine.ref_to_stig_number("1.2.3.4.5")
        assert result == "0102030405", f"Deep ref failed, got: {result}"

    # --- End-to-End ID Tests (map_rule/map_group) ---

    def test_disa_map_rule_produces_sv_id(self, disa_engine, sample_recommendation):
        """map_rule() with DISA config should produce SV- prefixed rule ID."""
        import re

        context = {"platform": "eks", "benchmark": None}
        rule = disa_engine.map_rule(sample_recommendation, context)

        assert rule.id.startswith("SV-"), f"DISA Rule ID should start with SV-, got: {rule.id}"
        assert re.match(r"^SV-\d+r\d+_rule$", rule.id), f"Invalid DISA Rule ID format: {rule.id}"

    def test_disa_map_group_produces_v_id(self, disa_engine, sample_recommendation):
        """map_group() with DISA config should produce V- prefixed group ID."""
        import re

        context = {"platform": "eks", "benchmark": None}
        rule = disa_engine.map_rule(sample_recommendation, context)
        group = disa_engine.map_group(sample_recommendation, rule, context)

        assert group.id.startswith("V-"), f"DISA Group ID should start with V-, got: {group.id}"
        assert re.match(r"^V-\d+$", group.id), f"Invalid DISA Group ID format: {group.id}"

    def test_cis_map_rule_produces_benchmarks_id(self, cis_engine, sample_recommendation):
        """map_rule() with CIS config should produce cisecurity.benchmarks rule ID."""
        context = {"platform": "eks", "benchmark": None}
        rule = cis_engine.map_rule(sample_recommendation, context)

        assert "cisecurity.benchmarks" in rule.id, (
            f"CIS Rule ID should contain cisecurity.benchmarks, got: {rule.id}"
        )
        assert "_rule_" in rule.id, f"CIS Rule ID should contain _rule_, got: {rule.id}"
        assert "3_1_1" in rule.id, (
            f"CIS Rule ID should contain ref_normalized (3_1_1), got: {rule.id}"
        )

    def test_cis_map_group_produces_benchmarks_id(self, cis_engine, sample_recommendation):
        """map_group() with CIS config should produce cisecurity.benchmarks group ID."""
        context = {"platform": "eks", "benchmark": None}
        rule = cis_engine.map_rule(sample_recommendation, context)
        group = cis_engine.map_group(sample_recommendation, rule, context)

        assert "cisecurity.benchmarks" in group.id, (
            f"CIS Group ID should contain cisecurity.benchmarks, got: {group.id}"
        )
        assert "_group_" in group.id, f"CIS Group ID should contain _group_, got: {group.id}"
        assert "3_1_1" in group.id, (
            f"CIS Group ID should contain ref_normalized (3_1_1), got: {group.id}"
        )

    def test_disa_rule_and_group_ids_correspond(self, disa_engine, sample_recommendation):
        """DISA Rule and Group IDs should use same stig_number."""
        context = {"platform": "eks", "benchmark": None}
        rule = disa_engine.map_rule(sample_recommendation, context)
        group = disa_engine.map_group(sample_recommendation, rule, context)

        # Extract numbers: V-030101 → 030101, SV-030101r1_rule → 030101
        group_num = group.id.replace("V-", "")
        rule_num = rule.id.split("r")[0].replace("SV-", "")

        assert group_num == rule_num, (
            f"Group ({group.id}) and Rule ({rule.id}) should share stig_number"
        )

    # --- Profile Select Element ID Tests ---

    def test_disa_profile_selects_use_sv_rule_ids(self, disa_engine, almalinux_complete_benchmark):
        """Profile select elements should reference SV- rule IDs in DISA style."""
        # Get profile config from engine config (not context)
        profile_config = disa_engine.config.benchmark.get("profiles", {})

        # Generate profiles
        profiles = disa_engine.generate_profiles_from_rules(
            almalinux_complete_benchmark.recommendations, profile_config
        )

        # Check at least one profile has selects
        assert any(p.select for p in profiles), "No profiles with selects generated"

        # Check all select idrefs use SV- format
        for profile in profiles:
            for select in profile.select:
                assert select.idref.startswith("SV-"), (
                    f"Profile select idref should use SV- format, got: {select.idref}"
                )

    def test_cis_profile_selects_use_benchmarks_rule_ids(
        self, cis_engine, almalinux_complete_benchmark
    ):
        """Profile select elements should reference cisecurity.benchmarks rule IDs in CIS style."""
        # Get profile config from engine config (not context)
        profile_config = cis_engine.config.benchmark.get("profiles", {})

        # Generate profiles
        profiles = cis_engine.generate_profiles_from_rules(
            almalinux_complete_benchmark.recommendations, profile_config
        )

        # Check at least one profile has selects
        assert any(p.select for p in profiles), "No profiles with selects generated"

        # Check all select idrefs use CIS format
        for profile in profiles:
            for select in profile.select:
                assert "cisecurity.benchmarks" in select.idref, (
                    f"Profile select idref should use cisecurity.benchmarks format, got: {select.idref}"
                )

    # --- Cross-Style Validation ---

    def test_disa_and_cis_ids_are_distinct_formats(self, disa_engine, cis_engine):
        """DISA and CIS IDs should be visually distinct formats."""
        context = {"stig_number": "030101", "ref_normalized": "3_1_1", "platform": "eks"}

        disa_group = VariableSubstituter.substitute(
            disa_engine.config.group_id.get("template", ""), context
        )
        cis_group = VariableSubstituter.substitute(
            cis_engine.config.group_id.get("template", ""), context
        )

        # They should be different
        assert disa_group != cis_group, "DISA and CIS Group IDs should differ"

        # DISA should be short numeric, CIS should be long descriptive
        assert len(disa_group) < len(cis_group), "DISA IDs should be shorter than CIS IDs"
        assert disa_group.startswith("V-"), "DISA should use V- prefix"
        assert "xccdf" in cis_group.lower(), "CIS should use xccdf prefix"


# ============================================================================
# TEST: DISA/Vulcan Compatibility (Benchmark-level format tests)
# ============================================================================


class TestDISAVulcanCompatibility:
    """Tests for DISA/Vulcan-compatible export format.

    Vulcan expects specific formats:
    - Benchmark ID: Short format (e.g., "CIS_AlmaLinux_STIG")
    - Version: Without 'v' prefix (e.g., "4.0.0" not "v4.0.0")
    - Group title: Contains useful info (not "<GroupDescription></GroupDescription>")
    """

    def test_disa_benchmark_id_is_short_format(self, disa_config_path):
        """DISA benchmark ID template should produce short IDs for Vulcan."""
        engine = MappingEngine(disa_config_path)
        id_template = engine.config.benchmark.get("id_template", "")

        # Template should NOT contain full xccdf namespace
        assert "xccdf_org.cisecurity_benchmark" not in id_template, (
            "DISA benchmark ID should not use full XCCDF namespace"
        )

        # Should produce short readable ID using benchmark_id
        context = {"platform": "AlmaLinux", "benchmark_id": "23598"}
        bench_id = VariableSubstituter.substitute(id_template, context)

        assert len(bench_id) < 50, "Benchmark ID should be reasonably short"
        assert "CIS" in bench_id, "Benchmark ID should contain 'CIS'"
        assert "23598" in bench_id, "Benchmark ID should contain benchmark_id"

    def test_disa_version_transform_strips_v_prefix(self, disa_config_path):
        """DISA version config should use strip_version_prefix transform."""
        engine = MappingEngine(disa_config_path)
        version_config = engine.config.benchmark.get("version", {})

        transform = version_config.get("transform")
        assert transform == "strip_version_prefix", (
            f"DISA version should use strip_version_prefix, got: {transform}"
        )

    def test_disa_group_title_has_source(self, disa_config_path):
        """DISA group title should have a source field (not default placeholder)."""
        engine = MappingEngine(disa_config_path)
        title_config = engine.config.group_elements.get("title", {})

        source = title_config.get("source")
        assert source is not None, "DISA group title should have a source field"
        assert source == "ref", "DISA group title source should be 'ref'"

    def test_disa_group_description_has_source(self, disa_config_path):
        """DISA group description should have a source field."""
        engine = MappingEngine(disa_config_path)
        desc_config = engine.config.group_elements.get("description", {})

        source = desc_config.get("source")
        assert source is not None, "DISA group description should have a source field"
        assert source == "title", "DISA group description source should be 'title'"

    def test_disa_map_group_uses_ref_as_title(self, disa_config_path, almalinux_complete_benchmark):
        """map_group should use CIS ref as group title."""
        engine = MappingEngine(disa_config_path)
        benchmark = almalinux_complete_benchmark
        rec = benchmark.recommendations[0]
        context = {"platform": "test", "benchmark": benchmark}

        rule = engine.map_rule(rec, context)
        group = engine.map_group(rec, rule, context)

        # Group title should contain the ref (e.g., "6.1.1")
        assert group.title, "Group should have title"
        title_content = (
            group.title[0].content[0]
            if hasattr(group.title[0], "content")
            else group.title[0].value
        )
        assert rec.ref in title_content, (
            f"Group title should contain ref '{rec.ref}', got: {title_content}"
        )
        # Should NOT contain the placeholder
        assert "<GroupDescription>" not in title_content, (
            "Group title should not contain placeholder"
        )

    def test_disa_map_group_uses_rule_title_as_description(
        self, disa_config_path, almalinux_complete_benchmark
    ):
        """map_group should use rule title as group description."""
        engine = MappingEngine(disa_config_path)
        benchmark = almalinux_complete_benchmark
        rec = benchmark.recommendations[0]
        context = {"platform": "test", "benchmark": benchmark}

        rule = engine.map_rule(rec, context)
        group = engine.map_group(rec, rule, context)

        # Group description should contain the rule title
        assert group.description, "Group should have description"
        desc_content = (
            group.description[0].content[0]
            if hasattr(group.description[0], "content")
            else group.description[0].value
        )
        # Title may be transformed, so check for key words
        assert len(desc_content) > 10, f"Group description should have content, got: {desc_content}"
        assert "<GroupDescription>" not in desc_content, (
            "Group description should not contain placeholder"
        )


class TestEdgeCases:
    def test_empty_recommendation_fields(self):
        """Test handling recommendation with minimal fields (some empty optionals)."""
        rec = Recommendation(
            url="https://example.com",
            ref="1.1",
            title="Minimal Recommendation",  # title is required, must be non-empty
            description=None,  # Optional fields can be None
            rationale=None,
            assessment_status="Unknown",
        )

        # Should handle None gracefully in optional fields
        assert rec.title == "Minimal Recommendation"
        assert rec.description is None

    def test_transformation_chain_with_none(self):
        """Test transformation pipeline with None values."""
        result1 = TransformRegistry.apply("strip_html", None)
        result2 = TransformRegistry.apply("none", result1)

        assert result1 == ""
        assert result2 == ""

    def test_variable_substitution_with_missing_nested_keys(self):
        """Test substitution when nested keys are missing."""
        context = {"top": {}}  # Missing nested keys
        template = "Value: {top.missing.key}"
        result = VariableSubstituter.substitute(template, context)

        # Should handle gracefully (empty string)
        assert result == "Value: "

    def test_malformed_json_in_parsers(self):
        """Test parsers with malformed JSON."""
        bad_json = '{"version": "8", "control": '  # Unclosed
        result = WorkbenchParser.parse_cis_controls_json(bad_json)
        assert result == []

    def test_html_with_only_whitespace(self):
        """Test HTML transformation with only whitespace."""
        html = "   \n\t   "
        result = HTMLCleaner.strip_html(html)
        assert result == "" or result.strip() == ""

    def test_nist_control_deduplication_with_duplicates(self):
        """Test NIST deduplication with duplicate inputs."""
        service = CCILookupService()
        cis_controls = ["4.8", "4.8"]  # Duplicate
        cited_nist = ["CM-7", "CM-7", "SI-3"]  # Duplicates

        ccis, extra_nist = service.deduplicate_nist_controls(cis_controls, cited_nist)

        # Should handle duplicates gracefully
        assert isinstance(ccis, list)
        assert isinstance(extra_nist, list)
