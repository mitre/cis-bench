"""The schema of an XCCDF style file.

A style is YAML. ConfigLoader loads an extends chain root first: each file is checked for a
safe merge (check_mergeable), merged onto the style built so far, and that style is checked
against StyleConfig (validate_style), its mistakes named with the file just merged. A
section or key the exporter does not read is refused (never ignored), a value of the wrong
kind is refused, and every mistake of one file is reported with the file and the dotted path
of the key.

A field mapping takes the keys of its structure (FieldMapping, a union discriminated on
structure: simple, composite, nested, dublin_core, embedded_xml_tags, ident_from_list or
metadata_from_config), at every level of its nested specification.

What needs the models is checked in the same validation, given StyleModels as pydantic
validation context: the fields a style names against the Recommendation and Benchmark
models, transforms and template filters against the engine's registry, the elements a
mapping writes against the XCCDF models of the style's version, and where Rule metadata
can go. Without that context only the shape is checked.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, is_dataclass
from types import ModuleType, UnionType
from typing import Annotated, Any, ClassVar, Final, Literal, Self, Union, get_args, get_origin

import yaml
from lxml import etree
from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Discriminator,
    Field,
    JsonValue,
    Tag,
    TypeAdapter,
    ValidationError,
    ValidationInfo,
    ValidatorFunctionWrapHandler,
    WrapValidator,
    model_validator,
)
from pydantic_core import InitErrorDetails, PydanticCustomError
from xsdata.formats.dataclass.context import XmlContext
from xsdata.formats.dataclass.models.elements import XmlVar


@dataclass(frozen=True)
class StyleModels:
    """The models a style is checked against when it loads, given to StyleConfig as pydantic
    validation context ({"models": StyleModels}): the generated XCCDF models of the style's
    version, the benchmark models whose fields a style names, and the engine's transform
    lookup and template parser (the engine passes its own, so there is one of each)."""

    xccdf: ModuleType
    xccdf_version: str
    xccdf_namespace: str
    recommendation: type[BaseModel]
    benchmark: type[BaseModel]
    cis_control: type[BaseModel]
    # Raises ValueError for a name no transform is registered under
    transform: Callable[[str], object]
    # The transforms a template's filters name; raises ValueError for a filter with no name
    template_filters: Callable[[str], list[str]]
    # The dotted paths a template's variables read ("item.control")
    template_variables: Callable[[str], list[str]]
    xml_context: XmlContext = field(default_factory=XmlContext, compare=False)

    def _meta_vars(self, clazz: type) -> list[XmlVar]:
        """The XML fields of a model class, built with the XCCDF namespace as the parent
        namespace, so a wildcard of ##other reads as "not the XCCDF namespace"."""
        return list(self.xml_context.build(clazz, parent_ns=self.xccdf_namespace).get_all_vars())

    def element(self, parent: str, name: str) -> XmlVar | None:
        """The element field name of Rule, Group or Benchmark in this XCCDF version (its
        type, whether it repeats); None when the parent has no such element."""
        return next(
            (
                var
                for var in self._meta_vars(getattr(self.xccdf, parent))
                if var.name == name and var.is_element
            ),
            None,
        )

    def child_element(self, holder: type, name: str) -> XmlVar | None:
        """The element of a model type named name as XML writes it (check-content), with its
        field and type; None when the type has no such element."""
        return next(
            (var for var in self._meta_vars(holder) if var.local_name == name and var.is_element),
            None,
        )

    def nested_child_problem(self, target: str, name: str) -> str | None:
        """Why a nested mapping cannot write the child element name inside the Rule element
        target (one whose type the target problem check found), or None if it can."""
        holder = self.element("Rule", target)
        child = self.child_element(holder.types[0], name) if holder is not None else None
        if child is None:
            return f"the XCCDF {self.xccdf_version} {target!r} element has no {name!r} element"
        if len(child.types) != 1 or not is_dataclass(child.types[0]):
            return (
                f"the {name!r} element of an XCCDF {self.xccdf_version} {target!r} holds a "
                "plain value, not an element type a mapping can fill"
            )
        return None

    def element_problem(self, parent: str, name: str) -> str | None:
        """Why a mapping cannot fill the element name of parent, or None if it can."""
        element = self.element(parent, name)
        if element is None:
            return f"XCCDF {self.xccdf_version} has no {name!r} element in {parent}"
        if len(element.types) != 1 or not is_dataclass(element.types[0]):
            return (
                f"the {name!r} element of an XCCDF {self.xccdf_version} {parent} holds a "
                "plain value, not an element type a mapping can fill"
            )
        return None

    def metadata_holder(self, target: str) -> tuple[type, str] | None:
        """The type of the Rule element target and the field of that type that holds
        metadata content, when the Rule can repeat target and its type takes elements of any
        namespace but XCCDF's (xsd:any namespace="##other", element-only); else None."""
        element = self.element("Rule", target)
        if element is None or not element.list_element or len(element.types) != 1:
            return None
        holder = element.types[0]
        if not is_dataclass(holder):
            return None
        other = f"!{self.xccdf_namespace}"
        wildcards = [
            var.name
            for var in self._meta_vars(holder)
            if var.is_wildcard
            and not var.mixed
            and any(namespace in ("##any", other) for namespace in var.namespaces)
        ]
        return (holder, wildcards[0]) if len(wildcards) == 1 else None


