"""Tests for field transformation utilities.

Tests for RecommendationFieldTransformer, SafeFieldAccessor, and CISControlFormatter.
"""

import pytest

from cis_bench.models.benchmark import (
    CISControl,
    MITREMapping,
    ParentReference,
    Recommendation,
)


@pytest.fixture
def sample_recommendation():
    """Create a sample recommendation for testing."""
    return Recommendation(
        ref="1.1.1",
        title="Test Recommendation",
        url="https://example.com/rec/1",
        assessment_status="Automated",
        profiles=["Level 1", "Level 2"],
        description="<p>Test description</p>",
        rationale="<b>Important</b> rationale",
        impact="No impact",
        audit="Run audit command",
        remediation="Apply fix",
        additional_info="Extra info",
        default_value="Default",
        cis_controls=[
            CISControl(version=8, control="4.1", title="Control 4.1", ig1=True, ig2=True, ig3=True),
            CISControl(
                version=8, control="4.8", title="Control 4.8", ig1=False, ig2=True, ig3=True
            ),
            CISControl(
                version=7, control="9.2", title="Control 9.2", ig1=True, ig2=False, ig3=False
            ),
        ],
        mitre_mapping=MITREMapping(
            techniques=["T1565.001", "T1485"],
            tactics=["TA0040"],
            mitigations=["M1022"],
        ),
        parent=ParentReference(
            title="Parent Section",
            url="https://example.com/parent",
        ),
    )


@pytest.fixture
def minimal_recommendation():
    """Create a minimal recommendation with mostly None fields."""
    return Recommendation(
        ref="1.1.2",
        title="Minimal",
        url="https://example.com/rec/2",
        assessment_status="Manual",
        profiles=[],
    )


class TestRecommendationFieldTransformer:
    """Tests for RecommendationFieldTransformer class."""

    def test_strip_all_html_converts_html(self, sample_recommendation):
        """strip_all_html should remove HTML tags from all fields."""
        from cis_bench.utils.field_transformers import RecommendationFieldTransformer

        fields = RecommendationFieldTransformer.strip_all_html(sample_recommendation)

        assert "Test description" in fields["description"]
        assert "<p>" not in fields["description"]
        assert "Important" in fields["rationale"]
        assert "<b>" not in fields["rationale"]

    def test_strip_all_html_handles_none_fields(self, minimal_recommendation):
        """strip_all_html should return empty strings for None fields."""
        from cis_bench.utils.field_transformers import RecommendationFieldTransformer

        fields = RecommendationFieldTransformer.strip_all_html(minimal_recommendation)

        assert fields["description"] == ""
        assert fields["rationale"] == ""
        assert fields["impact"] == ""

    def test_markdown_all_converts_html(self, sample_recommendation):
        """markdown_all should convert HTML to markdown."""
        from cis_bench.utils.field_transformers import RecommendationFieldTransformer

        fields = RecommendationFieldTransformer.markdown_all(sample_recommendation)

        # Bold HTML should become markdown bold
        assert "**Important**" in fields["rationale"] or "Important" in fields["rationale"]

    def test_markdown_all_handles_none_fields(self, minimal_recommendation):
        """markdown_all should return empty strings for None fields."""
        from cis_bench.utils.field_transformers import RecommendationFieldTransformer

        fields = RecommendationFieldTransformer.markdown_all(minimal_recommendation)

        assert fields["description"] == ""
        assert fields["rationale"] == ""

    def test_transform_field_strip_html(self, sample_recommendation):
        """transform_field should apply strip_html transformation."""
        from cis_bench.utils.field_transformers import RecommendationFieldTransformer

        result = RecommendationFieldTransformer.transform_field(
            sample_recommendation, "description", "strip_html"
        )

        assert "Test description" in result
        assert "<p>" not in result

    def test_transform_field_none_value(self, minimal_recommendation):
        """transform_field should return empty string for None field."""
        from cis_bench.utils.field_transformers import RecommendationFieldTransformer

        result = RecommendationFieldTransformer.transform_field(
            minimal_recommendation, "description", "strip_html"
        )

        assert result == ""

    def test_transform_field_nonexistent_field(self, sample_recommendation):
        """transform_field should return empty string for nonexistent field."""
        from cis_bench.utils.field_transformers import RecommendationFieldTransformer

        result = RecommendationFieldTransformer.transform_field(
            sample_recommendation, "nonexistent_field", "strip_html"
        )

        assert result == ""

    def test_content_fields_list(self):
        """CONTENT_FIELDS should contain expected field names."""
        from cis_bench.utils.field_transformers import RecommendationFieldTransformer

        fields = RecommendationFieldTransformer.CONTENT_FIELDS

        assert "description" in fields
        assert "rationale" in fields
        assert "audit" in fields
        assert "remediation" in fields


