from dataclasses import dataclass, field

from cis_bench.models.xccdf_v1_1.xml import LangValue

__NAMESPACE__ = "http://purl.org/dc/elements/1.1/"


@dataclass
class Contributor:
    class Meta:
        name = "contributor"
        namespace = "http://purl.org/dc/elements/1.1/"

    any_element: object | None = field(
        default=None,
        metadata={
            "type": "Wildcard",
            "namespace": "##any",
        },
    )


@dataclass
class Coverage:
    class Meta:
        name = "coverage"
        namespace = "http://purl.org/dc/elements/1.1/"

    any_element: object | None = field(
        default=None,
        metadata={
            "type": "Wildcard",
            "namespace": "##any",
        },
    )


@dataclass
class Creator:
    class Meta:
        name = "creator"
        namespace = "http://purl.org/dc/elements/1.1/"

    any_element: object | None = field(
        default=None,
        metadata={
            "type": "Wildcard",
            "namespace": "##any",
        },
    )


@dataclass
class Date:
    class Meta:
        name = "date"
        namespace = "http://purl.org/dc/elements/1.1/"

    any_element: object | None = field(
        default=None,
        metadata={
            "type": "Wildcard",
            "namespace": "##any",
        },
    )


@dataclass
class Description:
    class Meta:
        name = "description"
        namespace = "http://purl.org/dc/elements/1.1/"

    any_element: object | None = field(
        default=None,
        metadata={
            "type": "Wildcard",
            "namespace": "##any",
        },
    )


@dataclass
class Format:
    class Meta:
        name = "format"
        namespace = "http://purl.org/dc/elements/1.1/"

    any_element: object | None = field(
        default=None,
        metadata={
            "type": "Wildcard",
            "namespace": "##any",
        },
    )


@dataclass
class Identifier:
    class Meta:
        name = "identifier"
        namespace = "http://purl.org/dc/elements/1.1/"

    any_element: object | None = field(
        default=None,
        metadata={
            "type": "Wildcard",
            "namespace": "##any",
        },
    )


@dataclass
class Language:
    class Meta:
        name = "language"
        namespace = "http://purl.org/dc/elements/1.1/"

    any_element: object | None = field(
        default=None,
        metadata={
            "type": "Wildcard",
            "namespace": "##any",
        },
    )


@dataclass
class Publisher:
    class Meta:
        name = "publisher"
        namespace = "http://purl.org/dc/elements/1.1/"

    any_element: object | None = field(
        default=None,
        metadata={
            "type": "Wildcard",
            "namespace": "##any",
        },
    )


@dataclass
class Relation:
    class Meta:
        name = "relation"
        namespace = "http://purl.org/dc/elements/1.1/"

    any_element: object | None = field(
        default=None,
        metadata={
            "type": "Wildcard",
            "namespace": "##any",
        },
    )


@dataclass
class Rights:
    class Meta:
        name = "rights"
        namespace = "http://purl.org/dc/elements/1.1/"

    any_element: object | None = field(
        default=None,
        metadata={
            "type": "Wildcard",
            "namespace": "##any",
        },
    )


@dataclass
class Source:
    class Meta:
        name = "source"
        namespace = "http://purl.org/dc/elements/1.1/"

    any_element: object | None = field(
        default=None,
        metadata={
            "type": "Wildcard",
            "namespace": "##any",
        },
    )


@dataclass
class Subject:
    class Meta:
        name = "subject"
        namespace = "http://purl.org/dc/elements/1.1/"

    any_element: object | None = field(
        default=None,
        metadata={
            "type": "Wildcard",
            "namespace": "##any",
        },
    )


@dataclass
class Title:
    class Meta:
        name = "title"
        namespace = "http://purl.org/dc/elements/1.1/"

    any_element: object | None = field(
        default=None,
        metadata={
            "type": "Wildcard",
            "namespace": "##any",
        },
    )


@dataclass
class Type:
    class Meta:
        name = "type"
        namespace = "http://purl.org/dc/elements/1.1/"

    any_element: object | None = field(
        default=None,
        metadata={
            "type": "Wildcard",
            "namespace": "##any",
        },
    )


@dataclass
class SimpleLiteral:
    """This is the default type for all of the DC elements.

    It permits text content only with optional xml:lang attribute. Text
    is allowed because mixed="true", but sub-elements are disallowed
    because minOccurs="0" and maxOccurs="0" are on the xs:any tag. This
    complexType allows for restriction or extension permitting child
    elements.
    """

    lang: str | LangValue | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )
    content: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Wildcard",
            "namespace": "##any",
            "mixed": True,
        },
    )


@dataclass
class ElementContainer:
    """
    This complexType is included as a convenience for schema authors who need to
    define a root or container element for all of the DC elements.
    """

    class Meta:
        name = "elementContainer"

    rights: list[Rights] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://purl.org/dc/elements/1.1/",
        },
    )
    coverage: list[Coverage] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://purl.org/dc/elements/1.1/",
        },
    )
    relation: list[Relation] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://purl.org/dc/elements/1.1/",
        },
    )
    language: list[Language] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://purl.org/dc/elements/1.1/",
        },
    )
    source: list[Source] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://purl.org/dc/elements/1.1/",
        },
    )
    identifier: list[Identifier] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://purl.org/dc/elements/1.1/",
        },
    )
    format: list[Format] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://purl.org/dc/elements/1.1/",
        },
    )
    type_value: list[Type] = field(
        default_factory=list,
        metadata={
            "name": "type",
            "type": "Element",
            "namespace": "http://purl.org/dc/elements/1.1/",
        },
    )
    date: list[Date] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://purl.org/dc/elements/1.1/",
        },
    )
    contributor: list[Contributor] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://purl.org/dc/elements/1.1/",
        },
    )
    publisher: list[Publisher] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://purl.org/dc/elements/1.1/",
        },
    )
    description: list[Description] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://purl.org/dc/elements/1.1/",
        },
    )
    subject: list[Subject] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://purl.org/dc/elements/1.1/",
        },
    )
    creator: list[Creator] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://purl.org/dc/elements/1.1/",
        },
    )
    title: list[Title] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://purl.org/dc/elements/1.1/",
        },
    )


@dataclass
class AnyType(SimpleLiteral):
    class Meta:
        name = "any"
        namespace = "http://purl.org/dc/elements/1.1/"