def _models(info: ValidationInfo) -> StyleModels | None:
    """The models a validation was given as context, if any."""
    context = info.context if isinstance(info.context, Mapping) else {}
    models = context.get("models")
    return models if isinstance(models, StyleModels) else None


def _model_in(annotation: Any) -> type[BaseModel] | None:
    """The Pydantic model a field holds, directly or inside "X | None"; None for a list or a
    value that is not a model. A dotted path reads attributes one by one (getattr), so it
    can pass through an optional model but not through a list."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    if get_origin(annotation) is Annotated:
        return _model_in(get_args(annotation)[0])
    if get_origin(annotation) in (UnionType, Union):
        for arg in get_args(annotation):
            model = _model_in(arg)
            if model is not None:
                return model
    return None


def _missing_part(model: type[BaseModel] | None, path: str, dotted: bool) -> tuple[str, str] | None:
    """The first name of path that is no field, and the model it was looked for in; None
    when path names a field (with dotted, through the models the fields hold)."""
    current = model
    for part in path.split(".") if dotted else [path]:
        fields = current.model_fields if current is not None else {}
        if part not in fields:
            holder = current if current is not None else model
            return part, holder.__name__ if holder is not None else "the items"
        current = _model_in(fields[part].annotation)
    return None


def field_path_problem(model: type[BaseModel], path: str, dotted: bool) -> str | None:
    """Why path names no field of model, or None if it does: one field name, or with dotted
    a path through the models the fields hold (mitre_mapping.techniques)."""
    missing = _missing_part(model, path, dotted)
    if missing is None:
        return None
    part, holder = missing
    shown = f"{path!r}: {part!r}" if dotted and "." in path else repr(part)
    return f"{shown} is not a field of {holder}"


def field_model(model: type[BaseModel], path: str) -> type[BaseModel] | None:
    """The model the field at a dotted path holds (directly or as "X | None"), or None."""
    current: Any = model
    for part in path.split("."):
        current = _model_in(current.model_fields[part].annotation) if current else None
    return current if isinstance(current, type) else None


def list_item_model(model: type[BaseModel], path: str) -> type[BaseModel] | None:
    """The model of the items the list field at a dotted path holds, or None when the field
    is no list of models."""
    current: Any = model
    *parents, last = path.split(".")
    for part in parents:
        current = _model_in(current.model_fields[part].annotation)
    annotation = current.model_fields[last].annotation
    while get_origin(annotation) is Annotated or get_origin(annotation) in (UnionType, Union):
        annotation = next(arg for arg in get_args(annotation) if arg is not type(None))
    return _model_in(get_args(annotation)[0]) if get_origin(annotation) is list else None


def _registered_transform(value: str, info: ValidationInfo) -> str:
    """Refuse a transform no function is registered under (checked with the models)."""
    models = _models(info)
    if models is not None:
        try:
            models.transform(value)
        except ValueError as error:
            raise PydanticCustomError(
                "unknown_transform", "{error}", {"error": str(error)}
            ) from error
    return value


def _known_filters(value: str | None, info: ValidationInfo) -> str | None:
    """Refuse a template filter ({value|name}) that names no registered transform, or none
    (checked with the models). Text the template parser refuses is left to the export."""
    models = _models(info)
    if value is not None and models is not None:
        try:
            for name in models.template_filters(value):
                models.transform(name)
        except ValueError as error:
            raise PydanticCustomError("unknown_filter", "{error}", {"error": str(error)}) from error
    return value


# The values the engine gives a template, by where the template is (measured at each place the
# engine fills one): a name -> the model behind it, a dict of the keys the engine builds, or
# None for a value with no fields to check (text, a list, a value a transform made).
_TEMPLATE_VALUES: Final[dict[str, dict[str, Any]]] = {
    "benchmark": {"benchmark": "benchmark"},
    "plain_text": {"download_date": None, "benchmark": "benchmark"},
    "benchmark_id": {"benchmark_id": None, "version": None, "title_slug": None},
    "ref": {"ref": None, "ref_normalized": None, "stig_number": None},
    "rule": {
        "ref": None,
        "ref_normalized": None,
        "stig_number": None,
        "rec": "recommendation",
        "benchmark": "benchmark",
    },
    "profile": {"profile": {"title": None}},
    "nist": {"nist_control_id": None},
    "group": {"group_key": None},
}


def _values_of(kind: str, models: StyleModels) -> dict[str, Any]:
    """The values a template of a kind is given, with model names read from the models."""
    return {
        name: getattr(models, value) if isinstance(value, str) else value
        for name, value in _TEMPLATE_VALUES[kind].items()
    }


def variables_problem(template: str, values: Mapping[str, Any], models: StyleModels) -> str | None:
    """Why a template names a value it is not given, or None: the first name of each variable
    must be one of values, and each later name a field of the model before it (or a key of a
    dict the engine builds); after a value with no fields to check, the rest is not checked."""
    for path in models.template_variables(template):
        parts = path.split(".")
        if not all(parts):
            return f"template {template!r} names {path!r}, which has an empty name"
        if parts[0] not in values:
            return (
                f"template {template!r} names {path!r}; {parts[0]!r} is not a value this "
                f"template can use (it can use {', '.join(sorted(values))})"
            )
        current = values[parts[0]]
        for depth, part in enumerate(parts[1:], 1):
            if isinstance(current, type) and issubclass(current, BaseModel):
                declared = current.model_fields.get(part)
                if declared is None:
                    return (
                        f"template {template!r} names {path!r}; {part!r} is not a field of "
                        f"{current.__name__}"
                    )
                current = _model_in(declared.annotation)
            elif isinstance(current, Mapping):
                if part not in current:
                    holder = ".".join(parts[:depth])
                    return (
                        f"template {template!r} names {path!r}; {part!r} is not a key of {holder}"
                    )
                current = current[part]
            else:
                break
    return None


def _variables_in(kind: str) -> Any:
    """A check that a template names only the values the engine gives templates of a kind
    (checked with the models)."""

    def check(value: str | None, info: ValidationInfo) -> str | None:
        models = _models(info)
        if value is not None and models is not None:
            problem = variables_problem(value, _values_of(kind, models), models)
            if problem is not None:
                raise PydanticCustomError("unknown_variable", "{problem}", {"problem": problem})
        return value

    return AfterValidator(check)


def _template_problems(
    templates: list[tuple[tuple[int | str, ...], str | None]],
    values: Mapping[str, Any],
    models: StyleModels,
) -> list[tuple[tuple[int | str, ...], str]]:
    """The places of templates that name values they are not given, with why."""
    found = []
    for place, template in templates:
        problem = variables_problem(template, values, models) if template is not None else None
        if problem is not None:
            found.append((place, problem))
    return found


def _dc_element_problems(
    elements: list["DublinCoreElement"], kind: str, info: ValidationInfo
) -> list[tuple[tuple[int | str, ...], str]]:
    """Dublin Core element contents that name values their kind of template is not given."""
    models = _models(info)
    if models is None:
        return []
    return _template_problems(
        [
            (("dc_elements", index, "content"), element.content)
            for index, element in enumerate(elements)
        ],
        _values_of(kind, models),
        models,
    )


def _item_model(
    models: StyleModels, source_field: str, transform: str | None, one_value: bool = False
) -> type[BaseModel] | None:
    """The model of each item of the list a mapping reads, or with one_value the model of the
    field's own value when it holds no list (the ident builder reads one value as one item);
    None when the items are text, or a transform other than none makes them."""
    if not source_field or transform not in (None, "none"):
        return None
    items = list_item_model(models.recommendation, source_field)
    if items is None and one_value:
        return field_model(models.recommendation, source_field)
    return items


def _raise_problems(title: str, found: list[tuple[tuple[int | str, ...], str]]) -> None:
    """Raise one validation error with a mistake at each place, if there are any."""
    if found:
        raise ValidationError.from_exception_data(
            title,
            [
                InitErrorDetails(
                    type=PydanticCustomError("not_writable", "{problem}", {"problem": problem}),
                    loc=location,
                    input=None,
                )
                for location, problem in found
            ],
        )


def _field_of(model: Literal["recommendation", "benchmark"], dotted: bool = False) -> Any:
    """A check that a name is a field of the Recommendation or Benchmark model (checked with
    the models); an empty name names no source and is left to the structure."""

    def check(value: str, info: ValidationInfo) -> str:
        models = _models(info)
        if value and models is not None:
            problem = field_path_problem(getattr(models, model), value, dotted)
            if problem is not None:
                raise PydanticCustomError("unknown_field", "{problem}", {"problem": problem})
        return value

    return AfterValidator(check)


RecommendationField = Annotated[str, _field_of("recommendation")]
"""A field of the Recommendation model, by its name."""

RecommendationPath = Annotated[str, _field_of("recommendation", dotted=True)]
"""A field of the Recommendation model, or a dotted path through the models it holds."""

BenchmarkField = Annotated[str, _field_of("benchmark")]
"""A field of the Benchmark model, by its name."""


def _cis_controls_field(value: str | None, info: ValidationInfo) -> str | None:
    """The CCI lookup reads CIS controls, so the field must be declared to hold them; a list
    of anything else would read as no controls (checked with the models). An empty name
    names no field and is left to the lookup, as a missing one is."""
    models = _models(info)
    if value and models is not None:
        declared = models.recommendation.model_fields.get(value)
        holds = get_args(declared.annotation) if declared is not None else ()
        if (
            declared is None
            or get_origin(declared.annotation) is not list
            or holds != (models.cis_control,)
        ):
            raise PydanticCustomError(
                "not_cis_controls",
                "{name} is not a field of Recommendation holding CIS controls",
                {"name": repr(value)},
            )
    return value


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
# A number, or a decimal number written as text ("10.0"); declared as both so the published
# JSON Schema states what the style accepts
_DecimalText = Annotated[
    str, Field(pattern=r"^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$")
]


def _one_number_error(value: Any, handler: ValidatorFunctionWrapHandler) -> Any:
    """One error for a value that is neither form of a number, not one per form."""
    try:
        return handler(value)
    except ValidationError as error:
        raise PydanticCustomError(
            "not_a_number",
            '{value} is not a number (write 10 or "10.0")',
            {"value": repr(value)},
        ) from error


_Number = Annotated[float | _DecimalText, WrapValidator(_one_number_error), BeforeValidator(_given)]

Template = Annotated[str | None, BeforeValidator(_given), AfterValidator(_known_filters)]
"""Text the engine fills with {variables} and {value|transform} filters when it writes; its
filters name registered transforms."""

TemplateText = Annotated[str, BeforeValidator(_given), AfterValidator(_known_filters)]
"""A template that always has text: a value in a map of templates, or a key whose default
is a text."""

TransformName = Annotated[str, BeforeValidator(_given), AfterValidator(_registered_transform)]
"""The name of a transform registered in the engine's TransformRegistry; a field that names
none takes "none", which gives the value unchanged."""

# Templates by the values the engine fills them with (_TEMPLATE_VALUES)
BenchmarkTemplate = Annotated[Template, _variables_in("benchmark")]
BenchmarkTemplateText = Annotated[TemplateText, _variables_in("benchmark")]
PlainTextTemplateText = Annotated[TemplateText, _variables_in("plain_text")]
BenchmarkIdTemplate = Annotated[Template, _variables_in("benchmark_id")]
RefTemplate = Annotated[Template, _variables_in("ref")]
RuleTemplateText = Annotated[TemplateText, _variables_in("rule")]
ProfileTemplate = Annotated[Template, _variables_in("profile")]

# A file a style names (extends, a CCI mapping file), relative to its own file or absolute
_StyleFile = Annotated[str, Field(min_length=1)]


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
    xccdf_version: Annotated[str, BeforeValidator(_given)] = "1.2"


_RULE_ATTRIBUTE_FROM_MODEL: Final = (
    "the Rule is written with the XCCDF model's default; a style sets none"
)


class RuleDefaults(_Section):
    """The Rule attributes every Rule of the style is written with."""

    removed_keys: ClassVar[Mapping[str, str]] = {
        "selected": _RULE_ATTRIBUTE_FROM_MODEL,
        "role": _RULE_ATTRIBUTE_FROM_MODEL,
    }

    severity: Annotated[str, BeforeValidator(_given)] = "medium"
    weight: _Number = 10.0


class IdTemplate(_Section):
    """How an id is made from a recommendation ref (rule_id, group_id)."""

    removed_keys: ClassVar[Mapping[str, str]] = {"description": _IN_A_COMMENT}

    template: RefTemplate = None


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

    enabled: Annotated[bool, BeforeValidator(_given)] = False


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

    remove_override_attr: Annotated[bool, BeforeValidator(_given)] = True


class GroupElement(_Section):
    """What one Group element is filled from: a recommendation field, or fixed content."""

    removed_keys: ClassVar[Mapping[str, str]] = {"xccdf_type": _TYPE_FROM_MODEL}

    source: Annotated[RecommendationField | None, BeforeValidator(_given)] = None
    transform: TransformName = "none"
    content: _Text = None

    @model_validator(mode="after")
    def _filled_from_something(self) -> Self:
        """An element names where its text comes from; the exporter writes nothing of its
        own in its place."""
        if self.source is None and self.content is None:
            raise PydanticCustomError(
                "nothing_to_write",
                "names neither source nor content; give it a source or content, or leave the "
                "element out",
            )
        return self


_ELEMENT_FROM_MODEL: Final = "the element comes from the XCCDF model; a style names none"


class SourcedElement(_Section):
    """A Benchmark element filled from a benchmark field (title, description, version); its
    name is the element's, checked against the XCCDF model when the engine starts."""

    removed_keys: ClassVar[Mapping[str, str]] = {"xccdf_type": _TYPE_FROM_MODEL}

    source: BenchmarkField
    transform: TransformName = "none"
    prepend_text: _Text = None


