"""The schema of an XCCDF style file.

A style is YAML. Each file of an extends chain is checked against StyleConfig alone, so a
mistake is reported with its file, and the merged style is checked once more. A section or
key the exporter does not read is refused (never ignored), a value of the wrong kind is
refused, and every mistake of one load is reported with the file and the dotted path of
the key.

The benchmark section and the field mappings are accepted as written here; only
benchmark.namespaces is checked.
"""

from collections.abc import Mapping
from typing import Annotated, Any, ClassVar, Final, get_args, get_origin

from lxml import etree
from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationError,
)
from pydantic_core import InitErrorDetails, PydanticCustomError

_IN_A_COMMENT: Final = "descriptive text goes in a YAML comment"
_TYPE_FROM_MODEL: Final = "an element's type comes from the XCCDF model; a style declares none"


def _xml_name(value: str) -> str:
    """An XML name with no prefix and no namespace (an NCName), and not xmlns."""
    try:
        if value.startswith("{") or value == "xmlns":
            raise ValueError("an XML name without a prefix or a namespace is needed")
        etree.QName(None, value)
    except ValueError as error:
        raise PydanticCustomError(
            "xml_name",
            "{name} is not an XML name ({reason})",
            {"name": repr(value), "reason": str(error)},
        ) from error
    return value


XmlName = Annotated[str, AfterValidator(_xml_name)]
"""An element, attribute or prefix name as a style writes it: no colon, no "{uri}" form."""


# Namespaces in XML 1.0, section 3: the names no document may bind or rebind.
_RESERVED_NAMESPACES: Final[dict[str, str]] = {
    "xml": "http://www.w3.org/XML/1998/namespace",
    "xmlns": "http://www.w3.org/2000/xmlns/",
}


def _binding_problem(prefix: Any, uri: Any, bound: dict[str, Any]) -> str | None:
    """Why an XML document cannot declare this prefix -> URI binding, or None if it can."""
    if not isinstance(uri, str) or not uri:
        return f"prefix {prefix!r} needs a namespace URI"
    if prefix in _RESERVED_NAMESPACES:
        return f"prefix {prefix!r} is reserved by XML"
    if uri in _RESERVED_NAMESPACES.values():
        return f"prefix {prefix!r} is bound to a namespace XML reserves"
    if prefix != "default":
        try:
            if not isinstance(prefix, str):
                raise ValueError("a prefix is text")
            _xml_name(prefix)
        except ValueError as error:
            return f"{prefix!r} is not a namespace prefix ({error})"
    if uri in bound:
        return f"{prefix!r} and {bound[uri]!r} are both bound to {uri}; a namespace is listed once"
    bound[uri] = prefix
    return None


def _declarable_namespaces(value: Any) -> Any:
    """Refuse a prefix -> URI map an XML document cannot declare.

    A prefix is "default" (the default namespace) or an XML name without a colon, and never
    xml or xmlns; a URI is a non-empty string, never one of the two reserved namespaces, and
    is bound once (xsdata keeps one prefix per URI). Every binding that breaks a rule is
    reported at its own prefix.
    """
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise PydanticCustomError("namespace_map", "a mapping of prefix to namespace URI is needed")
    bound: dict[str, Any] = {}
    problems = [
        InitErrorDetails(
            type=PydanticCustomError("namespace_binding", "{problem}", {"problem": problem}),
            loc=(str(prefix),),
            input=uri,
        )
        for prefix, uri in value.items()
        if (problem := _binding_problem(prefix, uri, bound)) is not None
    ]
    if problems:
        raise ValidationError.from_exception_data("NamespaceMap", problems)
    return dict(value)


NamespaceMap = Annotated[dict[str, str], BeforeValidator(_declarable_namespaces)]
"""Prefix -> namespace URI, holding only bindings an XML document can declare."""


def _given(value: Any) -> Any:
    """Refuse a key written with no value: a style takes a default by leaving the key out."""
    if value is None:
        raise PydanticCustomError("no_value", "has no value; leave the key out for the default")
    return value


_Text = Annotated[str | None, BeforeValidator(_given)]
_Switch = Annotated[bool | None, BeforeValidator(_given)]
# A number, or a number written as text ("10.0")
_Number = Annotated[Annotated[float, Field(strict=False)] | None, BeforeValidator(_given)]


class _Section(BaseModel):
    """A part of a style: the keys it declares are the keys the exporter reads."""

    model_config = ConfigDict(extra="forbid", strict=True)

    # A key earlier styles carried that nothing reads, and what happens instead.
    removed_keys: ClassVar[Mapping[str, str]] = {}


class Metadata(_Section):
    """What the style is: its name and the XCCDF version it writes."""

    removed_keys: ClassVar[Mapping[str, str]] = {
        "xccdf_namespace": "the XCCDF namespace is the one bound in benchmark.namespaces",
        "description": _IN_A_COMMENT,
        "conventions": _IN_A_COMMENT,
        "target_tools": _IN_A_COMMENT,
    }

    style_name: _Text = None
    xccdf_version: _Text = None


_RULE_ATTRIBUTE_FROM_MODEL: Final = (
    "the Rule is written with the XCCDF model's default; a style sets none"
)


class RuleDefaults(_Section):
    """The Rule attributes every Rule of the style is written with."""

    removed_keys: ClassVar[Mapping[str, str]] = {
        "selected": _RULE_ATTRIBUTE_FROM_MODEL,
        "role": _RULE_ATTRIBUTE_FROM_MODEL,
    }

    severity: _Text = None
    weight: _Number = None


class IdTemplate(_Section):
    """How an id is made from a recommendation ref (rule_id, group_id)."""

    removed_keys: ClassVar[Mapping[str, str]] = {"description": _IN_A_COMMENT}

    template: _Text = None


_DEDUPLICATION_IS_CODE: Final = (
    "the deduplication is the exporter's own; a style only switches it with enabled"
)


class CciDeduplication(_Section):
    """Whether a NIST control a CCI restates is left out of the references."""

    removed_keys: ClassVar[Mapping[str, str]] = {
        "algorithm": _DEDUPLICATION_IS_CODE,
        "matching_rules": _DEDUPLICATION_IS_CODE,
        "description": _IN_A_COMMENT,
        "rationale": _IN_A_COMMENT,
    }

    enabled: _Switch = None


class PostProcessing(_Section):
    """What is changed on the rendered tree before it is written."""

    removed_keys: ClassVar[Mapping[str, str]] = {
        "handlers": "a Rule's metadata is model content (metadata_from_config); nothing "
        "is inserted after serialization",
        "strip_namespace_prefixes": "the serializer writes the namespaces declared in "
        "benchmark.namespaces; nothing rewrites prefixes afterwards",
        "preserve_namespaces": "a style declares exactly the namespaces its documents use in "
        "benchmark.namespaces, and all of them are declared on the root",
    }

    remove_override_attr: _Switch = None


class GroupElement(_Section):
    """What one Group element is filled from: a recommendation field, or fixed content."""

    removed_keys: ClassVar[Mapping[str, str]] = {"xccdf_type": _TYPE_FROM_MODEL}

    source: _Text = None
    transform: _Text = None
    content: _Text = None


class BenchmarkSection(BaseModel):
    """The benchmark section: its namespaces are checked, its other entries are accepted
    as written."""

    model_config = ConfigDict(extra="allow", strict=True)

    namespaces: NamespaceMap = Field(default_factory=dict)


class StyleConfig(_Section):
    """A whole style, after its extends chain is merged."""

    removed_keys: ClassVar[Mapping[str, str]] = {
        "namespaces": "declare namespaces in benchmark.namespaces",
        "rule_elements": _TYPE_FROM_MODEL,
        "transformations": "a mapping names a transform registered in TransformRegistry; "
        "a style declares none",
        "validation": "nothing checks an export against limits a style sets; a style declares none",
    }

    metadata: Metadata = Field(default_factory=Metadata)
    benchmark: BenchmarkSection = Field(default_factory=BenchmarkSection)
    rule_defaults: RuleDefaults = Field(default_factory=RuleDefaults)
    rule_id: IdTemplate = Field(default_factory=IdTemplate)
    group_id: IdTemplate = Field(default_factory=IdTemplate)
    field_mappings: dict[str, Any] = Field(default_factory=dict)
    cci_deduplication: CciDeduplication = Field(default_factory=CciDeduplication)
    group_elements: dict[XmlName, GroupElement] = Field(default_factory=dict)
    post_processing: PostProcessing = Field(default_factory=PostProcessing)


def _section_at(location: tuple[int | str, ...]) -> type[BaseModel] | None:
    """The model holding the keys at a place in a style, or None where the place is not a
    typed section."""
    model: type[BaseModel] = StyleConfig
    parts = list(location)
    while parts:
        declared = model.model_fields.get(str(parts.pop(0)))
        if declared is None:
            return None
        annotation = declared.annotation
        if get_origin(annotation) is dict:
            if not parts:
                return None
            parts.pop(0)
            annotation = get_args(annotation)[1]
        if not (isinstance(annotation, type) and issubclass(annotation, BaseModel)):
            return None
        model = annotation
    return model


def _dotted(location: tuple[int | str, ...]) -> str:
    """A place in a style as a dotted path: rule_defaults.weight. The typed sections hold
    no lists, so every part is a key (a key YAML read as a number shows as that number)."""
    return ".".join(str(part) for part in location if part != "[key]") or "the style"


def _unknown_key(location: tuple[int | str, ...]) -> str:
    """Why a key the schema does not declare is refused: what happens instead of a removed
    key, or the keys its section takes."""
    section = _section_at(location[:-1])
    hint = getattr(section, "removed_keys", {}).get(str(location[-1]))
    if hint:
        return f"is not read ({hint})"
    if section is None:
        return "is not a key the exporter reads"
    return "is not a key the exporter reads; the keys here are: " + ", ".join(
        sorted(section.model_fields)
    )


def validate_style(source: str, data: Any) -> StyleConfig:
    """Check one style file, or a merged style, against the schema.

    Args:
        source: The file name the mistakes are reported with
        data: The style as loaded from YAML

    Raises:
        ValueError: One line per mistake: the file, the dotted path of the key, and what is
            wrong with it.
    """
    try:
        return StyleConfig.model_validate(data)
    except ValidationError as error:
        raise ValueError(
            "\n".join(
                f"{source}: {_dotted(mistake['loc'])}: "
                + (
                    _unknown_key(mistake["loc"])
                    if mistake["type"] == "extra_forbidden"
                    else mistake["msg"]
                )
                for mistake in error.errors()
            )
        ) from error
