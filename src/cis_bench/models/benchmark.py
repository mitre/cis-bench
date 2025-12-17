"""Pydantic models for CIS benchmark data - Our canonical format.

This is our single source of truth for benchmark data structure.
All scrapers produce this format, all exporters consume this format.
"""

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, field_validator


class CISControl(BaseModel):
    """CIS Control mapping (v7 or v8)."""

    version: int = Field(..., description="CIS Controls version (7 or 8)")
    control: str = Field(..., description="Control ID (e.g., '4.8', '10.3')")
    title: str = Field(..., description="Control title")
    ig1: bool = Field(..., description="Implementation Group 1")
    ig2: bool = Field(..., description="Implementation Group 2")
    ig3: bool = Field(..., description="Implementation Group 3")


class MITREMapping(BaseModel):
    """MITRE ATT&CK framework mapping."""

    techniques: list[str] = Field(
        default_factory=list, description="MITRE technique IDs (e.g., ['T1068', 'T1203'])"
    )
    tactics: list[str] = Field(
        default_factory=list, description="MITRE tactic IDs (e.g., ['TA0001'])"
    )
    mitigations: list[str] = Field(
        default_factory=list, description="MITRE mitigation IDs (e.g., ['M1022'])"
    )


class Artifact(BaseModel):
    """Test artifact for automated compliance checking."""

    id: int
    view_level: str = Field(..., description="Artifact reference (e.g., '1.1.1.1.1')")
    title: str
    status: str
    artifact_type: dict[str, Any] = Field(..., description="Artifact type metadata")


class ParentReference(BaseModel):
    """Parent recommendation in hierarchy."""

    url: HttpUrl
    title: str


class Recommendation(BaseModel):
    """A single CIS recommendation within a benchmark.

    This represents one security configuration recommendation with all
    associated metadata, audit procedures, and remediation steps.
    """

    # ============ Core Metadata ============
    ref: str = Field(
        ...,
        description="Recommendation reference number (e.g., '3.1.1')",
        pattern=r"^[0-9]+(\.[0-9]+)*$",
    )

    title: str = Field(..., description="Recommendation title", min_length=1)

    url: HttpUrl = Field(..., description="Direct URL to recommendation page on CIS WorkBench")

    # ============ Classification & Compliance Mappings ============
    assessment_status: str = Field(..., description="Assessment type: 'Automated' or 'Manual'")

    profiles: list[str] = Field(
        default_factory=list,
        description="Applicable profiles (e.g., ['Level 1 - Server', 'Level 2 - Workstation'])",
    )

    cis_controls: list[CISControl] = Field(
        default_factory=list,
        description="CIS Controls v7 and v8 mappings with Implementation Groups",
    )

    mitre_mapping: MITREMapping | None = Field(
        None, description="MITRE ATT&CK framework mapping (techniques, tactics, mitigations)"
    )

    nist_controls: list[str] = Field(
        default_factory=list, description="NIST SP 800-53 control IDs (e.g., ['SI-3', 'MP-7'])"
    )

    # ============ Hierarchical Structure ============
    parent: ParentReference | None = Field(None, description="Parent recommendation in hierarchy")

    artifacts: list[Artifact] = Field(
        default_factory=list, description="Test artifacts for automated compliance checking"
    )

    # ============ Content Fields (HTML) ============
    description: str | None = Field(None, description="Detailed description (HTML format)")

    rationale: str | None = Field(None, description="Rationale/justification (HTML format)")

    impact: str | None = Field(None, description="Impact statement (HTML format)")

    audit: str | None = Field(None, description="Audit procedure (HTML format with code blocks)")

    remediation: str | None = Field(
        None, description="Remediation steps (HTML format with code blocks)"
    )

    additional_info: str | None = Field(
        None, description="Additional information and notes (HTML format)"
    )

    default_value: str | None = Field(None, description="Default configuration value (HTML format)")

    artifact_equation: str | None = Field(None, description="Artifact equation logic (HTML format)")

    references: str | None = Field(
        None, description="External references and citations (HTML format)"
    )


class Benchmark(BaseModel):
    """A complete CIS benchmark with metadata and recommendations."""

    # Required metadata
    title: str = Field(..., description="Full benchmark title")
    benchmark_id: str = Field(..., description="CIS WorkBench benchmark ID")
    url: HttpUrl = Field(..., description="Source URL")
    version: str = Field(..., description="Benchmark version")

    downloaded_at: datetime = Field(default_factory=datetime.now, description="Download timestamp")

    scraper_version: str = Field(..., description="Scraper strategy version used")

    total_recommendations: int = Field(..., ge=0)
    recommendations: list[Recommendation] = Field(...)

    @field_validator("recommendations")
    @classmethod
    def validate_recommendations_count_matches_total(cls, v, info):
        """Ensure recommendations list count matches total_recommendations field.

        This validator runs when recommendations field is set, and checks if
        total_recommendations (if already set) matches the actual count.
        """
        if "total_recommendations" in info.data:
            expected_count = info.data["total_recommendations"]
            actual_count = len(v)
            if expected_count != actual_count:
                raise ValueError(
                    f"total_recommendations field says {expected_count} but "
                    f"recommendations list has {actual_count} items"
                )
        return v

    def to_json_file(self, filepath: str):
        """Save benchmark to JSON file."""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.model_dump_json(indent=2, exclude_none=False))

    @classmethod
    def from_json_file(cls, filepath: str) -> "Benchmark":
        """Load benchmark from JSON file with validation."""
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        return cls(**data)