class Notice(_Section):
    """The Benchmark's notice: its id (XCCDF requires one), language and text; a style that
    declares no notice gets none."""

    removed_keys: ClassVar[Mapping[str, str]] = {
        "element": _ELEMENT_FROM_MODEL,
        "attributes": "write the notice's id and language as id and lang",
    }

    id: BenchmarkTemplateText
    lang: BenchmarkTemplate = None
    content: BenchmarkTemplate = None


class PlainText(_Section):
    """One plain-text element of the Benchmark."""

    id: str
    content: PlainTextTemplateText = ""


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
    id_template: ProfileTemplate = None
    description_transform: TransformName = "none"
    profile_mappings: list[ProfileMapping] = Field(default_factory=list)


class ReferenceAttributes(_Section):
    """The attributes of the Benchmark's reference."""

    href: BenchmarkTemplate = None


class DublinCoreElement(_Section):
    """A Dublin Core element of a reference: its prefixed name and its text (a template)."""

    element: PrefixedName
    content: TemplateText


class Reference(_Section):
    """The Benchmark's own reference: its href and its Dublin Core elements."""

    removed_keys: ClassVar[Mapping[str, str]] = {"element": _ELEMENT_FROM_MODEL}

    attributes: ReferenceAttributes = Field(default_factory=ReferenceAttributes)
    dc_elements: list[DublinCoreElement] = Field(default_factory=list)

    @model_validator(mode="after")
    def _element_variables(self, info: ValidationInfo) -> Self:
        """The Benchmark's Dublin Core elements are filled with the benchmark."""
        _raise_problems("Reference", _dc_element_problems(self.dc_elements, "benchmark", info))
        return self


