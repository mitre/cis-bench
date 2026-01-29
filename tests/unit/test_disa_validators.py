"""Unit tests for DISA conventions validator.

Tests all validation paths including:
- Required benchmark elements
- Plain-text elements and formatting
- Dublin Core reference elements
- Group structure validation
- Rule validation (severity, weight, idents, etc.)
- CCI format validation
- validate_disa_conventions convenience function
"""

import pytest

from cis_bench.validators.disa_conventions import (
    DISAConventionsValidator,
    validate_disa_conventions,
)

# ============================================================================
# Test Fixtures - XML Templates for Testing
# ============================================================================


@pytest.fixture
def valid_disa_xccdf(tmp_path):
    """Create a minimal valid DISA XCCDF file for testing."""
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1"
           xmlns:dc="http://purl.org/dc/elements/1.1/"
           id="test_benchmark">
  <status>draft</status>
  <title>Test Benchmark</title>
  <notice id="terms-of-use">Terms of use</notice>
  <front-matter>Front matter content</front-matter>
  <rear-matter>Rear matter content</rear-matter>
  <reference href="https://example.com">
    <dc:publisher>Test Publisher</dc:publisher>
    <dc:source>https://example.com</dc:source>
  </reference>
  <plain-text id="release-info">Release: 1 Benchmark Date: 18 Oct 2025</plain-text>
  <plain-text id="generator">cis-benchmark-cli 1.0.0</plain-text>
  <plain-text id="conventionsVersion">1.10.0</plain-text>
  <version>1.0.0</version>
  <Group id="G-1">
    <title>Test Group</title>
    <description>Test description</description>
    <Rule id="R-1" severity="medium" weight="10.0">
      <version>1.0</version>
      <title>Test Rule</title>
      <description>&lt;VulnDiscussion&gt;Test discussion&lt;/VulnDiscussion&gt;</description>
      <ident system="http://cyber.mil/cci">CCI-000001</ident>
      <fixtext fixref="F-1">Test fix</fixtext>
      <check system="C-1">
        <check-content>Test check</check-content>
      </check>
    </Rule>
  </Group>
</Benchmark>
"""
    file_path = tmp_path / "valid_disa.xml"
    file_path.write_text(xml_content)
    return file_path


@pytest.fixture
def minimal_xccdf(tmp_path):
    """Create a minimal XCCDF with only required elements for specific tests."""
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1" id="test">
  <status>draft</status>
  <title>Minimal Test</title>
</Benchmark>
"""
    file_path = tmp_path / "minimal.xml"
    file_path.write_text(xml_content)
    return file_path


# ============================================================================
# Test Class: DISAConventionsValidator Initialization
# ============================================================================


class TestDISAConventionsValidatorInit:
    """Tests for DISAConventionsValidator initialization."""

    def test_init_with_valid_file(self, valid_disa_xccdf):
        """Should initialize validator with valid XCCDF file."""
        validator = DISAConventionsValidator(str(valid_disa_xccdf))
        assert validator.tree is not None
        assert validator.root is not None
        assert validator.xccdf_ns == "http://checklists.nist.gov/xccdf/1.1"

    def test_init_auto_detects_namespace(self, tmp_path):
        """Should auto-detect XCCDF namespace from root element."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.2" id="test">
  <status>draft</status>
</Benchmark>
"""
        file_path = tmp_path / "xccdf12.xml"
        file_path.write_text(xml_content)

        validator = DISAConventionsValidator(str(file_path))
        assert validator.xccdf_ns == "http://checklists.nist.gov/xccdf/1.2"

    def test_init_fallback_namespace(self, tmp_path):
        """Should fallback to default namespace when none detected."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Benchmark id="test">
  <status>draft</status>
</Benchmark>
"""
        file_path = tmp_path / "no_ns.xml"
        file_path.write_text(xml_content)

        validator = DISAConventionsValidator(str(file_path))
        assert validator.xccdf_ns == "http://checklists.nist.gov/xccdf/1.1"


# ============================================================================
# Test Class: Required Benchmark Elements (Line 67)
# ============================================================================


class TestCheckRequiredBenchmarkElements:
    """Tests for _check_required_benchmark_elements method."""

    def test_missing_notice_element(self, tmp_path):
        """Should report error when notice element is missing (line 67)."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1" id="test">
  <status>draft</status>
  <front-matter/>
  <rear-matter/>
  <reference href="test"/>
  <plain-text id="test">test</plain-text>
  <version>1.0</version>
</Benchmark>
"""
        file_path = tmp_path / "missing_notice.xml"
        file_path.write_text(xml_content)

        validator = DISAConventionsValidator(str(file_path))
        is_valid, errors, warnings = validator.validate()

        assert not is_valid
        assert any("Missing required element: notice" in e for e in errors)

    def test_missing_multiple_elements(self, minimal_xccdf):
        """Should report errors for all missing required elements."""
        validator = DISAConventionsValidator(str(minimal_xccdf))
        is_valid, errors, warnings = validator.validate()

        assert not is_valid
        expected_missing = [
            "notice",
            "front-matter",
            "rear-matter",
            "reference",
            "plain-text",
            "version",
        ]
        for elem in expected_missing:
            assert any(f"Missing required element: {elem}" in e for e in errors)


# ============================================================================
# Test Class: Plain-Text Elements (Lines 78, 84, 90)
# ============================================================================


