"""Tests for XCCDF Profile generation from recommendation.profiles field."""

import pytest
from lxml import etree

from cis_bench.exporters import ExporterFactory
from cis_bench.models.benchmark import Benchmark


@pytest.fixture
def sample_benchmark(almalinux_complete_file):
    """Load sample benchmark for testing."""
    return Benchmark.from_json_file(str(almalinux_complete_file))


class TestDISAProfileGeneration:
    """Test Profile generation for DISA exports."""

    def test_disa_generates_profile_elements(self, sample_benchmark, tmp_path):
        """Test that DISA exports generate Profile elements at benchmark level."""
        output_file = tmp_path / "test_disa_profiles.xml"
        exporter = ExporterFactory.create("xccdf", style="disa")
        exporter.export(sample_benchmark, str(output_file))

        tree = etree.parse(str(output_file))
        root = tree.getroot()

        profiles = root.xpath('.//*[local-name()="Profile"]')
        assert len(profiles) > 0, "No Profile elements generated"
        assert len(profiles) >= 2, f"Expected at least 2 profiles, found {len(profiles)}"

    def test_disa_profile_structure(self, sample_benchmark, tmp_path):
        """Test Profile elements have correct structure (id, title, description, select)."""
        output_file = tmp_path / "test_disa_profiles.xml"
        exporter = ExporterFactory.create("xccdf", style="disa")
        exporter.export(sample_benchmark, str(output_file))

        tree = etree.parse(str(output_file))
        root = tree.getroot()

        profiles = root.xpath('.//*[local-name()="Profile"]')

        for profile in profiles:
            # Check required attributes
            profile_id = profile.get("id")
            assert profile_id, "Profile missing id attribute"

            # Check required elements
            titles = profile.xpath('.//*[local-name()="title"]')
            descriptions = profile.xpath('.//*[local-name()="description"]')
            selects = profile.xpath('.//*[local-name()="select"]')

            assert len(titles) > 0, f"Profile {profile_id} missing title"
            assert len(descriptions) > 0, f"Profile {profile_id} missing description"
            assert len(selects) > 0, f"Profile {profile_id} has no select elements"

    def test_disa_profile_select_lists(self, sample_benchmark, tmp_path):
        """Test Profile select elements reference actual rules."""
        output_file = tmp_path / "test_disa_profiles.xml"
        exporter = ExporterFactory.create("xccdf", style="disa")
        exporter.export(sample_benchmark, str(output_file))

        tree = etree.parse(str(output_file))
        root = tree.getroot()

        # Get all rule IDs
        rules = root.xpath('.//*[local-name()="Rule"]')
        rule_ids = {rule.get("id") for rule in rules}

        # Check profile select references
        profiles = root.xpath('.//*[local-name()="Profile"]')
        for profile in profiles:
            selects = profile.xpath('.//*[local-name()="select"]')

            for select in selects:
                idref = select.get("idref")
                assert idref, "select element missing idref"
                assert idref in rule_ids, f"select references non-existent rule: {idref}"
                assert select.get("selected") == "true", "select should have selected='true'"

    def test_disa_level_1_server_profile(self, sample_benchmark, tmp_path):
        """Test Level 1 Server profile is generated with expected rules."""
        output_file = tmp_path / "test_disa_profiles.xml"
        exporter = ExporterFactory.create("xccdf", style="disa")
        exporter.export(sample_benchmark, str(output_file))

        tree = etree.parse(str(output_file))
        root = tree.getroot()

        # Find Level 1 Server profile
        level1_server = root.xpath('.//*[local-name()="Profile"][@id="level-1-server"]')
        assert len(level1_server) == 1, "Level 1 Server profile not found"

        profile = level1_server[0]
        selects = profile.xpath('.//*[local-name()="select"]')

        # Level 1 Server should have significant number of rules
        assert len(selects) > 200, f"Level 1 Server should have >200 rules, found {len(selects)}"