_ONLY_SIMPLE: Final = "multiple applies to a simple mapping whose value is a list"

NamespacePrefix = Annotated[str, Field(min_length=1), AfterValidator(_known_filters)]
"""The prefix of a namespace bound in benchmark.namespaces; an ident attribute's prefix may
be a template filled per item (cc{item.version})."""


# The keys no field mapping reads any more, whatever its structure
_REMOVED_MAPPING_KEYS: Final[Mapping[str, str]] = {
    "description": _IN_A_COMMENT,
    "xccdf_type": _TYPE_FROM_MODEL,
    "requires_post_processing": "the Rule holds the metadata as model content; nothing "
    "is added after serialization",
}


class _FieldMapping(_Section):
    """What every field mapping takes."""

    removed_keys: ClassVar[Mapping[str, str]] = {**_REMOVED_MAPPING_KEYS, "multiple": _ONLY_SIMPLE}

    target_element: XmlName | None = None


class CciLookup(_Section):
    """Where the CCIs of a cci_lookup_with_deduplication mapping come from."""

    removed_keys: ClassVar[Mapping[str, str]] = {
        "enabled": "the lookup runs for source_logic: cci_lookup_with_deduplication",
        "deduplicate_nist": "deduplication is switched by cci_deduplication.enabled",
    }

    source_field: Annotated[
        str | None, BeforeValidator(_given), AfterValidator(_cis_controls_field)
    ] = None
    cis_controls_version: Annotated[int | None, BeforeValidator(_given)] = None
    extract: Annotated[Literal["all", "primary"], BeforeValidator(_given)] = "all"
    fallback_cci: _Text = None
    mapping_file: Annotated[_StyleFile | None, BeforeValidator(_given)] = None