class TestCheckPlainTextElements:
    """Tests for _check_plain_text_elements method."""

    def test_missing_required_plain_text_ids(self, tmp_path):
        """Should report error for missing plain-text ids (line 78)."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1" id="test">
  <status>draft</status>
  <notice id="test"/>
  <front-matter/>
  <rear-matter/>
  <reference href="test"><dc:publisher xmlns:dc="http://purl.org/dc/elements/1.1/">Test</dc:publisher><dc:source xmlns:dc="http://purl.org/dc/elements/1.1/">Test</dc:source></reference>
  <plain-text id="other-id">Some text</plain-text>
  <version>1.0</version>
</Benchmark>
"""
        file_path = tmp_path / "missing_plain_text_ids.xml"
        file_path.write_text(xml_content)

        validator = DISAConventionsValidator(str(file_path))
        is_valid, errors, warnings = validator.validate()

        assert not is_valid
        assert any("Missing required plain-text element: id='release-info'" in e for e in errors)
        assert any("Missing required plain-text element: id='generator'" in e for e in errors)
        assert any(
            "Missing required plain-text element: id='conventionsVersion'" in e for e in errors
        )

    def test_wrong_conventions_version(self, tmp_path):
        """Should warn when conventionsVersion is not 1.10.0 (line 84)."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1" id="test">
  <status>draft</status>
  <notice id="test"/>
  <front-matter/>
  <rear-matter/>
  <reference href="test"><dc:publisher xmlns:dc="http://purl.org/dc/elements/1.1/">Test</dc:publisher><dc:source xmlns:dc="http://purl.org/dc/elements/1.1/">Test</dc:source></reference>
  <plain-text id="release-info">Release: 1 Benchmark Date: 18 Oct 2025</plain-text>
  <plain-text id="generator">test</plain-text>
  <plain-text id="conventionsVersion">1.9.0</plain-text>
  <version>1.0</version>
</Benchmark>
"""
        file_path = tmp_path / "wrong_version.xml"
        file_path.write_text(xml_content)

        validator = DISAConventionsValidator(str(file_path))
        is_valid, errors, warnings = validator.validate()

        assert any("conventionsVersion is '1.9.0', expected '1.10.0'" in w for w in warnings)

    def test_wrong_release_info_format(self, tmp_path):
        """Should warn when release-info format doesn't match DISA pattern (line 90)."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1" id="test">
  <status>draft</status>
  <notice id="test"/>
  <front-matter/>
  <rear-matter/>
  <reference href="test"><dc:publisher xmlns:dc="http://purl.org/dc/elements/1.1/">Test</dc:publisher><dc:source xmlns:dc="http://purl.org/dc/elements/1.1/">Test</dc:source></reference>
  <plain-text id="release-info">Version 1.0</plain-text>
  <plain-text id="generator">test</plain-text>
  <plain-text id="conventionsVersion">1.10.0</plain-text>
  <version>1.0</version>
</Benchmark>
"""
        file_path = tmp_path / "wrong_release_format.xml"
        file_path.write_text(xml_content)

        validator = DISAConventionsValidator(str(file_path))
        is_valid, errors, warnings = validator.validate()

        assert any("release-info format doesn't match DISA pattern" in w for w in warnings)


# ============================================================================
# Test Class: Reference Element (Lines 97-98, 105, 108)
# ============================================================================


class TestCheckReferenceElement:
    """Tests for _check_reference_element method."""

    def test_missing_reference_element(self, tmp_path):
        """Should report error when reference element is missing (lines 97-98)."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1" id="test">
  <status>draft</status>
  <notice id="test"/>
  <front-matter/>
  <rear-matter/>
  <plain-text id="release-info">Release: 1 Benchmark Date: 18 Oct 2025</plain-text>
  <plain-text id="generator">test</plain-text>
  <plain-text id="conventionsVersion">1.10.0</plain-text>
  <version>1.0</version>
</Benchmark>
"""
        file_path = tmp_path / "no_reference.xml"
        file_path.write_text(xml_content)

        validator = DISAConventionsValidator(str(file_path))
        is_valid, errors, warnings = validator.validate()

        assert not is_valid
        assert any("Missing required reference element" in e for e in errors)

    def test_reference_missing_dc_publisher(self, tmp_path):
        """Should report error when dc:publisher is missing (line 105)."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1"
           xmlns:dc="http://purl.org/dc/elements/1.1/" id="test">
  <status>draft</status>
  <notice id="test"/>
  <front-matter/>
  <rear-matter/>
  <reference href="test">
    <dc:source>Test Source</dc:source>
  </reference>
  <plain-text id="release-info">Release: 1 Benchmark Date: 18 Oct 2025</plain-text>
  <plain-text id="generator">test</plain-text>
  <plain-text id="conventionsVersion">1.10.0</plain-text>
  <version>1.0</version>
</Benchmark>
"""
        file_path = tmp_path / "no_publisher.xml"
        file_path.write_text(xml_content)

        validator = DISAConventionsValidator(str(file_path))
        is_valid, errors, warnings = validator.validate()

        assert not is_valid
        assert any("reference missing required dc:publisher element" in e for e in errors)

    def test_reference_missing_dc_source(self, tmp_path):
        """Should report error when dc:source is missing (line 108)."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1"
           xmlns:dc="http://purl.org/dc/elements/1.1/" id="test">
  <status>draft</status>
  <notice id="test"/>
  <front-matter/>
  <rear-matter/>
  <reference href="test">
    <dc:publisher>Test Publisher</dc:publisher>
  </reference>
  <plain-text id="release-info">Release: 1 Benchmark Date: 18 Oct 2025</plain-text>
  <plain-text id="generator">test</plain-text>
  <plain-text id="conventionsVersion">1.10.0</plain-text>
  <version>1.0</version>
</Benchmark>
"""
        file_path = tmp_path / "no_source.xml"
        file_path.write_text(xml_content)

        validator = DISAConventionsValidator(str(file_path))
        is_valid, errors, warnings = validator.validate()

        assert not is_valid
        assert any("reference missing required dc:source element" in e for e in errors)


