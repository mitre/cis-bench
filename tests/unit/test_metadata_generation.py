"""Unit tests for generic metadata_from_config handler (TDD)."""

from pathlib import Path

import pytest

from cis_bench.exporters.mapping_engine import MappingEngine
from cis_bench.models.benchmark import CISControl, MITREMapping, Recommendation


@pytest.fixture
def mapping_engine():
    """Create MappingEngine for testing."""
    config_path = Path("src/cis_bench/exporters/configs/styles/disa.yaml")
    return MappingEngine(config_path)


@pytest.fixture
def sample_recommendation():
    """Create sample recommendation with CIS Controls."""
    return Recommendation(
        ref="6.1.1",
        title="Test recommendation",
        description="Test description",
        url="https://example.org",
        assessment_status="Automated",
        cis_controls=[
            CISControl(
                version="8",
                control="3.14",
                title="Log Sensitive Data Access",
                ig1=False,
                ig2=False,
                ig3=True,
            ),
            CISControl(
                version="7",
                control="14.9",
                title="Enforce Detail Logging",
                ig1=False,
                ig2=False,
                ig3=True,
            ),
        ],
        mitre_mapping=MITREMapping(
            techniques=["T1565", "T1565.001"],
            tactics=["TA0001"],
            mitigations=["M1022"],
        ),
        profiles=["Level 1 - Server", "Level 1 - Workstation"],
    )


class TestMetadataGenerationSimple:
    """Test basic metadata generation without grouping."""

    def test_simple_single_child(self, mapping_engine, sample_recommendation):
        """Test metadata with single child element."""
        field_mapping = {
            "source_field": "title",
            "metadata_spec": {
                "root_element": "custom_metadata",
                "namespace": "http://example.org/metadata",
                "namespace_prefix": "custom",
                "children": [
                    {
                        "element": "recommendation_title",
                        "content": "{item}",  # item = title string
                    }
                ],
            },
        }

        result = mapping_engine.generate_metadata_from_config(sample_recommendation, field_mapping)

        # Should return metadata object
        assert result is not None
        # TODO: Verify structure once implemented

    def test_simple_multiple_children(self, mapping_engine, sample_recommendation):
        """Test metadata with multiple child elements."""
        field_mapping = {
            "source_field": "profiles",  # List of strings
            "metadata_spec": {
                "root_element": "profile_metadata",
                "namespace": "http://example.org/profiles",
                "namespace_prefix": "prof",
                "children": [
                    {
                        "element": "profile",
                        "for_each": True,  # Create one per item
                        "content": "{item}",
                    }
                ],
            },
        }

        result = mapping_engine.generate_metadata_from_config(sample_recommendation, field_mapping)

        assert result is not None
        # Should create one profile element per item in profiles list


class TestMetadataGenerationWithGrouping:
    """Test metadata generation with grouping (like CIS Controls)."""

    def test_group_by_version(self, mapping_engine, sample_recommendation):
        """Test grouping items by version field (CIS Controls pattern)."""
        field_mapping = {
            "source_field": "cis_controls",
            "metadata_spec": {
                "root_element": "cis_controls",
                "namespace": "http://cisecurity.org/controls",
                "namespace_prefix": "controls",
                "allow_empty": True,
                "group_by": "item.version",  # Group by version
                "group_element": {
                    "element": "framework",
                    "attributes": {"urn": "urn:cisecurity.org:controls:{group_key}"},
                    "item_element": {
                        "element": "safeguard",
                        "attributes": {
                            "title": "{item.title}",
                            "urn": "urn:cisecurity.org:controls:{item.version}:{item.control}",
                        },
                        "children": [
                            {
                                "element": "implementation_groups",
                                "attributes": {
                                    "ig1": "{item.ig1}",
                                    "ig2": "{item.ig2}",
                                    "ig3": "{item.ig3}",
                                },
                            },
                            {"element": "asset_type", "content": "Unknown"},
                            {"element": "security_function", "content": "Protect"},
                        ],
                    },
                },
            },
        }

        result = mapping_engine.generate_metadata_from_config(sample_recommendation, field_mapping)

        assert result is not None
        # Should have 2 framework elements (version 7 and 8)
        # Each framework should have 1 safeguard
        # Each safeguard should have 3 children

    def test_empty_metadata_when_no_data(self, mapping_engine):
        """Test that empty metadata element created when allow_empty=True."""
        rec_no_controls = Recommendation(
            ref="1.1.1",
            title="No controls",
            description="Test",
            url="https://example.org",
            assessment_status="Automated",
            cis_controls=[],  # Empty!
        )

        field_mapping = {
            "source_field": "cis_controls",
            "metadata_spec": {
                "root_element": "cis_controls",
                "namespace": "http://cisecurity.org/controls",
                "allow_empty": True,  # Should create empty element
            },
        }

        result = mapping_engine.generate_metadata_from_config(rec_no_controls, field_mapping)

        # Should return empty metadata element
        assert result is not None
        # Should be <controls:cis_controls/> (self-closing)

    def test_skip_metadata_when_no_data_and_not_allowed(self, mapping_engine):
        """Test that no metadata created when allow_empty=False."""
        rec_no_controls = Recommendation(
            ref="1.1.1",
            title="No controls",
            description="Test",
            url="https://example.org",
            assessment_status="Automated",
            cis_controls=[],
        )

        field_mapping = {
            "source_field": "cis_controls",
            "metadata_spec": {
                "root_element": "cis_controls",
                "namespace": "http://cisecurity.org/controls",
                "allow_empty": False,  # Don't create if empty
            },
        }

        result = mapping_engine.generate_metadata_from_config(rec_no_controls, field_mapping)

        # Should return None
        assert result is None