class SimpleMapping(_FieldMapping):
    """A Rule element filled from one recommendation field (structure left out or simple)."""

    removed_keys: ClassVar[Mapping[str, str]] = {
        **_REMOVED_MAPPING_KEYS,
        "optional": "a mapping with no value is left out already",
        "content": "a Rule field mapping writes no fixed text; an element with attributes "
        "and no value is written empty",
    }

    structure: Literal["simple"] | None = None
    source_field: Annotated[RecommendationField | None, BeforeValidator(_given)] = None
    transform: TransformName = "none"
    source_logic: Annotated[
        Literal["cci_lookup_with_deduplication"] | None, BeforeValidator(_given)
    ] = None
    cci_lookup: CciLookup = Field(default_factory=CciLookup)
    multiple: Annotated[bool, BeforeValidator(_given)] = False
    attributes: dict[XmlName, RuleTemplateText] = Field(default_factory=dict)


class CompositeSource(_Section):
    """A field a composite mapping joins, with its label and transform."""

    field: Annotated[RecommendationField, Field(min_length=1)]
    label: _Text = None
    transform: TransformName = "none"


class CompositeMapping(_FieldMapping):
    """A Rule element whose text joins several recommendation fields."""

    structure: Literal["composite"]
    sources: Annotated[list[CompositeSource], Field(min_length=1)]
    separator: Annotated[str, BeforeValidator(_given)] = "\n\n"
    attributes: dict[XmlName, RuleTemplateText] = Field(default_factory=dict)


class NestedChild(_Section):
    """The one child element a nested mapping writes in its element."""

    source_field: RecommendationField
    element: str
    transform: TransformName = "none"


class NestedAttributes(_Section):
    """The attribute a nested mapping writes on its element."""

    system: RuleTemplateText = ""


class NestedMapping(_FieldMapping):
    """A Rule element holding one child element (check and its check-content)."""

    structure: Literal["nested"]
    children: Annotated[list[NestedChild], Field(min_length=1, max_length=1)]
    attributes: NestedAttributes = Field(default_factory=NestedAttributes)


class DublinCoreAttributes(_Section):
    """The attribute a Dublin Core reference mapping writes."""

    href: RuleTemplateText = ""


