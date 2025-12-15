from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional

from xsdata.models.datatype import XmlDate, XmlDateTime

from cis_bench.models.xccdf_v1_1.xml import LangValue

__NAMESPACE__ = "http://checklists.nist.gov/xccdf/1.1"


@dataclass
class UriidrefType:
    """Data type for elements that have no content, just a mandatory URI as an id.

    (This is mainly for the
    platform element, which uses CPE URIs and CPE Language
    identifers used as platform identifiers.)  When referring
    to a local CPE Language identifier, the URL should use
    local reference syntax: "#cpeid1".
    """

    class Meta:
        name = "URIidrefType"

    idref: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
        },
    )


class CcOperatorEnumType(Enum):
    """The type for the allowed operator names for the complex-check operator
    attribute.

    For now, we just allow boolean AND and OR as operators.  (The
    complex-check has a separate mechanism for negation.)
    """

    OR = "OR"
    AND = "AND"


@dataclass
class CheckContentRefType:
    """Data type for the check-content-ref element, which points to the code for a
    detached check in another file.

    This element has no body, just a couple of attributes: href and
    name.  The name is optional, if it does not appear then this
    reference is to the entire other document.
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
    """Data type for the check-content element, which holds the actual code of an
    enveloped check in some other (non-XCCDF) language.

    This element can hold almost anything; XCCDF tools do not process
    its content directly.
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
    """
    Data type for the check-export element, which specifies a mapping between an
    XCCDF internal Value id and a value name to be used by the checking system or
    processor.
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
    """Data type for the check-import element, which specifies a value that the
    benchmark author wishes to retrieve from the the checking system.

    The import-name attribute gives the name or id of the value in the
    checking system. When the check-import element appears in the
    context of a rule-result, then the element's content is the desired
    value.  When the check-import element appears in the context of a
    Rule, then it should be empty and any content must be ignored.
    """

    class Meta:
        name = "checkImportType"

    value: str = field(
        default="",
        metadata={
            "required": True,
        },
    )
    import_name: str | None = field(
        default=None,
        metadata={
            "name": "import-name",
            "type": "Attribute",
            "required": True,
        },
    )


class FixStrategyEnumType(Enum):
    """Allowed strategy keyword values for a Rule fix or fixtext.

    The allowed values are:
    unknown= strategy not defined (default for forward
    compatibility for XCCDF 1.0)
    configure=adjust target config or settings
    patch=apply a patch, hotfix, or update
    policy=remediation by changing policies/procedures
    disable=turn off or deinstall something
    enable=turn on or install something
    restrict=adjust permissions or ACLs
    update=install upgrade or update the system
    combination=combo of two or more of the above
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
    """
    Type for a long-term globally meaningful identifier, consisting of a string
    (ID) and a URI of the naming scheme within which the name is meaningful.
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


@dataclass
class IdentityType:
    """Type for an identity element in a TestResult.

    The content is a string, the name of the identity. The authenticated
    attribute indicates whether the test system authenticated using that
    identity in order to apply the benchmark.  The privileged attribute
    indicates whether the identity has access rights beyond those of
    normal system users (e.g. "root" on Unix")
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
    Data type for elements that have no content, just a space-separated list of id
    references.
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
    Data type for elements that have no content, just a mandatory id reference.
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
    """Type for an instance element in a fix element.

    The
    instance element inside a fix element designates a
    spot where the name of the instance should be
    substituted into the fix template to generate the
    final fix data.  The instance element in this usage
    has one optional attribute: context.
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
    """Type for an instance element in a rule-result.

    The content is a string, but the element may
    also have two attribute: context and parentContext.
    This type records the details of the target system
    instance for multiply instantiated rules.
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

    When an interfaceHint appears on the Value, it provides a suggestion
    to a tailoring or benchmarking tool about how to present the UI for
    adjusting a Value.
    """

    CHOICE = "choice"
    TEXTLINE = "textline"
    TEXT = "text"
    DATE = "date"
    DATETIME = "datetime"


@dataclass
class MetadataType:
    """Metadata for the Benchmark, should be Dublin Core or some other well-
    specified and accepted metadata format.

    If Dublin Core, then it will be a sequence of simple Dublin Core
    elements.  The NIST checklist metadata should also be supported,
    although the specification document is still in draft in NIST
    special pub 800-70.
    """

    class Meta:
        name = "metadataType"

    purl_org_dc_elements_1_1_element: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Wildcard",
            "namespace": "http://purl.org/dc/elements/1.1/",
        },
    )
    checklists_nist_gov_sccf_0_1_element: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Wildcard",
            "namespace": "http://checklists.nist.gov/sccf/0.1",
            "process_contents": "skip",
        },
    )


class MsgSevEnumType(Enum):
    """
    Allowed values for message severity.
    """

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ParamType:
    """Type for a scoring model parameter: a name and a
    string value."""

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
    """
    Data type for a reusable text block, with an unique id attribute.
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
    """Type for the set-value element in a Profile; it has one required attribute
    and string content.

    The attribute is 'idref', it refers to a Value.
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
    """Allowed rating values values for a Rule fix
    or fixtext: disruption, complexity, and maybe overhead.
    The possible values are:
    unknown= rating unknown or impossible to estimate
    (default for forward compatibility for XCCDF 1.0)
    low = little or no potential for disruption,
    very modest complexity
    medium= some chance of minor disruption,
    substantial complexity
    high = likely to cause serious disruption, very complex"""

    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class ReferenceType:
    """Data type for a reference citation, an href URL attribute (optional), with
    content of text or simple Dublin Core elements.

    Elements of this type can also have an override attribute to help
    manage inheritance.
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
    """Allowed result indicators for a test, several possibilities:

    pass= the test passed, target complies w/ benchmark fail= the test
    failed, target does not comply error= an error occurred and test
    could not complete, or the test does not apply to this plaform
    unknown= could not tell what happened, results with this status are
    not to be scored notapplicable=Rule did not apply to test target
    fixed=rule failed, but was later fixed (score as pass)
    notchecked=Rule did not cause any evaluation by the checking engine
    (role of "unchecked") notselected=Rule was not selected in the
    Benchmark, and therefore was not checked (selected="0")
    informational=Rule was evaluated by the checking engine, but isn't
    to be scored (role of "unscored")
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
    """Allowed checking and scoring roles for a Rule.

    There are several possible values:
    full = if the rule is selected, then check it and let the
    result contribute to the score and appear in reports
    (default, for compatibility for XCCDF 1.0).
    unscored = check the rule, and include the results in
    any report, but do not include the result in
    score computations (in the default scoring model
    the same effect can be achieved with weight=0)
    unchecked = don't check the rule, just force the result
    status to 'unknown'.  Include the rule's
    information in any reports.
    """

    FULL = "full"
    UNSCORED = "unscored"
    UNCHECKED = "unchecked"


@dataclass
class ScoreType:
    """
    Type for a score value in a TestResult, the content is a real number and the
    element can have two optional attributes.
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
class SelChoicesType:
    """The choice element specifies a list of legal or suggested choices for a
    Value object.

    It holds one or more choice elements, a mustMatch attribute, and a
    selector attribute.
    """

    class Meta:
        name = "selChoicesType"

    choice: list[str] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
            "min_occurs": 1,
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
class SelNumType:
    """This type is for an element that has numeric content and a selector
    attribute.

    It is used for two of the child elements of Value.
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
    """This type is for an element that has string content and a selector
    attribute.

    It is used for some of the child elements of Value.
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
    """Allowed severity values for a Rule.

    there are several possible values:
    unknown= severity not defined (default, for forward
    compatibility from XCCDF 1.0)
    info = rule is informational only, failing the
    rule does not imply failure to conform to
    the security guidance of the benchmark.
    (usually would also have a weight of 0)
    low = not a serious problem
    medium= fairly serious problem
    high = a grave or critical problem
    """

    UNKNOWN = "unknown"
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class SignatureType:
    """
    XML-Signature over the Benchmark; note that this will always be an 'enveloped'
    signature, so the single element child of this element should be
    dsig:Signature.
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
    The possible status codes for an Benchmark or Item to be inherited from the
    parent element if it is not defined.
    """

    ACCEPTED = "accepted"
    DEPRECATED = "deprecated"
    DRAFT = "draft"
    INCOMPLETE = "incomplete"
    INTERIM = "interim"


@dataclass
class UriRefType:
    """
    Data type for elements that have no content, just a URI.
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
    """Allowed operators for Values.

    Note that most of these are valid only for numeric data, but the
    schema doesn't enforce that.
    """

    EQUALS = "equals"
    NOT_EQUAL = "not equal"
    GREATER_THAN = "greater than"
    LESS_THAN = "less than"
    GREATER_THAN_OR_EQUAL = "greater than or equal"
    LESS_THAN_OR_EQUAL = "less than or equal"
    PATTERN_MATCH = "pattern match"


class ValueTypeType(Enum):
    """
    Allowed data types for Values, just string, numeric, and true/false.
    """

    NUMBER = "number"
    STRING = "string"
    BOOLEAN = "boolean"


@dataclass
class VersionType:
    """
    Type for a version number, with a timestamp attribute for when the version was
    made.
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
    """Allowed warning category keywords for the warning element.

    The allowed categories are:
    general=broad or general-purpose warning (default
    for compatibility for XCCDF 1.0)
    functionality=warning about possible impacts to
    functionality or operational features
    performance=warning about changes to target
    system performance or throughput
    hardware=warning about hardware restrictions or
    possible impacts to hardware
    legal=warning about legal implications
    regulatory=warning about regulatory obligations
    or compliance implications
    management=warning about impacts to the mgmt
    or administration of the target system
    audit=warning about impacts to audit or logging
    dependency=warning about dependencies between
    this Rule and other parts of the target
    system, or version dependencies.
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
    """Data type for the check element, a checking system specification URI, and
    XML content.

    The content of the
    check element is: zero or more check-export elements,
    zero or more check-content-ref elements, and finally
    an optional check-content element.  An content-less
    check element isn't legal, but XSD cannot express that!
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
    base: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass
class FactType:
    """Element type for a fact about a target system: a
    name-value pair with a type. The content of the element
    is the value, the type attribute gives the type.  This
    is an area where XML schema is weak: we can't make the
    schema validator check that the content matches the type."""

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
class FixType:
    """Type for a string with embedded Value and instance substitutions and an
    optional platform id ref attribute, but no embedded XHTML markup.

    The platform attribute should refer to a platform-definition element
    in the platform-definitions child of the Benchmark.
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
                    "type": IdrefType,
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
class HtmlTextType:
    """Type for a string with XHTML elements and xml:lang attribute.

    Elements of this type can also have an override attribute to help
    manage inheritance.
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
class HtmlTextWithSubType:
    """Type for a string with embedded Value substitutions and XHTML elements, and
    an xml:lang attribute.

    Elements of this type can also have an override attribute to help
    manage inheritance.  [Note: this definition is rather loose, it
    allows anything whatsoever to occur insides XHTML tags inside here.
    Further, constraints of the XHTML schema do not get checked!  It
    might be possible to solve this using XML Schema redefinition
    features.]
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
                    "type": IdrefType,
                    "namespace": "",
                },
            ),
        },
    )


@dataclass
class MessageType:
    """Type for a message generated by the checking engine or XCCDF tool during
    benchmark testing.

    Content is string plus required severity attribute.
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
    """A suggested scoring model for a Benchmark, also encapsulating any parameters
    needed by the model.

    Every model is designated with a URI, which appears here as the
    system attribute.
    """

    class Meta:
        name = "model"
        namespace = "http://checklists.nist.gov/xccdf/1.1"

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
    """
    Data type for legal notice element that has text content and a unique id
    attribute.
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
class OverrideableIdrefType(IdrefType):
    """
    Data type for elements that have no content, just a mandatory id reference, but
    also have an override attribute for controlling inheritance.
    """

    class Meta:
        name = "overrideableIdrefType"

    override: bool = field(
        default=False,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass
class OverrideableUriidrefType(UriidrefType):
    """
    Data type for elements that have no content, just a mandatory URI reference,
    but also have an override attribute for controlling inheritance.
    """

    class Meta:
        name = "overrideableURIidrefType"

    override: bool = field(
        default=False,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass
class ProfileNoteType:
    """
    Type for a string with embedded Value substitutions and XHTML elements, an
    xml:lang attribute, and a profile-note tag.
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
                    "type": IdrefType,
                    "namespace": "",
                },
            ),
        },
    )