class TestSafeFieldAccessor:
    """Tests for SafeFieldAccessor class."""

    def test_get_text_returns_value(self, sample_recommendation):
        """get_text should return field value when present."""
        from cis_bench.utils.field_transformers import SafeFieldAccessor

        result = SafeFieldAccessor.get_text(sample_recommendation, "title")
        assert result == "Test Recommendation"

    def test_get_text_returns_default_for_none(self, minimal_recommendation):
        """get_text should return default for None field."""
        from cis_bench.utils.field_transformers import SafeFieldAccessor

        result = SafeFieldAccessor.get_text(minimal_recommendation, "description", "N/A")
        assert result == "N/A"

    def test_get_text_returns_default_for_none_description(self, minimal_recommendation):
        """get_text should return default for None description."""
        from cis_bench.utils.field_transformers import SafeFieldAccessor

        # minimal_recommendation has None for description
        result = SafeFieldAccessor.get_text(minimal_recommendation, "description", "N/A")
        assert result == "N/A"

    def test_get_list_as_csv_joins_items(self):
        """get_list_as_csv should join list items."""
        from cis_bench.utils.field_transformers import SafeFieldAccessor

        items = ["Level 1", "Level 2", "Level 3"]
        result = SafeFieldAccessor.get_list_as_csv(items)
        assert result == "Level 1, Level 2, Level 3"

    def test_get_list_as_csv_custom_separator(self):
        """get_list_as_csv should use custom separator."""
        from cis_bench.utils.field_transformers import SafeFieldAccessor

        items = ["a", "b", "c"]
        result = SafeFieldAccessor.get_list_as_csv(items, separator=" | ")
        assert result == "a | b | c"

    def test_get_list_as_csv_none(self):
        """get_list_as_csv should return empty string for None."""
        from cis_bench.utils.field_transformers import SafeFieldAccessor

        result = SafeFieldAccessor.get_list_as_csv(None)
        assert result == ""

    def test_get_list_as_csv_empty_list(self):
        """get_list_as_csv should return empty string for empty list."""
        from cis_bench.utils.field_transformers import SafeFieldAccessor

        result = SafeFieldAccessor.get_list_as_csv([])
        assert result == ""

    def test_get_mitre_field_techniques(self, sample_recommendation):
        """get_mitre_field should return techniques as CSV."""
        from cis_bench.utils.field_transformers import SafeFieldAccessor

        result = SafeFieldAccessor.get_mitre_field(sample_recommendation, "techniques")
        assert "T1565.001" in result
        assert "T1485" in result

    def test_get_mitre_field_no_mapping(self, minimal_recommendation):
        """get_mitre_field should return empty string when no MITRE mapping."""
        from cis_bench.utils.field_transformers import SafeFieldAccessor

        result = SafeFieldAccessor.get_mitre_field(minimal_recommendation, "techniques")
        assert result == ""

    def test_get_parent_title(self, sample_recommendation):
        """get_parent_title should return parent title."""
        from cis_bench.utils.field_transformers import SafeFieldAccessor

        result = SafeFieldAccessor.get_parent_title(sample_recommendation)
        assert result == "Parent Section"

    def test_get_parent_title_no_parent(self, minimal_recommendation):
        """get_parent_title should return empty string when no parent."""
        from cis_bench.utils.field_transformers import SafeFieldAccessor

        result = SafeFieldAccessor.get_parent_title(minimal_recommendation)
        assert result == ""

    def test_format_parent_link_markdown(self, sample_recommendation):
        """format_parent_link should create markdown link."""
        from cis_bench.utils.field_transformers import SafeFieldAccessor

        result = SafeFieldAccessor.format_parent_link(sample_recommendation, "markdown")
        assert result == "[Parent Section](https://example.com/parent)"

    def test_format_parent_link_html(self, sample_recommendation):
        """format_parent_link should create HTML link."""
        from cis_bench.utils.field_transformers import SafeFieldAccessor

        result = SafeFieldAccessor.format_parent_link(sample_recommendation, "html")
        assert result == '<a href="https://example.com/parent">Parent Section</a>'

    def test_format_parent_link_plain(self, sample_recommendation):
        """format_parent_link should return plain title."""
        from cis_bench.utils.field_transformers import SafeFieldAccessor

        result = SafeFieldAccessor.format_parent_link(sample_recommendation, "plain")
        assert result == "Parent Section"

    def test_format_parent_link_no_parent(self, minimal_recommendation):
        """format_parent_link should return empty string when no parent."""
        from cis_bench.utils.field_transformers import SafeFieldAccessor

        result = SafeFieldAccessor.format_parent_link(minimal_recommendation, "markdown")
        assert result == ""