class DublinCoreMapping(_FieldMapping):
    """References with Dublin Core elements, one per NIST control of a field."""

    removed_keys: ClassVar[Mapping[str, str]] = {
        **_REMOVED_MAPPING_KEYS,
        "multiple": "one reference is written per NIST control",
    }

    structure: Literal["dublin_core"]
    source_field: RecommendationField
    source_logic: Annotated[
        Literal["nist_after_cci_deduplication"] | None, BeforeValidator(_given)
    ] = None
    dc_elements: list[DublinCoreElement] = Field(default_factory=list)
    attributes: DublinCoreAttributes = Field(default_factory=DublinCoreAttributes)

    @model_validator(mode="after")
    def _element_variables(self, info: ValidationInfo) -> Self:
        """A rule's Dublin Core elements are filled with each NIST control."""
        _raise_problems("DublinCoreMapping", _dc_element_problems(self.dc_elements, "nist", info))
        return self


class TagSource(_Section):
    """A field whose text an embedded tag holds, its transform, and the text written between
    it and the next source's text."""

    field: Annotated[RecommendationField, Field(min_length=1)]
    transform: TransformName = "none"
    separator: Annotated[str, BeforeValidator(_given)] = ""


class EmbeddedTag(_Section):
    """One tag an embedded_xml_tags mapping writes in its element's text: its text joins its
    sources' texts, or is fixed content, and is empty when it gives neither."""

    tag: XmlName
    # No sources (sources: []) write the tag empty, as content: "" does
    sources: Annotated[list[TagSource] | None, BeforeValidator(_given)] = None
    content: Annotated[str, BeforeValidator(_given)] = ""

    @model_validator(mode="after")
    def _one_text(self) -> Self:
        """The engine writes the sources' texts when a tag has sources, so content beside
        them would never be written."""
        if self.sources is not None and "content" in self.model_fields_set:
            raise PydanticCustomError(
                "one_text", "a tag takes its text from sources or content, not both"
            )
        return self


class EmbeddedXmlTagsMapping(_FieldMapping):
    """A Rule element whose text holds tags (a STIG description: VulnDiscussion and the tags
    after it), written in the order given."""

    structure: Literal["embedded_xml_tags"]
    components: Annotated[list[EmbeddedTag], Field(min_length=1)]
    attributes: dict[XmlName, RuleTemplateText] = Field(default_factory=dict)


class IdentAttribute(_Section):
    """An attribute from another namespace an ident is written with (cc8:controlURI)."""

    name: XmlName
    template: TemplateText = ""
    namespace_prefix: NamespacePrefix


class IdentSpec(_Section):
    """How each item of the list becomes an ident: its system, its value and its attributes,
    each a template over {item}."""

    system_template: TemplateText = ""
    value_template: TemplateText = "{item}"
    attributes: list[IdentAttribute] = Field(default_factory=list)


class IdentFromListMapping(_FieldMapping):
    """One ident per item of a list field (a dotted path), or per line of a text field read
    through a transform."""

    structure: Literal["ident_from_list"]
    source_field: RecommendationPath
    transform: TransformName = "none"
    ident_spec: IdentSpec

    @model_validator(mode="after")
    def _item_variables(self, info: ValidationInfo) -> Self:
        """The ident templates are filled with each item of the list."""
        models = _models(info)
        if models is None:
            return self
        values = {"item": _item_model(models, self.source_field, self.transform, one_value=True)}
        spec = self.ident_spec
        templates: list[tuple[tuple[int | str, ...], str | None]] = [
            (("ident_spec", "system_template"), spec.system_template),
            (("ident_spec", "value_template"), spec.value_template),
        ]
        for index, attribute in enumerate(spec.attributes):
            place = ("ident_spec", "attributes", index)
            templates += [
                ((*place, "template"), attribute.template),
                ((*place, "namespace_prefix"), attribute.namespace_prefix),
            ]
        _raise_problems("IdentFromListMapping", _template_problems(templates, values, models))
        return self


class MetadataElement(_Section):
    """The element written per item inside a group, or a child of it: its name, its text and
    attributes (templates over {item}), and its own children."""

    element: XmlName
    content: Template = None
    attributes: dict[XmlName, TemplateText] = Field(default_factory=dict)
    children: list["MetadataElement"] = Field(default_factory=list)


class MetadataGroup(_Section):
    """The element written per group of items (attributes are templates over {group_key}),
    holding one item element per item."""

    element: XmlName
    attributes: dict[XmlName, TemplateText] = Field(default_factory=dict)
    item_element: MetadataElement


class MetadataSpec(_Section):
    """The metadata a mapping writes: a root element in the namespace of namespace_prefix,
    holding one group element per value of group_by among the items."""

    removed_keys: ClassVar[Mapping[str, str]] = {
        "namespace": "the namespace comes from benchmark.namespaces by "
        "metadata_spec.namespace_prefix",
    }

    root_element: XmlName
    namespace_prefix: NamespacePrefix
    allow_empty: _Switch = None
    group_by: str
    group_element: MetadataGroup