# ============================================================================
# Test Class: Group Elements (Lines 116, 121, 124, 128)
# ============================================================================


class TestCheckGroups:
    """Tests for _check_groups method."""

    def test_no_groups_warning(self, tmp_path):
        """Should warn when no Group elements found (line 116)."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1"
           xmlns:dc="http://purl.org/dc/elements/1.1/" id="test">
  <status>draft</status>
  <notice id="test"/>
  <front-matter/>
  <rear-matter/>
  <reference href="test">
    <dc:publisher>Test</dc:publisher>
    <dc:source>Test</dc:source>
  </reference>
  <plain-text id="release-info">Release: 1 Benchmark Date: 18 Oct 2025</plain-text>
  <plain-text id="generator">test</plain-text>
  <plain-text id="conventionsVersion">1.10.0</plain-text>
  <version>1.0</version>
</Benchmark>
"""
        file_path = tmp_path / "no_groups.xml"
        file_path.write_text(xml_content)

        validator = DISAConventionsValidator(str(file_path))
        is_valid, errors, warnings = validator.validate()

        assert any("No Group elements found" in w for w in warnings)

    def test_group_missing_title(self, tmp_path):
        """Should report error when Group is missing title (line 121)."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1"
           xmlns:dc="http://purl.org/dc/elements/1.1/" id="test">
  <status>draft</status>
  <notice id="test"/>
  <front-matter/>
  <rear-matter/>
  <reference href="test">
    <dc:publisher>Test</dc:publisher>
    <dc:source>Test</dc:source>
  </reference>
  <plain-text id="release-info">Release: 1 Benchmark Date: 18 Oct 2025</plain-text>
  <plain-text id="generator">test</plain-text>
  <plain-text id="conventionsVersion">1.10.0</plain-text>
  <version>1.0</version>
  <Group id="G-1">
    <description>Test description</description>
    <Rule id="R-1" severity="medium" weight="10.0">
      <version>1.0</version>
      <title>Rule Title</title>
      <description>&lt;VulnDiscussion&gt;Test&lt;/VulnDiscussion&gt;</description>
      <fixtext>Fix</fixtext>
      <check system="test"><check-content>Check</check-content></check>
    </Rule>
  </Group>
</Benchmark>
"""
        file_path = tmp_path / "group_no_title.xml"
        file_path.write_text(xml_content)

        validator = DISAConventionsValidator(str(file_path))
        is_valid, errors, warnings = validator.validate()

        assert not is_valid
        assert any("Group G-1 missing title" in e for e in errors)

    def test_group_missing_description(self, tmp_path):
        """Should report error when Group is missing description (line 124)."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1"
           xmlns:dc="http://purl.org/dc/elements/1.1/" id="test">
  <status>draft</status>
  <notice id="test"/>
  <front-matter/>
  <rear-matter/>
  <reference href="test">
    <dc:publisher>Test</dc:publisher>
    <dc:source>Test</dc:source>
  </reference>
  <plain-text id="release-info">Release: 1 Benchmark Date: 18 Oct 2025</plain-text>
  <plain-text id="generator">test</plain-text>
  <plain-text id="conventionsVersion">1.10.0</plain-text>
  <version>1.0</version>
  <Group id="G-1">
    <title>Group Title</title>
    <Rule id="R-1" severity="medium" weight="10.0">
      <version>1.0</version>
      <title>Rule Title</title>
      <description>&lt;VulnDiscussion&gt;Test&lt;/VulnDiscussion&gt;</description>
      <fixtext>Fix</fixtext>
      <check system="test"><check-content>Check</check-content></check>
    </Rule>
  </Group>
</Benchmark>
"""
        file_path = tmp_path / "group_no_description.xml"
        file_path.write_text(xml_content)

        validator = DISAConventionsValidator(str(file_path))
        is_valid, errors, warnings = validator.validate()

        assert not is_valid
        assert any("Group G-1 missing description" in e for e in errors)

    def test_group_with_multiple_rules(self, tmp_path):
        """Should warn when Group has multiple Rules (line 128)."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1"
           xmlns:dc="http://purl.org/dc/elements/1.1/" id="test">
  <status>draft</status>
  <notice id="test"/>
  <front-matter/>
  <rear-matter/>
  <reference href="test">
    <dc:publisher>Test</dc:publisher>
    <dc:source>Test</dc:source>
  </reference>
  <plain-text id="release-info">Release: 1 Benchmark Date: 18 Oct 2025</plain-text>
  <plain-text id="generator">test</plain-text>
  <plain-text id="conventionsVersion">1.10.0</plain-text>
  <version>1.0</version>
  <Group id="G-1">
    <title>Group Title</title>
    <description>Group description</description>
    <Rule id="R-1" severity="medium" weight="10.0">
      <version>1.0</version>
      <title>Rule 1</title>
      <description>&lt;VulnDiscussion&gt;Test&lt;/VulnDiscussion&gt;</description>
      <fixtext>Fix</fixtext>
      <check system="test"><check-content>Check</check-content></check>
    </Rule>
    <Rule id="R-2" severity="low" weight="10.0">
      <version>2.0</version>
      <title>Rule 2</title>
      <description>&lt;VulnDiscussion&gt;Test 2&lt;/VulnDiscussion&gt;</description>
      <fixtext>Fix 2</fixtext>
      <check system="test2"><check-content>Check 2</check-content></check>
    </Rule>
  </Group>
</Benchmark>
"""
        file_path = tmp_path / "group_multiple_rules.xml"
        file_path.write_text(xml_content)

        validator = DISAConventionsValidator(str(file_path))
        is_valid, errors, warnings = validator.validate()

        assert any("Group G-1 has 2 Rules" in w for w in warnings)

    def test_group_with_no_rules(self, tmp_path):
        """Should warn when Group has zero Rules (line 128)."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1"
           xmlns:dc="http://purl.org/dc/elements/1.1/" id="test">
  <status>draft</status>
  <notice id="test"/>
  <front-matter/>
  <rear-matter/>
  <reference href="test">
    <dc:publisher>Test</dc:publisher>
    <dc:source>Test</dc:source>
  </reference>
  <plain-text id="release-info">Release: 1 Benchmark Date: 18 Oct 2025</plain-text>
  <plain-text id="generator">test</plain-text>
  <plain-text id="conventionsVersion">1.10.0</plain-text>
  <version>1.0</version>
  <Group id="G-1">
    <title>Group Title</title>
    <description>Group description</description>
  </Group>
</Benchmark>
"""
        file_path = tmp_path / "group_no_rules.xml"
        file_path.write_text(xml_content)

        validator = DISAConventionsValidator(str(file_path))
        is_valid, errors, warnings = validator.validate()

        assert any("Group G-1 has 0 Rules" in w for w in warnings)


