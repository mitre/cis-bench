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

from cis_bench.catalog.database import deserialize_benchmark_json

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
#   - synthetic_complete_file (points to tests/fixtures/benchmarks/synthetic_complete.json)
#   - valid_disa_xccdf_file (points to tests/fixtures/xccdf/generated/disa/valid_disa_full.xml)


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
        "title": "Ensure filesystem integrity verification agent is active",
        "url": "https://workbench.cisecurity.org/sections/900010/recommendations/900611",
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
        "description": "<p>Periodic cryptographic checksum verification detects tampering.</p>",
        "rationale": "<p>Security rationale here</p>",
        "impact": "<p>Impact statement</p>",
        "audit": "<p>Run: <code>integrity-agent --status</code></p>",
        "remediation": "<p>Run: <code>service-ctl enable --now integrity-agent</code></p>",
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

    def test_profiles_joined_by_a_line_break_are_one_entry_each(self, minimal_recommendation_data):
        # WorkBench gives a rule's profiles as one text with a Markdown line break between them.
        rec = Recommendation(
            **minimal_recommendation_data,
            profiles=["Level 1 - Server  \nLevel 1 - Workstation"],
        )
        assert rec.profiles == ["Level 1 - Server", "Level 1 - Workstation"]

    def test_profiles_are_stripped_kept_in_order_and_listed_once(self, minimal_recommendation_data):
        rec = Recommendation(
            **minimal_recommendation_data,
            profiles=[
                "  Level 2 - Server  ",
                "",
                "Level 1 - Server\r\nLevel 2 - Server",
                "\n",
                "Level 2 - Workstation",
            ],
        )
        assert rec.profiles == ["Level 2 - Server", "Level 1 - Server", "Level 2 - Workstation"]

    def test_a_cached_copy_with_joined_profiles_loads_one_entry_per_profile(
        self, minimal_benchmark_data, minimal_recommendation_data
    ):
        stored = json.dumps(
            {
                **minimal_benchmark_data,
                "total_recommendations": 1,
                "recommendations": [
                    {
                        **minimal_recommendation_data,
                        "profiles": ["Level 2 - Server  \nLevel 2 - Workstation"],
                    }
                ],
            }
        )

        benchmark = deserialize_benchmark_json(stored)

        assert benchmark.recommendations[0].profiles == [
            "Level 2 - Server",
            "Level 2 - Workstation",
        ]

    def test_a_copy_saved_before_profile_definitions_loads_with_none(self, minimal_benchmark_data):
        stored = json.dumps(minimal_benchmark_data)  # no profile_definitions key

        assert deserialize_benchmark_json(stored).profile_definitions == []

    def test_a_benchmark_defines_each_profile_title_once(self, minimal_benchmark_data):
        # Profile titles are what rules name; two definitions of one title are ambiguous.
        definition = {"title": "Level 1 - Alpha"}
        stored = json.dumps({**minimal_benchmark_data, "profile_definitions": [definition] * 2})

        with pytest.raises(ValidationError, match="'Level 1 - Alpha'"):
            deserialize_benchmark_json(stored)

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
        # Validator exists - test it works
        with pytest.raises(ValidationError) as exc:
            Benchmark(
                title="Test",
                benchmark_id="12345",
                url="https://example.org",
                version="1.0.0",
                scraper_version="v1",
                total_recommendations=5,  # Says 5
                recommendations=[],  # But has 0!
            )
        assert "total_recommendations" in str(exc.value)

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
        assert benchmark.downloaded_at.tzinfo is not None
        assert benchmark.downloaded_at.utcoffset().total_seconds() == 0

    def test_benchmark_downloaded_at_is_written_with_its_offset(self, minimal_benchmark_data):
        minimal_benchmark_data.pop("downloaded_at", None)
        benchmark = Benchmark(**minimal_benchmark_data)

        written = json.loads(benchmark.model_dump_json())["downloaded_at"]

        assert datetime.fromisoformat(written) == benchmark.downloaded_at
        assert datetime.fromisoformat(written).tzinfo is not None

    def test_a_zoneless_downloaded_at_from_an_earlier_file_is_kept_as_it_is(
        self, minimal_benchmark_data
    ):
        minimal_benchmark_data["downloaded_at"] = "2026-11-06T20:05:58.615168"

        benchmark = Benchmark(**minimal_benchmark_data)

        assert benchmark.downloaded_at == datetime(2026, 11, 6, 20, 5, 58, 615168)
        assert benchmark.downloaded_at.tzinfo is None

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