class MetadataFromConfigMapping(_FieldMapping):
    """Metadata of a Rule written as model content from a list field (a dotted path)."""

    structure: Literal["metadata_from_config"]
    source_field: Annotated[RecommendationPath, Field(min_length=1)]
    metadata_spec: MetadataSpec

    @model_validator(mode="after")
    def _item_variables(self, info: ValidationInfo) -> Self:
        """A group's attributes are filled with its group_key; the item element and its
        children with each item of the list."""
        models = _models(info)
        if models is None:
            return self
        group = self.metadata_spec.group_element
        place: tuple[int | str, ...] = ("metadata_spec", "group_element")
        found = _template_problems(
            [((*place, "attributes", name), value) for name, value in group.attributes.items()],
            _values_of("group", models),
            models,
        )
        item = {"item": _item_model(models, self.source_field, None)}
        pending = [((*place, "item_element"), group.item_element)]
        while pending:
            where, element = pending.pop(0)
            found += _template_problems(
                [((*where, "content"), element.content)]
                + [
                    ((*where, "attributes", name), value)
                    for name, value in element.attributes.items()
                ],
                item,
                models,
            )
            pending += [
                ((*where, "children", index), child) for index, child in enumerate(element.children)
            ]
        _raise_problems("MetadataFromConfigMapping", found)
        return self


def structure(value: Any) -> str | None:
    """The structure of a field mapping: simple when it names none; None for a value that is
    no mapping."""
    match value:
        case {"structure": named} if named:
            return str(named)
        case Mapping():
            return "simple"
        case _:
            return None


FieldMapping = Annotated[
    Annotated[SimpleMapping, Tag("simple")]
    | Annotated[CompositeMapping, Tag("composite")]
    | Annotated[NestedMapping, Tag("nested")]
    | Annotated[DublinCoreMapping, Tag("dublin_core")]
    | Annotated[EmbeddedXmlTagsMapping, Tag("embedded_xml_tags")]
    | Annotated[IdentFromListMapping, Tag("ident_from_list")]
    | Annotated[MetadataFromConfigMapping, Tag("metadata_from_config")],
    Discriminator(structure),
]
"""A field mapping: the model of its structure; null switches off an inherited mapping."""