# ============================================================================
# Test Class: Rule Elements (Lines 142, 144, 147, 149, 157, 166, 170, 173, 180)
# ============================================================================


class TestCheckRules:
    """Tests for _check_rules method."""

    def test_rule_missing_severity(self, tmp_path):
        """Should report error when Rule is missing severity (line 142)."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1"
           xmlns:dc="http://purl.org/dc/elements/1.1/" id="test">
  <status>draft</status>
  <notice id="test"/>
  <front-matter/>
  <rear-matter/>
  <reference href="test">
    <dc:publisher>Test</dc:publisher>
    <dc:source>Test</dc:source>
  </reference>
  <plain-text id="release-info">Release: 1 Benchmark Date: 18 Oct 2025</plain-text>
  <plain-text id="generator">test</plain-text>
  <plain-text id="conventionsVersion">1.10.0</plain-text>
  <version>1.0</version>
  <Group id="G-1">
    <title>Group Title</title>
    <description>Group description</description>
    <Rule id="R-1" weight="10.0">
      <version>1.0</version>
      <title>Rule Title</title>
      <description>&lt;VulnDiscussion&gt;Test&lt;/VulnDiscussion&gt;</description>
      <fixtext>Fix</fixtext>
      <check system="test"><check-content>Check</check-content></check>
    </Rule>
  </Group>
</Benchmark>
"""
        file_path = tmp_path / "rule_no_severity.xml"
        file_path.write_text(xml_content)

        validator = DISAConventionsValidator(str(file_path))
        is_valid, errors, warnings = validator.validate()

        assert not is_valid
        assert any("Rule R-1 missing severity attribute" in e for e in errors)

    def test_rule_invalid_severity(self, tmp_path):
        """Should report error when Rule has invalid severity (line 144)."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1"
           xmlns:dc="http://purl.org/dc/elements/1.1/" id="test">
  <status>draft</status>
  <notice id="test"/>
  <front-matter/>
  <rear-matter/>
  <reference href="test">
    <dc:publisher>Test</dc:publisher>
    <dc:source>Test</dc:source>
  </reference>
  <plain-text id="release-info">Release: 1 Benchmark Date: 18 Oct 2025</plain-text>
  <plain-text id="generator">test</plain-text>
  <plain-text id="conventionsVersion">1.10.0</plain-text>
  <version>1.0</version>
  <Group id="G-1">
    <title>Group Title</title>
    <description>Group description</description>
    <Rule id="R-1" severity="critical" weight="10.0">
      <version>1.0</version>
      <title>Rule Title</title>
      <description>&lt;VulnDiscussion&gt;Test&lt;/VulnDiscussion&gt;</description>
      <fixtext>Fix</fixtext>
      <check system="test"><check-content>Check</check-content></check>
    </Rule>
  </Group>
</Benchmark>
"""
        file_path = tmp_path / "rule_invalid_severity.xml"
        file_path.write_text(xml_content)

        validator = DISAConventionsValidator(str(file_path))
        is_valid, errors, warnings = validator.validate()

        assert not is_valid
        assert any("Rule R-1 invalid severity: critical" in e for e in errors)

    def test_rule_missing_weight(self, tmp_path):
        """Should report error when Rule is missing weight (line 147)."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1"
           xmlns:dc="http://purl.org/dc/elements/1.1/" id="test">
  <status>draft</status>
  <notice id="test"/>
  <front-matter/>
  <rear-matter/>
  <reference href="test">
    <dc:publisher>Test</dc:publisher>
    <dc:source>Test</dc:source>
  </reference>
  <plain-text id="release-info">Release: 1 Benchmark Date: 18 Oct 2025</plain-text>
  <plain-text id="generator">test</plain-text>
  <plain-text id="conventionsVersion">1.10.0</plain-text>
  <version>1.0</version>
  <Group id="G-1">
    <title>Group Title</title>
    <description>Group description</description>
    <Rule id="R-1" severity="medium">
      <version>1.0</version>
      <title>Rule Title</title>
      <description>&lt;VulnDiscussion&gt;Test&lt;/VulnDiscussion&gt;</description>
      <fixtext>Fix</fixtext>
      <check system="test"><check-content>Check</check-content></check>
    </Rule>
  </Group>
</Benchmark>
"""
        file_path = tmp_path / "rule_no_weight.xml"
        file_path.write_text(xml_content)

        validator = DISAConventionsValidator(str(file_path))
        is_valid, errors, warnings = validator.validate()

        assert not is_valid
        assert any("Rule R-1 missing weight attribute" in e for e in errors)

    def test_rule_nonstandard_weight(self, tmp_path):
        """Should warn when Rule has non-standard weight (line 149)."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1"
           xmlns:dc="http://purl.org/dc/elements/1.1/" id="test">
  <status>draft</status>
  <notice id="test"/>
  <front-matter/>
  <rear-matter/>
  <reference href="test">
    <dc:publisher>Test</dc:publisher>
    <dc:source>Test</dc:source>
  </reference>
  <plain-text id="release-info">Release: 1 Benchmark Date: 18 Oct 2025</plain-text>
  <plain-text id="generator">test</plain-text>
  <plain-text id="conventionsVersion">1.10.0</plain-text>
  <version>1.0</version>
  <Group id="G-1">
    <title>Group Title</title>
    <description>Group description</description>
    <Rule id="R-1" severity="medium" weight="5.0">
      <version>1.0</version>
      <title>Rule Title</title>
      <description>&lt;VulnDiscussion&gt;Test&lt;/VulnDiscussion&gt;</description>
      <fixtext>Fix</fixtext>
      <check system="test"><check-content>Check</check-content></check>
    </Rule>
  </Group>
</Benchmark>
"""
        file_path = tmp_path / "rule_nonstandard_weight.xml"
        file_path.write_text(xml_content)

        validator = DISAConventionsValidator(str(file_path))
        is_valid, errors, warnings = validator.validate()

        assert any("Rule R-1 weight is 5.0, DISA standard is 10.0" in w for w in warnings)

    def test_rule_missing_required_elements(self, tmp_path):
        """Should report errors for missing version, title, description (line 157)."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1"
           xmlns:dc="http://purl.org/dc/elements/1.1/" id="test">
  <status>draft</status>
  <notice id="test"/>
  <front-matter/>
  <rear-matter/>
  <reference href="test">
    <dc:publisher>Test</dc:publisher>
    <dc:source>Test</dc:source>
  </reference>
  <plain-text id="release-info">Release: 1 Benchmark Date: 18 Oct 2025</plain-text>
  <plain-text id="generator">test</plain-text>
  <plain-text id="conventionsVersion">1.10.0</plain-text>
  <version>1.0</version>
  <Group id="G-1">
    <title>Group Title</title>
    <description>Group description</description>
    <Rule id="R-1" severity="medium" weight="10.0">
      <fixtext>Fix</fixtext>
      <check system="test"><check-content>Check</check-content></check>
    </Rule>
  </Group>
</Benchmark>
"""
        file_path = tmp_path / "rule_missing_elements.xml"
        file_path.write_text(xml_content)

        validator = DISAConventionsValidator(str(file_path))
        is_valid, errors, warnings = validator.validate()

        assert not is_valid
        assert any("Rule R-1 missing version element" in e for e in errors)
        assert any("Rule R-1 missing title element" in e for e in errors)
        assert any("Rule R-1 missing description element" in e for e in errors)

    def test_rule_missing_vuln_discussion(self, tmp_path):
        """Should warn when description missing VulnDiscussion (line 166)."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1"
           xmlns:dc="http://purl.org/dc/elements/1.1/" id="test">
  <status>draft</status>
  <notice id="test"/>
  <front-matter/>
  <rear-matter/>
  <reference href="test">
    <dc:publisher>Test</dc:publisher>
    <dc:source>Test</dc:source>
  </reference>
  <plain-text id="release-info">Release: 1 Benchmark Date: 18 Oct 2025</plain-text>
  <plain-text id="generator">test</plain-text>
  <plain-text id="conventionsVersion">1.10.0</plain-text>
  <version>1.0</version>
  <Group id="G-1">
    <title>Group Title</title>
    <description>Group description</description>
    <Rule id="R-1" severity="medium" weight="10.0">
      <version>1.0</version>
      <title>Rule Title</title>
      <description>Plain description without VulnDiscussion</description>
      <fixtext>Fix</fixtext>
      <check system="test"><check-content>Check</check-content></check>
    </Rule>
  </Group>
</Benchmark>
"""
        file_path = tmp_path / "rule_no_vuln_discussion.xml"
        file_path.write_text(xml_content)

        validator = DISAConventionsValidator(str(file_path))
        is_valid, errors, warnings = validator.validate()

        assert any("Rule R-1 description missing VulnDiscussion tag" in w for w in warnings)

    def test_rule_missing_fixtext(self, tmp_path):
        """Should warn when Rule missing fixtext (line 170)."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1"
           xmlns:dc="http://purl.org/dc/elements/1.1/" id="test">
  <status>draft</status>
  <notice id="test"/>
  <front-matter/>
  <rear-matter/>
  <reference href="test">
    <dc:publisher>Test</dc:publisher>
    <dc:source>Test</dc:source>
  </reference>
  <plain-text id="release-info">Release: 1 Benchmark Date: 18 Oct 2025</plain-text>
  <plain-text id="generator">test</plain-text>
  <plain-text id="conventionsVersion">1.10.0</plain-text>
  <version>1.0</version>
  <Group id="G-1">
    <title>Group Title</title>
    <description>Group description</description>
    <Rule id="R-1" severity="medium" weight="10.0">
      <version>1.0</version>
      <title>Rule Title</title>
      <description>&lt;VulnDiscussion&gt;Test&lt;/VulnDiscussion&gt;</description>
      <check system="test"><check-content>Check</check-content></check>
    </Rule>
  </Group>
</Benchmark>
"""
        file_path = tmp_path / "rule_no_fixtext.xml"
        file_path.write_text(xml_content)

        validator = DISAConventionsValidator(str(file_path))
        is_valid, errors, warnings = validator.validate()

        assert any("Rule R-1 missing fixtext element" in w for w in warnings)

    def test_rule_missing_check(self, tmp_path):
        """Should warn when Rule missing check element (line 173)."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1"
           xmlns:dc="http://purl.org/dc/elements/1.1/" id="test">
  <status>draft</status>
  <notice id="test"/>
  <front-matter/>
  <rear-matter/>
  <reference href="test">
    <dc:publisher>Test</dc:publisher>
    <dc:source>Test</dc:source>
  </reference>
  <plain-text id="release-info">Release: 1 Benchmark Date: 18 Oct 2025</plain-text>
  <plain-text id="generator">test</plain-text>
  <plain-text id="conventionsVersion">1.10.0</plain-text>
  <version>1.0</version>
  <Group id="G-1">
    <title>Group Title</title>
    <description>Group description</description>
    <Rule id="R-1" severity="medium" weight="10.0">
      <version>1.0</version>
      <title>Rule Title</title>
      <description>&lt;VulnDiscussion&gt;Test&lt;/VulnDiscussion&gt;</description>
      <fixtext>Fix</fixtext>
    </Rule>
  </Group>
</Benchmark>
"""
        file_path = tmp_path / "rule_no_check.xml"
        file_path.write_text(xml_content)

        validator = DISAConventionsValidator(str(file_path))
        is_valid, errors, warnings = validator.validate()

        assert any("Rule R-1 missing check element" in w for w in warnings)

    def test_rule_invalid_cci_format(self, tmp_path):
        """Should report error for invalid CCI format (line 180)."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1"
           xmlns:dc="http://purl.org/dc/elements/1.1/" id="test">
  <status>draft</status>
  <notice id="test"/>
  <front-matter/>
  <rear-matter/>
  <reference href="test">
    <dc:publisher>Test</dc:publisher>
    <dc:source>Test</dc:source>
  </reference>
  <plain-text id="release-info">Release: 1 Benchmark Date: 18 Oct 2025</plain-text>
  <plain-text id="generator">test</plain-text>
  <plain-text id="conventionsVersion">1.10.0</plain-text>
  <version>1.0</version>
  <Group id="G-1">
    <title>Group Title</title>
    <description>Group description</description>
    <Rule id="R-1" severity="medium" weight="10.0">
      <version>1.0</version>
      <title>Rule Title</title>
      <description>&lt;VulnDiscussion&gt;Test&lt;/VulnDiscussion&gt;</description>
      <ident system="http://cyber.mil/cci">CCI-123</ident>
      <fixtext>Fix</fixtext>
      <check system="test"><check-content>Check</check-content></check>
    </Rule>
  </Group>
</Benchmark>
"""
        file_path = tmp_path / "rule_invalid_cci.xml"
        file_path.write_text(xml_content)

        validator = DISAConventionsValidator(str(file_path))
        is_valid, errors, warnings = validator.validate()

        assert not is_valid
        assert any("Rule R-1 invalid CCI format: CCI-123" in e for e in errors)

    def test_rule_valid_cci_formats(self, tmp_path):
        """Should accept valid CCI formats."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1"
           xmlns:dc="http://purl.org/dc/elements/1.1/" id="test">
  <status>draft</status>
  <notice id="test"/>
  <front-matter/>
  <rear-matter/>
  <reference href="test">
    <dc:publisher>Test</dc:publisher>
    <dc:source>Test</dc:source>
  </reference>
  <plain-text id="release-info">Release: 1 Benchmark Date: 18 Oct 2025</plain-text>
  <plain-text id="generator">test</plain-text>
  <plain-text id="conventionsVersion">1.10.0</plain-text>
  <version>1.0</version>
  <Group id="G-1">
    <title>Group Title</title>
    <description>Group description</description>
    <Rule id="R-1" severity="medium" weight="10.0">
      <version>1.0</version>
      <title>Rule Title</title>
      <description>&lt;VulnDiscussion&gt;Test&lt;/VulnDiscussion&gt;</description>
      <ident system="http://cyber.mil/cci">CCI-000001</ident>
      <ident system="http://cyber.mil/cci">CCI-123456</ident>
      <fixtext>Fix</fixtext>
      <check system="test"><check-content>Check</check-content></check>
    </Rule>
  </Group>
</Benchmark>
"""
        file_path = tmp_path / "rule_valid_cci.xml"
        file_path.write_text(xml_content)

        validator = DISAConventionsValidator(str(file_path))
        is_valid, errors, warnings = validator.validate()

        # Should not have any CCI format errors
        assert not any("invalid CCI format" in e for e in errors)


