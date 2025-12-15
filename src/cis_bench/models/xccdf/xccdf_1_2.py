from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from xsdata.models.datatype import XmlDate, XmlDateTime

from cis_bench.models.xccdf.xml import LangValue

__NAMESPACE__ = "http://checklists.nist.gov/xccdf/1.2"


@dataclass
class Cpe2IdrefType:
    """Data type for &lt;xccdf:platform&gt; elements that do not need @override
    attributes.

    (I.e., &lt;xccdf:platform&gt; elements that are in structures that
    cannot be extended, such as &lt;xccdf:TestResult&gt; and
    &lt;xccdf:Benchmark&gt; elements.) This is used to identify the
    applicable target platform for its respective parent elements.

    :ivar idref: Should be a CPE 2.3 Applicability Language identifier
        using the Formatted String binding or the value of a
        &lt;cpe:platform-specification&gt; element's @id attribute, the
        latter acting as a reference to some expression defined using
        the CPE schema in the &lt;xccdf:Benchmark&gt; element's
        &lt;cpe:platform-specification&gt; element. The @idref may be a
        CPE Applicability Language identifier using the URI binding,
        although this is less preferred.
    """

    class Meta:
        name = "CPE2idrefType"

    idref: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )


@dataclass
class BenchmarkReferenceType:
    """
    Type for a reference to the &lt;xccdf:Benchmark&gt; document.

    :ivar href: The URI of the &lt;xccdf:Benchmark&gt; document.
    :ivar id: The value of that &lt;xccdf:Benchmark&gt; element's @id
        attribute.
    """

    class Meta:
        name = "benchmarkReferenceType"

    href: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )
    id: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


class CcOperatorEnumType(Enum):
    """The type for the allowed @operator names for the &lt;xccdf:complex-check&gt;
    operator attribute.

    Only AND and OR operators are supported. (The &lt;xccdf:complex-
    check&gt; has a separate mechanism for negation.)

    :cvar OR: The logical OR of the component terms
    :cvar AND: The logical AND of the component terms
    """

    OR = "OR"
    AND = "AND"


@dataclass
class CheckContentRefType:
    """Data type for the &lt;xccdf:check-content-ref&gt; element, which points to
    the code for a detached check in another file.

    This element has no body, just a couple of attributes: @href and
    @name. The @name is optional, if it does not appear then this
    reference is to the entire document.

    :ivar href: Identifies the referenced document containing checking
        instructions.
    :ivar name: Identifies a particular part or element of the
        referenced check document.
    """

    class Meta:
        name = "checkContentRefType"

    href: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )
    name: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass
class CheckContentType:
    """Data type for the &lt;xccdf:check-content&gt; element.

    The body of this element holds the actual code of a check, in the
    language or system specified by the &lt;xccdf:check&gt; element’s
    @system attribute. The body of this element may be any XML, but
    cannot contain any XCCDF elements. XCCDF tools do not process its
    content directly but instead pass the content directly to checking
    engines.
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


@dataclass
class CheckExportType:
    """Data type for the &lt;xccdf:check-export&gt; element, which specifies a
    mapping from an &lt;xccdf:Value&gt; element to a checking system variable
    (i.e., external name or id for use by the checking system).

    This supports export of tailoring &lt;xccdf:Value&gt; elements from
    the XCCDF processing environment to the checking system. The
    interface between the XCCDF benchmark consumer and the checking
    system should support, at a minimum, passing the &lt;xccdf:value&gt;
    property of the &lt;xccdf:Value&gt; element, but may also support
    passing the &lt;xccdf:Value&gt; element's @type and @operator
    properties.

    :ivar value_id: The id of the &lt;xccdf:Value&gt; element to export.
    :ivar export_name: An identifier indicating some structure in the
        checking system into which the identified &lt;xccdf:Value&gt;
        element's properties will be mapped.
    """

    class Meta:
        name = "checkExportType"

    value_id: str | None = field(
        default=None,
        metadata={
            "name": "value-id",
            "type": "Attribute",
            "required": True,
        },
    )
    export_name: str | None = field(
        default=None,
        metadata={
            "name": "export-name",
            "type": "Attribute",
            "required": True,
        },
    )


@dataclass
class CheckImportType:
    """Data type for the &lt;xccdf:check-import&gt; element, which specifies a
    value that the &lt;xccdf:Benchmark&gt; author wishes to retrieve from the
    checking system during testing of a target system.

    The @import-name attribute identifies some structure in the checking
    system that is then retrieved. The mapping from the values of this
    attribute to specific checking system structures is beyond the scope
    of the XCCDF specification. When the &lt;xccdf:check-import&gt;
    element appears in the context of an &lt;xccdf:Rule&gt;, then it
    should be empty and any content must be ignored. When the
    &lt;xccdf:check-import&gt; element appears in the context of an
    &lt;xccdf:rule-result&gt;, then its body holds the imported value.

    :ivar import_name: An identifier indicating some structure in the
        checking system to be collected.
    :ivar import_xpath: An XPath that is used to select specific values
        or structures from the imported structure. This allows further
        refinement of the collected data if the imported value takes the
        form of XML structures.
    :ivar content:
    """

    class Meta:
        name = "checkImportType"

    import_name: str | None = field(
        default=None,
        metadata={
            "name": "import-name",
            "type": "Attribute",
            "required": True,
        },
    )
    import_xpath: str | None = field(
        default=None,
        metadata={
            "name": "import-xpath",
            "type": "Attribute",
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
class ComplexValueType:
    """Data type that supports values that are lists of simple types.

    Each element in the list is represented by an instance of the
    &lt;xccdf:item&gt; child element. If there are no &lt;xccdf:item&gt;
    child elements then this represents an empty list.

    :ivar item: A single item in the list of values.
    """

    class Meta:
        name = "complexValueType"

    item: list[str] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )


@dataclass
class DcStatusType:
    """
    Data type element for the &lt;xccdf:dc-status&gt; element, which holds status
    information about its parent element using the Dublin Core format, expressed as
    elements of the DCMI Simple DC Element specification.
    """

    class Meta:
        name = "dc-statusType"

    purl_org_dc_elements_1_1_element: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Wildcard",
            "namespace": "http://purl.org/dc/elements/1.1/",
        },
    )


class FixStrategyEnumType(Enum):
    """Allowed @strategy keyword values for an &lt;xccdf:Rule&gt; element's
    &lt;xccdf:fix&gt; or &lt;xccdf:fixtext&gt; elements.

    The values indicate the method or approach for fixing non-compliance
    with a particular &lt;xccdf:Rule&gt;.

    :cvar UNKNOWN: Strategy not defined (default)
    :cvar CONFIGURE: Adjust target configuration/settings
    :cvar COMBINATION: Combination of two or more approaches
    :cvar DISABLE: Turn off or uninstall a target component
    :cvar ENABLE: Turn on or install a target component
    :cvar PATCH: Apply a patch, hotfix, update, etc.
    :cvar POLICY: Remediation requires out-of-band adjustments to
        policies or procedures
    :cvar RESTRICT: Adjust permissions, access rights, filters, or other
        access restrictions
    :cvar UPDATE: Install, upgrade or update the system
    """

    UNKNOWN = "unknown"
    CONFIGURE = "configure"
    COMBINATION = "combination"
    DISABLE = "disable"
    ENABLE = "enable"
    PATCH = "patch"
    POLICY = "policy"
    RESTRICT = "restrict"
    UPDATE = "update"


@dataclass
class IdentType:
    """Data type for the &lt;xccdf:ident&gt; element, a globally meaningful
    identifier for an &lt;xccdf:Rule&gt;.

    The body of &lt;xccdf:ident&gt; element is the name or identifier of
    a security configuration issue or vulnerability that the
    &lt;xccdf:Rule&gt; addresses. It has an associated URI that denotes
    the organization or naming scheme that assigned the name. By setting
    an &lt;xccdf:ident&gt; element on an &lt;xccdf:Rule&gt;, the
    &lt;xccdf:Benchmark&gt; author effectively declares that the
    &lt;xccdf:Rule&gt; instantiates, implements, or remediates the issue
    for which the name was assigned.

    :ivar value:
    :ivar system: Denotes the organization or naming scheme that
        assigned the identifier.
    :ivar other_attributes: May also have other attributes from other
        namespaces in order to provide additional metadata for the given
        identifier.
    """

    class Meta:
        name = "identType"

    value: str = field(
        default="",
        metadata={
            "required": True,
        },
    )
    system: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )
    other_attributes: dict[str, str] = field(
        default_factory=dict,
        metadata={
            "type": "Attributes",
            "namespace": "##other",
        },
    )


@dataclass
class IdentityType:
    """Type for an &lt;xccdf:identity&gt; element in an &lt;xccdf:TestResult&gt;.

    It contains information about the system identity or user employed
    during application of the &lt;xccdf:Benchmark&gt;. If used, shall
    specify the name of the authenticated identity.

    :ivar value:
    :ivar authenticated: Whether the identity was authenticated with the
        target system during the application of the
        &lt;xccdf:Benchmark&gt;.
    :ivar privileged: Whether the identity was granted administrative or
        other special privileges beyond those of a normal user.
    """

    class Meta:
        name = "identityType"

    value: str = field(
        default="",
        metadata={
            "required": True,
        },
    )
    authenticated: bool | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )
    privileged: bool | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )


@dataclass
class IdrefListType:
    """
    Data type for elements contain list of references to other XCCDF elements.

    :ivar idref: A space-separated list of id values from other XCCDF
        elements
    """

    class Meta:
        name = "idrefListType"

    idref: list[str] = field(
        default_factory=list,
        metadata={
            "type": "Attribute",
            "tokens": True,
        },
    )


@dataclass
class IdrefType:
    """
    Data type for elements that contain a reference to another XCCDF element.

    :ivar idref: The id value of another XCCDF element
    """

    class Meta:
        name = "idrefType"

    idref: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )


@dataclass
class InstanceFixType:
    """Type for an &lt;xccdf:instance&gt; element which may appear in an
    &lt;xccdf:fix&gt; element.

    The &lt;xccdf:instance&gt; element inside an &lt;xccdf:fix&gt;
    element designates a spot where the name of the instance should be
    substituted into the fix template to generate the final fix data.

    :ivar context: Describes the scope or significance of the instance
        content. The context attribute is intended to be informative and
        does not affect basic processing.
    """

    class Meta:
        name = "instanceFixType"

    context: str = field(
        default="undefined",
        metadata={
            "type": "Attribute",
        },
    )


@dataclass
class InstanceResultType:
    """Type for an &lt;xccdf:instance&gt; element in an &lt;xccdf:rule-result&gt;.

    The content is a string, but the element may also have
    two attributes: @context and @parentContext. Both attributes are intended to provide
    hints as to the nature of the substituted content. This body of this type records
    the details of the target system instance for multiply instantiated
    &lt;xccdf:Rule&gt; elements.

    :ivar value:
    :ivar context: Describes the scope or significance of the instance
        content.
    :ivar parent_context: Used to express nested structure in instance
        context structures.
    """

    class Meta:
        name = "instanceResultType"

    value: str = field(
        default="",
        metadata={
            "required": True,
        },
    )
    context: str = field(
        default="undefined",
        metadata={
            "type": "Attribute",
        },
    )
    parent_context: str | None = field(
        default=None,
        metadata={
            "name": "parentContext",
            "type": "Attribute",
        },
    )


class InterfaceHintType(Enum):
    """Allowed interface hint values.

    &lt;xccdf:Value&gt; elements may contain a hint or recommendation to
    a benchmark consumer or producer about how the user might select or
    adjust the &lt;xccdf:Value&gt;. This type enumerates the possible
    values of this hint.

    :cvar CHOICE: Multiple choice
    :cvar TEXTLINE: Multiple lines of text
    :cvar TEXT: Single line of text
    :cvar DATE: Date
    :cvar DATETIME: Date and time
    """

    CHOICE = "choice"
    TEXTLINE = "textline"
    TEXT = "text"
    DATE = "date"
    DATETIME = "datetime"


@dataclass
class MetadataType:
    """Data type that supports inclusion of metadata about a document or element.

    This is particularly useful for facilitating the discovery and
    retrieval of XCCDF checklists from public repositories. When used,
    the contents of the &lt;xccdf:metadata&gt; element are expressed in
    XML. The &lt;xccdf:Benchmark&gt; element's metadata should contain
    information formatted using the Dublin Core Metadata Initiative
    (DCMI) Simple DC Element specification, as described in [DCES] and
    [DCXML]. Benchmark consumers should be prepared to process Dublin
    Core metadata in the &lt;xccdf:metadata&gt; element. Other metadata
    schemes, including ad-hoc elements, are also allowed, both in the
    &lt;xccdf:Benchmark&gt; and in other elements.
    """

    class Meta:
        name = "metadataType"

    other_element: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Wildcard",
            "namespace": "##other",
        },
    )


class MsgSevEnumType(Enum):
    """Allowed values to indicate the severity of messages from the checking
    engine.

    These values don't affect scoring themselves but are present merely
    to convey diagnostic information from the checking engine. Benchmark
    consumers may choose to log these messages or display them to the
    user.

    :cvar ERROR: Denotes a serious problem identified; test did not run.
    :cvar WARNING: Denotes a possible issue; test may not have run.
    :cvar INFO: Denotes important information about the tests.
    """

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ParamType:
    """Type for a parameter used in the &lt;xccdf:model&gt; element, which records
    scoring model information.

    The contents of this type represent a name-value pair, where the
    name is recorded in the @name attribute and the value appears in the
    element body. &lt;xccdf:param&gt; elements with equal values for the
    @name attribute may not appear as children of the same
    &lt;xccdf:model&gt; element.

    :ivar value:
    :ivar name: The name associated with the contained value.
    """

    class Meta:
        name = "paramType"

    value: str = field(
        default="",
        metadata={
            "required": True,
        },
    )
    name: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )


@dataclass
class PlainTextType:
    """The data type for an &lt;xccdf:plain-text&gt; element, which is a reusable
    text block for reference by the &lt;xccdf:sub&gt; element.

    This allows text to be defined once and then reused multiple times.
    Each &lt;xccdf:plain-text&gt; element mush have a unique id.

    :ivar value:
    :ivar id: The unique identifier for this &lt;xccdf:plain-text&gt;
        element.
    """

    class Meta:
        name = "plainTextType"

    value: str = field(
        default="",
        metadata={
            "required": True,
        },
    )
    id: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )


@dataclass
class ProfileSetValueType:
    """Type for the &lt;xccdf:set-value&gt; element in an &lt;xccdf:Profile&gt;.

    This element upports the direct specification of simple value types
    such as numbers, strings, and boolean values. This overrides the
    &lt;xccdf:value&gt; and &lt;xccdf:complex-value&gt; element(s) of an
    &lt;xccdf:Value&gt; element.

    :ivar value:
    :ivar idref: The @id value of an &lt;xccdf:Value&gt; or the
        @cluster-id value of one or more &lt;xccdf:Value&gt; elements
    """

    class Meta:
        name = "profileSetValueType"

    value: str = field(
        default="",
        metadata={
            "required": True,
        },
    )
    idref: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )


class RatingEnumType(Enum):
    """
    This type enumerates allowed rating values the disruption and complexity
    properties of an &lt;xccdf:Rule&gt; element's &lt;xccdf:fix&gt; or
    &lt;xccdf:fixtext&gt; elements.

    :cvar UNKNOWN: Rating unknown or impossible to estimate (default)
    :cvar LOW: Little or no potential for disruption, very modest
        complexity
    :cvar MEDIUM: Some chance of minor disruption, substantial
        complexity
    :cvar HIGH: Likely to cause serious disruption, very complex
    """

    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class ReferenceType:
    """This element provides supplementary descriptive text for a XCCDF elements.

    When used, it has either a simple string value or a value consisting
    of simple Dublin Core elements. If a bare string appears, then it is
    taken to be the string content for a Dublin Core title element.
    Multiple &lt;xccdf:reference&gt; elements may appear; a document
    generation processing tool may concatenate them, or put them into a
    reference list, and may choose to number them.

    :ivar href: A URL pointing to the referenced resource.
    :ivar override: Used to manage inheritance processing.
    :ivar content:
    """

    class Meta:
        name = "referenceType"

    href: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    override: bool | None = field(
        default=None,
        metadata={
            "type": "Attribute",
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


class ResultEnumType(Enum):
    """
    Allowed result indicators for a test.

    :cvar PASS: The target system or system component satisfied all the
        conditions of the &lt;xccdf:Rule&gt;.
    :cvar FAIL: The target system or system component did not satisfy
        all the conditions of the &lt;xccdf:Rule&gt;.
    :cvar ERROR: The checking engine could not complete the evaluation;
        therefore the status of the target’s compliance with the
        &lt;xccdf:Rule&gt; is not certain. This could happen, for
        example, if a testing tool was run with insufficient privileges
        and could not gather all of the necessary information.
    :cvar UNKNOWN: The testing tool encountered some problem and the
        result is unknown. For example, a result of ‘unknown’ might be
        given if the testing tool was unable to interpret the output of
        the checking engine (the output has no meaning to the testing
        tool).
    :cvar NOTAPPLICABLE: The &lt;xccdf:Rule&gt; was not applicable to
        the target of the test. For example, the &lt;xccdf:Rule&gt;
        might have been specific to a different version of the target
        OS, or it might have been a test against a platform feature that
        was not installed.
    :cvar NOTCHECKED: The &lt;xccdf:Rule&gt; was not evaluated by the
        checking engine. This status is designed for &lt;xccdf:Rule&gt;
        elements that have no check. It may also correspond to a status
        returned by a checking engine if the checking engine does not
        support the indicated check code.
    :cvar NOTSELECTED: The &lt;xccdf:Rule&gt; was not selected in the
        &lt;xccdf:Benchmark&gt;.
    :cvar INFORMATIONAL: The &lt;xccdf:Rule&gt; was checked, but the
        output from the checking engine is simply information for
        auditors or administrators; it is not a compliance category.
        This status value is designed for &lt;xccdf:Rule&gt; elements
        whose main purpose is to extract information from the target
        rather than test the target.
    :cvar FIXED: The &lt;xccdf:Rule&gt; had failed, but was then fixed
        (possibly by a tool that can automatically apply remediation, or
        possibly by the human auditor).
    """

    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    UNKNOWN = "unknown"
    NOTAPPLICABLE = "notapplicable"
    NOTCHECKED = "notchecked"
    NOTSELECTED = "notselected"
    INFORMATIONAL = "informational"
    FIXED = "fixed"


class RoleEnumType(Enum):
    """
    Allowed checking and scoring roles for an &lt;xccdf:Rule&gt;.

    :cvar FULL: If the &lt;xccdf:Rule&gt; is selected, then check it and
        let the result contribute to the score and appear in reports
        (default).
    :cvar UNSCORED: If the &lt;xccdf:Rule&gt; is selected, then check it
        and include it in the test report, but give the result a status
        of informational and do not use the result in score
        computations.
    :cvar UNCHECKED: Do not check the &lt;xccdf:Rule&gt;; just force the
        result status to notchecked.
    """

    FULL = "full"
    UNSCORED = "unscored"
    UNCHECKED = "unchecked"


@dataclass
class ScoreType:
    """
    Type for a score value in an &lt;xccdf:TestResult&gt;.

    :ivar value:
    :ivar system: A URI indicating the scoring model used to create this
        score.
    :ivar maximum: The maximum possible score value that could have been
        achieved under the named scoring system.
    """

    class Meta:
        name = "scoreType"

    value: Decimal | None = field(
        default=None,
        metadata={
            "required": True,
        },
    )
    system: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    maximum: Decimal | None = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass
class SelNumType:
    """
    This type is for an element that has numeric content and a @selector attribute
    for use during tailoring.

    :ivar value:
    :ivar selector: This may be referenced from &lt;xccdf:Profile&gt;
        selection elements or used during manual tailoring to refine the
        application of this property. If no selectors are specified for
        a given property by &lt;xccdf:Profile&gt; elements or manual
        tailoring, properties with empty or non-existent @selector
        attributes are activated. If a selector is applied that does not
        match the @selector attribute of any of a given type of
        property, then no property of that type considered activated.
    """

    class Meta:
        name = "selNumType"

    value: Decimal | None = field(
        default=None,
        metadata={
            "required": True,
        },
    )
    selector: str = field(
        default="",
        metadata={
            "type": "Attribute",
        },
    )


@dataclass
class SelStringType:
    """
    This type is for an element that has string content and a @selector attribute
    for use in tailoring.

    :ivar value:
    :ivar selector: This may be referenced from &lt;xccdf:Profile&gt;
        selection elements or used during manual tailoring to refine the
        application of this property. If no selectors are specified for
        a given property by &lt;xccdf:Profile&gt; elements or manual
        tailoring, properties with empty or non-existent @selector
        attributes are activated. If a selector is applied that does not
        match the @selector attribute of any of a given type of
        property, then no property of that type is considered activated.
        The only exception is the &lt;xccdf:value&gt; and
        &lt;xccdf:complex-value&gt; properties of an &lt;xccdf:Value&gt;
        element - if there is no &lt;xccdf:value&gt; or
        &lt;xccdf:complex-value&gt; property with a matching @selector
        value then the &lt;xccdf:value&gt;/&lt;xccdf:complex-value&gt;
        property with an empty or absent @selector attribute becomes
        active. If there is no such &lt;xccdf:value&gt; or
        &lt;xccdf:complex-value&gt;, then the first &lt;xccdf:value&gt;
        or &lt;xccdf:complex-value&gt; listed in the XML becomes active.
        This reflects the fact that all &lt;xccdf:Value&gt; elements
        require an active value property at all times.
    """

    class Meta:
        name = "selStringType"

    value: str = field(
        default="",
        metadata={
            "required": True,
        },
    )
    selector: str = field(
        default="",
        metadata={
            "type": "Attribute",
        },
    )


class SeverityEnumType(Enum):
    """Allowed severity values for the @severity attribute of an
    &lt;xccdf:Rule&gt;.

    The value of this attribute provides an indication of the importance
    of the &lt;xccdf:Rule&gt; element's recommendation. This information
    is informative only and does not affect scoring.

    :cvar UNKNOWN: Severity not defined (default).
    :cvar INFO: &lt;xccdf:Rule&gt; is informational and failure does not
        represent a problem.
    :cvar LOW: Not a serious problem.
    :cvar MEDIUM: Fairly serious problem.
    :cvar HIGH: A grave or critical problem.
    """

    UNKNOWN = "unknown"
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class SignatureType:
    """
    The type of an &lt;XMLDSig:signature&gt; element, which holds an enveloped
    digital signature asserting authorship and allowing verification of the
    integrity of associated data (e.g., its parent element, other documents,
    portions of other documents).
    """

    class Meta:
        name = "signatureType"

    w3_org_2000_09_xmldsig_element: object | None = field(
        default=None,
        metadata={
            "type": "Wildcard",
            "namespace": "http://www.w3.org/2000/09/xmldsig#",
            "process_contents": "skip",
        },
    )


class StatusType(Enum):
    """
    The statusType represents the possible levels of maturity or consensus level
    for its parent element as recorded by an &lt;xccdf:status&gt; element.

    :cvar ACCEPTED: Released as final
    :cvar DEPRECATED: No longer needed
    :cvar DRAFT: Released in draft state
    :cvar INCOMPLETE: Under initial development
    :cvar INTERIM: Revised and in the process of being finalized
    """

    ACCEPTED = "accepted"
    DEPRECATED = "deprecated"
    DRAFT = "draft"
    INCOMPLETE = "incomplete"
    INTERIM = "interim"


class SubUseEnumType(Enum):
    """This holds the possible values of the @use attribute within an
    &lt;xccdf:sub&gt; element.

    The @use attribute is only applicable with the subType's @idref
    attribute holds the value of the @id of an &lt;xccdf:Value&gt;
    element.

    :cvar VALUE: Replace with the selected &lt;xccdf:value&gt; or
        &lt;xccdf:complex-value&gt; of an &lt;xccdf:Value&gt;.
    :cvar TITLE: Replace with the &lt;xccdf:title&gt; of the
        &lt;xccdf:Value&gt;.
    :cvar LEGACY: Use the context-dependent processing of
        &lt;xccdf:sub&gt; elements outlined in XCCDF 1.1.4.
    """

    VALUE = "value"
    TITLE = "title"
    LEGACY = "legacy"


@dataclass
class TailoringReferenceType:
    """Type for the &lt;xccdf:tailoring&gt; element within an
    &lt;xccdf:TestResult&gt;.

    This element is used to indicate the identity and location of an
    &lt;xccdf:Tailoring&gt; file that was used to create the assessment
    results.

    :ivar href: The URI of the &lt;xccdf:Tailoring&gt; file's location.
    :ivar id: The &lt;xccdf:Tailoring&gt; element's @id value.
    :ivar version: The value of the &lt;xccdf:Tailoring&gt; element's
        &lt;xccdf:version&gt; property.
    :ivar time: The value of the @time attribute in the
        &lt;xccdf:Tailoring&gt; element's &lt;xccdf:version&gt;
        property.
    """

    class Meta:
        name = "tailoringReferenceType"

    href: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )
    id: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )
    version: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )
    time: XmlDateTime | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )


@dataclass
class TailoringVersionType:
    """
    Type for version information about an &lt;xccdf:Tailoring&gt; element.

    :ivar value:
    :ivar time: The time when this version of the
        &lt;xccdf:Tailoring&gt; document was completed.
    """

    class Meta:
        name = "tailoringVersionType"

    value: str = field(
        default="",
        metadata={
            "required": True,
        },
    )
    time: XmlDateTime | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )


@dataclass
class TargetIdRefType:
    """Type for an &lt;xccdf:target-id-ref&gt; element in an
    &lt;xccdf:TestResult&gt; element.

    This element contains references to external structures with
    identifying information about the target of an assessment.

    :ivar system: Indicates the language in which this identifying
        information is expressed. If the identifying language uses XML
        namespaces, then the @system attribute for the language should
        be its namespace.
    :ivar href: Points to the external resource (e.g., a file) that
        contains the identifying information.
    :ivar name: Identifies a specific structure within the referenced
        file. If the @name attribute is absent, the reference is to the
        entire resource indicated in the @href attribute.
    """

    class Meta:
        name = "targetIdRefType"

    system: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )
    href: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )
    name: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass
class UriRefType:
    """
    Data type for elements that have no content and a single @uri attribute.

    :ivar uri: A URI.
    """

    class Meta:
        name = "uriRefType"

    uri: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )


class ValueOperatorType(Enum):
    """This type enumerates allowed values of the @operator property of
    &lt;xccdf:Value&gt; elements.

    The specific interpretation of these operators depends on the
    checking system used.
    """

    EQUALS = "equals"
    NOT_EQUAL = "not equal"
    GREATER_THAN = "greater than"
    LESS_THAN = "less than"
    GREATER_THAN_OR_EQUAL = "greater than or equal"
    LESS_THAN_OR_EQUAL = "less than or equal"
    PATTERN_MATCH = "pattern match"


class ValueTypeType(Enum):
    """Allowed data types for &lt;xccdf:Value&gt; elements, string, numeric, and
    boolean.

    A tool may choose any convenient form to store an
    &lt;xccdf:Value&gt; element’s &lt;xccdf:value&gt; element, but the
    @type conveys how the value should be treated for user input
    validation purposes during tailoring processing. The @type may also
    be used to give additional guidance to the user or to validate the
    user’s input. For example, if an &lt;xccdf:value&gt; element’s @type
    attribute is “number”, then a tool might choose to reject user
    tailoring input that is not composed of digits. In the case of a
    list of values, the @type applies to all elements of the list
    individually. Note that checking systems may have their own
    understanding of data types that may not be identical to the typing
    indicated in XCCDF

    :cvar NUMBER: A numeric value. This may be decimal or integer.
    :cvar STRING: Any character data
    :cvar BOOLEAN: True/false
    """

    NUMBER = "number"
    STRING = "string"
    BOOLEAN = "boolean"


@dataclass
class VersionType:
    """
    Type for most &lt;xccdf:version&gt; elements.

    :ivar value:
    :ivar time: The time that this version of the associated element was
        completed.
    :ivar update: A URI indicating a location where updates to the
        associated element may be obtained.
    """

    class Meta:
        name = "versionType"

    value: str = field(
        default="",
        metadata={
            "required": True,
        },
    )
    time: XmlDateTime | None = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    update: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


class WarningCategoryEnumType(Enum):
    """
    Allowed warning category keywords for the &lt;xccdf:warning&gt; element used in
    &lt;xccdf:Rule&gt; elements.

    :cvar GENERAL: Broad or general-purpose warning (default)
    :cvar FUNCTIONALITY: Warning about possible impacts to functionality
        or operational features
    :cvar PERFORMANCE: Warning about changes to target system
        performance or throughput
    :cvar HARDWARE: Warning about hardware restrictions or possible
        impacts to hardware
    :cvar LEGAL: Warning about legal implications
    :cvar REGULATORY: Warning about regulatory obligations or compliance
        implications
    :cvar MANAGEMENT: Warning about impacts to the management or
        administration of the target system
    :cvar AUDIT: Warning about impacts to audit or logging
    :cvar DEPENDENCY: Warning about dependencies between this element
        and other parts of the target system, or version dependencies
    """

    GENERAL = "general"
    FUNCTIONALITY = "functionality"
    PERFORMANCE = "performance"
    HARDWARE = "hardware"
    LEGAL = "legal"
    REGULATORY = "regulatory"
    MANAGEMENT = "management"
    AUDIT = "audit"
    DEPENDENCY = "dependency"


@dataclass
class CheckType:
    """Data type for the &lt;xccdf:check&gt; element.

    The &lt;xccdf:check&gt; element identifies instructions for tests to
    determine compliance with the &lt;xccdf:Rule&gt; as well as
    parameters controlling the reporting of those test results. The
    &lt;xccdf:check&gt; element must have at least one child element.

    :ivar check_import: Identifies a value to be retrieved from the
        checking system during testing of a target system. This
        element's body must be empty within an &lt;xccdf:check&gt;.
        After the associated check results have been collected, the
        result structure returned by the checking engine is processed to
        collect the named information. This information is then recorded
        in the check-import element in the corresponding &lt;xccdf:rule-
        result&gt;.
    :ivar check_export: A mapping from an &lt;xccdf:Value&gt; element to
        a checking system variable (i.e., external name or id for use by
        the checking system). This supports export of tailoring values
        from the XCCDF processing environment to the checking system.
    :ivar check_content_ref: Points to code for a detached check in
        another location that uses the language or system specified by
        the &lt;xccdf:check&gt; element’s @system attribute. If multiple
        &lt;xccdf:check-content-ref&gt; elements appear, they represent
        alternative locations from which a benchmark consumer may obtain
        the check content. Benchmark consumers should process the
        alternatives in the order in which they appear in the XML. The
        first &lt;xccdf:check-content-ref&gt; from which content can be
        successfully retrieved should be used.
    :ivar check_content: Holds the actual code of a check, in the
        language or system specified by the &lt;xccdf:check&gt;
        element’s @system attribute. If both &lt;xccdf:check-content-
        ref&gt; and &lt;xccdf:check-content&gt; elements appear in a
        single &lt;xccdf:check&gt; element, benchmark consumers should
        use the &lt;xccdf:check-content&gt; element only if none of the
        references can be resolved to provide content.
    :ivar system: The URI for a checking system. If the checking system
        uses XML namespaces, then the system attribute for the system
        should be its namespace.
    :ivar negate: If set to true, the final result of the
        &lt;xccdf:check&gt; is negated according to the truth table
        given below.
    :ivar id: Unique identifier for this element. Optional, but must be
        globally unique if present.
    :ivar selector: This may be referenced from &lt;xccdf:Profile&gt;
        selection elements or used during manual tailoring to refine the
        application of the &lt;xccdf:Rule&gt;. If no selector values are
        specified for a given &lt;xccdf:Rule&gt; by
        &lt;xccdf:Profile&gt; elements or manual tailoring, all
        &lt;xccdf:check&gt; elements with non-empty @selector attributes
        are ignored. If an &lt;xccdf:Rule&gt; has multiple
        &lt;xccdf:check&gt; elements with the same @selector attribute,
        each must employ a different checking system, as identified by
        the @system attribute of the &lt;xccdf:check&gt; element.
    :ivar multi_check: Applicable in cases where multiple checks are
        executed to determine compliance with a single
        &lt;xccdf:Rule&gt;. This situation can arise when an
        &lt;xccdf:check&gt; includes an &lt;xccdf:check-content-ref&gt;
        element that does not include a @name attribute. The default
        behavior of a nameless &lt;xccdf:check-content-ref&gt; is to
        execute all checks in the referenced check content location and
        AND their results together into a single &lt;xccdf:rule-
        result&gt; using the AND truth table below. This corresponds to
        a @multi-check attribute value of “false”. If, however, the
        @multi-check attribute is set to "true" and a nameless
        &lt;xccdf:check-content-ref&gt; is used, the &lt;xccdf:Rule&gt;
        produces a separate &lt;xccdf:rule-result&gt; for each check.
    :ivar base:
    """

    class Meta:
        name = "checkType"

    check_import: list[CheckImportType] = field(
        default_factory=list,
        metadata={
            "name": "check-import",
            "type": "Element",
            "namespace": "",
        },
    )
    check_export: list[CheckExportType] = field(
        default_factory=list,
        metadata={
            "name": "check-export",
            "type": "Element",
            "namespace": "",
        },
    )
    check_content_ref: list[CheckContentRefType] = field(
        default_factory=list,
        metadata={
            "name": "check-content-ref",
            "type": "Element",
            "namespace": "",
        },
    )
    check_content: CheckContentType | None = field(
        default=None,
        metadata={
            "name": "check-content",
            "type": "Element",
            "namespace": "",
        },
    )
    system: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )
    negate: bool = field(
        default=False,
        metadata={
            "type": "Attribute",
        },
    )
    id: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    selector: str = field(
        default="",
        metadata={
            "type": "Attribute",
        },
    )
    multi_check: bool = field(
        default=False,
        metadata={
            "name": "multi-check",
            "type": "Attribute",
        },
    )
    base: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass
class FactType:
    """Data type for an &lt;xccdf:fact&gt; element, which
    holds information about a target system: a name-value pair with a type. The content
    of the element is the value, and the @name attribute indicates the name. The @name
    is in the form of a URI that indicates the nature of the fact. A table of defined
    fact URIs appears in section 6.6.3 of the XCCDF specification. Additional URIs may
    be defined by authors to indicate additional kinds of facts.

    :ivar value:
    :ivar name: A URI that indicates the name of the fact.
    :ivar type_value: The data type of the fact value.
    """

    class Meta:
        name = "factType"

    value: str = field(
        default="",
        metadata={
            "required": True,
        },
    )
    name: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )
    type_value: ValueTypeType = field(
        default=ValueTypeType.BOOLEAN,
        metadata={
            "name": "type",
            "type": "Attribute",
        },
    )


@dataclass
class HtmlTextType:
    """
    The type for a string with optional XHTML elements and an @xml:lang attribute.

    :ivar lang:
    :ivar override: Used to manage inheritance.
    :ivar content:
    """

    class Meta:
        name = "htmlTextType"

    lang: str | LangValue | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )
    override: bool = field(
        default=False,
        metadata={
            "type": "Attribute",
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
class MessageType:
    """Type for a message generated by the checking engine or XCCDF tool during
    &lt;xccdf:Benchmark&gt; testing.

    The message is contained in string format in the body of the
    element.

    :ivar value:
    :ivar severity: Denotes the seriousness of the message.
    """

    class Meta:
        name = "messageType"

    value: str = field(
        default="",
        metadata={
            "required": True,
        },
    )
    severity: MsgSevEnumType | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )


@dataclass
class Model:
    """A suggested scoring model for an &lt;xccdf:Benchmark&gt;, also encapsulating
    any parameters needed by the model.

    Every model is designated with a URI, which appears here as the
    system attribute. See the XCCDF specification for a list of standard
    scoring models and their associated URIs. Vendors may define their
    own scoring models and provide additional URIs to designate them.
    Some models may need additional parameters; to support such a model,
    zero or more &lt;xccdf:param&gt; elements may appear as children of
    the &lt;xccdf:model&gt; element.

    :ivar param: Parameters provided as input to the designated scoring
        model.
    :ivar system: A URI designating a scoring model.
    """

    class Meta:
        name = "model"
        namespace = "http://checklists.nist.gov/xccdf/1.2"

    param: list[ParamType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    system: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )


@dataclass
class NoticeType:
    """Data type for an &lt;xccdf:notice&gt; element.

    &lt;xccdf:notice&gt; elements are used to include legal notices
    (licensing information, terms of use, etc.), copyright statements,
    warnings, and other advisory notices about this
    &lt;xccdf:Benchmark&gt; and its use. This information may be
    expressed using XHTML or may be a simply text expression. Each
    &lt;xccdf:notice&gt; element must have a unique identifier.

    :ivar id: The unique identifier for this &lt;xccdf:notice&gt;.
    :ivar base:
    :ivar lang:
    :ivar content:
    """

    class Meta:
        name = "noticeType"

    id: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    base: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )
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
class OverrideableCpe2IdrefType(Cpe2IdrefType):
    """Data type for &lt;xccdf:platform&gt; elements that need
    @override attributes. (I.e., &lt;xccdf:platform&gt; elements that are in structures
    that can be extended, such as Items and &lt;xccdf:Profile&gt; elements.) This is
    used to identify the applicable target platform for its respective parent elements.

    :ivar override: Used to manage inheritance.
    """

    class Meta:
        name = "overrideableCPE2idrefType"

    override: bool = field(
        default=False,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass
class ProfileSetComplexValueType(ComplexValueType):
    """Type for the &lt;xccdf:set-complex-value&gt; element in an
    &lt;xccdf:Profile&gt;.

    This element supports the direct specification of complex value
    types such as lists. Zero or more &lt;xccdf:item&gt; elements may
    appear as children of this element; if no child elements are
    present, this element represents an empty list. This overrides the
    &lt;xccdf:value&gt; and &lt;xccdf:complex-value&gt; element(s) of an
    &lt;xccdf:Value&gt; element.

    :ivar idref: The @id value of an &lt;xccdf:Value&gt; or the
        @cluster-id value of one or more &lt;xccdf:Value&gt; elements
    """

    class Meta:
        name = "profileSetComplexValueType"

    idref: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )


@dataclass
class SelChoicesType:
    """
    The type of the &lt;xccdf:choice&gt; element, which specifies a list of legal
    or suggested choices for an &lt;xccdf:Value&gt; object.

    :ivar choice: A single choice holding a simple type. (I.e., number,
        string, or boolean.)
    :ivar complex_choice: A single choice holding a list of simple
        types.
    :ivar must_match: True if the listed choices are the only
        permissible settings for the given &lt;xccdf:Value&gt;. False if
        choices not specified in this &lt;xccdf:choices&gt; element are
        acceptable settings for this &lt;xccdf:Value&gt;.
    :ivar selector: This may be referenced from &lt;xccdf:Profile&gt;
        selection elements or used during manual tailoring to refine the
        application of the &lt;xccdf:Rule&gt;. If no selectors are
        specified for a given &lt;xccdf:Value&gt; by
        &lt;xccdf:Profile&gt; elements or manual tailoring, an
        &lt;xccdf:choice&gt; element with an empty or non-existent
        @selector attribute is activated. If a selector is applied that
        does not match the @selector attribute of any
        &lt;xccdf:choices&gt; element, then no &lt;xccdf:choices&gt;
        element is considered activated.
    """

    class Meta:
        name = "selChoicesType"

    choice: list[str] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    complex_choice: list[ComplexValueType] = field(
        default_factory=list,
        metadata={
            "name": "complex-choice",
            "type": "Element",
            "namespace": "",
        },
    )
    must_match: bool | None = field(
        default=None,
        metadata={
            "name": "mustMatch",
            "type": "Attribute",
        },
    )
    selector: str = field(
        default="",
        metadata={
            "type": "Attribute",
        },
    )


@dataclass
class SelComplexValueType(ComplexValueType):
    """
    Data type that supports values that are lists of simple types with an
    associated @selector attribute used in tailoring.

    :ivar selector: This may be referenced from &lt;xccdf:Profile&gt;
        selection elements or used during manual tailoring to refine the
        application of this property. If no selectors are specified for
        a given item by &lt;xccdf:Profile&gt; elements or manual
        tailoring, properties with empty or non-existent @selector
        attributes are activated. If a selector is applied that does not
        match the @selector attribute of any of a given type of
        property, then no &lt;xccdf:choices&gt; element is considered
        activated. The only exception is the &lt;xccdf:value&gt; and
        &lt;xccdf:complex-value&gt; properties of an &lt;xccdf:Value&gt;
        element - if there is no &lt;xccdf:value&gt; or
        &lt;xccdf:complex-value&gt; property with a matching @selector
        value then the &lt;xccdf:value&gt;/&lt;xccdf:complex-value&gt;
        property with an empty or absent @selector attribute becomes
        active. If there is no such &lt;xccdf:value&gt; or
        &lt;xccdf:complex-value&gt;, then the first &lt;xccdf:value&gt;
        or &lt;xccdf:complex-value&gt; listed becomes active. This
        reflects the fact that all &lt;xccdf:Value&gt; elements require
        an active value property at all times.
    """

    class Meta:
        name = "selComplexValueType"

    selector: str = field(
        default="",
        metadata={
            "type": "Attribute",
        },
    )


@dataclass
class Status:
    """The acceptance status of an element with an optional date attribute, which
    signifies the date of the status change.

    If an element does not have its own &lt;xccdf:status&gt; element,
    its status is that of its parent element. If there is more than one
    &lt;xccdf:status&gt; for a single element, then every instance of
    the &lt;xccdf:status&gt; element must have a @date attribute, and
    the &lt;xccdf:status&gt; element with the latest date is considered
    the current status.

    :ivar value:
    :ivar date: The date the parent element achieved the indicated
        status.
    """

    class Meta:
        name = "status"
        namespace = "http://checklists.nist.gov/xccdf/1.2"

    value: StatusType | None = field(
        default=None,
        metadata={
            "required": True,
        },
    )
    date: XmlDate | None = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass
class SubType(IdrefType):
    """The type used for &lt;xccdf:sub&gt; elements.

    The &lt;xccdf:sub&gt; element identifies replacement content that
    should appear in place of the &lt;xccdf:sub&gt; element during text
    substitution. The subType consists of a regular idrefType with an
    additional @use attribute to dictate the behavior of the
    &lt;xccdf:sub&gt; element under substitution. When the @idref is to
    an &lt;xccdf:Value&gt;, the @use attribute indicates whether the
    &lt;xccdf:Value&gt; element's title or value should replace the
    &lt;xccdf:sub&gt; element. The @use attribute is ignored when the
    @idref is to an &lt;xccdf:plain-text&gt; element; the body of the
    &lt;xccdf:plain-text&gt; element is always used to replace the
    &lt;xccdf:sub&gt; element.

    :ivar use: Dictates the nature of the content inserted under text
        substitution processing.
    """

    class Meta:
        name = "subType"

    use: SubUseEnumType = field(
        default=SubUseEnumType.VALUE,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass
class TailoringBenchmarkReferenceType(BenchmarkReferenceType):
    """
    Identifies the &lt;xccdf:Benchmark&gt; to which an &lt;xccdf:Tailoring&gt;
    element applies.

    :ivar version: Identifies the version of the referenced
        &lt;xccdf:Benchmark&gt;.
    """

    class Meta:
        name = "tailoringBenchmarkReferenceType"

    version: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass
class TextType:
    """
    Type for a simple text string with an @override attribute for controlling
    inheritance.

    :ivar value:
    :ivar lang:
    :ivar override: Used to manage inheritance.
    """

    class Meta:
        name = "textType"

    value: str = field(
        default="",
        metadata={
            "required": True,
        },
    )
    lang: str | LangValue | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )
    override: bool = field(
        default=False,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass
class ComplexCheckType:
    """The type for an element that contains a boolean combination of
    &lt;xccdf:checks&gt;.

    This element can have only &lt;xccdf:complex-check&gt; and
    &lt;xccdf:check&gt; elements as children. Child elements may appear
    in any order but at least one child element must be present. It has
    two attributes, @operator and @negate, which dictate how
    &lt;xccdf:check&gt; or &lt;xccdf:complex-check&gt; child elements
    are to be combined. Truth tables for these operations appear below.

    :ivar check: Instructions for a single test.
    :ivar complex_check: A child &lt;xccdf:complex-check&gt;, allowing
        another level of logic in combining component checks.
    :ivar operator: Indicates whether the child &lt;xccdf:check&gt;
        and/or &lt;xccdf:complex-check&gt; elements of this
        &lt;xccdf:complex-check&gt; should be combined using an AND or
        OR operation
    :ivar negate: If true, negate the final result of this
        &lt;xccdf:complex-check&gt; after the child elements are
        combined using the identified operator.
    """

    class Meta:
        name = "complexCheckType"

    check: list[CheckType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    complex_check: list["ComplexCheckType"] = field(
        default_factory=list,
        metadata={
            "name": "complex-check",
            "type": "Element",
            "namespace": "",
        },
    )
    operator: CcOperatorEnumType | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )
    negate: bool = field(
        default=False,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass
class FixType:
    """Data type for the &lt;xccdf:fix&gt; element.

    The body of this element contains a command string, script, or other
    system modification statement that, if executed on the target
    system, can bring it into full, or at least better, compliance with
    this &lt;xccdf:Rule&gt;.

    :ivar id: A local identifier for the element. It is optional for the
        @id to be unique; multiple &lt;xccdf:fix&gt; elements may have
        the same @id but different values for their other attributes. It
        is used primarily to allow &lt;xccdf:fixtext&gt; elements to be
        associated with one or more &lt;xccdf:fix&gt; elements
    :ivar reboot: True if a reboot is known to be required and false
        otherwise.
    :ivar strategy: The method or approach for making the described fix.
    :ivar disruption: An estimate of the potential for disruption or
        operational degradation that the application of this fix will
        impose on the target.
    :ivar complexity: The estimated complexity or difficulty of applying
        the fix to the target.
    :ivar system: A URI that identifies the scheme, language, engine, or
        process for which the fix contents are written. Table 17 in the
        XCCDF specification defines several general-purpose URNs that
        may be used for this, and tool vendors and system providers may
        define and use target-specific URNs.
    :ivar platform: In case different fix scripts or procedures are
        required for different target platform types (e.g., different
        patches for Windows Vista and Windows 7), this attribute allows
        a CPE name or CPE applicability language expression to be
        associated with an &lt;xccdf:fix&gt; element. This should appear
        on an &lt;xccdf:fix&gt; when the content applies to only one
        platform out of several to which the &lt;xccdf:Rule&gt; could
        apply.
    :ivar content:
    """

    class Meta:
        name = "fixType"

    id: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    reboot: bool = field(
        default=False,
        metadata={
            "type": "Attribute",
        },
    )
    strategy: FixStrategyEnumType = field(
        default=FixStrategyEnumType.UNKNOWN,
        metadata={
            "type": "Attribute",
        },
    )
    disruption: RatingEnumType = field(
        default=RatingEnumType.UNKNOWN,
        metadata={
            "type": "Attribute",
        },
    )
    complexity: RatingEnumType = field(
        default=RatingEnumType.UNKNOWN,
        metadata={
            "type": "Attribute",
        },
    )
    system: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    platform: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    content: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Wildcard",
            "namespace": "##any",
            "mixed": True,
            "choices": (
                {
                    "name": "sub",
                    "type": SubType,
                    "namespace": "",
                },
                {
                    "name": "instance",
                    "type": InstanceFixType,
                    "namespace": "",
                },
            ),
        },
    )


@dataclass
class HtmlTextWithSubType:
    """
    The type for a string with optional XHTML elements, and an @xml:lang attribute.

    :ivar lang:
    :ivar override: Used to manage inheritance.
    :ivar content:
    """

    class Meta:
        name = "htmlTextWithSubType"

    lang: str | LangValue | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )
    override: bool = field(
        default=False,
        metadata={
            "type": "Attribute",
        },
    )
    content: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Wildcard",
            "namespace": "##any",
            "mixed": True,
            "choices": (
                {
                    "name": "sub",
                    "type": SubType,
                    "namespace": "",
                },
            ),
        },
    )


@dataclass
class OverrideType:
    """Type for an &lt;xccdf:override&gt; element in an &lt;xccdf:rule-result&gt;.

    This element is used to record manual modification or annotation of
    a particular &lt;xccdf:rule-result&gt;. All attributes and child
    elements are required. It will not always be the case that the
    &lt;xccdf:new-result&gt; value will differ from the &lt;xccdf:old-
    result&gt; value. They might match if an authority wished to make a
    remark on the result without changing it. If &lt;xccdf:new-
    result&gt; and &lt;xccdf:old-result&gt; differ, the
    &lt;xccdf:result&gt; element of the enclosing &lt;xccdf:rule-
    result&gt; must match the &lt;xccdf:new-result&gt; value.

    :ivar old_result: The &lt;xccdf:rule-result&gt; status before this
        override.
    :ivar new_result: The new, override &lt;xccdf:rule-result&gt;
        status.
    :ivar remark: Rationale or explanation text for why or how the
        override was applied.
    :ivar time: When the override was applied.
    :ivar authority: Name or other identification for the human
        principal authorizing the override.
    """

    class Meta:
        name = "overrideType"

    old_result: ResultEnumType | None = field(
        default=None,
        metadata={
            "name": "old-result",
            "type": "Element",
            "namespace": "",
            "required": True,
        },
    )
    new_result: ResultEnumType | None = field(
        default=None,
        metadata={
            "name": "new-result",
            "type": "Element",
            "namespace": "",
            "required": True,
        },
    )
    remark: TextType | None = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "",
            "required": True,
        },
    )
    time: XmlDateTime | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )
    authority: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )


@dataclass
class ProfileNoteType:
    """Type for an &lt;xccdf:profile-note&gt; within an &lt;xccdf:Rule&gt;.

    This element contains text that describes special aspects of an
    &lt;xccdf:Rule&gt; relative to one or more &lt;xccdf:Profile&gt;
    elements. This allows an author to document things within
    &lt;xccdf:Rule&gt; elements that are specific to a given
    &lt;xccdf:Profile&gt;. This information might then be displayed to a
    reader based on the selection of a particular &lt;xccdf:Profile&gt;.
    The body text may include XHTML mark-up as well as &lt;xccdf:sub&gt;
    elements.

    :ivar lang:
    :ivar tag: The identifier of this note.
    :ivar content:
    """

    class Meta:
        name = "profileNoteType"

    lang: str | LangValue | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )
    tag: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )
    content: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Wildcard",
            "namespace": "##any",
            "mixed": True,
            "choices": (
                {
                    "name": "sub",
                    "type": SubType,
                    "namespace": "",
                },
            ),
        },
    )


@dataclass
class ProfileRefineRuleType:
    """Type for the &lt;xccdf:refine-rule&gt; element in an &lt;xccdf:Profile&gt;.

    A &lt;xccdf:refine-rule&gt; element allows the author to select
    &lt;xccdf:check&gt; statements and override the @weight, @severity,
    and @role of an &lt;xccdf:Rule&gt;, &lt;xccdf:Group&gt;, or cluster
    of &lt;xccdf:Rule&gt; and &lt;xccdf:Group&gt; elements. Despite the
    name, this selector does apply for &lt;xccdf:Group&gt; elements and
    for clusters that include &lt;xccdf:Group&gt; elements, but it only
    affects their @weight attribute.

    :ivar remark: Explanatory material or other prose.
    :ivar idref: The @id value of an &lt;xccdf:Rule&gt; or
        &lt;xccdf:Group&gt;, or the @cluster-id value of one or more
        &lt;xccdf:Rule&gt; or &lt;xccdf:Group&gt; elements.
    :ivar weight: The new value for the identified element's @weight
        property.
    :ivar selector: Holds a selector value corresponding to the value of
        a @selector property in an &lt;xccdf:Rule&gt; element's
        &lt;xccdf:check&gt; element. If the selector specified does not
        match any of the @selector attributes specified on any of the
        &lt;xccdf:check&gt; children of an &lt;xccdf:Rule&gt;, then the
        &lt;xccdf:check&gt; child element without a @selector attribute
        is used. If there is no child without a @selector attribute,
        then that Rule would have no effective &lt;xccdf:check&gt;
        element.
    :ivar severity: The new value for the identified &lt;xccdf:Rule&gt;
        element's @severity property.
    :ivar role: The new value for the identified &lt;xccdf:Rule&gt;
        element's @role property.
    """

    class Meta:
        name = "profileRefineRuleType"

    remark: list[TextType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    idref: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )
    weight: Decimal | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "min_inclusive": Decimal("0.0"),
            "total_digits": 3,
        },
    )
    selector: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    severity: SeverityEnumType | None = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    role: RoleEnumType | None = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass
class ProfileRefineValueType:
    """Type for the &lt;xccdf:refine-value&gt; element in an &lt;xccdf:Profile&gt;.

    This element designates the &lt;xccdf:Value&gt; constraints to be
    applied during tailoring for an &lt;xccdf:Value&gt; element or the
    &lt;xccdf:Value&gt; members of a cluster.

    :ivar remark: Explanatory material or other prose.
    :ivar idref: The @id value of an &lt;xccdf:Value&gt; or the
        @cluster-id value of one or more &lt;xccdf:Value&gt; elements
    :ivar selector: Holds a selector value corresponding to the value of
        a @selector property in an &lt;xccdf:Value&gt; element's child
        properties. Properties with a matching @selector are considered
        active and all other properties are inactive. This may mean
        that, after selector application, some classes of
        &lt;xccdf:Value&gt; properties will be completely inactive
        because none of those properties had a matching @selector. The
        only exception is the &lt;xccdf:value&gt; and &lt;xccdf:complex-
        value&gt; properties of an &lt;xccdf:Value&gt; element - if
        there is no &lt;xccdf:value&gt; or &lt;xccdf:complex-value&gt;
        property with a matching @selector value then the
        &lt;xccdf:value&gt;/&lt;xccdf:complex-value&gt; property with an
        empty or absent @selector attribute becomes active. If there is
        no such &lt;xccdf:value&gt; or &lt;xccdf:complex-value&gt;, then
        the first &lt;xccdf:value&gt; or &lt;xccdf:complex-value&gt;
        listed in the XML becomes active. This reflects the fact that
        all &lt;xccdf:Value&gt; elements require an active value
        property at all times.
    :ivar operator: The new value for the identified &lt;xccdf:Value&gt;
        element's @operator property.
    """

    class Meta:
        name = "profileRefineValueType"

    remark: list[TextType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    idref: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )
    selector: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    operator: ValueOperatorType | None = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass
class ProfileSelectType:
    """Type for the &lt;xccdf:select&gt; element in an &lt;xccdf:Profile&gt;.

    This element designates an &lt;xccdf:Rule&gt;, &lt;xccdf:Group&gt;,
    or cluster of &lt;xccdf:Rule&gt; and &lt;xccdf:Group&gt; elements
    and overrides the @selected attribute on the designated items,
    providing a means for including or excluding &lt;xccdf:Rule&gt;
    elements from an assessment.

    :ivar remark: Explanatory material or other prose.
    :ivar idref: The @id value of an &lt;xccdf:Rule&gt; or
        &lt;xccdf:Group&gt;, or the @cluster-id value of one or more
        &lt;xccdf:Rule&gt; or &lt;xccdf:Group&gt; elements.
    :ivar selected: The new value for the indicated item's @selected
        property.
    """

    class Meta:
        name = "profileSelectType"

    remark: list[TextType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    idref: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )
    selected: bool | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )


@dataclass
class TargetFactsType:
    """Data type for the &lt;xccdf:target-facts&gt; elements in
    &lt;xccdf:TestResult&gt; elements.

    A &lt;xccdf:target-facts&gt; element holds a list of named facts
    about the target system or platform. Each fact is an element of type
    factType. Each &lt;xccdf:fact&gt; must have a name, but duplicate
    names are allowed. (For example, if you had a fact about MAC
    addresses, and the target system had three NICs, then you'd need
    three instances of the "urn:xccdf:fact:ethernet:MAC" fact.)

    :ivar fact: A named fact about the target system or platform.
    """

    class Meta:
        name = "targetFactsType"

    fact: list[FactType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )


@dataclass
class TextWithSubType:
    """
    Type for a string with embedded &lt;xccdf:Value&gt; substitutions and an
    @override attribute to help manage inheritance.

    :ivar lang:
    :ivar override: Used to manage inheritance.
    :ivar content:
    """

    class Meta:
        name = "textWithSubType"

    lang: str | LangValue | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )
    override: bool = field(
        default=False,
        metadata={
            "type": "Attribute",
        },
    )
    content: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Wildcard",
            "namespace": "##any",
            "mixed": True,
            "choices": (
                {
                    "name": "sub",
                    "type": SubType,
                    "namespace": "",
                },
            ),
        },
    )


@dataclass
class FixTextType(HtmlTextWithSubType):
    """Data type for the &lt;xccdf:fixtext&gt; element, which contains data that
    describes how to bring a target system into compliance with an
    &lt;xccdf:Rule&gt;.

    Each &lt;xccdf:fixtext&gt; element may be associated with one or
    more &lt;xccdf:fix&gt; elements through the @fixref attribute. The
    body holds explanatory text about the fix procedures.

    :ivar fixref: A reference to the @id of an &lt;xccdf:fix&gt;
        element.
    :ivar reboot: True if a reboot is known to be required and false
        otherwise.
    :ivar strategy: The method or approach for making the described fix.
    :ivar disruption: An estimate of the potential for disruption or
        operational degradation that the application of this fix will
        impose on the target.
    :ivar complexity: The estimated complexity or difficulty of applying
        the fix to the target.
    """

    class Meta:
        name = "fixTextType"

    fixref: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    reboot: bool = field(
        default=False,
        metadata={
            "type": "Attribute",
        },
    )
    strategy: FixStrategyEnumType = field(
        default=FixStrategyEnumType.UNKNOWN,
        metadata={
            "type": "Attribute",
        },
    )
    disruption: RatingEnumType = field(
        default=RatingEnumType.UNKNOWN,
        metadata={
            "type": "Attribute",
        },
    )
    complexity: RatingEnumType = field(
        default=RatingEnumType.UNKNOWN,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass
class ProfileType:
    """Data type for the &lt;xccdf:Profile&gt; element, which holds a specific
    tailoring of the &lt;xccdf:Benchmark&gt;.

    The main part of an &lt;xccdf:Profile&gt; is the selectors:
    &lt;xccdf:select&gt;, &lt;xccdf:set-value&gt;, &lt;xccdf:set-
    complex-value&gt;, &lt;xccdf:refine-rule&gt;, and &lt;xccdf:refine-
    value&gt;. An &lt;xccdf:Profile&gt; may also be signed with an XML-
    Signature.

    :ivar status: Status of the &lt;xccdf:Profile&gt; and date at which
        it attained that status. Authors may use this element to record
        the maturity or consensus level of an &lt;xccdf:Profile&gt;. If
        the &lt;xccdf:status&gt; is not given explicitly, then the
        &lt;xccdf:Profile&gt; is taken to have the same status as its
        parent &lt;xccdf:Benchmark&gt;.
    :ivar dc_status: Holds additional status information using the
        Dublin Core format.
    :ivar version: Version information about this &lt;xccdf:Profile&gt;.
    :ivar title: Title of the &lt;xccdf:Profile&gt;.
    :ivar description: Text that describes the &lt;xccdf:Profile&gt;.
    :ivar reference: A reference where the user can learn more about the
        subject of this &lt;xccdf:Profile&gt;.
    :ivar platform: A target platform for this &lt;xccdf:Profile&gt;.
    :ivar select: Select or deselect &lt;xccdf:Group&gt; and
        &lt;xccdf:Rule&gt; elements.
    :ivar set_complex_value: Set the value of an &lt;xccdf:Value&gt; to
        a list.
    :ivar set_value: Set the value of an &lt;xccdf:Value&gt; to a simple
        data value.
    :ivar refine_value: Customize the properties of an
        &lt;xccdf:Value&gt;.
    :ivar refine_rule: Customize the properties of an &lt;xccdf:Rule&gt;
        or &lt;xccdf:Group&gt;.
    :ivar metadata: Metadata associated with this &lt;xccdf:Profile&gt;.
    :ivar signature: A digital signature asserting authorship and
        allowing verification of the integrity of the
        &lt;xccdf:Profile&gt;.
    :ivar id: Unique identifier for this &lt;xccdf:Profile&gt;.
    :ivar prohibit_changes: Whether or not products should prohibit
        changes to this &lt;xccdf:Profile&gt;.
    :ivar abstract: If true, then this &lt;xccdf:Profile&gt; exists
        solely to be extended by other &lt;xccdf:Profile&gt; elements.
    :ivar note_tag: Tag identifier to specify which &lt;xccdf:profile-
        note&gt; element from an &lt;xccdf:Rule&gt; should be associated
        with this &lt;xccdf:Profile&gt;.
    :ivar extends: The id of an &lt;xccdf:Profile&gt; on which to base
        this &lt;xccdf:Profile&gt;.
    :ivar base:
    :ivar id_attribute: An identifier used for referencing elements
        included in an XML signature.
    """

    class Meta:
        name = "profileType"

    status: list[Status] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://checklists.nist.gov/xccdf/1.2",
        },
    )
    dc_status: list[DcStatusType] = field(
        default_factory=list,
        metadata={
            "name": "dc-status",
            "type": "Element",
            "namespace": "",
        },
    )
    version: VersionType | None = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    title: list[TextWithSubType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
            "min_occurs": 1,
        },
    )
    description: list[HtmlTextWithSubType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    reference: list[ReferenceType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    platform: list[OverrideableCpe2IdrefType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    select: list[ProfileSelectType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    set_complex_value: list[ProfileSetComplexValueType] = field(
        default_factory=list,
        metadata={
            "name": "set-complex-value",
            "type": "Element",
            "namespace": "",
        },
    )
    set_value: list[ProfileSetValueType] = field(
        default_factory=list,
        metadata={
            "name": "set-value",
            "type": "Element",
            "namespace": "",
        },
    )
    refine_value: list[ProfileRefineValueType] = field(
        default_factory=list,
        metadata={
            "name": "refine-value",
            "type": "Element",
            "namespace": "",
        },
    )
    refine_rule: list[ProfileRefineRuleType] = field(
        default_factory=list,
        metadata={
            "name": "refine-rule",
            "type": "Element",
            "namespace": "",
        },
    )
    metadata: list[MetadataType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    signature: SignatureType | None = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    id: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
            "pattern": r"xccdf_[^_]+_profile_.+",
        },
    )
    prohibit_changes: bool = field(
        default=False,
        metadata={
            "name": "prohibitChanges",
            "type": "Attribute",
        },
    )
    abstract: bool = field(
        default=False,
        metadata={
            "type": "Attribute",
        },
    )
    note_tag: str | None = field(
        default=None,
        metadata={
            "name": "note-tag",
            "type": "Attribute",
        },
    )
    extends: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    base: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )
    id_attribute: str | None = field(
        default=None,
        metadata={
            "name": "Id",
            "type": "Attribute",
        },
    )


@dataclass
class RuleResultType:
    """Type for the &lt;xccdf:rule-result&gt; element within an
    &lt;xccdf:TestResult&gt;.

    An &lt;xccdf:rule-result&gt; holds the result of applying an
    &lt;xccdf:Rule&gt; from the &lt;xccdf:Benchmark&gt; to a target
    system or component of a target system.

    :ivar result: Result of applying the referenced &lt;xccdf:Rule&gt;
        to a target or target component. (E.g., Pass, Fail, etc.)
    :ivar override: An XML block explaining how and why an auditor chose
        to override the result.
    :ivar ident: A long-term globally meaningful identifier for the
        issue, vulnerability, platform, etc. copied from the referenced
        &lt;xccdf:Rule&gt;.
    :ivar metadata: XML metadata associated with this &lt;xccdf:rule-
        result&gt;.
    :ivar message: Diagnostic messages from the checking engine. These
        elements do not affect scoring; they are present merely to
        convey diagnostic information from the checking engine.
    :ivar instance: Name of the target subsystem or component to which
        this result applies, for a multiply instantiated
        &lt;xccdf:Rule&gt;. The element is important for an
        &lt;xccdf:Rule&gt; that applies to components of the target
        system, especially when a target might have several such
        components, and where the @multiple attribute of the
        &lt;xccdf:Rule&gt; is set to true.
    :ivar fix: Fix script for this target platform, if available (would
        normally appear only for result values of “fail”). It is assumed
        to have been ‘instantiated’ by the testing tool and any
        substitutions or platform selections already made.
    :ivar check: Encapsulated or referenced results to detailed testing
        output from the checking engine (if any).
    :ivar complex_check: A copy of the &lt;xccdf:Rule&gt; element’s
        &lt;xccdf:complex-check&gt; element where each component
        &lt;xccdf:check&gt; element of the &lt;xccdf:complex-check&gt;
        element is an encapsulated or referenced results to detailed
        testing output from the checking engine (if any) as described in
        the &lt;xccdf:rule-result&gt; &lt;xccdf:check&gt; property.
    :ivar idref: The value of the @id property of an &lt;xccdf:Rule&gt;.
        This &lt;xccdf:rule-result&gt; reflects the result of applying
        this &lt;xccdf:Rule&gt; to a target or target component.
    :ivar role: The value of the @role property of the referenced
        &lt;xccdf:Rule&gt;.
    :ivar severity: The value of the @severity property of the
        referenced &lt;xccdf:Rule&gt;.
    :ivar time: Time when application of this instance of the referenced
        &lt;xccdf:Rule&gt; was completed.
    :ivar version: The value of the @version property of the referenced
        &lt;xccdf:Rule&gt;.
    :ivar weight: The value of the @weight property of the referenced
        &lt;xccdf:Rule&gt;.
    """

    class Meta:
        name = "ruleResultType"

    result: ResultEnumType | None = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "",
            "required": True,
        },
    )
    override: list[OverrideType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    ident: list[IdentType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    metadata: list[MetadataType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    message: list[MessageType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    instance: list[InstanceResultType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    fix: list[FixType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    check: list[CheckType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    complex_check: ComplexCheckType | None = field(
        default=None,
        metadata={
            "name": "complex-check",
            "type": "Element",
            "namespace": "",
        },
    )
    idref: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )
    role: RoleEnumType | None = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    severity: SeverityEnumType | None = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    time: XmlDateTime | None = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    version: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    weight: Decimal | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "min_inclusive": Decimal("0.0"),
            "total_digits": 3,
        },
    )


@dataclass
class WarningType(HtmlTextWithSubType):
    """Data type for the &lt;xccdf:warning&gt; element under the &lt;xccdf:Rule&gt;
    element.

    This element holds a note or caveat about the item intended to
    convey important cautionary information for the
    &lt;xccdf:Benchmark&gt; user.

    :ivar category: A hint as to the nature of the warning.
    """

    class Meta:
        name = "warningType"

    category: WarningCategoryEnumType = field(
        default=WarningCategoryEnumType.GENERAL,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass
class Profile(ProfileType):
    """The &lt;xccdf:Profile&gt; element is a named tailoring for an
    &lt;xccdf:Benchmark&gt;.

    While an &lt;xccdf:Benchmark&gt; can be tailored in place by setting
    properties of various elements, &lt;xccdf:Profile&gt; elements allow
    one &lt;xccdf:Benchmark&gt; document to hold several independent
    tailorings.
    """

    class Meta:
        namespace = "http://checklists.nist.gov/xccdf/1.2"


@dataclass
class ItemType:
    """This abstract itemType represents the basic data shared by all
    &lt;xccdf:Group&gt;, &lt;xccdf:Rule&gt; and &lt;xccdf:Value&gt; elements.

    All elements in an itemType are optional, although each element that
    builds on the itemType may add its own elements, some of which will
    be required for that element.

    :ivar status: Status of the item and date at which it attained that
        status. &lt;xccdf:Benchmark&gt; authors may use this element to
        record the maturity or consensus level for elements in the
        &lt;xccdf:Benchmark&gt;. If an item does not have an explicit
        &lt;xccdf:status&gt; given, then its status is that of its
        parent.
    :ivar dc_status: Holds additional status information using the
        Dublin Core format.
    :ivar version: Version information about this item.
    :ivar title: Title of the item. Every item should have an
        &lt;xccdf:title&gt;, because this helps people understand the
        purpose of the item.
    :ivar description: Text that describes the item.
    :ivar warning: A note or caveat about the item intended to convey
        important cautionary information for the &lt;xccdf:Benchmark&gt;
        user (e.g., “Complying with this rule will cause the system to
        reject all IP packets”). If multiple &lt;xccdf:warning&gt;
        elements appear, benchmark consumers should concatenate them for
        generating reports or documents. Benchmark consumers may present
        this information in a special manner in generated documents.
    :ivar question: Interrogative text to present to the user during
        tailoring. It may also be included into a generated document.
        For &lt;xccdf:Rule&gt; and &lt;xccdf:Group&gt; elements, the
        &lt;xccdf:question&gt; text should be a simple binary (yes/no)
        question because it is supporting the selection aspect of
        tailoring. For &lt;xccdf:Value&gt; elements, the
        &lt;xccdf:question&gt; should solicit the user to provide a
        specific value. Tools may also display constraints on values and
        any defaults as specified by the other &lt;xccdf:Value&gt;
        properties.
    :ivar reference: References where the user can learn more about the
        subject of this item.
    :ivar metadata: XML metadata associated with this item, such as
        sources, special information, or other details.
    :ivar abstract: If true, then this item is abstract and exists only
        to be extended. The use of this attribute for
        &lt;xccdf:Group&gt; elements is deprecated and should be
        avoided.
    :ivar cluster_id: An identifier to be used as a means to identify
        (refer to) related items. It designates membership in a cluster
        of items, which are used for controlling items via
        &lt;xccdf:Profile&gt; elements. All the items with the same
        cluster identifier belong to the same cluster. A selector in an
        &lt;xccdf:Profile&gt; may refer to a cluster, thus making it
        easier for authors to create and maintain &lt;xccdf:Profile&gt;
        elements in a complex &lt;xccdf:Benchmark&gt;.
    :ivar extends: The identifier of an item on which to base this item.
        If present, it must have a value equal to the @id attribute of
        another item. The use of this attribute for &lt;xccdf:Group&gt;
        elements is deprecated and should be avoided.
    :ivar hidden: If this item should be excluded from any generated
        documents although it may still be used during assessments.
    :ivar prohibit_changes: If benchmark producers should prohibit
        changes to this item during tailoring. An author should use this
        when they do not want to allow end users to change the item.
    :ivar lang:
    :ivar base:
    :ivar id: An identifier used for referencing elements included in an
        XML signature
    """

    class Meta:
        name = "itemType"

    status: list[Status] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://checklists.nist.gov/xccdf/1.2",
        },
    )
    dc_status: list[DcStatusType] = field(
        default_factory=list,
        metadata={
            "name": "dc-status",
            "type": "Element",
            "namespace": "",
        },
    )
    version: VersionType | None = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    title: list[TextWithSubType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    description: list[HtmlTextWithSubType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    warning: list[WarningType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    question: list[TextType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    reference: list[ReferenceType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    metadata: list[MetadataType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    abstract: bool = field(
        default=False,
        metadata={
            "type": "Attribute",
        },
    )
    cluster_id: str | None = field(
        default=None,
        metadata={
            "name": "cluster-id",
            "type": "Attribute",
        },
    )
    extends: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    hidden: bool = field(
        default=False,
        metadata={
            "type": "Attribute",
        },
    )
    prohibit_changes: bool = field(
        default=False,
        metadata={
            "name": "prohibitChanges",
            "type": "Attribute",
        },
    )
    lang: str | LangValue | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )
    base: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )
    id: str | None = field(
        default=None,
        metadata={
            "name": "Id",
            "type": "Attribute",
        },
    )


@dataclass
class TestResultType:
    """Data type for the &lt;xccdf:TestResult&gt; element, which holds the results
    of one application of the &lt;xccdf:Benchmark&gt;.

    The &lt;xccdf:TestResult&gt; element normally appears as the child
    of the &lt;xccdf:Benchmark&gt; element, although it may also appear
    as the top-level element of an XCCDF results document. XCCDF is not
    intended to be a database format for detailed results; the
    &lt;xccdf:TestResult&gt; element offers a way to store the results
    of individual tests in modest detail, with the ability to reference
    lower-level testing data. Although several of the child elements of
    this type technically support the @override attribute, the
    &lt;xccdf:TestResult&gt; element cannot be extended. Therefore,
    @override has no meaning within an &lt;xccdf:TestResult&gt; element
    and its children, and should not be used for them.

    :ivar benchmark: Reference to the &lt;xccdf:Benchmark&gt; for which
        the &lt;xccdf:TestResult&gt; records results. This property is
        required if this &lt;xccdf:TestResult&gt; element is the top-
        level element and optional otherwise.
    :ivar tailoring_file: The tailoring file element contains attributes
        used to identify an &lt;xccdf:Tailoring&gt; element used to
        guide the assessment reported on in this
        &lt;xccdf:TestResult&gt;. The tailoring element is required in
        an &lt;xccdf:TestResult&gt; if and only if an
        &lt;xccdf:Tailoring&gt; element guided the assessment recorded
        in the &lt;xccdf:TestResult&gt; or if the
        &lt;xccdf:Tailoring&gt; element records manual tailoring actions
        applied to this assessment.
    :ivar title: Title of the test.
    :ivar remark: A remark about the test, possibly supplied by the
        person administering the &lt;xccdf:Benchmark&gt; assessment
    :ivar organization: The name of the organization or other entity
        responsible for applying this &lt;xccdf:Benchmark&gt; and
        generating this result. When multiple &lt;xccdf:organization&gt;
        elements are used to indicate multiple organization names in a
        hierarchical organization, the highest-level organization should
        appear first.
    :ivar identity: Information about the system identity or user
        employed during application of the &lt;xccdf:Benchmark&gt;. If
        used, specifies the name of the authenticated identity.
    :ivar profile: The &lt;xccdf:profile&gt; element holds the value of
        the @id attribute value of the &lt;xccdf:Profile&gt; selected to
        be used in the assessment reported on by this
        &lt;xccdf:TestResult&gt;. This &lt;xccdf:Profile&gt; might be
        from the &lt;xccdf:Benchmark&gt; or from an
        &lt;xccdf:Tailoring&gt; file, if used. This element should
        appear if and only if an &lt;xccdf:Profile&gt; was selected to
        guide the assessment.
    :ivar target: Name or description of the target system whose test
        results are recorded in the &lt;xccdf:TestResult&gt; element
        (the system to which an &lt;xccdf:Benchmark&gt; test was
        applied). Each appearance of the element supplies a name by
        which the target host or device was identified at the time the
        test was run. The name may be any string, but applications
        should include the fully qualified DNS name whenever possible.
    :ivar target_address: Network address of the target system to which
        an &lt;xccdf:Benchmark&gt; test was applied. Typical forms for
        the address include IP version 4 (IPv4), IP version 6 (IPv6),
        and Ethernet media access control (MAC).
    :ivar target_facts: A list of named facts about the target system or
        platform.
    :ivar target_id_ref: References to external structures with
        identifying information about the target of this assessment.
    :ivar other_element: Identifying information expressed in other XML
        formats can be included here.
    :ivar platform: A platform on the target system. There should be one
        instance of this property for every platform that the target
        system was found to meet.
    :ivar set_value: Specific setting for a single &lt;xccdf:Value&gt;
        element used during the test.
    :ivar set_complex_value: Specific setting for a single
        &lt;xccdf:Value&gt; element used during the test when the given
        value is set to a complex type, such as a list.
    :ivar rule_result: The result of a single instance of an
        &lt;xccdf:Rule&gt; application against the target. The
        &lt;xccdf:TestResult&gt; must include at least one
        &lt;xccdf:rule-result&gt; record for each &lt;xccdf:Rule&gt;
        that was selected in the resolved &lt;xccdf:Benchmark&gt;.
    :ivar score: An overall score for this &lt;xccdf:Benchmark&gt; test.
    :ivar metadata: XML metadata associated with this
        &lt;xccdf:TestResult&gt;.
    :ivar signature: A digital signature asserting authorship and
        allowing verification of the integrity of the
        &lt;xccdf:TestResult&gt;.
    :ivar id: Unique identifier for this element.
    :ivar start_time: Time when testing began.
    :ivar end_time: Time when testing was completed and the results
        recorded.
    :ivar test_system: Name of the benchmark consumer program that
        generated this &lt;xccdf:TestResult&gt; element; should be
        either a CPE name or a CPE applicability language expression.
    :ivar version: The version number string copied from the
        &lt;xccdf:Benchmark&gt; used to direct this assessment.
    :ivar id_attribute: An identifier used for referencing elements
        included in an XML signature.
    """

    class Meta:
        name = "testResultType"

    benchmark: BenchmarkReferenceType | None = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    tailoring_file: TailoringReferenceType | None = field(
        default=None,
        metadata={
            "name": "tailoring-file",
            "type": "Element",
            "namespace": "",
        },
    )
    title: list[TextType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    remark: list[TextType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    organization: list[str] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    identity: IdentityType | None = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    profile: IdrefType | None = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    target: list[str] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
            "min_occurs": 1,
        },
    )
    target_address: list[str] = field(
        default_factory=list,
        metadata={
            "name": "target-address",
            "type": "Element",
            "namespace": "",
        },
    )
    target_facts: TargetFactsType | None = field(
        default=None,
        metadata={
            "name": "target-facts",
            "type": "Element",
            "namespace": "",
        },
    )
    target_id_ref: list[TargetIdRefType] = field(
        default_factory=list,
        metadata={
            "name": "target-id-ref",
            "type": "Element",
            "namespace": "",
        },
    )
    other_element: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Wildcard",
            "namespace": "##other",
        },
    )
    platform: list[Cpe2IdrefType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    set_value: list[ProfileSetValueType] = field(
        default_factory=list,
        metadata={
            "name": "set-value",
            "type": "Element",
            "namespace": "",
        },
    )
    set_complex_value: list[ProfileSetComplexValueType] = field(
        default_factory=list,
        metadata={
            "name": "set-complex-value",
            "type": "Element",
            "namespace": "",
        },
    )
    rule_result: list[RuleResultType] = field(
        default_factory=list,
        metadata={
            "name": "rule-result",
            "type": "Element",
            "namespace": "",
        },
    )
    score: list[ScoreType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
            "min_occurs": 1,
        },
    )
    metadata: list[MetadataType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    signature: SignatureType | None = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    id: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
            "pattern": r"xccdf_[^_]+_testresult_.+",
        },
    )
    start_time: XmlDateTime | None = field(
        default=None,
        metadata={
            "name": "start-time",
            "type": "Attribute",
        },
    )
    end_time: XmlDateTime | None = field(
        default=None,
        metadata={
            "name": "end-time",
            "type": "Attribute",
            "required": True,
        },
    )
    test_system: str | None = field(
        default=None,
        metadata={
            "name": "test-system",
            "type": "Attribute",
        },
    )
    version: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    id_attribute: str | None = field(
        default=None,
        metadata={
            "name": "Id",
            "type": "Attribute",
        },
    )


@dataclass
class Item(ItemType):
    """An item is a named constituent of an &lt;xccdf:Benchmark&gt;.

    There are three types of items: &lt;xccdf:Group&gt;,
    &lt;xccdf:Rule&gt; and &lt;xccdf:Value&gt;. The &lt;xccdf:Item&gt; element type
    imposes constraints shared by all &lt;xccdf:Group&gt;, &lt;xccdf:Rule&gt; and
    &lt;xccdf:Value&gt; elements. The itemType is abstract, so the element
    &lt;xccdf:Item&gt; can never appear in a valid XCCDF document.
    """

    class Meta:
        namespace = "http://checklists.nist.gov/xccdf/1.2"


@dataclass
class TestResult(TestResultType):
    """The &lt;xccdf:TestResult&gt; element encapsulates the results of a single
    application of an &lt;xccdf:Benchmark&gt; to a single target platform.

    The &lt;xccdf:TestResult&gt; element normally appears as the child
    of the &lt;xccdf:Benchmark&gt; element, although it may also appear
    as the top-level element of an XCCDF results document. XCCDF is not
    intended to be a database format for detailed results; the
    &lt;xccdf:TestResult&gt; element offers a way to store the results
    of individual tests in modest detail, with the ability to reference
    lower-level testing data.
    """

    class Meta:
        namespace = "http://checklists.nist.gov/xccdf/1.2"


@dataclass
class SelectableItemType(ItemType):
    """
    This abstract item type represents the basic data shared by all
    &lt;xccdf:Group&gt; and &lt;xccdf:Rule&gt; elements.

    :ivar rationale: Descriptive text giving rationale or motivations
        for abiding by this &lt;xccdf:Group&gt;/&lt;xccdf:Rule&gt;
        (i.e., why it is important to the security of the target
        platform).
    :ivar platform: Platforms to which this
        &lt;xccdf:Group&gt;/&lt;xccdf:Rule&gt; applies.
    :ivar requires: The identifiers of other &lt;xccdf:Group&gt; or
        &lt;xccdf:Rule&gt; elements that must be selected for this
        &lt;xccdf:Group&gt;/&lt;xccdf:Rule&gt; to be evaluated and
        scored properly. Each &lt;xccdf:requires&gt; element specifies a
        list of one or more required items by their identifiers. If at
        least one of the specified &lt;xccdf:Group&gt; or
        &lt;xccdf:Rule&gt; elements is selected, the requirement is met.
    :ivar conflicts: The identifier of another &lt;xccdf:Group&gt; or
        &lt;xccdf:Rule&gt; that must be unselected for this
        &lt;xccdf:Group&gt;/&lt;xccdf:Rule&gt; to be evaluated and
        scored properly. Each &lt;xccdf:conflicts&gt; element specifies
        a single conflicting item using its idref attribute. If the
        specified &lt;xccdf:Group&gt; or &lt;xccdf:Rule&gt; element is
        not selected, the requirement is met.
    :ivar selected: If true, this &lt;xccdf:Group&gt;/&lt;xccdf:Rule&gt;
        is selected to be processed as part of the
        &lt;xccdf:Benchmark&gt; when it is applied to a target system.
        An unselected &lt;xccdf:Group&gt; does not get processed, and
        its contents are not processed either (i.e., all descendants of
        an unselected &lt;xccdf:Group&gt; are implicitly unselected). An
        unselected &lt;xccdf:Rule&gt; is not checked and does not
        contribute to scoring.
    :ivar weight: The relative scoring weight of this
        &lt;xccdf:Group&gt;/&lt;xccdf:Rule&gt;, for computing a score,
        expressed as a non-negative real number. It denotes the
        importance of an &lt;xccdf:Group&gt;/&lt;xccdf:Rule&gt;. Under
        some scoring models, scoring is computed independently for each
        collection of sibling &lt;xccdf:Group&gt; and &lt;xccdf:Rule&gt;
        elements, then normalized as part of the overall scoring
        process.
    """

    class Meta:
        name = "selectableItemType"

    rationale: list[HtmlTextWithSubType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    platform: list[OverrideableCpe2IdrefType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    requires: list[IdrefListType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    conflicts: list[IdrefType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    selected: bool = field(
        default=True,
        metadata={
            "type": "Attribute",
        },
    )
    weight: Decimal = field(
        default=Decimal("1.0"),
        metadata={
            "type": "Attribute",
            "min_inclusive": Decimal("0.0"),
            "total_digits": 3,
        },
    )


@dataclass
class TailoringType:
    """Data type for the &lt;xccdf:Tailoring&gt; element.

    The &lt;xccdf:Tailoring&gt; element allows named tailorings (i.e.,
    &lt;xccdf:Profile&gt; elements) of an &lt;xccdf:Benchmark&gt; to be
    defined separately from the &lt;xccdf:Benchmark&gt; itself. The
    &lt;xccdf:Profile&gt; elements in an &lt;xccdf:Tailoring&gt; element
    can be used in two ways: First, an organization might wish to pre-
    define a set of tailoring actions to be applied on top of or instead
    of the tailoring performed by an &lt;xccdf:Benchmark&gt; element's
    &lt;xccdf:Profile&gt; elements. Second, an &lt;xccdf:Tailoring&gt;
    element can be used to record manual tailoring actions performed
    during the course of an assessment.

    :ivar benchmark: Identifies the &lt;xccdf:Benchmark&gt; to which
        this tailoring applies. A &lt;xccdf:Tailoring&gt; document is
        only applicable to a single &lt;xccdf:Benchmark&gt;. Note,
        however, that this is a purely informative field.
    :ivar status: Status of the tailoring and date at which it attained
        that status. Authors may use this element to record the maturity
        or consensus level of an &lt;xccdf:Tailoring&gt; element.
    :ivar dc_status: Holds additional status information using the
        Dublin Core format.
    :ivar version: The version of this &lt;xccdf:Tailoring&gt; element,
        with a required @time attribute that records when the
        &lt;xccdf:Tailoring&gt; element was created. This timestamp is
        necessary because, under some circumstances, a copy of an
        &lt;xccdf:Tailoring&gt; document might be automatically
        generated. Without the version and timestamp, tracking of these
        automatically created &lt;xccdf:Tailoring&gt; documents could
        become problematic.
    :ivar metadata: XML metadata for the &lt;xccdf:Tailoring&gt;
        element.
    :ivar profile: &lt;xccdf:Profile&gt; elements that reference and
        customize sets of items in an &lt;xccdf:Benchmark&gt;.
    :ivar signature: A digital signature asserting authorship and
        allowing verification of the integrity of the
        &lt;xccdf:Tailoring&gt;.
    :ivar id: Unique identifier for this element.
    :ivar id_attribute: An identifier used for referencing elements
        included in an XML signature.
    """

    class Meta:
        name = "tailoringType"

    benchmark: TailoringBenchmarkReferenceType | None = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    status: list[Status] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://checklists.nist.gov/xccdf/1.2",
        },
    )
    dc_status: list[DcStatusType] = field(
        default_factory=list,
        metadata={
            "name": "dc-status",
            "type": "Element",
            "namespace": "",
        },
    )
    version: TailoringVersionType | None = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "",
            "required": True,
        },
    )
    metadata: list[MetadataType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    profile: list[Profile] = field(
        default_factory=list,
        metadata={
            "name": "Profile",
            "type": "Element",
            "namespace": "http://checklists.nist.gov/xccdf/1.2",
            "min_occurs": 1,
        },
    )
    signature: SignatureType | None = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    id: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
            "pattern": r"xccdf_[^_]+_tailoring_.+",
        },
    )
    id_attribute: str | None = field(
        default=None,
        metadata={
            "name": "Id",
            "type": "Attribute",
        },
    )


@dataclass
class ValueType(ItemType):
    """
    Data type for the &lt;xccdf:Value&gt; element, which is a named parameter that
    can be substituted into properties of other elements within the
    &lt;xccdf:Benchmark&gt;, including the interior of structured check
    specifications and fix scripts.

    :ivar value: A simple (number, string, or boolean) value associated
        with this &lt;xccdf:Value&gt;. At any time an
        &lt;xccdf:Value&gt; has one active (simple or complex) value. If
        a selector value has been provided under &lt;xccdf:Profile&gt;
        selection or tailoring then the active
        &lt;xccdf:value&gt;/&lt;xccdf:complex-value&gt; is the one with
        a matching @selector. If there is no provided selector or if the
        provided selector does not match the @selector attribute of any
        &lt;xccdf:value&gt; or &lt;xccdf:complex-value&gt;, the active
        &lt;xccdf:value&gt;/&lt;xccdf:complex-value&gt; is the one with
        an empty or absent @selector or, failing that, the first
        &lt;xccdf:value&gt; or &lt;xccdf:complex-value&gt; in the XML.
        When an &lt;xccdf:Value&gt; is exported or used in text
        substitution, it is the currently active &lt;xccdf:value&gt; or
        &lt;xccdf:complex-value&gt; that is actually used. If there are
        multiple &lt;xccdf:value&gt; and/or &lt;xccdf:complex-value&gt;
        elements, only one may omit a @selector attribute and no two may
        have the same @selector value.
    :ivar complex_value: A complex (list) value associated with this
        &lt;xccdf:Value&gt;. See the description of the
        &lt;xccdf:value&gt; property for &lt;xccdf:Rule&gt; elements
        regarding activation of an &lt;xccdf:complex-value&gt;.
    :ivar default: The default value displayed to the user as a
        suggestion by benchmark producers during tailoring of this
        &lt;xccdf:Value&gt; element. (This is not the default value of
        an &lt;xccdf:Value&gt;; it is just the default display.) If
        there are multiple &lt;xccdf:default&gt; and/or
        &lt;xccdf:complex-default&gt; elements, only one may omit a
        @selector attribute and no two may have the same @selector
        value.
    :ivar complex_default: The default &lt;xccdf:complex-value&gt;
        displayed to the user as a suggestion by benchmark producers
        during tailoring of this &lt;xccdf:Value&gt; element. (This is
        not the default value of an &lt;xccdf:Value&gt;; it is just the
        default display.) If there are multiple &lt;xccdf:default&gt;
        and &lt;xccdf:complex-default&gt; elements, only one may omit a
        @selector attribute and no two may have the same @selector
        value.
    :ivar match: A Perl Compatible Regular Expression that a benchmark
        producer may apply during tailoring to validate a user’s input
        for the &lt;xccdf:Value&gt;. It uses implicit anchoring. It
        applies only when the @type property is “string” or “number” or
        a list of strings and/or numbers.
    :ivar lower_bound: Minimum legal value for this &lt;xccdf:Value&gt;.
        It is used to constrain value input during tailoring, when the
        @type property is “number”. Values supplied by the user for
        tailoring the &lt;xccdf:Benchmark&gt; must be equal to or
        greater than this number.
    :ivar upper_bound: Maximum legal value for this &lt;xccdf:Value&gt;.
        It is used to constrain value input during tailoring, when the
        @type is “number”. Values supplied by the user for tailoring the
        &lt;xccdf:Benchmark&gt; must be less than or equal to than this
        number.
    :ivar choices: A list of legal or suggested choices (values) for an
        &lt;xccdf:Value&gt; element, to be used during tailoring and
        document generation.
    :ivar source: URI indicating where the tool may acquire values,
        value bounds, or value choices for this &lt;xccdf:Value&gt;
        element. XCCDF does not attach any meaning to the URI; it may be
        an arbitrary community or tool-specific value, or a pointer
        directly to a resource. If several instances of the
        &lt;xccdf:source&gt; property appear, then they represent
        alternative means or locations for obtaining the value in
        descending order of preference (i.e., most preferred first).
    :ivar signature: A digital signature asserting authorship and
        allowing verification of the integrity of the
        &lt;xccdf:Value&gt;.
    :ivar id: The unique identifier for this element.
    :ivar type_value: The data type of the &lt;xccdf:Value&gt;. A tool
        may choose any convenient form to store an &lt;xccdf:Value&gt;
        element’s &lt;xccdf:value&gt; element, but the @type attribute
        conveys how the &lt;xccdf:Value&gt; should be treated for user
        input validation purposes during tailoring processing. The @type
        attribute may also be used to give additional guidance to the
        user or to validate the user’s input. In the case of a list of
        values, the @type attribute, if present, applies to all elements
        of the list individually.
    :ivar operator: The operator to be used for comparing this
        &lt;xccdf:Value&gt; to some part of the test system’s
        configuration during &lt;xccdf:Rule&gt; checking.
    :ivar interactive: Whether tailoring for this &lt;xccdf:Value&gt;
        should be performed during &lt;xccdf:Benchmark&gt; application.
        The benchmark consumer may ignore the attribute if asking the
        user is not feasible or not supported.
    :ivar interface_hint: A hint or recommendation to a benchmark
        consumer or producer about how the user might select or adjust
        the &lt;xccdf:Value&gt;.
    """

    class Meta:
        name = "valueType"

    value: list[SelStringType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    complex_value: list[SelComplexValueType] = field(
        default_factory=list,
        metadata={
            "name": "complex-value",
            "type": "Element",
            "namespace": "",
        },
    )
    default: list[SelStringType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    complex_default: list[SelComplexValueType] = field(
        default_factory=list,
        metadata={
            "name": "complex-default",
            "type": "Element",
            "namespace": "",
        },
    )
    match: list[SelStringType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    lower_bound: list[SelNumType] = field(
        default_factory=list,
        metadata={
            "name": "lower-bound",
            "type": "Element",
            "namespace": "",
        },
    )
    upper_bound: list[SelNumType] = field(
        default_factory=list,
        metadata={
            "name": "upper-bound",
            "type": "Element",
            "namespace": "",
        },
    )
    choices: list[SelChoicesType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    source: list[UriRefType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    signature: SignatureType | None = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    id: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
            "pattern": r"xccdf_[^_]+_value_.+",
        },
    )
    type_value: ValueTypeType = field(
        default=ValueTypeType.STRING,
        metadata={
            "name": "type",
            "type": "Attribute",
        },
    )
    operator: ValueOperatorType = field(
        default=ValueOperatorType.EQUALS,
        metadata={
            "type": "Attribute",
        },
    )
    interactive: bool = field(
        default=False,
        metadata={
            "type": "Attribute",
        },
    )
    interface_hint: InterfaceHintType | None = field(
        default=None,
        metadata={
            "name": "interfaceHint",
            "type": "Attribute",
        },
    )


@dataclass
class Tailoring(TailoringType):
    """The &lt;xccdf:Tailoring&gt; element holds one or more &lt;xccdf:Profile&gt;
    elements.

    These &lt;xccdf:Profile&gt; elements record additional tailoring
    activities that apply to a given &lt;xccdf:Benchmark&gt;.
    &lt;xccdf:Tailoring&gt; elements are separate from
    &lt;xccdf:Benchmark&gt; documents, but each &lt;xccdf:Tailoring&gt;
    element is associated with a specific &lt;xccdf:Benchmark&gt;
    document. By defining these tailoring actions separately from the
    &lt;xccdf:Benchmark&gt; document to which they apply, these actions
    can be recorded without affecting the integrity of the source
    itself.
    """

    class Meta:
        namespace = "http://checklists.nist.gov/xccdf/1.2"


@dataclass
class Value(ValueType):
    """
    The &lt;xccdf:Value&gt; element is a named parameter that can be substituted
    into properties of other elements within the &lt;xccdf:Benchmark&gt;, including
    the interior of structured check specifications and fix scripts.
    """

    class Meta:
        namespace = "http://checklists.nist.gov/xccdf/1.2"


@dataclass
class RuleType(SelectableItemType):
    """
    Data type for the &lt;xccdf:Rule&gt; element that represents a specific
    &lt;xccdf:Benchmark&gt; test.

    :ivar ident: A globally meaningful identifier for this
        &lt;xccdf:Rule&gt;. This may be the name or identifier of a
        security configuration issue or vulnerability that the
        &lt;xccdf:Rule&gt; assesses.
    :ivar impact_metric: The potential impact of failure to conform to
        the &lt;xccdf:Rule&gt;, expressed as a CVSS 2.0 base vector.
    :ivar profile_note: Text that describes special aspects of the
        &lt;xccdf:Rule&gt; related to one or more &lt;xccdf:Profile&gt;
        elements. This allows an author to document things within
        &lt;xccdf:Rule&gt; elements that are specific to a given
        &lt;xccdf:Profile&gt;, and then select the appropriate text
        based on the selected &lt;xccdf:Profile&gt; and display it to
        the reader.
    :ivar fixtext: Data that describes how to bring a target system into
        compliance with this &lt;xccdf:Rule&gt;.
    :ivar fix: A command string, script, or other system modification
        statement that, if executed on the target system, can bring it
        into full, or at least better, compliance with this
        &lt;xccdf:Rule&gt;.
    :ivar check: The definition of, or a reference to, the target system
        check needed to test compliance with this &lt;xccdf:Rule&gt;.
        Sibling &lt;xccdf:check&gt; elements must have different values
        for the combination of their @selector and @system attributes,
        and must have different values for their @id attribute (if any).
    :ivar complex_check: A boolean expression composed of operators
        (and, or, not) and individual checks.
    :ivar signature: A digital signature asserting authorship and
        allowing verification of the integrity of the
        &lt;xccdf:Rule&gt;.
    :ivar id: Unique element identifier used by other elements to refer
        to this element.
    :ivar role: The &lt;xccdf:Rule&gt; element’s role in scoring and
        reporting.
    :ivar severity: Severity level code to be used for metrics and
        tracking.
    :ivar multiple: Applicable in cases where there are multiple
        instances of a target. For example, an &lt;xccdf:Rule&gt; may
        provide a recommendation about the configuration of application
        user accounts, but an application may have many user accounts.
        Each account would be considered an instance of the broader
        assessment target of user accounts. If the @multiple attribute
        is set to true, each instance of the target to which the
        &lt;xccdf:Rule&gt; can apply should be tested separately and the
        results should be recorded separately. If @multiple is set to
        false, the test results of such instances should be combined. If
        the checking system does not combine these results
        automatically, the results of each instance should be ANDed
        together to produce a single result. If the benchmark consumer
        cannot perform multiple instantiation, or if multiple
        instantiation of the &lt;xccdf:Rule&gt; is not applicable for
        the target system, then the benchmark consumer may ignore this
        attribute.
    """

    class Meta:
        name = "ruleType"

    ident: list[IdentType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    impact_metric: str | None = field(
        default=None,
        metadata={
            "name": "impact-metric",
            "type": "Element",
            "namespace": "",
        },
    )
    profile_note: list[ProfileNoteType] = field(
        default_factory=list,
        metadata={
            "name": "profile-note",
            "type": "Element",
            "namespace": "",
        },
    )
    fixtext: list[FixTextType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    fix: list[FixType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    check: list[CheckType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    complex_check: ComplexCheckType | None = field(
        default=None,
        metadata={
            "name": "complex-check",
            "type": "Element",
            "namespace": "",
        },
    )
    signature: SignatureType | None = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    id: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
            "pattern": r"xccdf_[^_]+_rule_.+",
        },
    )
    role: RoleEnumType = field(
        default=RoleEnumType.FULL,
        metadata={
            "type": "Attribute",
        },
    )
    severity: SeverityEnumType = field(
        default=SeverityEnumType.UNKNOWN,
        metadata={
            "type": "Attribute",
        },
    )
    multiple: bool = field(
        default=False,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass
class Rule(RuleType):
    """The &lt;xccdf:Rule&gt; element contains the description for a single item of
    guidance or constraint.

    &lt;xccdf:Rule&gt; elements form the basis for testing a target
    platform for compliance with an &lt;xccdf:Benchmark&gt;, for
    scoring, and for conveying descriptive prose, identifiers,
    references, and remediation information.
    """

    class Meta:
        namespace = "http://checklists.nist.gov/xccdf/1.2"


@dataclass
class GroupType(SelectableItemType):
    """Data type for the &lt;xccdf:Group&gt; element.

    A &lt;xccdf:Group&gt; element contains descriptive information about
    a portion of an &lt;xccdf:Benchmark&gt;, as well as
    &lt;xccdf:Rule&gt;, &lt;xccdf:Value&gt;, and/or other
    &lt;xccdf:Group&gt; elements

    :ivar value: &lt;xccdf:Value&gt; elements that belong to this
        &lt;xccdf:Group&gt;.
    :ivar group: Sub-&lt;xccdf:Groups&gt; under this
        &lt;xccdf:Group&gt;.
    :ivar rule: &lt;xccdf:Rule&gt; elements that belong to this
        &lt;xccdf:Group&gt;.
    :ivar signature: A digital signature asserting authorship and
        allowing verification of the integrity of the
        &lt;xccdf:Group&gt;.
    :ivar id: Unique element identifier; used by other elements to refer
        to this element.
    """

    class Meta:
        name = "groupType"

    value: list[Value] = field(
        default_factory=list,
        metadata={
            "name": "Value",
            "type": "Element",
            "namespace": "http://checklists.nist.gov/xccdf/1.2",
        },
    )
    group: list["Group"] = field(
        default_factory=list,
        metadata={
            "name": "Group",
            "type": "Element",
            "namespace": "http://checklists.nist.gov/xccdf/1.2",
        },
    )
    rule: list[Rule] = field(
        default_factory=list,
        metadata={
            "name": "Rule",
            "type": "Element",
            "namespace": "http://checklists.nist.gov/xccdf/1.2",
        },
    )
    signature: SignatureType | None = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    id: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
            "pattern": r"xccdf_[^_]+_group_.+",
        },
    )


@dataclass
class Group(GroupType):
    """An item that can hold other items.

    It allows an author to collect related items into a common structure
    and provide descriptive text and references about them.
    """

    class Meta:
        namespace = "http://checklists.nist.gov/xccdf/1.2"


@dataclass
class Benchmark:
    """This is the root element of the XCCDF document; it must appear exactly once.

    It encloses the entire benchmark, and contains both descriptive
    information and structural information. Note that the order of
    &lt;xccdf:Group&gt; and &lt;xccdf:Rule&gt; child elements may matter
    for the appearance of a generated document. &lt;xccdf:Group&gt; and
    &lt;xccdf:Rule&gt; children may be freely intermingled, but they
    must appear after any &lt;xccdf:Value&gt; children. All the other
    children must appear in the order shown.

    :ivar status: Status of the &lt;xccdf:Benchmark&gt; indicating its
        level of maturity or consensus. If more than one
        &lt;xccdf:status&gt; element appears, the element's @date
        attribute should be included.
    :ivar dc_status: Holds additional status information using the
        Dublin Core format.
    :ivar title: Title of the &lt;xccdf:Benchmark&gt;; an
        &lt;xccdf:Benchmark&gt; should have an &lt;xccdf:title&gt;.
    :ivar description: Text that describes the &lt;xccdf:Benchmark&gt;;
        an &lt;xccdf:Benchmark&gt; should have an
        &lt;xccdf:description&gt;.
    :ivar notice: Legal notices (licensing information, terms of use,
        etc.), copyright statements, warnings, and other advisory
        notices about this &lt;xccdf:Benchmark&gt; and its use.
    :ivar front_matter: Introductory matter for the beginning of the
        &lt;xccdf:Benchmark&gt; document; intended for use during
        Document Generation.
    :ivar rear_matter: Concluding material for the end of the
        &lt;xccdf:Benchmark&gt; document; intended for use during
        Document Generation.
    :ivar reference: Supporting references for the
        &lt;xccdf:Benchmark&gt; document.
    :ivar plain_text: Definitions for reusable text blocks, each with a
        unique identifier.
    :ivar platform_specification: A list of identifiers for complex
        platform definitions, written in CPE applicability language
        format. Authors may define complex platforms within this
        element, and then use their locally unique identifiers anywhere
        in the &lt;xccdf:Benchmark&gt; element in place of a CPE name.
    :ivar platform: Applicable platforms for this
        &lt;xccdf:Benchmark&gt;. Authors should use the element to
        identify the systems or products to which the
        &lt;xccdf:Benchmark&gt; applies.
    :ivar version: Version number of the &lt;xccdf:Benchmark&gt;.
    :ivar metadata: XML metadata for the &lt;xccdf:Benchmark&gt;.
        Metadata allows many additional pieces of information, including
        authorship, publisher, support, and other similar details, to be
        embedded in an &lt;xccdf:Benchmark&gt;.
    :ivar model: URIs of suggested scoring models to be used when
        computing a score for this &lt;xccdf:Benchmark&gt;. A suggested
        list of scoring models and their URIs is provided in the XCCDF
        specification.
    :ivar profile: &lt;xccdf:Profile&gt; elements that reference and
        customize sets of items in the &lt;xccdf:Benchmark&gt;.
    :ivar value: Parameter &lt;xccdf:Value&gt; elements that support
        &lt;xccdf:Rule&gt; elements and descriptions in the
        &lt;xccdf:Benchmark&gt;.
    :ivar group: &lt;xccdf:Group&gt; elements that comprise the
        &lt;xccdf:Benchmark&gt;; each may contain additional
        &lt;xccdf:Value&gt;, &lt;xccdf:Rule&gt;, and other
        &lt;xccdf:Group&gt; elements.
    :ivar rule: &lt;xccdf:Rule&gt; elements that comprise the
        &lt;xccdf:Benchmark&gt;.
    :ivar test_result: &lt;xccdf:Benchmark&gt; test result records (one
        per &lt;xccdf:Benchmark&gt; run).
    :ivar signature: A digital signature asserting authorship and
        allowing verification of the integrity of the
        &lt;xccdf:Benchmark&gt;.
    :ivar id: Unique &lt;xccdf:Benchmark&gt; identifier.
    :ivar id_attribute: An identifier used for referencing elements
        included in an XML signature.
    :ivar resolved: True if &lt;xccdf:Benchmark&gt; has already
        undergone the resolution process.
    :ivar style: Name of an &lt;xccdf:Benchmark&gt; authoring style or
        set of conventions or constraints to which this
        &lt;xccdf:Benchmark&gt; conforms (e.g., “SCAP 1.2”).
    :ivar style_href: URL of a supplementary stylesheet or schema
        extension that can be used to verify conformance to the named
        style.
    :ivar lang:
    """

    class Meta:
        namespace = "http://checklists.nist.gov/xccdf/1.2"

    status: list[Status] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "min_occurs": 1,
        },
    )
    dc_status: list[DcStatusType] = field(
        default_factory=list,
        metadata={
            "name": "dc-status",
            "type": "Element",
            "namespace": "",
        },
    )
    title: list[TextType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    description: list[HtmlTextWithSubType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    notice: list[NoticeType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    front_matter: list[HtmlTextWithSubType] = field(
        default_factory=list,
        metadata={
            "name": "front-matter",
            "type": "Element",
            "namespace": "",
        },
    )
    rear_matter: list[HtmlTextWithSubType] = field(
        default_factory=list,
        metadata={
            "name": "rear-matter",
            "type": "Element",
            "namespace": "",
        },
    )
    reference: list[ReferenceType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    plain_text: list[PlainTextType] = field(
        default_factory=list,
        metadata={
            "name": "plain-text",
            "type": "Element",
            "namespace": "",
        },
    )
    platform_specification: str | None = field(
        default=None,
        metadata={
            "name": "platform-specification",
            "type": "Element",
            "namespace": "http://cpe.mitre.org/language/2.0",
        },
    )
    platform: list[Cpe2IdrefType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    version: VersionType | None = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "",
            "required": True,
        },
    )
    metadata: list[MetadataType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    model: list[Model] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    profile: list[Profile] = field(
        default_factory=list,
        metadata={
            "name": "Profile",
            "type": "Element",
        },
    )
    value: list[Value] = field(
        default_factory=list,
        metadata={
            "name": "Value",
            "type": "Element",
        },
    )
    group: list[Group] = field(
        default_factory=list,
        metadata={
            "name": "Group",
            "type": "Element",
        },
    )
    rule: list[Rule] = field(
        default_factory=list,
        metadata={
            "name": "Rule",
            "type": "Element",
        },
    )
    test_result: list[TestResult] = field(
        default_factory=list,
        metadata={
            "name": "TestResult",
            "type": "Element",
        },
    )
    signature: SignatureType | None = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )
    id: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
            "pattern": r"xccdf_[^_]+_benchmark_.+",
        },
    )
    id_attribute: str | None = field(
        default=None,
        metadata={
            "name": "Id",
            "type": "Attribute",
        },
    )
    resolved: bool = field(
        default=False,
        metadata={
            "type": "Attribute",
        },
    )
    style: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    style_href: str | None = field(
        default=None,
        metadata={
            "name": "style-href",
            "type": "Attribute",
        },
    )
    lang: str | LangValue | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )
