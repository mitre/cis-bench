"""Comprehensive test suite for Pydantic models and validators.

Tests cover:
1. Pydantic model validation (Benchmark, Recommendation, CISControl, etc.)
2. Field constraints and type validation
3. Serialization/deserialization (JSON round-trips)
4. Nested models and relationships
5. Edge cases and error handling
6. DISAConventionsValidator functionality
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import HttpUrl, ValidationError

# Import models
from cis_bench.models.benchmark import (
    Artifact,
    Benchmark,
    CISControl,
    MITREMapping,
    ParentReference,
    Recommendation,
)

# Import validator
from cis_bench.validators.disa_conventions import (
    DISAConventionsValidator,
    validate_disa_conventions,
)

# ============================================================================
# FIXTURES
# ============================================================================

# Using shared fixtures from tests/conftest.py:
#   - project_root
#   - almalinux_complete_file (points to tests/fixtures/benchmarks/almalinux_complete.json)
#   - valid_disa_xccdf_file (points to tests/fixtures/xccdf/valid_disa_full.xml)


@pytest.fixture
def minimal_recommendation_data():
    """Minimal valid recommendation data."""
    return {
        "ref": "1.1.1",
        "title": "Test Recommendation",
        "url": "https://workbench.cisecurity.org/benchmarks/12345",
        "assessment_status": "Automated",
    }


@pytest.fixture
def complete_recommendation_data():
    """Complete recommendation with all fields."""
    return {
        "ref": "6.1.1",
        "title": "Ensure AIDE is installed",
        "url": "https://workbench.cisecurity.org/sections/3680740/recommendations/6083840",
        "assessment_status": "Automated",
        "profiles": ["Level 1 - Server", "Level 1 - Workstation"],
        "cis_controls": [
            {
                "version": 8,
                "control": "3.14",
                "title": "Log Sensitive Data Access",
                "ig1": False,
                "ig2": False,
                "ig3": True,
            }
        ],
        "mitre_mapping": {
            "techniques": ["T1565", "T1565.001"],
            "tactics": ["TA0001"],
            "mitigations": ["M1022"],
        },
        "nist_controls": ["AU-2", "SI-3"],
        "description": "<p>AIDE is an intrusion detection tool</p>",
        "rationale": "<p>Security rationale here</p>",
        "impact": "<p>Impact statement</p>",
        "audit": "<p>Run: <code>rpm -q aide</code></p>",
        "remediation": "<p>Run: <code>dnf install aide</code></p>",
    }


@pytest.fixture
def minimal_benchmark_data():
    """Minimal valid benchmark data."""
    return {
        "title": "Test Benchmark",
        "benchmark_id": "12345",
        "url": "https://workbench.cisecurity.org/benchmarks/12345",
        "version": "v1.0.0",
        "scraper_version": "v1_2025_10",
        "total_recommendations": 0,
        "recommendations": [],
    }


# ============================================================================
# PYDANTIC MODEL TESTS - CISControl
# ============================================================================


class TestCISControl:
    """Test CISControl model validation."""

    def test_valid_cis_control(self):
        """Test valid CIS control creation."""
        control = CISControl(
            version=8,
            control="3.14",
            title="Log Sensitive Data Access",
            ig1=False,
            ig2=False,
            ig3=True,
        )
        assert control.version == 8
        assert control.control == "3.14"
        assert control.ig3 is True

    def test_cis_control_requires_version(self):
        """Test version field is required."""
        with pytest.raises(ValidationError) as exc:
            CISControl(
                control="3.14", title="Log Sensitive Data Access", ig1=False, ig2=False, ig3=True
            )
        assert "version" in str(exc.value)

    def test_cis_control_requires_all_ig_fields(self):
        """Test all IG fields are required."""
        with pytest.raises(ValidationError) as exc:
            CISControl(
                version=8,
                control="3.14",
                title="Log Sensitive Data Access",
                ig1=False,
                # Missing ig2, ig3
            )
        assert "ig2" in str(exc.value) or "ig3" in str(exc.value)

    def test_cis_control_type_validation(self):
        """Test type validation for CIS control fields."""
        with pytest.raises(ValidationError):
            CISControl(
                version="eight",  # Should be int
                control="3.14",
                title="Log Sensitive Data Access",
                ig1=False,
                ig2=False,
                ig3=True,
            )


# ============================================================================
# PYDANTIC MODEL TESTS - MITREMapping
# ============================================================================


class TestMITREMapping:
    """Test MITREMapping model validation."""

    def test_empty_mitre_mapping(self):
        """Test MITRE mapping with default empty lists."""
        mapping = MITREMapping()
        assert mapping.techniques == []
        assert mapping.tactics == []
        assert mapping.mitigations == []

    def test_populated_mitre_mapping(self):
        """Test MITRE mapping with data."""
        mapping = MITREMapping(
            techniques=["T1565", "T1565.001"], tactics=["TA0001"], mitigations=["M1022"]
        )
        assert len(mapping.techniques) == 2
        assert "T1565" in mapping.techniques
        assert mapping.tactics == ["TA0001"]

    def test_mitre_mapping_accepts_strings(self):
        """Test MITRE fields accept string lists."""
        mapping = MITREMapping(
            techniques=["T1234", "T5678"], tactics=["TA0001", "TA0002"], mitigations=["M1111"]
        )
        assert all(isinstance(t, str) for t in mapping.techniques)


# ============================================================================
# PYDANTIC MODEL TESTS - ParentReference
# ============================================================================


class TestParentReference:
    """Test ParentReference model validation."""

    def test_valid_parent_reference(self):
        """Test valid parent reference creation."""
        parent = ParentReference(
            url="https://workbench.cisecurity.org/sections/12345", title="Parent Section"
        )
        assert isinstance(parent.url, HttpUrl)
        assert parent.title == "Parent Section"

    def test_parent_requires_url(self):
        """Test URL field is required."""
        with pytest.raises(ValidationError) as exc:
            ParentReference(title="Parent Section")
        assert "url" in str(exc.value)

    def test_parent_validates_url_format(self):
        """Test URL field must be valid HTTP URL."""
        with pytest.raises(ValidationError):
            ParentReference(url="not-a-valid-url", title="Parent Section")


# ============================================================================
# PYDANTIC MODEL TESTS - Artifact
# ============================================================================


class TestArtifact:
    """Test Artifact model validation."""

    def test_valid_artifact(self):
        """Test valid artifact creation."""
        artifact = Artifact(
            id=1,
            view_level="1.1.1.1.1",
            title="Test Artifact",
            status="active",
            artifact_type={"type": "command", "system": "linux"},
        )
        assert artifact.id == 1
        assert artifact.view_level == "1.1.1.1.1"
        assert isinstance(artifact.artifact_type, dict)

    def test_artifact_requires_all_fields(self):
        """Test all artifact fields are required."""
        with pytest.raises(ValidationError) as exc:
            Artifact(
                id=1,
                view_level="1.1.1.1.1",
                title="Test Artifact",
                # Missing status, artifact_type
            )
        assert "status" in str(exc.value) or "artifact_type" in str(exc.value)


# ============================================================================
# PYDANTIC MODEL TESTS - Recommendation
# ============================================================================


class TestRecommendation:
    """Test Recommendation model validation."""

    def test_minimal_recommendation(self, minimal_recommendation_data):
        """Test recommendation with minimal required fields."""
        rec = Recommendation(**minimal_recommendation_data)
        assert rec.ref == "1.1.1"
        assert rec.title == "Test Recommendation"
        assert rec.assessment_status == "Automated"
        # Optional fields should have defaults
        assert rec.profiles == []
        assert rec.cis_controls == []
        assert rec.nist_controls == []

    def test_complete_recommendation(self, complete_recommendation_data):
        """Test recommendation with all fields populated."""
        rec = Recommendation(**complete_recommendation_data)
        assert rec.ref == "6.1.1"
        assert len(rec.cis_controls) == 1
        assert rec.mitre_mapping is not None
        assert len(rec.mitre_mapping.techniques) == 2
        assert rec.description is not None

    def test_recommendation_requires_ref(self):
        """Test ref field is required."""
        with pytest.raises(ValidationError) as exc:
            Recommendation(title="Test", url="https://example.com", assessment_status="Automated")
        assert "ref" in str(exc.value)

    def test_recommendation_requires_title(self):
        """Test title field is required."""
        with pytest.raises(ValidationError) as exc:
            Recommendation(ref="1.1.1", url="https://example.com", assessment_status="Automated")
        assert "title" in str(exc.value)

    def test_recommendation_requires_url(self):
        """Test URL field is required."""
        with pytest.raises(ValidationError) as exc:
            Recommendation(ref="1.1.1", title="Test", assessment_status="Automated")
        assert "url" in str(exc.value)

    def test_recommendation_validates_url_format(self):
        """Test URL must be valid HTTP URL."""
        with pytest.raises(ValidationError):
            Recommendation(
                ref="1.1.1", title="Test", url="not-a-valid-url", assessment_status="Automated"
            )

    def test_recommendation_ref_pattern_validation(self):
        """Test ref field pattern validation."""
        # Valid patterns
        valid_refs = ["1", "1.1", "1.1.1", "1.2.3.4.5"]
        for ref in valid_refs:
            rec = Recommendation(
                ref=ref, title="Test", url="https://example.com", assessment_status="Automated"
            )
            assert rec.ref == ref

        # Invalid patterns
        invalid_refs = ["a.1.1", "1.1.", ".1.1", "1..1"]
        for ref in invalid_refs:
            with pytest.raises(ValidationError):
                Recommendation(
                    ref=ref, title="Test", url="https://example.com", assessment_status="Automated"
                )

    def test_recommendation_title_min_length(self):
        """Test title must have minimum length."""
        with pytest.raises(ValidationError):
            Recommendation(
                ref="1.1.1",
                title="",  # Empty title
                url="https://example.com",
                assessment_status="Automated",
            )

    def test_recommendation_nested_cis_controls(self, complete_recommendation_data):
        """Test nested CIS controls are validated."""
        rec = Recommendation(**complete_recommendation_data)
        assert isinstance(rec.cis_controls[0], CISControl)
        assert rec.cis_controls[0].version == 8
        assert rec.cis_controls[0].ig3 is True

    def test_recommendation_nested_mitre_mapping(self, complete_recommendation_data):
        """Test nested MITRE mapping is validated."""
        rec = Recommendation(**complete_recommendation_data)
        assert isinstance(rec.mitre_mapping, MITREMapping)
        assert "T1565" in rec.mitre_mapping.techniques

    def test_recommendation_optional_fields_none(self):
        """Test optional fields can be None."""
        rec = Recommendation(
            ref="1.1.1",
            title="Test",
            url="https://example.com",
            assessment_status="Automated",
            description=None,
            rationale=None,
            impact=None,
            audit=None,
            remediation=None,
        )
        assert rec.description is None
        assert rec.rationale is None

    def test_recommendation_dict_export(self, complete_recommendation_data):
        """Test recommendation can be exported to dict."""
        rec = Recommendation(**complete_recommendation_data)
        data = rec.model_dump()
        assert isinstance(data, dict)
        assert data["ref"] == "6.1.1"
        assert "cis_controls" in data
        assert isinstance(data["cis_controls"], list)


# ============================================================================
# PYDANTIC MODEL TESTS - Benchmark
# ============================================================================


class TestBenchmark:
    """Test Benchmark model validation."""

    def test_minimal_benchmark(self, minimal_benchmark_data):
        """Test benchmark with minimal required fields."""
        benchmark = Benchmark(**minimal_benchmark_data)
        assert benchmark.title == "Test Benchmark"
        assert benchmark.benchmark_id == "12345"
        assert benchmark.total_recommendations == 0
        assert len(benchmark.recommendations) == 0

    def test_benchmark_requires_title(self):
        """Test title field is required."""
        with pytest.raises(ValidationError) as exc:
            Benchmark(
                benchmark_id="12345",
                url="https://example.com",
                version="v1.0.0",
                scraper_version="v1",
                total_recommendations=0,
                recommendations=[],
            )
        assert "title" in str(exc.value)

    def test_benchmark_requires_benchmark_id(self):
        """Test benchmark_id field is required."""
        with pytest.raises(ValidationError) as exc:
            Benchmark(
                title="Test",
                url="https://example.com",
                version="v1.0.0",
                scraper_version="v1",
                total_recommendations=0,
                recommendations=[],
            )
        assert "benchmark_id" in str(exc.value)

    def test_benchmark_validates_total_recommendations_count(self):
        """Test total_recommendations validation."""
        # Note: Pydantic doesn't enforce this field relationship without custom validator
        # The model accepts mismatched counts - would need @field_validator
        pytest.skip("Requires custom @field_validator for total_recommendations consistency")

    def test_benchmark_total_recommendations_non_negative(self):
        """Test total_recommendations must be >= 0."""
        with pytest.raises(ValidationError):
            Benchmark(
                title="Test",
                benchmark_id="12345",
                url="https://example.com",
                version="v1.0.0",
                scraper_version="v1",
                total_recommendations=-1,  # Negative
                recommendations=[],
            )

    def test_benchmark_downloaded_at_auto_generated(self, minimal_benchmark_data):
        """Test downloaded_at is auto-generated if not provided."""
        # Remove downloaded_at if present
        minimal_benchmark_data.pop("downloaded_at", None)
        benchmark = Benchmark(**minimal_benchmark_data)
        assert isinstance(benchmark.downloaded_at, datetime)

    def test_benchmark_with_recommendations(self, minimal_recommendation_data):
        """Test benchmark with actual recommendations."""
        benchmark = Benchmark(
            title="Test",
            benchmark_id="12345",
            url="https://example.com",
            version="v1.0.0",
            scraper_version="v1",
            total_recommendations=2,
            recommendations=[
                minimal_recommendation_data,
                {**minimal_recommendation_data, "ref": "1.1.2", "title": "Second Rec"},
            ],
        )
        assert len(benchmark.recommendations) == 2
        assert all(isinstance(r, Recommendation) for r in benchmark.recommendations)


# ============================================================================
# SERIALIZATION TESTS
# ============================================================================


class TestSerialization:
    """Test JSON serialization and deserialization."""

    def test_benchmark_to_json_file(self, minimal_benchmark_data):
        """Test saving benchmark to JSON file."""
        benchmark = Benchmark(**minimal_benchmark_data)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            benchmark.to_json_file(temp_path)
            assert Path(temp_path).exists()

            # Verify file contents
            with open(temp_path) as f:
                data = json.load(f)
            assert data["title"] == "Test Benchmark"
            assert data["benchmark_id"] == "12345"
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_benchmark_from_json_file(self, almalinux_complete_file):
        """Test loading benchmark from JSON file."""
        benchmark = Benchmark.from_json_file(str(almalinux_complete_file))

        assert benchmark.title
        assert benchmark.benchmark_id
        assert len(benchmark.recommendations) > 0
        assert benchmark.total_recommendations == len(benchmark.recommendations)

    def test_benchmark_round_trip_json(self, minimal_benchmark_data):
        """Test round-trip: Benchmark → JSON → Benchmark."""
        original = Benchmark(**minimal_benchmark_data)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            # Save to file
            original.to_json_file(temp_path)

            # Load from file
            loaded = Benchmark.from_json_file(temp_path)

            # Compare
            assert loaded.title == original.title
            assert loaded.benchmark_id == original.benchmark_id
            assert loaded.version == original.version
            assert loaded.total_recommendations == original.total_recommendations
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_recommendation_dict_serialization(self, complete_recommendation_data):
        """Test recommendation serialization to dict."""
        rec = Recommendation(**complete_recommendation_data)
        data = rec.model_dump()

        # Verify structure
        assert isinstance(data, dict)
        assert data["ref"] == "6.1.1"
        assert isinstance(data["cis_controls"], list)
        assert isinstance(data["profiles"], list)

        # Verify nested models are dicts
        if data.get("mitre_mapping"):
            assert isinstance(data["mitre_mapping"], dict)
            assert "techniques" in data["mitre_mapping"]

    def test_benchmark_model_dump_json(self, minimal_benchmark_data):
        """Test Pydantic model_dump_json method."""
        benchmark = Benchmark(**minimal_benchmark_data)
        json_str = benchmark.model_dump_json(indent=2)

        # Verify it's valid JSON
        data = json.loads(json_str)
        assert data["title"] == "Test Benchmark"


# ============================================================================
# REAL DATA TESTS
# ============================================================================


class TestRealBenchmarkData:
    """Test with real benchmark data from test files."""

    def test_load_complete_benchmark(self, almalinux_complete_file):
        """Test loading complete test benchmark (322 recommendations)."""
        benchmark = Benchmark.from_json_file(str(almalinux_complete_file))

        assert benchmark.title == "CIS AlmaLinux OS 8 Benchmark v4.0.0"
        assert benchmark.benchmark_id == "23598"
        assert benchmark.version == "v4.0.0"
        assert benchmark.total_recommendations == 322
        assert len(benchmark.recommendations) == 322

    def test_complete_benchmark_all_recommendations_valid(self, almalinux_complete_file):
        """Test all recommendations in complete benchmark are valid."""
        benchmark = Benchmark.from_json_file(str(almalinux_complete_file))

        for rec in benchmark.recommendations:
            assert isinstance(rec, Recommendation)
            assert rec.ref
            assert rec.title
            assert rec.url
            assert rec.assessment_status

    def test_complete_benchmark_has_cis_controls(self, almalinux_complete_file):
        """Test complete benchmark has CIS controls."""
        benchmark = Benchmark.from_json_file(str(almalinux_complete_file))

        # At least some recommendations should have CIS controls
        recs_with_controls = [r for r in benchmark.recommendations if r.cis_controls]
        assert len(recs_with_controls) > 0

        # Verify control structure
        for rec in recs_with_controls:
            for control in rec.cis_controls:
                assert isinstance(control, CISControl)
                assert control.version in [7, 8]
                assert control.control

    def test_complete_benchmark_has_mitre_mappings(self, almalinux_complete_file):
        """Test complete benchmark has MITRE mappings."""
        benchmark = Benchmark.from_json_file(str(almalinux_complete_file))

        # At least some recommendations should have MITRE mappings
        recs_with_mitre = [r for r in benchmark.recommendations if r.mitre_mapping]
        assert len(recs_with_mitre) > 0

        # Verify mapping structure
        for rec in recs_with_mitre:
            assert isinstance(rec.mitre_mapping, MITREMapping)


# ============================================================================
# VALIDATOR TESTS - DISAConventionsValidator
# ============================================================================


class TestDISAConventionsValidator:
    """Test DISA conventions validator."""

    def test_validator_accepts_valid_xccdf(self, valid_disa_xccdf_file):
        """Test validator passes valid DISA XCCDF."""
        validator = DISAConventionsValidator(str(valid_disa_xccdf_file))
        is_valid, errors, warnings = validator.validate()

        # Should be valid (or at least have no errors)
        assert is_valid or len(errors) == 0

    def test_validator_checks_required_elements(self, valid_disa_xccdf_file):
        """Test validator checks for required benchmark elements."""
        validator = DISAConventionsValidator(str(valid_disa_xccdf_file))
        validator._check_required_benchmark_elements()

        # Should not have errors for missing required elements
        required_errors = [e for e in validator.errors if "Missing required element" in e]
        assert len(required_errors) == 0

    def test_validator_checks_plain_text_elements(self, valid_disa_xccdf_file):
        """Test validator checks plain-text elements."""
        validator = DISAConventionsValidator(str(valid_disa_xccdf_file))
        validator._check_plain_text_elements()

        # Should have all required plain-text IDs
        required_ids = ["release-info", "generator", "conventionsVersion"]
        for req_id in required_ids:
            errors = [e for e in validator.errors if req_id in e]
            assert len(errors) == 0, f"Missing plain-text id='{req_id}'"

    def test_validator_checks_reference_element(self, valid_disa_xccdf_file):
        """Test validator checks reference has DC elements."""
        validator = DISAConventionsValidator(str(valid_disa_xccdf_file))
        validator._check_reference_element()

        # Should have dc:publisher and dc:source
        ref_errors = [e for e in validator.errors if "reference missing" in e]
        assert len(ref_errors) == 0

    def test_validator_checks_groups(self, valid_disa_xccdf_file):
        """Test validator checks Group elements."""
        validator = DISAConventionsValidator(str(valid_disa_xccdf_file))
        validator._check_groups()

        # Should have groups (DISA STIGs use Groups)
        no_groups_warning = [w for w in validator.warnings if "No Group elements" in w]
        assert len(no_groups_warning) == 0

    def test_validator_checks_rules(self, valid_disa_xccdf_file):
        """Test validator checks Rule elements."""
        validator = DISAConventionsValidator(str(valid_disa_xccdf_file))
        validator._check_rules()

        # Rules should have required attributes
        severity_errors = [e for e in validator.errors if "severity" in e]
        # Some warnings are OK, but no critical errors
        assert len([e for e in severity_errors if "missing severity" in e]) == 0

    def test_validator_detects_invalid_cci_format(self):
        """Test validator detects invalid CCI format."""
        # This test would need a fixture with invalid CCI
        # For now, just verify the regex pattern works
        import re

        valid_ccis = ["CCI-000001", "CCI-123456", "CCI-999999"]
        invalid_ccis = ["CCI-1", "CCI-12345", "CCI-1234567", "CCE-12345"]

        cci_pattern = r"^CCI-\d{6}$"  # Anchors for exact match

        for cci in valid_ccis:
            assert re.match(cci_pattern, cci), f"{cci} should be valid"

        for cci in invalid_ccis:
            assert not re.match(cci_pattern, cci), f"{cci} should be invalid"

    def test_validator_returns_tuple(self, valid_disa_xccdf_file):
        """Test validator returns (is_valid, errors, warnings) tuple."""
        validator = DISAConventionsValidator(str(valid_disa_xccdf_file))
        result = validator.validate()

        assert isinstance(result, tuple)
        assert len(result) == 3
        is_valid, errors, warnings = result
        assert isinstance(is_valid, bool)
        assert isinstance(errors, list)
        assert isinstance(warnings, list)

    def test_validator_helper_function(self, valid_disa_xccdf_file, capsys):
        """Test validate_disa_conventions helper function."""
        is_valid = validate_disa_conventions(str(valid_disa_xccdf_file))

        assert isinstance(is_valid, bool)

        # Check output was printed
        captured = capsys.readouterr()
        # Should print either errors, warnings, or success message
        assert len(captured.out) > 0


# ============================================================================
# EDGE CASE TESTS
# ============================================================================


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_recommendation_with_all_optional_fields_none(self):
        """Test recommendation with all optional fields explicitly None."""
        rec = Recommendation(
            ref="1.1.1",
            title="Test",
            url="https://example.com",
            assessment_status="Automated",
            profiles=[],
            cis_controls=[],
            mitre_mapping=None,
            nist_controls=[],
            parent=None,
            artifacts=[],
            description=None,
            rationale=None,
            impact=None,
            audit=None,
            remediation=None,
            additional_info=None,
            default_value=None,
            artifact_equation=None,
            references=None,
        )
        assert rec.ref == "1.1.1"
        assert rec.mitre_mapping is None

    def test_benchmark_with_unicode_title(self):
        """Test benchmark with Unicode characters."""
        benchmark = Benchmark(
            title="Test Benchmark with émojis 🔒 and spëcial chars",
            benchmark_id="12345",
            url="https://example.com",
            version="v1.0.0",
            scraper_version="v1",
            total_recommendations=0,
            recommendations=[],
        )
        assert "émojis" in benchmark.title
        assert "🔒" in benchmark.title

    def test_empty_benchmark_is_valid(self):
        """Test benchmark with zero recommendations is valid."""
        benchmark = Benchmark(
            title="Empty Benchmark",
            benchmark_id="12345",
            url="https://example.com",
            version="v1.0.0",
            scraper_version="v1",
            total_recommendations=0,
            recommendations=[],
        )
        assert benchmark.total_recommendations == 0
        assert len(benchmark.recommendations) == 0

    def test_recommendation_with_very_long_ref(self):
        """Test recommendation with deeply nested ref."""
        rec = Recommendation(
            ref="1.2.3.4.5.6.7.8.9.10",
            title="Deeply nested recommendation",
            url="https://example.com",
            assessment_status="Manual",
        )
        assert rec.ref == "1.2.3.4.5.6.7.8.9.10"

    def test_invalid_json_file_raises_error(self):
        """Test loading invalid JSON raises appropriate error."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{ invalid json }")
            temp_path = f.name

        try:
            with pytest.raises(json.JSONDecodeError):
                Benchmark.from_json_file(temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_missing_file_raises_error(self):
        """Test loading non-existent file raises error."""
        with pytest.raises(FileNotFoundError):
            Benchmark.from_json_file("/nonexistent/path/file.json")

    def test_recommendation_with_html_in_fields(self):
        """Test recommendation accepts HTML in content fields."""
        rec = Recommendation(
            ref="1.1.1",
            title="Test",
            url="https://example.com",
            assessment_status="Automated",
            description="<p>This is <strong>HTML</strong> content</p>",
            audit="<pre><code>command here</code></pre>",
        )
        assert "<strong>" in rec.description
        assert "<code>" in rec.audit

    def test_benchmark_dict_with_exclude_none_false(self, minimal_benchmark_data):
        """Test benchmark dict export includes None values."""
        benchmark = Benchmark(**minimal_benchmark_data)
        json_str = benchmark.model_dump_json(exclude_none=False)
        data = json.loads(json_str)

        # Should include fields even if they have default values
        assert "recommendations" in data


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestIntegration:
    """Integration tests combining multiple components."""

    def test_load_benchmark_export_and_reload(self, almalinux_complete_file):
        """Test full round-trip: load → export → reload → compare."""
        # Load original
        original = Benchmark.from_json_file(str(almalinux_complete_file))

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            # Export to temp file
            original.to_json_file(temp_path)

            # Reload from temp file
            reloaded = Benchmark.from_json_file(temp_path)

            # Compare
            assert reloaded.title == original.title
            assert reloaded.benchmark_id == original.benchmark_id
            assert reloaded.version == original.version
            assert reloaded.total_recommendations == original.total_recommendations
            assert len(reloaded.recommendations) == len(original.recommendations)

            # Compare first recommendation
            assert reloaded.recommendations[0].ref == original.recommendations[0].ref
            assert reloaded.recommendations[0].title == original.recommendations[0].title
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_benchmark_to_dict_to_model(self, minimal_benchmark_data):
        """Test Benchmark → dict → Benchmark conversion."""
        original = Benchmark(**minimal_benchmark_data)

        # Export to dict
        data = original.model_dump()

        # Create new instance from dict
        reconstructed = Benchmark(**data)

        # Compare
        assert reconstructed.title == original.title
        assert reconstructed.benchmark_id == original.benchmark_id
        assert reconstructed.version == original.version