# What a benchmark's WorkBench page says about it beyond its recommendations, in our own
# words: release type, contributors, the benchmark it came from, community, milestone,
# audience, acknowledgements, assets (CPE names) and revision history.
PAGE_METADATA = {
    "release_type": "Planned Update",
    "contributors": ["Alex Example", "Sam Sample", "Alex Example"],
    "parent_benchmark_url": "https://workbench.cisecurity.org/benchmarks/11111",
    "parent_benchmark_title": "CIS Example Platform Benchmark v1.0.0",
    "community_url": "https://workbench.cisecurity.org/communities/42",
    "milestone_name": "Example Platform v2.0.0",
    "milestone_url": "https://workbench.cisecurity.org/community/42/milestones/7",
    "intended_audience": "Administrators who install and run the example platform.",
    "acknowledgements": "The example platform community.",
    "assets": [
        {"title": "Example OS 9", "cpe_id": "cpe:2.3:o:example:example_os:9:*:*:*:*:*:*:*"},
        {"title": "Example OS 10", "cpe_id": "cpe:2.3:o:example:example_os:10:*:*:*:*:*:*:*"},
    ],
    "revision_history": [
        {"revised_at": "2025-09-23T14:54:00", "author": "Alex", "modification_count": 1},
        {"revised_at": "2025-09-23T14:53:00", "author": "Sam", "modification_count": 2},
    ],
}


class TestBenchmarkPageMetadata:
    """The page metadata a Benchmark carries is kept through the stored JSON."""

    def test_the_page_metadata_round_trips_through_the_stored_json(self, minimal_benchmark_data):
        from cis_bench.catalog.database import serialize_benchmark_json

        benchmark = Benchmark(**minimal_benchmark_data, **PAGE_METADATA)

        content_json, _ = serialize_benchmark_json(benchmark)
        stored = json.loads(content_json)
        loaded = deserialize_benchmark_json(content_json)

        for name, value in PAGE_METADATA.items():
            assert stored[name] == value, name
        assert loaded == benchmark

    def test_the_page_metadata_round_trips_through_a_json_file(
        self, minimal_benchmark_data, tmp_path
    ):
        benchmark = Benchmark(**minimal_benchmark_data, **PAGE_METADATA)
        path = tmp_path / "benchmark.json"

        benchmark.to_json_file(str(path))
        loaded = Benchmark.from_json_file(str(path)).model_dump(mode="json")

        for name, value in PAGE_METADATA.items():
            assert loaded.get(name) == value, name

    def test_a_copy_saved_before_the_page_metadata_loads_with_none_and_empty_lists(
        self, minimal_benchmark_data
    ):
        loaded = deserialize_benchmark_json(json.dumps(minimal_benchmark_data))

        dumped = loaded.model_dump()
        for name in PAGE_METADATA:
            assert name in dumped, name
            expected = [] if isinstance(PAGE_METADATA[name], list) else None
            assert dumped[name] == expected, name

    def test_an_asset_needs_its_cpe_name(self, minimal_benchmark_data):
        with pytest.raises(ValidationError, match="cpe_id"):
            Benchmark(**minimal_benchmark_data, assets=[{"title": "Example OS 9"}])

    def test_the_page_metadata_is_part_of_the_content_hash(self, minimal_benchmark_data):
        # A copy whose page metadata changed is different content.
        from cis_bench.catalog.database import serialize_benchmark_json

        _, before = serialize_benchmark_json(Benchmark(**minimal_benchmark_data))
        _, after = serialize_benchmark_json(
            Benchmark(**minimal_benchmark_data, release_type="Planned Update")
        )

        assert before != after


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

    def test_benchmark_from_json_file(self, synthetic_complete_file):
        """Test loading benchmark from JSON file."""
        benchmark = Benchmark.from_json_file(str(synthetic_complete_file))

        assert benchmark.title == "CIS Synthetic Enterprise Platform Benchmark v1.0.0"
        assert benchmark.benchmark_id == "90001"
        assert len(benchmark.recommendations) == 20
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
# SYNTHETIC FIXTURE DATA TESTS
# ============================================================================


