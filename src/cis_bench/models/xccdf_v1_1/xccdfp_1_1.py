from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from cis_bench.models.xccdf_v1_1.xml import LangValue

__NAMESPACE__ = "http://checklists.nist.gov/xccdf-p/1.1"


@dataclass(kw_only=True)
class CheckContentRefType:
    """
    Data type for the check-content-ref element, which points to the code
    for a detached check in another file.

    This element has no body, just a couple of attributes: href and name.
    The name is optional, if it does not appear then this reference is to
    the entire other document.
    """

    class Meta:
        name = "checkContentRefType"

    href: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    name: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class CheckContentType:
    """
    Data type for the check-content element, which holds the actual code of
    an enveloped check in some other (non-XCCDF-P) language.

    This element can hold almost anything. The content is not meaningful as
    XCCDF-P, though tools may process it or hand it off to other tools.
    """

    class Meta:
        name = "checkContentType"

    content: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Wildcard",
            "namespace": "##any",
            "mixed": True,
        },
    )


@dataclass(kw_only=True)
class FactRefType:
    """
    Type for a reference to Fact; the reference is always by name.

    This is the type for the element fact-ref, which can appear in a
    Platform definition or in a logical-test in a Platform definition.
    """

    class Meta:
        name = "factRefType"

    name: str = field(
        metadata={
            "type": "Attribute",
        }
    )


class LogicOperatorEnumType(Enum):
    """
    Allowed operators for logic tests: we only have two, AND and OR.

    They're capitalized for consistency with usage in OVAL v4.
    """

    OR = "OR"
    AND = "AND"


@dataclass(kw_only=True)
class CheckType:
    """
    Data type for the check element, a checking system specification URI,
    and XML content.

    The check element may appear inside a Fact, giving a means to ascertain
    the value of that Fact using a particular checking engine. (This
    checkType is based on the one in XCCDF, but is somewhat simpler. It
    does not include the notion of exporting values from the scope of an
    XCCDF document to the checking engine.).
    """

    class Meta:
        name = "checkType"

    check_content: None | CheckContentType = field(
        default=None,
        metadata={
            "name": "check-content",
            "type": "Element",
            "namespace": "http://checklists.nist.gov/xccdf-p/1.1",
        },
    )
    check_content_ref: None | CheckContentRefType = field(
        default=None,
        metadata={
            "name": "check-content-ref",
            "type": "Element",
            "namespace": "http://checklists.nist.gov/xccdf-p/1.1",
        },
    )
    system: str = field(
        metadata={
            "type": "Attribute",
        }
    )


@dataclass(kw_only=True)
class LogicTestType:
    """
    Type for a test against several Facts; the content is one or more
    fact-refs and nested logical-tests.

    Allowed operators are AND and OR. The negate attribute, if set, makes
    the test its logical inverse (so you get NAND and NOR). Note that the
    output of a logical-test is always TRUE or FALSE, Unknowns map to
    FALSE.
    """

    class Meta:
        name = "logicTestType"

    fact_ref: list[FactRefType] = field(
        default_factory=list,
        metadata={
            "name": "fact-ref",
            "type": "Element",
            "namespace": "http://checklists.nist.gov/xccdf-p/1.1",
        },
    )
    logical_test: list[LogicTestType] = field(
        default_factory=list,
        metadata={
            "name": "logical-test",
            "type": "Element",
            "namespace": "http://checklists.nist.gov/xccdf-p/1.1",
        },
    )
    operator: LogicOperatorEnumType = field(
        metadata={
            "type": "Attribute",
        }
    )
    negate: bool = field(
        default=False,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class TextType:
    """
    Type for a string with an xml:lang attribute.
    """

    class Meta:
        name = "textType"

    value: str = field(default="")
    lang: None | str | LangValue = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class Fact:
    """
    This element denotes a single named Fact.

    Every fact has the following: - name, a URI, which must be a unique key
    - title, arbitrary text with xml:lang, optional - remark, arbitrary
    text with xml:lang, optional - check, XML content, optional.
    """

    class Meta:
        namespace = "http://checklists.nist.gov/xccdf-p/1.1"

    title: list[TextType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    remark: list[TextType] = field(
        default_factory=list,
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
class Platform:
    """
    This element denotes a single Platform definition.

    A Platform definition represents the qualifications an IT asset or
    target must have to be considered an instance of a particular Platform.
    A Platform has the following: - id, a locally unique id - name, a URI,
    which must be a unique key - title, arbitrary text with xml:lang,
    optional - remark, arbitrary text with xml:lang, optional - definition
    ref, either a fact ref or a logical test (boolean combination of fact
    refs).
    """

    class Meta:
        namespace = "http://checklists.nist.gov/xccdf-p/1.1"

    title: list[TextType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    remark: list[TextType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    fact_ref: None | FactRefType = field(
        default=None,
        metadata={
            "name": "fact-ref",
            "type": "Element",
        },
    )
    logical_test: None | LogicTestType = field(
        default=None,
        metadata={
            "name": "logical-test",
            "type": "Element",
        },
    )
    name: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    id: str = field(
        metadata={
            "type": "Attribute",
        }
    )


@dataclass(kw_only=True)
class PlatformSpecification:
    """
    This element can act as a top-level container for the Fact definitions
    and Platform definitions that make up a full XCCDF-P specification.

    It should be used when a XCCDF-P spec is being distributed as a
    standalone document, or included in an XCCDF 1.1 specification. This
    element schema used to include a keyref for Fact names, but it has been
    removed to allow for pre-defined Fact dictionaries.
    """

    class Meta:
        name = "Platform-Specification"
        namespace = "http://checklists.nist.gov/xccdf-p/1.1"

    fact: list[Fact] = field(
        default_factory=list,
        metadata={
            "name": "Fact",
            "type": "Element",
        },
    )
    platform: list[Platform] = field(
        default_factory=list,
        metadata={
            "name": "Platform",
            "type": "Element",
        },
    )
