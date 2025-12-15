"""Enhanced Metadata Models for CIS XCCDF Extensions.

These models define the enhanced namespace for data not in official CIS XCCDF:
- MITRE ATT&CK mappings (techniques, tactics, mitigations)
- Additional profile information
- Custom annotations

Namespace: http://cisecurity.org/xccdf/enhanced/1.0

This follows XCCDF best practices for extensibility:
- Separate namespace for extensions
- Tools can safely ignore unknown elements
- Forward-compatible when CIS adds official support
"""

from dataclasses import dataclass, field


@dataclass
class Technique:
    """MITRE ATT&CK Technique reference.

    Example:
        <technique id="T1565.001">Data Manipulation: Stored Data Manipulation</technique>
    """

    class Meta:
        name = "technique"
        namespace = "http://cisecurity.org/xccdf/enhanced/1.0"

    id: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )
    value: str = field(
        default="",
        metadata={
            "required": True,
        },
    )


@dataclass
class Tactic:
    """MITRE ATT&CK Tactic reference.

    Example:
        <tactic id="TA0040">Impact</tactic>
    """

    class Meta:
        name = "tactic"
        namespace = "http://cisecurity.org/xccdf/enhanced/1.0"

    id: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )
    value: str = field(
        default="",
        metadata={
            "required": True,
        },
    )


@dataclass
class Mitigation:
    """MITRE ATT&CK Mitigation reference.

    Example:
        <mitigation id="M1022">Restrict File and Directory Permissions</mitigation>
    """

    class Meta:
        name = "mitigation"
        namespace = "http://cisecurity.org/xccdf/enhanced/1.0"

    id: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )
    value: str = field(
        default="",
        metadata={
            "required": True,
        },
    )


@dataclass
class MitreMetadata:
    """Container for MITRE ATT&CK mappings.

    Groups techniques, tactics, and mitigations for a recommendation.

    Example:
        <mitre xmlns="http://cisecurity.org/xccdf/enhanced/1.0">
          <technique id="T1565.001">Data Manipulation</technique>
          <tactic id="TA0040">Impact</tactic>
          <mitigation id="M1022">Restrict File Permissions</mitigation>
        </mitre>
    """

    class Meta:
        name = "mitre"
        namespace = "http://cisecurity.org/xccdf/enhanced/1.0"

    technique: list[Technique] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    tactic: list[Tactic] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    mitigation: list[Mitigation] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )


@dataclass
class Profile:
    """CIS Profile membership indicator.

    Indicates which profiles this recommendation belongs to.
    Note: CIS official format uses top-level <Profile> elements with <select> statements.
    This is our simplified metadata representation.

    Example:
        <profile>Level 1 - Server</profile>
    """

    class Meta:
        name = "profile"
        namespace = "http://cisecurity.org/xccdf/enhanced/1.0"

    value: str = field(
        default="",
        metadata={
            "required": True,
        },
    )


@dataclass
class EnhancedMetadata:
    """Container for all enhanced metadata extensions.

    Groups MITRE mappings, profiles, and other custom data.

    Example:
        <enhanced xmlns="http://cisecurity.org/xccdf/enhanced/1.0">
          <mitre>...</mitre>
          <profile>Level 1 - Server</profile>
        </enhanced>
    """

    class Meta:
        name = "enhanced"
        namespace = "http://cisecurity.org/xccdf/enhanced/1.0"

    mitre: MitreMetadata | None = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    profile: list[Profile] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