# ============================================================================
# Test Class: validate_disa_conventions Function (Lines 197-201, 204-208)
# ============================================================================


class TestValidateDISAConventionsFunction:
    """Tests for validate_disa_conventions convenience function."""

    def test_valid_file_returns_true(self, valid_disa_xccdf):
        """Should return True for valid file."""
        result = validate_disa_conventions(str(valid_disa_xccdf))
        assert result is True

    def test_invalid_file_returns_false_and_prints_errors(self, minimal_xccdf, capsys):
        """Should return False and print errors for invalid file (lines 197-201)."""
        result = validate_disa_conventions(str(minimal_xccdf))

        assert result is False

        captured = capsys.readouterr()
        assert "ERRORS:" in captured.out

    def test_valid_file_with_warnings_prints_warnings(self, tmp_path, capsys):
        """Should print warnings even when valid (lines 204-208)."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1"
           xmlns:dc="http://purl.org/dc/elements/1.1/" id="test">
  <status>draft</status>
  <notice id="test"/>
  <front-matter/>
  <rear-matter/>
  <reference href="test">
    <dc:publisher>Test</dc:publisher>
    <dc:source>Test</dc:source>
  </reference>
  <plain-text id="release-info">Release: 1 Benchmark Date: 18 Oct 2025</plain-text>
  <plain-text id="generator">test</plain-text>
  <plain-text id="conventionsVersion">1.9.0</plain-text>
  <version>1.0</version>
  <Group id="G-1">
    <title>Group Title</title>
    <description>Group description</description>
    <Rule id="R-1" severity="medium" weight="10.0">
      <version>1.0</version>
      <title>Rule Title</title>
      <description>&lt;VulnDiscussion&gt;Test&lt;/VulnDiscussion&gt;</description>
      <fixtext>Fix</fixtext>
      <check system="test"><check-content>Check</check-content></check>
    </Rule>
  </Group>
</Benchmark>
"""
        file_path = tmp_path / "valid_with_warnings.xml"
        file_path.write_text(xml_content)

        result = validate_disa_conventions(str(file_path))

        # Still valid (warnings don't fail validation)
        assert result is True

        captured = capsys.readouterr()
        assert "WARNINGS:" in captured.out

    def test_completely_valid_prints_success(self, valid_disa_xccdf, capsys):
        """Should print success message when fully valid with no warnings."""
        result = validate_disa_conventions(str(valid_disa_xccdf))

        assert result is True

        captured = capsys.readouterr()
        assert "Passes all DISA conventions v1.10.0 checks" in captured.out