@dataclass
class Status:
    """
    The acceptance status of an Item with an optional date attribute that signifies
    the date of the status change.
    """

    class Meta:
        name = "status"
        namespace = "http://checklists.nist.gov/xccdf/1.1"

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
class TextType:
    """Type for a string with an xml:lang attribute.

    Elements of this type can also have an override attribute to help
    manage inheritance.
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
class TextWithSubType:
    """Type for a string with embedded Value substitutions and XHTML elements, and
    an xml:lang attribute.

    Elements of this type can also have an override attribute to help
    manage inheritance.
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
                    "type": IdrefType,
                    "namespace": "",
                },
            ),
        },
    )


@dataclass
class ComplexCheckType:
    """The type for an element that can contains a boolean expression based on
    checks.

    This element can have only
    complex-check and check elements as children.  It has two
    attributes: operator and negate.  The operator attribute
    can have values "OR" or "AND", and the negate attribute is
    boolean.  See the specification document for truth tables
    for the operators and negations.  Note: complex-check is
    defined in this way for conceptual equivalence with OVAL.
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
class FixTextType(HtmlTextWithSubType):
    """
    Data type for the fixText element that represents a rich text string, with
    substitutions allowed, and a series of attributes that qualify the fix.
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
class OverrideType:
    """Type for an override block in a rule-result.

    It contains five mandatory parts: time, authority,
    old-result, new-result, and remark.
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
class ProfileRefineRuleType:
    """Type for the refine-rule element in a Profile; all it has are four
    attributes, no content.

    The main attribute is
    'idref' which refers to a Rule, and three attributes that
    allow the Profile author to adjust aspects of how a Rule is
    processed during a benchmark run: weight, severity, role.
    As content, the refine-rule element can contain zero or more
    remark elements, which allows the benchmark author to
    add explanatory material or other additional prose.
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
    """Type for the refine-value element in a Profile; all it has are three
    attributes, no content.

    The three attributes are 'idref' which refers to a Value, 'selector'
    which designates certain element children of the Value, and
    'operator' which can override the operator attribute of the Value.
    As content, the refine-value element can contain zero or more remark
    elements, which allows the benchmark author to add explanatory
    material or other additional prose.
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
    """Type for the select element in a Profile; all it has are two attributes, no
    content.

    The two attributes are idref which refers to a Group or Rule, and
    selected which is boolean. As content, the select element can
    contain zero or more remark elements, which allows the benchmark
    author to add explanatory material or other additional prose.
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
    """This element holds a list of facts about the target system or platform.

    Each fact is an element of type factType. Each fact must have a
    name, but duplicate names are allowed. (For example, if you had a
    fact about MAC addresses, and the target system had three NICs, then
    you'd need three instance of the "urn:xccdf:fact:ethernet:MAC"
    fact.)
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
class WarningType(HtmlTextWithSubType):
    """
    Data type for the warning element under the Rule object, a rich text string
    with substitutions allowed, plus an attribute for the kind of warning.
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
class ItemType:
    """
    This abstract item type represents the basic data shared by all Groups, Rules
    and Values.
    """

    class Meta:
        name = "itemType"

    status: list[Status] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://checklists.nist.gov/xccdf/1.1",
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
    id: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "required": True,
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
    id_attribute: str | None = field(
        default=None,
        metadata={
            "name": "Id",
            "type": "Attribute",
        },
    )