class BenchmarkSection(_Section):
    """The benchmark section: the entries the engine reads by name, and the elements filled
    from a benchmark field (every other entry)."""

    model_config = ConfigDict(extra="allow", strict=True)

    # The type of every other entry (pydantic's documented form)
    __pydantic_extra__: dict[str, SourcedElement] = Field(init=False)

    id_template: BenchmarkIdTemplate = None
    namespaces: NamespaceMap = Field(default_factory=dict)
    notice: Annotated[Notice | None, BeforeValidator(_given)] = None
    plain_text: list[PlainText] = Field(default_factory=list)
    profiles: Profiles = Field(default_factory=Profiles)
    reference: Reference = Field(default_factory=Reference)


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
    field_mappings: dict[str, FieldMapping | None] = Field(default_factory=dict)
    cci_deduplication: CciDeduplication = Field(default_factory=CciDeduplication)
    group_elements: dict[XmlName, GroupElement] = Field(default_factory=dict)
    post_processing: PostProcessing = Field(default_factory=PostProcessing)

    @property
    def cci_lookup(self) -> CciLookup:
        """Where the CCIs come from: the cci_lookup of the mapping named ident, or the defaults
        when that mapping is switched off or is no simple mapping."""
        match self.field_mappings:
            case {"ident": SimpleMapping() as ident}:
                return ident.cci_lookup
            case _:
                return CciLookup()

    @model_validator(mode="after")
    def _prefixes_declared(self) -> Self:
        """Refuse a prefixed element name whose prefix the style does not bind in
        benchmark.namespaces (the style is always a whole one: see validate_style)."""
        named = [
            (("benchmark", "reference", "dc_elements", index, "element"), element.element)
            for index, element in enumerate(self.benchmark.reference.dc_elements)
        ] + [
            (
                ("field_mappings", name, "dublin_core", "dc_elements", index, "element"),
                element.element,
            )
            for name, mapping in self.field_mappings.items()
            if isinstance(mapping, DublinCoreMapping)
            for index, element in enumerate(mapping.dc_elements)
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

    @model_validator(mode="after")
    def _writable_with_the_models(self, info: ValidationInfo) -> Self:
        """Refuse an element the XCCDF version does not have (a field mapping's target, a
        Group element, a Benchmark element filled from a field), and Rule metadata the Rule
        cannot hold as written (checked with the models)."""
        models = _models(info)
        if models is None:
            return self
        found: list[tuple[tuple[int | str, ...], str]] = []
        for name, mapping in self.field_mappings.items():
            if mapping is None:
                continue
            place: tuple[int | str, ...] = ("field_mappings", name, mapping.structure or "simple")
            target = mapping.target_element or name
            target_place = (*place, "target_element") if mapping.target_element else place
            problem = models.element_problem("Rule", target)
            if problem is not None:
                found.append((target_place, problem))
            elif isinstance(mapping, NestedMapping):
                (child,) = mapping.children
                problem = models.nested_child_problem(target, child.element)
                if problem is not None:
                    found.append(((*place, "children", 0, "element"), problem))
            elif isinstance(mapping, MetadataFromConfigMapping):
                found.extend(self._metadata_problems(models, mapping, place, target_place, target))
        for name in self.group_elements:
            problem = models.element_problem("Group", name)
            if problem is not None:
                found.append((("group_elements", name), problem))
        for name in self.benchmark.__pydantic_extra__ or {}:
            problem = models.element_problem("Benchmark", name)
            if problem is not None:
                found.append((("benchmark", name), problem))
        if found:
            raise ValidationError.from_exception_data(
                "StyleConfig",
                [
                    InitErrorDetails(
                        type=PydanticCustomError("not_writable", "{problem}", {"problem": problem}),
                        loc=location,
                        input=None,
                    )
                    for location, problem in found
                ],
            )
        return self

    def _metadata_problems(
        self,
        models: StyleModels,
        mapping: "MetadataFromConfigMapping",
        place: tuple[int | str, ...],
        target_place: tuple[int | str, ...],
        target: str,
    ) -> list[tuple[tuple[int | str, ...], str]]:
        """Why a metadata mapping cannot be written as XCCDF allows: its namespace must be
        declared and not XCCDF's (metadata holds only elements from another namespace), its
        items are grouped by a field they have, and the target must be a Rule element that
        repeats and takes elements of any namespace but XCCDF's."""
        spec = mapping.metadata_spec
        found: list[tuple[tuple[int | str, ...], str]] = []
        prefix_place = (*place, "metadata_spec", "namespace_prefix")
        namespaces = self.benchmark.namespaces
        namespace = (
            namespaces[spec.namespace_prefix] if spec.namespace_prefix in namespaces else None
        )
        if namespace is None:
            found.append(
                (prefix_place, f"{spec.namespace_prefix!r} is not declared in benchmark.namespaces")
            )
        elif namespace == models.xccdf_namespace:
            found.append(
                (
                    prefix_place,
                    f"namespace_prefix {spec.namespace_prefix!r} is the XCCDF namespace; XCCDF "
                    "metadata holds only elements from another namespace",
                )
            )
        items = list_item_model(models.recommendation, mapping.source_field)
        missing = _missing_part(items, spec.group_by.removeprefix("item."), dotted=True)
        if missing is not None:
            found.append(
                (
                    (*place, "metadata_spec", "group_by"),
                    f"{spec.group_by!r}: {missing[0]!r} is not a field of the items "
                    f"{mapping.source_field!r} lists",
                )
            )
        if models.metadata_holder(target) is None:
            found.append(
                (
                    target_place,
                    f"the Rule's {target!r} element cannot hold repeated elements of the "
                    f"namespace {namespace or spec.namespace_prefix}; metadata content goes in "
                    "metadata",
                )
            )
        return found


def _variants(annotation: Any) -> dict[str, type[BaseModel]]:
    """The models of a discriminated union by their tag (FieldMapping), through Optional and
    Annotated; empty for any other type."""
    found: dict[str, type[BaseModel]] = {}
    if get_origin(annotation) in (Union, UnionType):
        for arg in get_args(annotation):
            found.update(_variants(arg))
    elif get_origin(annotation) is Annotated:
        inner, *extras = get_args(annotation)
        tag = next((extra.tag for extra in extras if isinstance(extra, Tag)), None)
        if tag is not None and isinstance(inner, type) and issubclass(inner, BaseModel):
            found[tag] = inner
        else:
            found.update(_variants(inner))
    return found


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
        variants = _variants(annotation)
        if variants:
            # a discriminated union: the next place is the tag of the model that applies
            if not parts:
                return None
            annotation = variants.get(str(parts.pop(0)))
        # a section the style may leave out (benchmark.notice) is "Section | None"
        section = _model_in(annotation)
        if section is None:
            return None
        model = section
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


_FILE_NAME: Final = TypeAdapter(_StyleFile)
_MERGEABLE: Final = TypeAdapter(dict[str, JsonValue])
# The tags pydantic puts in a JsonValue error's place, after each mapping or list it enters
_JSON_VALUE_TAGS: Final = frozenset({"dict", "list", "str", "int", "float", "bool", "none"})


def file_name(value: Any) -> str | None:
    """A file name a style writes (extends, a CCI mapping file), as written; None when the
    value is no file name the schema accepts (validate_style reports that)."""
    try:
        return _FILE_NAME.validate_python(value, strict=True)
    except ValidationError:
        return None


def extended_style(data: Mapping[str, Any]) -> str | None:
    """The style file a style extends, as written; None when it names none, or names it in
    a way the schema refuses (validate_style reports that)."""
    match data:
        case {"extends": written}:
            return file_name(written)
        case _:
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


def validate_style(source: str, data: Any, models: StyleModels | None = None) -> StyleConfig:
    """Check a whole style against the schema: a style file with no extends, or the style
    an extends chain has built up to and including the file named source.

    Args:
        source: The file name the mistakes are reported with
        data: The style as built so far
        models: The models of the style's XCCDF version, for the checks that need them;
            without them only the shape is checked

    Raises:
        ValueError: One line per mistake: the file, the dotted path of the key, and what is
            wrong with it.
    """
    try:
        return StyleConfig.model_validate(data, context={"models": models})
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