# ============================================================================
# Test Class: Edge Cases and Special Scenarios
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_empty_description_text(self, tmp_path):
        """Should handle empty description text gracefully.

        Note: The validator checks `if desc is not None and desc.text:` before
        checking for VulnDiscussion, so empty description text does NOT trigger
        the VulnDiscussion warning. This is intentional - empty text is already
        a problem at a higher level.
        """
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1"
           xmlns:dc="http://purl.org/dc/elements/1.1/" id="test">
  <status>draft</status>
  <notice id="test"/>
  <front-matter/>
  <rear-matter/>
  <reference href="test">
    <dc:publisher>Test</dc:publisher>
    <dc:source>Test</dc:source>
  </reference>
  <plain-text id="release-info">Release: 1 Benchmark Date: 18 Oct 2025</plain-text>
  <plain-text id="generator">test</plain-text>
  <plain-text id="conventionsVersion">1.10.0</plain-text>
  <version>1.0</version>
  <Group id="G-1">
    <title>Group Title</title>
    <description>Group description</description>
    <Rule id="R-1" severity="medium" weight="10.0">
      <version>1.0</version>
      <title>Rule Title</title>
      <description></description>
      <fixtext>Fix</fixtext>
      <check system="test"><check-content>Check</check-content></check>
    </Rule>
  </Group>
