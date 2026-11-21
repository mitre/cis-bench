from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from cis_bench.models.xccdf_v1_1.xml import LangValue

__NAMESPACE__ = "http://www.cisecurity.org/xccdf/platform/0.2.3"


class LogicalOperatorOperator(Enum):
    AND = "and"
    OR = "or"


@dataclass(kw_only=True)
class Product:
    class Meta:
        name = "product"
        namespace = "http://www.cisecurity.org/xccdf/platform/0.2.3"

    idref: str = field(
        metadata={
            "type": "Attribute",
        }
    )


class VersionOperatorType(Enum):
    """
    Allowed operators for version elements.

    These are valid only for quasi-numeric version numbers, but the schema
    doesn't enforce it.
    """

    EQUALS = "equals"
    NOT_EQUAL = "not equal"


@dataclass(kw_only=True)
class LogicalOperator:
    class Meta:
        name = "logical-operator"
        namespace = "http://www.cisecurity.org/xccdf/platform/0.2.3"

    product: list[Product] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    logical_operator: list[LogicalOperator] = field(
        default_factory=list,
        metadata={
            "name": "logical-operator",
            "type": "Element",
        },
    )
    operator: LogicalOperatorOperator = field(
        metadata={
            "type": "Attribute",
        }
    )


@dataclass(kw_only=True)
class TextType:
    """
    Type for a string with an xml:lang attribute. (Note: changed this to
    allow any xml: attribute because xml:lang is a bit narrow, and also
    would require the validation processor to download the XML namespace
    schema every time.

    We cannot count on XCCDF or other benchmark users have a live Internet
    connection at all times.).
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
class Platform:
    """
    A listing of all supported platforms.
    """

    class Meta:
        name = "platform"
        namespace = "http://www.cisecurity.org/xccdf/platform/0.2.3"

    remark: list[TextType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    idref: str = field(
        metadata={
            "type": "Attribute",
        }
    )


@dataclass(kw_only=True)
class ProductType:
    """
    An individual product or component that makes up the overall platform.

    For more information see the subtypes below. A product consists of: a
    name, a version designator, zero or more named properties, and zero or
    more remarks.

    :ivar title:
    :ivar remark:
    :ivar vendor: The organization responsible for development and
        maintenance of the product
    :ivar family: The product family the software or device belongs to.
        This will be used along with the optional model and level
        elements to determine version-range comparisons. Example:
        "Windows", "routers", "portal server".
    :ivar model: The product's model which will differentiate major
        versions of software.  This may be useful when defining that all
        versions of software of a specific model are acceptable.
    :ivar level: The product's level which will differentiate functional
        capabilities across the same software version. Example:
        "enterprise", "home"
    :ivar version: The version designation for a platform component.
        This is the type for the version element: the element content is
        a version name or number, and the operator attribute specifies
        how that version applies.  For example, to say 'IOS 12.1 or
        later', the content would be "12.1" and the operator attribute
        would be "greater than or equal to".
    :ivar version_range:
    """

    class Meta:
        name = "productType"

    title: TextType = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.cisecurity.org/xccdf/platform/0.2.3",
        }
    )
    remark: list[TextType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://www.cisecurity.org/xccdf/platform/0.2.3",
        },
    )
    vendor: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.cisecurity.org/xccdf/platform/0.2.3",
        }
    )
    family: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.cisecurity.org/xccdf/platform/0.2.3",
        }
    )
    model: None | str = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.cisecurity.org/xccdf/platform/0.2.3",
        },
    )
    level: None | str = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.cisecurity.org/xccdf/platform/0.2.3",
        },
    )
    version: None | ProductType.Version = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.cisecurity.org/xccdf/platform/0.2.3",
        },
    )
    version_range: None | ProductType.VersionRange = field(
        default=None,
        metadata={
            "name": "version-range",
            "type": "Element",
            "namespace": "http://www.cisecurity.org/xccdf/platform/0.2.3",
        },
    )

    @dataclass(kw_only=True)
    class Version:
        value: str = field(default="")
        operator: VersionOperatorType = field(
            default=VersionOperatorType.EQUALS,
            metadata={
                "type": "Attribute",
            },
        )

    @dataclass(kw_only=True)
    class VersionRange:
        min_inclusive: None | str = field(
            default=None,
            metadata={
                "name": "min-inclusive",
                "type": "Element",
                "namespace": "http://www.cisecurity.org/xccdf/platform/0.2.3",
            },
        )
        min_exclusive: None | str = field(
            default=None,
            metadata={
                "name": "min-exclusive",
                "type": "Element",
                "namespace": "http://www.cisecurity.org/xccdf/platform/0.2.3",
            },
        )
        max_inclusive: None | str = field(
            default=None,
            metadata={
                "name": "max-inclusive",
                "type": "Element",
                "namespace": "http://www.cisecurity.org/xccdf/platform/0.2.3",
            },
        )
        max_exclusive: None | str = field(
            default=None,
            metadata={
                "name": "max-exclusive",
                "type": "Element",
                "namespace": "http://www.cisecurity.org/xccdf/platform/0.2.3",
            },
        )


@dataclass(kw_only=True)
class Application(ProductType):
    """
    An application or user-level program component product, part of a
    platform.

    Examples: Microsoft Word, Mozilla.
    """

    class Meta:
        name = "application"
        namespace = "http://www.cisecurity.org/xccdf/platform/0.2.3"

    id: str = field(
        metadata={
            "type": "Attribute",
            "pattern": r"app-[a-zA-Z0-9\-]+",
        }
    )


@dataclass(kw_only=True)
class Hardware(ProductType):
    """
    A hardware chassis or designation that is part of the specification of
    a benchmark platform.

    Examples: Cisco C3725, Juniper M7.
    """

    class Meta:
        name = "hardware"
        namespace = "http://www.cisecurity.org/xccdf/platform/0.2.3"

    id: str = field(
        metadata={
            "type": "Attribute",
            "pattern": r"hwr-[a-zA-Z0-9\-]+",
        }
    )


@dataclass(kw_only=True)
class Os(ProductType):
    """
    The operating system for a benchmark platform.

    Examples: Microsoft Windows XP, Sun Solaris, Cisco IOS.
    """

    class Meta:
        name = "os"
        namespace = "http://www.cisecurity.org/xccdf/platform/0.2.3"

    id: str = field(
        metadata={
            "type": "Attribute",
            "pattern": r"os-[a-zA-Z0-9\-]+",
        }
    )


@dataclass(kw_only=True)
class Service(ProductType):
    """
    A system or network service that is a component of a benchmark
    platform.

    Examples: Apache HTTPD, Microsoft Exchange, IBM MQSeries Message
    Server.
    """

    class Meta:
        name = "service"
        namespace = "http://www.cisecurity.org/xccdf/platform/0.2.3"

    id: str = field(
        metadata={
            "type": "Attribute",
            "pattern": r"srv-[a-zA-Z0-9\-]+",
        }
    )


@dataclass(kw_only=True)
class PlatformDefinitions:
    """
    This element contains the individual application, service, os and
    hardware definitions which will be used in an a-la-cart fashion to
    define specific platform support rulesets.
    """

    class Meta:
        name = "platform-definitions"
        namespace = "http://www.cisecurity.org/xccdf/platform/0.2.3"

    application: list[Application] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    service: list[Service] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    os: list[Os] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    hardware: list[Hardware] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    platform_definition: list[PlatformDefinitions.PlatformDefinition] = field(
        default_factory=list,
        metadata={
            "name": "platform-definition",
            "type": "Element",
            "min_occurs": 1,
        },
    )
    base: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )

    @dataclass(kw_only=True)
    class PlatformDefinition:
        title: TextType = field(
            metadata={
                "type": "Element",
            }
        )
        remark: list[TextType] = field(
            default_factory=list,
            metadata={
                "type": "Element",
            },
        )
        product: None | Product = field(
            default=None,
            metadata={
                "type": "Element",
            },
        )
        logical_operator: None | LogicalOperator = field(
            default=None,
            metadata={
                "name": "logical-operator",
                "type": "Element",
            },
        )
        id: str = field(
            metadata={
                "type": "Attribute",
            }
        )
