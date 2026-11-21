from __future__ import annotations

from dataclasses import dataclass, field

__NAMESPACE__ = "http://cpe.mitre.org/XMLSchema/cpe/1.0"


@dataclass(kw_only=True)
class CheckType:
    """
    Data type for the check element, a checking system specification URI,
    string content, and an optional external file reference.

    The checking system specification should be the URI for a particular
    version of OVAL or a related system testing language, and the content
    will be an identifier of a test written in that language. The external
    file reference could be used to point to the file in which the content
    test identifier is defined.
    """

    class Meta:
        name = "checkType"

    value: str = field(default="")
    system: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    href: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class ReferenceType:
    """
    Type for an reference in the description of a CPE item.

    This would normally be used to point to extra descriptive material, or
    the supplier's web site, or the platform documentation. It consists of
    a piece of text (intended to be human-readable) and a URI (intended to
    be a URL, and point to a real resource).
    """

    class Meta:
        name = "referenceType"

    value: str = field(default="")
    href: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class CpeItem:
    """
    This element denotes a single name in the Common Platform Enumeration.

    It has the following parts: - name, a URI, which must be a unique key,
    and should follow the URI structure outlined in the CPE specification.
    - title, arbitrary friendly name - notes, optional descriptive material
    - references, optional external info references - check, optional
    reference to an OVAL test that can confirm or reject an IT system as an
    instance of the named platform.
    """

    class Meta:
        name = "cpe-item"
        namespace = "http://cpe.mitre.org/XMLSchema/cpe/1.0"

    title: str = field(
        metadata={
            "type": "Element",
        }
    )
    notes: None | CpeItem.Notes = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    references: None | CpeItem.References = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    check: list[CheckType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    name: str = field(
        metadata={
            "type": "Attribute",
        }
    )

    @dataclass(kw_only=True)
    class Notes:
        note: list[str] = field(
            default_factory=list,
            metadata={
                "type": "Element",
                "min_occurs": 1,
            },
        )

    @dataclass(kw_only=True)
    class References:
        reference: list[ReferenceType] = field(
            default_factory=list,
            metadata={
                "type": "Element",
                "min_occurs": 1,
            },
        )


@dataclass(kw_only=True)
class CpeList:
    """
    This element acts as a top-level container for CPE name items.
    """

    class Meta:
        name = "cpe-list"
        namespace = "http://cpe.mitre.org/XMLSchema/cpe/1.0"

    cpe_item: list[CpeItem] = field(
        default_factory=list,
        metadata={
            "name": "cpe-item",
            "type": "Element",
            "min_occurs": 1,
        },
    )