</Benchmark>
"""
        file_path = tmp_path / "empty_description.xml"
        file_path.write_text(xml_content)

        validator = DISAConventionsValidator(str(file_path))
        is_valid, errors, warnings = validator.validate()

        # Empty description text skips VulnDiscussion check (intentional behavior)
        # The validator checks `if desc is not None and desc.text:` first
        assert not any("missing VulnDiscussion tag" in w for w in warnings)

    def test_rule_with_no_id(self, tmp_path):
        """Should handle Rule without id attribute."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1"
           xmlns:dc="http://purl.org/dc/elements/1.1/" id="test">
  <status>draft</status>
  <notice id="test"/>
  <front-matter/>
  <rear-matter/>
  <reference href="test">
    <dc:publisher>Test</dc:publisher>
    <dc:source>Test</dc:source>
  </reference>
  <plain-text id="release-info">Release: 1 Benchmark Date: 18 Oct 2025</plain-text>
  <plain-text id="generator">test</plain-text>
  <plain-text id="conventionsVersion">1.10.0</plain-text>
  <version>1.0</version>
  <Group id="G-1">
    <title>Group Title</title>
    <description>Group description</description>
    <Rule severity="medium" weight="10.0">
      <version>1.0</version>
      <title>Rule Title</title>
      <description>&lt;VulnDiscussion&gt;Test&lt;/VulnDiscussion&gt;</description>
      <fixtext>Fix</fixtext>
      <check system="test"><check-content>Check</check-content></check>
    </Rule>
  </Group>
