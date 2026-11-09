"""Pydantic models for CIS benchmark data - Our canonical format.

This is our single source of truth for benchmark data structure.
All scrapers produce this format, all exporters consume this format.
"""

import json
from datetime import UTC, date, datetime
from typing import Annotated, Any, Final, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    field_validator,
    model_validator,
)

from cis_bench.utils.markdown_text import html_to_markdown, unix_line_breaks

# Scraper strategy versions that saved the page's rendered HTML in recommendation text.
# WorkbenchV1Strategy (v1_2025_10, the first strategy) copied each field's HTML from the
# page; WorkbenchV2Strategy (v2_2026_01, its successor) reads the Markdown WorkBench gives.
# A stored copy names the strategy that saved it in scraper_version, and a copy from one
# of these versions is converted to Markdown when it loads (Benchmark.text_as_markdown).
HTML_ERA_SCRAPER_VERSIONS: Final[frozenset[str]] = frozenset({"v1_2025_10"})

# A recommendation's text fields: Markdown in a loaded copy, with \n line breaks.
RECOMMENDATION_TEXT_FIELDS: Final[tuple[str, ...]] = (
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

    # ============ Content Fields (Markdown, as WorkBench gives it) ============
    description: str | None = Field(None, description="Detailed description (Markdown)")

    rationale: str | None = Field(None, description="Rationale/justification (Markdown)")

    impact: str | None = Field(None, description="Impact statement (Markdown)")

    audit: str | None = Field(None, description="Audit procedure (Markdown with code blocks)")

    remediation: str | None = Field(
        None, description="Remediation steps (Markdown with code blocks)"
    )

    additional_info: str | None = Field(
        None, description="Additional information and notes (Markdown)"
    )

    default_value: str | None = Field(None, description="Default configuration value (Markdown)")

    artifact_equation: str | None = Field(None, description="Artifact equation logic (Markdown)")

    references: str | None = Field(None, description="External references and citations (Markdown)")

    @field_validator(*RECOMMENDATION_TEXT_FIELDS)
    @classmethod
    def line_breaks_are_newlines(cls, value: str | None) -> str | None:
        """Every text field's line breaks are \\n; WorkBench's Markdown comes with \\r\\n."""
        return None if value is None else unix_line_breaks(value)

    @field_validator("profiles")
    @classmethod
    def one_entry_per_profile(cls, profiles: list[str]) -> list[str]:
        """One entry per profile, whatever the source gave.

        WorkBench's recommendation page gives a rule's profiles as one text with a line
        break between the names, and copies saved before this rule hold that text as a
        single entry. Every line is a profile: stripped, empty lines dropped, first
        appearance kept in order.
        """
        names = (line.strip() for entry in profiles for line in entry.splitlines())
        return list(dict.fromkeys(name for name in names if name))


class ProfileDefinition(BaseModel):
    """One of a benchmark's profiles as its WorkBench page defines it."""

    model_config = ConfigDict(frozen=True)

    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] = Field(
        ..., description="Profile title, as rules name it"
    )
    description: str | None = Field(None, description="What the profile is for (HTML format)")
    parent: Annotated[str, StringConstraints(strip_whitespace=True)] | None = Field(
        None, description="Title of the profile this one extends (its rules are included)"
    )

    @field_validator("description", "parent")
    @classmethod
    def blank_is_none(cls, value: str | None) -> str | None:
        """Blank text is no description or no parent."""
        return value if value and value.strip() else None


def one_definition_per_title(definitions: list[ProfileDefinition]) -> list[ProfileDefinition]:
    """Rules name profiles by title, so a benchmark defines each title once."""
    seen: set[str] = set()
    for definition in definitions:
        if definition.title in seen:
            raise ValueError(f"profile {definition.title!r} is defined more than once")
        seen.add(definition.title)
    return definitions


ProfileDefinitions = Annotated[list[ProfileDefinition], AfterValidator(one_definition_per_title)]


class BenchmarkPage(BaseModel):
    """What a benchmark's own WorkBench page says about the release.

    Read whenever a command fetches the page (every download, and an online check-updates)
    and recorded on the release's catalog row; the catalog listing carries none of it.
    """

    model_config = ConfigDict(frozen=True)

    title: str
    published_date: date | None = None
    description: str | None = None
    profile_definitions: ProfileDefinitions = Field(default_factory=list)


class Benchmark(BaseModel):
    """A complete CIS benchmark with metadata and recommendations."""

    # Required metadata
    title: str = Field(..., description="Full benchmark title")
    benchmark_id: str = Field(..., description="CIS WorkBench benchmark ID")
    url: HttpUrl = Field(..., description="Source URL")
    version: str = Field(..., description="Benchmark version")
    published_date: date | None = Field(
        None,
        description="The date WorkBench shows this release as published, read from its page",
    )
    description: str | None = Field(
        None, description="The benchmark's overview, as plain text, read from its page"
    )
    profile_definitions: ProfileDefinitions = Field(
        default_factory=list,
        description="The benchmark's profiles as its page defines them (title, description, "
        "the profile each extends); empty for copies saved before they were read",
    )

    downloaded_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the benchmark was downloaded, with its zone (UTC)",
    )

    scraper_version: str = Field(..., description="Scraper strategy version used")

    text_format: Literal["html", "markdown"] = Field(
        default="markdown",
        description="The form of the recommendation text fields as written: 'markdown', the "
        "form WorkBench gives and every loaded copy holds, or 'html' for a copy the v1 "
        "scraper saved, which is converted to Markdown when it loads. A stored copy without "
        "this field is 'html' when its scraper_version saved HTML and 'markdown' otherwise",
    )

    total_recommendations: int = Field(..., ge=0)
    recommendations: list[Recommendation] = Field(...)

    @model_validator(mode="before")
    @classmethod
    def text_format_of_a_copy_saved_without_one(cls, data: Any) -> Any:
        """A copy saved before text_format existed names its text's form by its scraper."""
        if isinstance(data, dict) and "text_format" not in data:
            html_era = data.get("scraper_version") in HTML_ERA_SCRAPER_VERSIONS
            return {**data, "text_format": "html" if html_era else "markdown"}
        return data

    @model_validator(mode="after")
    def text_as_markdown(self) -> "Benchmark":
        """A loaded copy holds Markdown: HTML a v1-era copy saved is converted here."""
        if self.text_format == "html":
            for recommendation in self.recommendations:
                for name in RECOMMENDATION_TEXT_FIELDS:
                    value = getattr(recommendation, name)
                    if value:
                        setattr(recommendation, name, html_to_markdown(value))
            self.text_format = "markdown"
        return self

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
