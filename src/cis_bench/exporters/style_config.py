"""The schema of an XCCDF style file.

A style is YAML. Each file of an extends chain is checked against StyleConfig alone, so a
mistake is reported with its file, and the merged style is checked once more. A section or
key the exporter does not read is refused (never ignored), a value of the wrong kind is
refused, and every mistake of one load is reported with the file and the dotted path of
the key.

The field mappings are checked only as JSON-like data: text keys, values that are text,
numbers, booleans, lists and mappings, and no mapping that contains itself (pydantic's
JsonValue).
"""

from collections.abc import Mapping
from typing import Annotated, Any, ClassVar, Final, Self, get_args, get_origin

import yaml
from lxml import etree
from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    JsonValue,
    TypeAdapter,
    ValidationError,
    model_validator,
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
    _given(value)
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


def _prefixed_name(value: str) -> str:
    """An element name with a namespace prefix: prefix:name, each part an XML name."""
    prefix, colon, local = value.partition(":")
    if not colon:
        raise PydanticCustomError(
            "prefixed_name",
            "{name} needs a namespace prefix (prefix:name) declared in benchmark.namespaces",
            {"name": repr(value)},
        )
    _xml_name(prefix)
    _xml_name(local)
    return value


PrefixedName = Annotated[str, AfterValidator(_prefixed_name)]
"""An element in a namespace the style declares, written prefix:name (dc:publisher); the
prefix must be bound in benchmark.namespaces of the whole style."""


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


_ELEMENT_FROM_MODEL: Final = "the element comes from the XCCDF model; a style names none"


class SourcedElement(_Section):
    """A Benchmark element filled from a benchmark field (title, description, version); its
    name is the element's, checked against the XCCDF model when the engine starts."""

    removed_keys: ClassVar[Mapping[str, str]] = {"xccdf_type": _TYPE_FROM_MODEL}

    source: str
    transform: _Text = None
    prepend_text: _Text = None


class Notice(_Section):
    """The Benchmark's notice: its id (terms-of-use when left out), language and text."""

    removed_keys: ClassVar[Mapping[str, str]] = {
        "element": _ELEMENT_FROM_MODEL,
        "attributes": "write the notice's id and language as id and lang",
    }

    id: _Text = None
    lang: _Text = None
    content: _Text = None


class PlainText(_Section):
    """One plain-text element of the Benchmark."""

    id: str
    content: _Text = None


class ProfileMapping(_Section):
    """How a profile named on the recommendations is written."""

    removed_keys: ClassVar[Mapping[str, str]] = {
        "id": "a profile's id comes from benchmark.profiles.id_template",
    }

    match: str
    title: _Text = None
    description: _Text = None
    includes: list[str] = Field(default_factory=list)


class Profiles(_Section):
    """Whether and how the Benchmark's Profile elements are written."""

    generate_from_rules: _Switch = None
    id_template: _Text = None
    description_transform: _Text = None
    profile_mappings: list[ProfileMapping] = Field(default_factory=list)


class ReferenceAttributes(_Section):
    """The attributes of the Benchmark's reference."""

    href: _Text = None


class DublinCoreElement(_Section):
    """A Dublin Core element of a reference: its prefixed name and its text."""

    element: PrefixedName
    content: str


class Reference(_Section):
    """The Benchmark's own reference: its href and its Dublin Core elements."""

    removed_keys: ClassVar[Mapping[str, str]] = {"element": _ELEMENT_FROM_MODEL}

    attributes: ReferenceAttributes = Field(default_factory=ReferenceAttributes)
    dc_elements: list[DublinCoreElement] = Field(default_factory=list)


class BenchmarkSection(_Section):
    """The benchmark section: the entries the engine reads by name, and the elements filled
    from a benchmark field (every other entry)."""

    model_config = ConfigDict(extra="allow", strict=True)

    # The type of every other entry (pydantic's documented form)
    __pydantic_extra__: dict[str, SourcedElement] = Field(init=False)

    id_template: _Text = None
    namespaces: NamespaceMap = Field(default_factory=dict)
    notice: Notice = Field(default_factory=Notice)
    plain_text: list[PlainText] = Field(default_factory=list)
    profiles: Profiles = Field(default_factory=Profiles)
    reference: Reference = Field(default_factory=Reference)


# The style file a style extends, relative to its own file or absolute
_StyleFile = Annotated[str, Field(min_length=1)]


class StyleConfig(_Section):
    """One style file, or a whole style after its extends chain is merged."""

    removed_keys: ClassVar[Mapping[str, str]] = {
        "namespaces": "declare namespaces in benchmark.namespaces",
        "rule_elements": _TYPE_FROM_MODEL,
        "transformations": "a mapping names a transform registered in TransformRegistry; "
        "a style declares none",
        "validation": "nothing checks an export against limits a style sets; a style declares none",
    }

    extends: Annotated[_StyleFile | None, BeforeValidator(_given)] = None
    metadata: Metadata = Field(default_factory=Metadata)
    benchmark: BenchmarkSection = Field(default_factory=BenchmarkSection)
    rule_defaults: RuleDefaults = Field(default_factory=RuleDefaults)
    rule_id: IdTemplate = Field(default_factory=IdTemplate)
    group_id: IdTemplate = Field(default_factory=IdTemplate)
    field_mappings: dict[str, JsonValue] = Field(default_factory=dict)
    cci_deduplication: CciDeduplication = Field(default_factory=CciDeduplication)
    group_elements: dict[XmlName, GroupElement] = Field(default_factory=dict)
    post_processing: PostProcessing = Field(default_factory=PostProcessing)

    @model_validator(mode="after")
    def _prefixes_declared(self) -> Self:
        """Refuse a prefixed element name whose prefix the style does not bind in
        benchmark.namespaces (the style is always a whole one: see validate_style)."""
        named = [
            (("benchmark", "reference", "dc_elements", index, "element"), element.element)
            for index, element in enumerate(self.benchmark.reference.dc_elements)
        ]
        problems = [
            InitErrorDetails(
                type=PydanticCustomError(
                    "undeclared_prefix",
                    "the prefix '{prefix}' is not bound in benchmark.namespaces",
                    {"prefix": prefix},
                ),
                loc=location,
                input=name,
            )
            for location, name in named
            if (prefix := name.partition(":")[0]) not in self.benchmark.namespaces
        ]
        if problems:
            raise ValidationError.from_exception_data("StyleConfig", problems)
        return self