class TestCISControlFormatter:
    """Tests for CISControlFormatter class."""

    def test_filter_by_version_v8(self, sample_recommendation):
        """filter_by_version should return v8 controls."""
        from cis_bench.utils.field_transformers import CISControlFormatter

        result = CISControlFormatter.filter_by_version(sample_recommendation.cis_controls, 8)
        assert "4.1" in result
        assert "4.8" in result
        assert "9.2" not in result

    def test_filter_by_version_v7(self, sample_recommendation):
        """filter_by_version should return v7 controls."""
        from cis_bench.utils.field_transformers import CISControlFormatter

        result = CISControlFormatter.filter_by_version(sample_recommendation.cis_controls, 7)
        assert "9.2" in result
        assert "4.1" not in result

    def test_filter_by_version_empty(self):
        """filter_by_version should return empty for nonexistent version."""
        from cis_bench.utils.field_transformers import CISControlFormatter

        controls = [
            CISControl(version=8, control="4.1", title="Test", ig1=True, ig2=True, ig3=True)
        ]
        result = CISControlFormatter.filter_by_version(controls, 7)
        assert result == ""

    def test_format_all_with_version(self, sample_recommendation):
        """format_all_with_version should include version prefix."""
        from cis_bench.utils.field_transformers import CISControlFormatter

        result = CISControlFormatter.format_all_with_version(sample_recommendation.cis_controls)
        assert "v8:4.1" in result
        assert "v8:4.8" in result
        assert "v7:9.2" in result

    def test_group_by_version(self, sample_recommendation):
        """group_by_version should group controls by version."""
        from cis_bench.utils.field_transformers import CISControlFormatter

        result = CISControlFormatter.group_by_version(sample_recommendation.cis_controls)

        assert 8 in result
        assert 7 in result
        assert "4.1" in result[8]
        assert "4.8" in result[8]
        assert "9.2" in result[7]

    def test_group_by_version_empty(self):
        """group_by_version should return empty dict for empty list."""
        from cis_bench.utils.field_transformers import CISControlFormatter

        result = CISControlFormatter.group_by_version([])
        assert result == {}

    def test_format_with_details_includes_igs(self, sample_recommendation):
        """format_with_details should include IG levels."""
        from cis_bench.utils.field_transformers import CISControlFormatter

        result = CISControlFormatter.format_with_details(
            sample_recommendation.cis_controls, include_igs=True
        )

        # First control has IG1, IG2, IG3
        assert any("IG1" in r and "IG2" in r and "IG3" in r for r in result)
        # Second control has IG2, IG3 only
        assert any("IG2" in r and "IG3" in r and "IG1" not in r for r in result)

    def test_format_with_details_no_igs(self, sample_recommendation):
        """format_with_details should exclude IGs when disabled."""
        from cis_bench.utils.field_transformers import CISControlFormatter

        result = CISControlFormatter.format_with_details(
            sample_recommendation.cis_controls, include_igs=False
        )

        # Should not contain IG strings
        for r in result:
            assert "IG1" not in r
            assert "IG2" not in r
            assert "IG3" not in r

    def test_format_with_details_includes_title(self, sample_recommendation):
        """format_with_details should include control title."""
        from cis_bench.utils.field_transformers import CISControlFormatter

        result = CISControlFormatter.format_with_details(sample_recommendation.cis_controls)

        assert any("Control 4.1" in r for r in result)
        assert any("Control 4.8" in r for r in result)
        assert any("Control 9.2" in r for r in result)

    def test_format_with_details_empty(self):
        """format_with_details should return empty list for empty input."""
        from cis_bench.utils.field_transformers import CISControlFormatter

        result = CISControlFormatter.format_with_details([])
        assert result == []

    def test_format_with_details_no_igs_set(self):
        """format_with_details should handle control with no IGs set."""
        from cis_bench.utils.field_transformers import CISControlFormatter

        controls = [
            CISControl(
                version=8, control="1.1", title="Test Control", ig1=False, ig2=False, ig3=False
            )
        ]

        result = CISControlFormatter.format_with_details(controls, include_igs=True)

        # Should not have IG parentheses since all IGs are False
        assert len(result) == 1
        # Should not contain (IG1, IG2, IG3) parenthetical
        assert "(" not in result[0]