@dataclass
class ProfileType:
    """Data type for the Profile element, which holds a specific tailoring of the
    Benchmark.

    The main part
    of a Profile is the selectors: select, set-value,
    refine-rule, and refine-value.  A Profile may also be
    signed with an XML-Signature.
    """

    class Meta:
        name = "profileType"

    status: list[Status] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://checklists.nist.gov/xccdf/1.1",
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
    platform: list[UriidrefType] = field(
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
    """This element holds all the information about the application of one rule to
    a target.

    It may only appear as part of a TestResult object.
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
class Item(ItemType):
    """Type element type imposes constraints shared by all Groups, Rules and
    Values.

    The itemType is abstract, so the element Item can never appear in a
    valid XCCDF document.
    """

    class Meta:
        namespace = "http://checklists.nist.gov/xccdf/1.1"


@dataclass
class Profile(ProfileType):
    class Meta:
        namespace = "http://checklists.nist.gov/xccdf/1.1"


@dataclass
class SelectableItemType(ItemType):
    """This abstract item type represents the basic data shared by all Groups and
    Rules.

    It extends the itemType given above.
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
    platform: list[OverrideableUriidrefType] = field(
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
class TestResultType:
    """Data type for the TestResult element, which holds the results of one
    application of the Benchmark.

    The optional test-system attribute gives the name of the
    benchmarking tool.
    """

    class Meta:
        name = "testResultType"

    benchmark: Optional["TestResultType.Benchmark"] = field(
        default=None,
        metadata={
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
    platform: list[UriidrefType] = field(
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
    class Benchmark:
        href: str | None = field(
            default=None,
            metadata={
                "type": "Attribute",
                "required": True,
            },
        )


@dataclass
class ValueType(ItemType):
    """
    Data type for the Value element, which represents a tailorable string, boolean,
    or number in the Benchmark.
    """

    class Meta:
        name = "valueType"

    value: list[SelStringType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "",
            "min_occurs": 1,
        },
    )
    default: list[SelStringType] = field(
        default_factory=list,
        metadata={
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
class TestResult(TestResultType):
    class Meta:
        namespace = "http://checklists.nist.gov/xccdf/1.1"


@dataclass
class Value(ValueType):
    class Meta:
        namespace = "http://checklists.nist.gov/xccdf/1.1"


@dataclass
class RuleType(SelectableItemType):
    """
    Data type for the Rule element that represents a specific benchmark test.
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
    multiple: bool | None = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass
class Rule(RuleType):
    """The Rule element contains the description for a single item of guidance or
    constraint.

    Rules form the basis for testing a target platform for compliance
    with a benchmark, for scoring, and for conveying descriptive prose,
    identifiers, references, and remediation information.
    """

    class Meta:
        namespace = "http://checklists.nist.gov/xccdf/1.1"


@dataclass
class GroupType(SelectableItemType):
    """
    Data type for the Group element that represents a grouping of Groups, Rules and
    Values.
    """

    class Meta:
        name = "groupType"

    value: list[Value] = field(
        default_factory=list,
        metadata={
            "name": "Value",
            "type": "Element",
            "namespace": "http://checklists.nist.gov/xccdf/1.1",
        },
    )
    group: list["Group"] = field(
        default_factory=list,
        metadata={
            "name": "Group",
            "type": "Element",
            "namespace": "http://checklists.nist.gov/xccdf/1.1",
        },
    )
    rule: list[Rule] = field(
        default_factory=list,
        metadata={
            "name": "Rule",
            "type": "Element",
            "namespace": "http://checklists.nist.gov/xccdf/1.1",
        },
    )
    signature: SignatureType | None = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "",
        },
    )


@dataclass
class Group(GroupType):
    class Meta:
        namespace = "http://checklists.nist.gov/xccdf/1.1"


@dataclass
class Benchmark:
    """The benchmark tag is the top level element representing a complete security
    checklist, including descriptive text, metadata, test items, and test results.

    A Benchmark may be signed with a XML-Signature.
    """

    class Meta:
        namespace = "http://checklists.nist.gov/xccdf/1.1"

    status: list[Status] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "min_occurs": 1,
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
    platform_definitions: str | None = field(
        default=None,
        metadata={
            "name": "platform-definitions",
            "type": "Element",
            "namespace": "http://www.cisecurity.org/xccdf/platform/0.2.3",
        },
    )
    platform_specification: str | None = field(
        default=None,
        metadata={
            "name": "Platform-Specification",
            "type": "Element",
            "namespace": "http://checklists.nist.gov/xccdf-p/1.1",
        },
    )
    cpe_list: str | None = field(
        default=None,
        metadata={
            "name": "cpe-list",
            "type": "Element",
            "namespace": "http://cpe.mitre.org/XMLSchema/cpe/1.0",
        },
    )
    cpe_mitre_org_language_2_0_platform_specification: str | None = field(
        default=None,
        metadata={
            "name": "platform-specification",
            "type": "Element",
            "namespace": "http://cpe.mitre.org/language/2.0",
        },
    )
    platform: list[UriidrefType] = field(
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