def _section_at(location: tuple[int | str, ...]) -> type[BaseModel] | None:
    """The model holding the keys at a place in a style, or None where the place is not a
    typed section."""
    model: type[BaseModel] = StyleConfig
    parts = list(location)
    while parts:
        name = str(parts.pop(0))
        declared = model.model_fields.get(name)
        annotation: Any = declared.annotation if declared else None
        if declared is None and model.model_config.get("extra") == "allow":
            # an entry the model takes beyond its fields: the type of __pydantic_extra__
            annotation = get_args(model.__annotations__.get("__pydantic_extra__"))[1:2]
            annotation = annotation[0] if annotation else None
        if annotation is None:
            return None
        if get_origin(annotation) in (dict, list):
            # a mapping's key or a list's position, then the type of its values
            if not parts:
                return None
            parts.pop(0)
            annotation = get_args(annotation)[-1]
        if not (isinstance(annotation, type) and issubclass(annotation, BaseModel)):
            return None
        model = annotation
    return model


def _dotted(location: tuple[int | str, ...], kind: str = "") -> str:
    """A place in a style as a dotted path: benchmark.plain_text[0].id. A number is a
    position in a list, unless it is a mapping key YAML read as a number: pydantic marks
    such a key with "[key]" after it, or reports it as the place of an invalid_key."""
    path = ""
    for index, part in enumerate(location):
        if part == "[key]":
            continue
        is_key = location[index + 1 : index + 2] == ("[key]",) or (
            kind == "invalid_key" and index == len(location) - 1
        )
        if isinstance(part, int) and not isinstance(part, bool) and not is_key:
            path += f"[{part}]"
        else:
            path += f".{part}" if path else str(part)
    return path or "the style"


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


_EXTENDS: Final = TypeAdapter(_StyleFile)
_MERGEABLE: Final = TypeAdapter(dict[str, JsonValue])
# The tags pydantic puts in a JsonValue error's place, after each mapping or list it enters
_JSON_VALUE_TAGS: Final = frozenset({"dict", "list", "str", "int", "float", "bool", "none"})


def extended_style(data: Mapping[str, Any]) -> str | None:
    """The style file a style extends, as written; None when it names none, or names it in
    a way the schema refuses (validate_style reports that)."""
    try:
        return _EXTENDS.validate_python(data.get("extends"), strict=True)
    except ValidationError:
        return None


def _as_written(key: Any) -> str:
    """A key as YAML wrote it: true, 1, null, 2026-01-01."""
    return yaml.safe_dump(key, default_flow_style=True).splitlines()[0].removesuffix(" ...")


def check_mergeable(source: str, data: Any) -> None:
    """Refuse a style file that cannot be merged safely: a key that is not text (YAML reads
    an unquoted true or 1 as a boolean or a number, and a mapping takes them as one key), or
    a mapping that contains itself (a YAML anchor), which a merge would follow without end.
    pydantic's JsonValue checks both; nothing else of the schema is checked here.

    Raises:
        ValueError: One line per mistake, with the file and the dotted path.
    """
    try:
        _MERGEABLE.validate_python(data, strict=True)
    except ValidationError as error:
        lines = []
        for mistake in error.errors():
            # the file is dict[str, JsonValue]: its place reads key, tag, key, tag, ...
            place = tuple(
                part
                for index, part in enumerate(mistake["loc"])
                if not (index % 2 and part in _JSON_VALUE_TAGS)
            )
            why = mistake["msg"]
            if place[-1:] == ("[key]",):
                place = (*place[:-2], _as_written(mistake["input"]), "[key]")
                why = "is not text; write the key in quotes"
            lines.append(f"{source}: {_dotted(place, mistake['type'])}: {why}")
        raise ValueError("\n".join(lines)) from error


def validate_style(source: str, data: Any) -> StyleConfig:
    """Check a whole style against the schema: a style file with no extends, or the style
    an extends chain has built up to and including the file named source.

    Args:
        source: The file name the mistakes are reported with
        data: The style as built so far

    Raises:
        ValueError: One line per mistake: the file, the dotted path of the key, and what is
            wrong with it.
    """
    try:
        return StyleConfig.model_validate(data)
    except ValidationError as error:
        raise ValueError(
            "\n".join(
                f"{source}: {_dotted(mistake['loc'], mistake['type'])}: "
                + (
                    _unknown_key(mistake["loc"])
                    if mistake["type"] == "extra_forbidden"
                    else mistake["msg"]
                )
                for mistake in error.errors()
            )
        ) from error