class TestSyntheticBenchmarkData:
    """Test deterministic platform-agnostic synthetic benchmark fixture."""

    def test_load_synthetic_complete_benchmark(self, synthetic_complete_file):
        """Test loading complete synthetic benchmark and verifying full domain coverage."""
        import re

        from cis_bench.utils.cci_lookup import get_cci_service

        benchmark = Benchmark.from_json_file(str(synthetic_complete_file))

        assert benchmark.title == "CIS Synthetic Enterprise Platform Benchmark v1.0.0"
        assert benchmark.benchmark_id == "90001"
        assert benchmark.version == "v1.0.0"
        assert benchmark.total_recommendations == 20
        assert len(benchmark.recommendations) == 20

        refs = [r.ref for r in benchmark.recommendations]
        assert refs[0] == "1.1.1"
        assert refs[-1] == "6.2.1"
        assert len({ref.split(".")[0] for ref in refs}) == 6

        profiles_seen = {p for r in benchmark.recommendations for p in r.profiles}
        assert profiles_seen == {
            "Level 1 - Server",
            "Level 1 - Workstation",
            "Level 2 - Server",
            "Level 2 - Workstation",
        }

        statuses_seen = {r.assessment_status for r in benchmark.recommendations}
        assert statuses_seen == {"Automated", "Manual"}

        recs_with_parent = [r for r in benchmark.recommendations if r.parent is not None]
        recs_with_artifacts = [r for r in benchmark.recommendations if r.artifacts]
        assert len(recs_with_parent) >= 4
        assert len(recs_with_artifacts) >= 4

        cci_service = get_cci_service()
        resolved_ccis: list[str] = []
        for rec in benchmark.recommendations:
            if rec.cis_controls:
                ccis, _ = cci_service.deduplicate_nist_controls(
                    [c.control for c in rec.cis_controls],
                    rec.nist_controls,
                )
                resolved_ccis.extend(ccis)
        assert len(resolved_ccis) >= 40
        assert all(re.fullmatch(r"CCI-\d{6}", cci) for cci in resolved_ccis)

        # The fixture was saved by the v1 scraper, so its text loads as Markdown holding
        # the shapes exports have to carry: inline code, fences, lists, tables, and the
        # characters XML has to escape
        combined_text = "\n".join(
            field
            for r in benchmark.recommendations
            for field in (
                r.description,
                r.rationale,
                r.impact,
                r.audit,
                r.remediation,
                r.additional_info,
                r.default_value,
            )
            if field
        )
        for token in ("`", "```\n", "\n- ", "| --- |", "&", "<", ">", '"', "'"):
            assert token in combined_text, f"Expected Markdown token {token!r} in synthetic fixture"

    def test_complete_benchmark_all_recommendations_valid(self, synthetic_complete_file):
        """Test all recommendations in complete synthetic benchmark are valid."""
        benchmark = Benchmark.from_json_file(str(synthetic_complete_file))

        for rec in benchmark.recommendations:
            assert isinstance(rec, Recommendation)
            assert rec.ref
            assert rec.title
            assert rec.url
            assert rec.assessment_status in {"Automated", "Manual"}

    def test_complete_benchmark_has_cis_controls(self, synthetic_complete_file):
        """Test synthetic benchmark has dual v7 + v8 CIS controls and IG combinations."""
        benchmark = Benchmark.from_json_file(str(synthetic_complete_file))

        recs_with_controls = [r for r in benchmark.recommendations if r.cis_controls]
        assert len(recs_with_controls) == 19

        ig_tuples: set[tuple[bool, bool, bool]] = set()
        for rec in recs_with_controls:
            versions = {c.version for c in rec.cis_controls}
            assert versions == {7, 8}
            for control in rec.cis_controls:
                assert isinstance(control, CISControl)
                assert control.control
                ig_tuples.add((control.ig1, control.ig2, control.ig3))

        assert (True, True, True) in ig_tuples
        assert (False, True, True) in ig_tuples
        assert (False, False, True) in ig_tuples

    def test_complete_benchmark_has_mitre_mappings(self, synthetic_complete_file):
        """Test synthetic benchmark has MITRE techniques, tactics, and mitigations."""
        benchmark = Benchmark.from_json_file(str(synthetic_complete_file))

        recs_with_mitre = [r for r in benchmark.recommendations if r.mitre_mapping]
        assert len(recs_with_mitre) == 18

        for rec in recs_with_mitre:
            assert isinstance(rec.mitre_mapping, MITREMapping)
            assert rec.mitre_mapping.techniques
            assert rec.mitre_mapping.tactics
            assert rec.mitre_mapping.mitigations


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

    def test_load_benchmark_export_and_reload(self, synthetic_complete_file):
        """Test full round-trip: load → export → reload → compare."""
        # Load original
        original = Benchmark.from_json_file(str(synthetic_complete_file))

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


# ============================================================================
# LOADED TEXT IS MARKDOWN WITH \n LINE BREAKS
# ============================================================================


def _copy(minimal_benchmark_data, scraper_version, **text_fields):
    """A stored copy with one recommendation whose text fields are the given ones."""
    recommendation = {
        "ref": "5.4.1.2",
        "title": "Ensure minimum password days is configured",
        "url": "https://workbench.cisecurity.org/sections/1/recommendations/2",
        "assessment_status": "Automated",
        **text_fields,
    }
    return {
        **minimal_benchmark_data,
        "scraper_version": scraper_version,
        "total_recommendations": 1,
        "recommendations": [recommendation],
    }


class TestLoadedTextIsMarkdown:
    """A loaded copy holds Markdown with \\n line breaks whatever scraper saved it.

    The v1 scraper (v1_2025_10) saved the page's rendered HTML, with placeholders such as
    <user> escaped as entities; the v2 scraper saves the Markdown WorkBench gives, where a
    placeholder is bare angle brackets, and often with Windows line breaks.
    """

    def test_a_copy_saved_by_the_v1_scraper_loads_with_a_fenced_code_block(
        self, minimal_benchmark_data
    ):
        data = _copy(
            minimal_benchmark_data,
            "v1_2025_10",
            remediation="<p>Run:</p><pre><code># chage --mindays &lt;N&gt; &lt;user&gt;</code></pre>",
        )

        remediation = Benchmark(**data).recommendations[0].remediation

        assert remediation == "Run:\n\n```\n# chage --mindays <N> <user>\n```"

    def test_a_v1_copy_keeps_words_structure_and_placeholders(self, minimal_benchmark_data):
        data = _copy(
            minimal_benchmark_data,
            "v1_2025_10",
            audit=(
                "<p>Run the following for each <code>&lt;user&gt;</code> and check "
                "<strong>net.ipv4.ip_forward</strong>:</p>"
                "<ul><li>one</li><li>two</li></ul>"
                "<ol><li>first</li><li>second</li></ol>"
            ),
        )

        audit = Benchmark(**data).recommendations[0].audit

        assert audit == (
            "Run the following for each `<user>` and check **net.ipv4.ip_forward**:\n\n"
            "- one\n- two\n\n1. first\n2. second"
        )

    def test_every_text_field_of_a_v1_copy_is_converted(self, minimal_benchmark_data):
        fields = {
            name: f"<p>{name} with <code>&lt;path&gt;</code></p>"
            for name in (
                "description",
                "rationale",
                "impact",
                "audit",
                "remediation",
                "additional_info",
                "default_value",
                "artifact_equation",
                "references",
            )
        }

        recommendation = Benchmark(**_copy(minimal_benchmark_data, "v1_2025_10", **fields))
        loaded = recommendation.recommendations[0]

        assert {name: getattr(loaded, name) for name in fields} == {
            name: f"{name} with `<path>`" for name in fields
        }

    def test_a_v1_copy_with_a_field_left_empty_keeps_it_empty(self, minimal_benchmark_data):
        data = _copy(minimal_benchmark_data, "v1_2025_10", impact=None, default_value="")

        loaded = Benchmark(**data).recommendations[0]

        assert (loaded.impact, loaded.default_value) == (None, "")

    def test_a_v2_copy_is_not_converted_so_its_placeholders_survive(self, minimal_benchmark_data):
        remediation = "Run:\n\n```\n# chage --mindays <N> <user>\n```\n\n# A heading\n\n- item"
        data = _copy(minimal_benchmark_data, "v2_2026_01", remediation=remediation)

        assert Benchmark(**data).recommendations[0].remediation == remediation

    def test_a_v2_copy_with_windows_line_breaks_loads_with_unix_ones_and_nothing_else_changed(
        self, minimal_benchmark_data
    ):
        downloaded = {**minimal_benchmark_data, "downloaded_at": "2026-04-18T12:00:00Z"}
        windows = _copy(
            downloaded,
            "v2_2026_01",
            description="First line\r\nSecond line\r\n\r\nThird\rFourth",
            audit="```\r\n# stat <path>\r\n```",
            remediation="unchanged",
        )
        unix = _copy(
            downloaded,
            "v2_2026_01",
            description="First line\nSecond line\n\nThird\nFourth",
            audit="```\n# stat <path>\n```",
            remediation="unchanged",
        )

        assert Benchmark(**windows).model_dump() == Benchmark(**unix).model_dump()

    def test_a_v1_copy_written_out_and_loaded_again_holds_the_same_text(
        self, minimal_benchmark_data, tmp_path
    ):
        data = _copy(
            minimal_benchmark_data,
            "v1_2025_10",
            remediation="<p>Run:</p><pre><code># chage --mindays &lt;N&gt; &lt;user&gt;</code></pre>",
        )
        loaded = Benchmark(**data)
        path = tmp_path / "copy.json"
        loaded.to_json_file(str(path))

        reloaded = Benchmark.from_json_file(str(path))

        assert reloaded.model_dump() == loaded.model_dump()

    def test_the_html_era_versions_are_the_v1_strategy_and_not_the_v2_one(self):
        from cis_bench.fetcher.strategies.v1_current import WorkbenchV1Strategy
        from cis_bench.fetcher.strategies.v2_2026 import WorkbenchV2Strategy
        from cis_bench.models.benchmark import HTML_ERA_SCRAPER_VERSIONS

        assert WorkbenchV1Strategy().version in HTML_ERA_SCRAPER_VERSIONS
        assert WorkbenchV2Strategy().version not in HTML_ERA_SCRAPER_VERSIONS

    def test_a_v1_copy_built_twice_from_the_same_recommendation_objects_converts_each_time_once(
        self, minimal_benchmark_data
    ):
        html = "<p>Run <code>chage --mindays &lt;N&gt; &lt;user&gt;</code></p>"
        recommendation = Recommendation(
            ref="5.4.1.2",
            title="Ensure minimum password days is configured",
            url="https://workbench.cisecurity.org/sections/1/recommendations/2",
            assessment_status="Automated",
            remediation=html,
        )
        data = {
            **minimal_benchmark_data,
            "scraper_version": "v1_2025_10",
            "total_recommendations": 1,
            "recommendations": [recommendation],
        }

        first = Benchmark(**data)
        second = Benchmark(**data)

        assert recommendation.remediation == html
        assert first.recommendations[0].remediation == "Run `chage --mindays <N> <user>`"
        assert second.recommendations[0].remediation == first.recommendations[0].remediation

    def test_a_line_break_the_v1_html_spelled_as_an_entity_loads_as_a_newline(
        self, minimal_benchmark_data
    ):
        data = _copy(
            minimal_benchmark_data,
            "v1_2025_10",
            audit="<pre><code>line one&#13;\nline two&#13;</code></pre>",
        )

        audit = Benchmark(**data).recommendations[0].audit

        assert audit == "```\nline one\nline two\n```"

    def test_a_loaded_v1_copy_dumped_without_its_defaults_loads_again_unchanged(
        self, minimal_benchmark_data
    ):
        data = _copy(
            minimal_benchmark_data,
            "v1_2025_10",
            remediation="<p>Run:</p><pre><code># chage --mindays &lt;N&gt; &lt;user&gt;</code></pre>",
        )
        loaded = Benchmark(**data)

        reloaded = Benchmark.model_validate_json(loaded.model_dump_json(exclude_defaults=True))

        assert reloaded.model_dump() == loaded.model_dump()