class TestMetadataAttributeTemplates:
    """Test attribute template substitution."""

    def test_static_attributes(self, mapping_engine, sample_recommendation):
        """Test static attribute values."""
        field_mapping = {
            "source_field": "title",
            "metadata_spec": {
                "root_element": "metadata",
                "namespace": "http://example.org",
                "attributes": {"static_attr": "static_value", "another": "fixed"},
            },
        }

        result = mapping_engine.generate_metadata_from_config(sample_recommendation, field_mapping)

        assert result is not None
        # Attributes should be: static_attr="static_value", another="fixed"

    def test_template_attributes(self, mapping_engine, sample_recommendation):
        """Test attribute templates with variable substitution."""
        field_mapping = {
            "source_field": "cis_controls",
            "metadata_spec": {
                "root_element": "control",
                "namespace": "http://example.org",
                "group_element": {
                    "element": "framework",
                    "attributes": {
                        "version": "{group_key}",  # Should be "7" or "8"
                        "count": "{group_count}",  # Number of items in group
                    },
                },
            },
        }

        result = mapping_engine.generate_metadata_from_config(sample_recommendation, field_mapping)

        assert result is not None
        # Attributes should use actual values from data


class TestMetadataContentTemplates:
    """Test content template substitution."""

    def test_static_content(self, mapping_engine, sample_recommendation):
        """Test static content in elements."""
        field_mapping = {
            "source_field": "profiles",
            "metadata_spec": {
                "root_element": "metadata",
                "namespace": "http://example.org",
                "children": [{"element": "category", "content": "Security"}],
            },
        }

        result = mapping_engine.generate_metadata_from_config(sample_recommendation, field_mapping)

        assert result is not None
        # Should have <category>Security</category>

    def test_template_content(self, mapping_engine, sample_recommendation):
        """Test content templates with variables."""
        field_mapping = {
            "source_field": "cis_controls",
            "metadata_spec": {
                "root_element": "metadata",
                "namespace": "http://example.org",
                "children": [{"element": "control_id", "content": "{item.control}"}],
            },
        }

        result = mapping_engine.generate_metadata_from_config(sample_recommendation, field_mapping)

        assert result is not None
        # Content should use actual control IDs


class TestMetadataRealWorld:
    """Test with real-world CIS Controls structure."""

    def test_generates_cis_controls_metadata(self, mapping_engine, sample_recommendation):
        """Test full CIS Controls metadata structure (matches official CIS XCCDF)."""
        field_mapping = {
            "source_field": "cis_controls",
            "metadata_spec": {
                "root_element": "cis_controls",
                "namespace": "http://cisecurity.org/controls",
                "namespace_prefix": "controls",
                "allow_empty": True,
                "group_by": "item.version",
                "group_element": {
                    "element": "framework",
                    "attributes": {"urn": "urn:cisecurity.org:controls:{group_key}"},
                    "item_element": {
                        "element": "safeguard",
                        "attributes": {
                            "title": "{item.title}",
                            "urn": "urn:cisecurity.org:controls:{item.version}:{item.control}",
                        },
                        "children": [
                            {
                                "element": "implementation_groups",
                                "attributes": {
                                    "ig1": "{item.ig1}",
                                    "ig2": "{item.ig2}",
                                    "ig3": "{item.ig3}",
                                },
                            },
                            {"element": "asset_type", "content": "Unknown"},
                            {"element": "security_function", "content": "Protect"},
                        ],
                    },
                },
            },
        }

        result = mapping_engine.generate_metadata_from_config(sample_recommendation, field_mapping)

        assert result is not None
        # Should match structure:
        # <controls:cis_controls>
        #   <controls:framework urn="urn:cisecurity.org:controls:8">
        #     <controls:safeguard title="..." urn="...">
        #       <controls:implementation_groups ig1="false" ig2="false" ig3="true"/>
        #       <controls:asset_type>Unknown</controls:asset_type>
        #       <controls:security_function>Protect</controls:security_function>
        #     </controls:safeguard>
        #   </controls:framework>
        #   <controls:framework urn="urn:cisecurity.org:controls:7">
        #     ... (same for v7)
        #   </controls:framework>
        # </controls:cis_controls>

    def test_generates_empty_cis_controls_when_no_data(self, mapping_engine):
        """Test empty CIS Controls metadata (official CIS pattern)."""
        rec_no_controls = Recommendation(
            ref="1.1.1",
            title="No controls",
            description="Test",
            url="https://example.org",
            assessment_status="Automated",
            cis_controls=[],
        )

        field_mapping = {
            "source_field": "cis_controls",
            "metadata_spec": {
                "root_element": "cis_controls",
                "namespace": "http://cisecurity.org/controls",
                "namespace_prefix": "controls",
                "allow_empty": True,
            },
        }

        result = mapping_engine.generate_metadata_from_config(rec_no_controls, field_mapping)

        assert result is not None
        # Should be <controls:cis_controls/> (empty, self-closing)