</Benchmark>
"""
        file_path = tmp_path / "rule_no_id.xml"
        file_path.write_text(xml_content)

        validator = DISAConventionsValidator(str(file_path))
        # Should not raise exception - uses "unknown" as default
        is_valid, errors, warnings = validator.validate()
        assert is_valid is True

    def test_ident_with_different_system(self, tmp_path):
        """Should not validate idents with non-CCI system."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1"
           xmlns:dc="http://purl.org/dc/elements/1.1/" id="test">
  <status>draft</status>
  <notice id="test"/>
  <front-matter/>
  <rear-matter/>
  <reference href="test">
    <dc:publisher>Test</dc:publisher>
    <dc:source>Test</dc:source>
  </reference>
  <plain-text id="release-info">Release: 1 Benchmark Date: 18 Oct 2025</plain-text>
  <plain-text id="generator">test</plain-text>
  <plain-text id="conventionsVersion">1.10.0</plain-text>
  <version>1.0</version>
  <Group id="G-1">
    <title>Group Title</title>
    <description>Group description</description>
    <Rule id="R-1" severity="medium" weight="10.0">
      <version>1.0</version>
      <title>Rule Title</title>
      <description>&lt;VulnDiscussion&gt;Test&lt;/VulnDiscussion&gt;</description>
      <ident system="http://cce.mitre.org">CCE-12345-6</ident>
      <fixtext>Fix</fixtext>
      <check system="test"><check-content>Check</check-content></check>
    </Rule>
  </Group>
</Benchmark>
"""
        file_path = tmp_path / "ident_other_system.xml"
        file_path.write_text(xml_content)

        validator = DISAConventionsValidator(str(file_path))
        is_valid, errors, warnings = validator.validate()

        # Should not report CCI format error for non-CCI idents
        assert not any("invalid CCI format" in e for e in errors)

    def test_vuln_discussion_with_entity_encoding(self, tmp_path):
        """Should accept VulnDiscussion with entity-encoded tags."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1"
           xmlns:dc="http://purl.org/dc/elements/1.1/" id="test">
  <status>draft</status>
  <notice id="test"/>
  <front-matter/>
  <rear-matter/>
  <reference href="test">
    <dc:publisher>Test</dc:publisher>
    <dc:source>Test</dc:source>
  </reference>
  <plain-text id="release-info">Release: 1 Benchmark Date: 18 Oct 2025</plain-text>
  <plain-text id="generator">test</plain-text>
  <plain-text id="conventionsVersion">1.10.0</plain-text>
  <version>1.0</version>
  <Group id="G-1">
    <title>Group Title</title>
    <description>Group description</description>
    <Rule id="R-1" severity="medium" weight="10.0">
      <version>1.0</version>
      <title>Rule Title</title>
      <description>&amp;lt;VulnDiscussion&amp;gt;Test&amp;lt;/VulnDiscussion&amp;gt;</description>
      <fixtext>Fix</fixtext>
      <check system="test"><check-content>Check</check-content></check>
    </Rule>
  </Group>
</Benchmark>
"""
        file_path = tmp_path / "encoded_vuln_discussion.xml"
        file_path.write_text(xml_content)

        validator = DISAConventionsValidator(str(file_path))
        is_valid, errors, warnings = validator.validate()

        # Should accept entity-encoded VulnDiscussion
        assert not any("missing VulnDiscussion tag" in w for w in warnings)

    def test_all_valid_severities(self, tmp_path):
        """Should accept all valid severity values: low, medium, high."""
        for severity in ["low", "medium", "high"]:
            xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1"
           xmlns:dc="http://purl.org/dc/elements/1.1/" id="test">
  <status>draft</status>
  <notice id="test"/>
  <front-matter/>
  <rear-matter/>
  <reference href="test">
    <dc:publisher>Test</dc:publisher>
    <dc:source>Test</dc:source>
  </reference>
  <plain-text id="release-info">Release: 1 Benchmark Date: 18 Oct 2025</plain-text>
  <plain-text id="generator">test</plain-text>
  <plain-text id="conventionsVersion">1.10.0</plain-text>
  <version>1.0</version>
  <Group id="G-1">
    <title>Group Title</title>
    <description>Group description</description>
    <Rule id="R-1" severity="{severity}" weight="10.0">
      <version>1.0</version>
      <title>Rule Title</title>
      <description>&lt;VulnDiscussion&gt;Test&lt;/VulnDiscussion&gt;</description>
      <fixtext>Fix</fixtext>
      <check system="test"><check-content>Check</check-content></check>
    </Rule>
  </Group>
</Benchmark>
"""
            file_path = tmp_path / f"severity_{severity}.xml"
            file_path.write_text(xml_content)

            validator = DISAConventionsValidator(str(file_path))
            is_valid, errors, warnings = validator.validate()

            assert is_valid, f"Should accept severity='{severity}'"
            assert not any("invalid severity" in e for e in errors)


# ============================================================================
# Test Class: Validate Method
# ============================================================================


class TestValidateMethod:
    """Tests for the validate() method itself."""

    def test_validate_returns_tuple(self, valid_disa_xccdf):
        """Should return (is_valid, errors, warnings) tuple."""
        validator = DISAConventionsValidator(str(valid_disa_xccdf))
        result = validator.validate()

        assert isinstance(result, tuple)
        assert len(result) == 3
        assert isinstance(result[0], bool)
        assert isinstance(result[1], list)
        assert isinstance(result[2], list)

    def test_validate_resets_errors_on_each_call(self, minimal_xccdf):
        """Should reset errors/warnings on each validate() call."""
        validator = DISAConventionsValidator(str(minimal_xccdf))

        # First validation
        is_valid1, errors1, warnings1 = validator.validate()

        # Second validation should have same results (not accumulate)
        is_valid2, errors2, warnings2 = validator.validate()

        assert errors1 == errors2
        assert warnings1 == warnings2

    def test_valid_file_has_empty_errors_list(self, valid_disa_xccdf):
        """Should have empty errors list for valid file."""
        validator = DISAConventionsValidator(str(valid_disa_xccdf))
        is_valid, errors, warnings = validator.validate()

        assert is_valid is True
        assert errors == []