class TestArtifactTitlesAreMarkdown:
    """A loaded copy's artifact titles are Markdown, converted once.

    WorkBench's artifact payload gives some titles as HTML (``<p>...</p>``); the parser
    converts them as the payload is read, and a copy saved before that holds them as the
    payload gave them. artifact_title_format says which form a copy holds: a copy saved
    without it is html and is converted once as it loads. The form is never read from the
    text itself: a placeholder such as <user> looks like a tag.
    """

    def _copy_with_an_artifact(self, minimal_benchmark_data, title, **fields):
        data = _copy(minimal_benchmark_data, "v2_2026_01")
        data["recommendations"][0]["artifacts"] = [
            {
                "id": 7,
                "view_level": "5.4.1.2.1",
                "title": title,
                "status": "accepted",
                "artifact_type": {},
            }
        ]
        return {**data, **fields}

    def test_a_copy_saved_without_the_marker_loads_with_the_title_as_markdown(
        self, minimal_benchmark_data
    ):
        data = self._copy_with_an_artifact(
            minimal_benchmark_data, "<p>Ensure the agent is <em>active</em></p>"
        )

        loaded = Benchmark(**data)

        assert loaded.recommendations[0].artifacts[0].title == "Ensure the agent is *active*"
        assert loaded.artifact_title_format == "markdown"

    def test_a_copy_marked_markdown_keeps_a_title_with_a_placeholder(self, minimal_benchmark_data):
        title = "Ensure <user> owns the file"
        data = self._copy_with_an_artifact(
            minimal_benchmark_data, title, artifact_title_format="markdown"
        )

        assert Benchmark(**data).recommendations[0].artifacts[0].title == title

    def test_a_loaded_copy_dumped_and_loaded_again_keeps_the_placeholder_its_html_title_held(
        self, minimal_benchmark_data
    ):
        data = self._copy_with_an_artifact(
            minimal_benchmark_data, "<p>Ensure &lt;user&gt; owns the file</p>"
        )
        loaded = Benchmark(**data)

        reloaded = Benchmark.model_validate_json(loaded.model_dump_json(exclude_defaults=True))

        assert reloaded.recommendations[0].artifacts[0].title == "Ensure <user> owns the file"
        assert reloaded.model_dump() == loaded.model_dump()

    def test_a_v1_copy_converts_its_text_fields_and_its_artifact_titles_once(
        self, minimal_benchmark_data
    ):
        data = _copy(
            minimal_benchmark_data, "v1_2025_10", remediation="<p>Run <code>&lt;cmd&gt;</code></p>"
        )
        data["recommendations"][0]["artifacts"] = [
            {
                "id": 7,
                "view_level": "5.4.1.2.1",
                "title": "<p>Ensure &lt;user&gt; owns the file</p>",
                "status": "accepted",
                "artifact_type": {},
            }
        ]

        recommendation = Benchmark(**data).recommendations[0]

        assert (recommendation.remediation, recommendation.artifacts[0].title) == (
            "Run `<cmd>`",
            "Ensure <user> owns the file",
        )


class TestRecommendationCountMismatchCountsTheItems:
    @pytest.mark.parametrize(("kept", "noun"), [(1, "item"), (2, "items")])
    def test_the_message_agrees_with_the_number(self, sample_recommendation_complete, kept, noun):
        from datetime import UTC, datetime

        from pydantic import ValidationError

        from cis_bench.models.benchmark import Benchmark

        with pytest.raises(ValidationError, match=rf"recommendations list has {kept} {noun}(?!s)"):
            Benchmark(
                title="Synthetic",
                benchmark_id="90001",
                url="https://workbench.cisecurity.org/benchmarks/90001",
                version="v1.0.0",
                downloaded_at=datetime(2026, 11, 1, tzinfo=UTC),
                scraper_version="v1_2025_10",
                total_recommendations=5,
                recommendations=[sample_recommendation_complete] * kept,
            )
