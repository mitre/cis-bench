"""Configuration-driven XCCDF mapping engine.

Reads YAML configs and applies transformations to convert
Pydantic Benchmark models to XCCDF format.

CRITICAL: Config-Driven Architecture
=====================================
ALL structure generation MUST be config-driven, not hard-coded.

RED FLAGS (Stop immediately if you see these):
- Organization names in method names (build_cis_*, generate_mitre_*)
- Hard-coded URIs (http://cisecurity.org/... in literals)
- Organization-specific if/else branching
- Structure logic in Python instead of YAML

APPROVED PATTERNS:
- ident_from_list: Generic ident generation from config
- metadata_from_config: Generic nested XML from config, as model content (AnyElement)
- generate_profiles_from_rules: Generic profile generation from config

See ARCHITECTURE_PRINCIPLES.md for complete guidelines.

Adding PCI-DSS, ISO 27001, HIPAA, etc. MUST require ZERO code changes (YAML only).
"""

import inspect
import logging
import re
import string
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field, fields, is_dataclass
from gettext import ngettext
from pathlib import Path
from types import ModuleType, UnionType
from typing import Annotated, Any, Final, Union, get_args, get_origin

import yaml
from lxml import etree
from pydantic import BaseModel
from xsdata.formats.dataclass.context import XmlContext
from xsdata.formats.dataclass.models.elements import XmlVar
from xsdata.formats.dataclass.models.generics import AnyElement
from xsdata.formats.dataclass.serializers.mixins import EventHandler

from cis_bench.exceptions import ExportError
from cis_bench.models.benchmark import (
    Benchmark,
    CISControl,
    ProfileDefinition,
    Recommendation,
)

# Import XCCDF types for element creation (XCCDF 1.2 - for type hints only)
# Note: Engine dynamically loads version-specific types based on config
from cis_bench.utils.cci_lookup import get_cci_service
from cis_bench.utils.xml_utils import ncname_slug

# Set up logger
logger = logging.getLogger(__name__)


@dataclass
class MappingConfig:
    """Loaded mapping configuration: one field per top-level section of a style's YAML.

    ConfigLoader fills and inherits (extends) every field the same way, so a section
    added here is loaded and inherited without further code.
    """

    metadata: dict[str, Any] = field(default_factory=dict)
    benchmark: dict[str, Any] = field(default_factory=dict)
    rule_defaults: dict[str, Any] = field(default_factory=dict)
    rule_id: dict[str, str] = field(default_factory=dict)
    group_id: dict[str, str] = field(default_factory=dict)  # Group ID template configuration
    field_mappings: dict[str, Any] = field(default_factory=dict)
    cci_deduplication: dict[str, Any] = field(default_factory=dict)
    # Specification of each Rule and Group element and its xsdata type
    rule_elements: dict[str, Any] = field(default_factory=dict)
    group_elements: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] | None = None
    # How the serialized XML is finished (remove_override_attr)
    post_processing: dict[str, Any] = field(default_factory=dict)

    @property
    def namespaces(self) -> dict[str, str]:
        """Prefix -> namespace URI, declared in benchmark.namespaces."""
        return dict(self.benchmark.get("namespaces") or {})


class TransformRegistry:
    """Registry of transformation functions."""

    _transforms: dict[str, Callable] = {}

    @classmethod
    def register(cls, name: str, func: Callable):
        """Register a transformation function."""
        cls._transforms[name] = func

    @classmethod
    def get(cls, name: str) -> Callable:
        """Get transformation function."""
        if name not in cls._transforms:
            raise ValueError(f"Unknown transformation: {name}")
        return cls._transforms[name]

    @classmethod
    def apply(cls, name: str, value: Any) -> Any:
        """Apply named transformation to value."""
        if not value:
            return ""
        transform = cls.get(name)
        return transform(value)


# Register built-in transformations
TransformRegistry.register("none", lambda x: x)


def strip_version_prefix(version: str | None) -> str:
    """Strip leading 'v' or 'V' prefix from version strings.

    DISA/Vulcan expects version without prefix (e.g., "4.0.0" not "v4.0.0").
    Vulcan adds its own "V" prefix per DISA convention.

    Examples:
        "v4.0.0" → "4.0.0"
        "V1.2.3" → "1.2.3"
        "4.0.0" → "4.0.0" (unchanged)
    """
    if not version:
        return ""
    if version.startswith(("v", "V")):
        return version[1:]
    return version


TransformRegistry.register("strip_version_prefix", strip_version_prefix)


def lines(text: str) -> list[str]:
    """The non-empty lines of a text, each stripped: a text field read as a list (a
    references field as one ident per line)."""
    return [line.strip() for line in text.splitlines() if line.strip()]


TransformRegistry.register("lines", lines)


_DOTTED_NUMBER = re.compile(r"[0-9]+(?:\.[0-9]+)*")


def dotted_number_path(value: Any, *labels: str) -> str:
    """A dotted numbered ID as a URI path, each sub-level after a label the config names.

    With the label "subcontrol", "8.5" is "8/subcontrol/5" and "13" is "13" (the form CIS
    Controls URIs use). An ID with more levels than labels allow, or with anything but
    numbers between the dots, is refused, so a malformed ID never becomes a URI.

    Examples:
        dotted_number_path("8.5", "subcontrol") -> "8/subcontrol/5"
        dotted_number_path("1.2.3", "section", "item") -> "1/section/2/item/3"
    """
    if any(not label.strip() for label in labels):
        raise ValueError(f"empty label in {labels!r}: each sub-level needs a name")
    text = "" if value is None else str(value).strip()
    parts = text.split(".") if _DOTTED_NUMBER.fullmatch(text) else []
    if not parts or len(parts) > len(labels) + 1:
        levels = len(labels) + 1
        raise ValueError(
            ngettext(
                "{value} is not a dotted number of at most {levels} level (such as 13 or 8.5)",
                "{value} is not a dotted number of at most {levels} levels (such as 13 or 8.5)",
                levels,
            ).format(value=repr(value), levels=levels)
        )
    sublevels = zip(labels[: len(parts) - 1], parts[1:], strict=True)
    return parts[0] + "".join(f"/{label}/{part}" for label, part in sublevels)


TransformRegistry.register("dotted_number_path", dotted_number_path)


_NOT_SLUG = re.compile(r"[^0-9a-z]+")


def slug(value: Any, separator: str = "_") -> str:
    """A title as an id-safe slug: accents dropped (NFKD), lower case, each run of other
    characters one separator.

    Examples:
        slug("Level 1 - Server", "_") -> "level_1_server"
        slug("Level 1 - Server", "-") -> "level-1-server"
        slug("Café", "_") -> "cafe"
    """
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.strip().lower()
    result = _NOT_SLUG.sub(separator, text).strip(separator)
    if not result:
        raise ValueError(f"{value!r} has nothing a slug can keep")
    return result


TransformRegistry.register("slug", slug)


class ConfigLoader:
    """Loads and validates mapping configuration from YAML with inheritance support."""

    # Where a setting a style might put in an unread section is actually read.
    _UNREAD_SECTION_HINTS: Final[dict[str, str]] = {
        "namespaces": "declare namespaces in benchmark.namespaces",
        "transformations": "a mapping names a transform registered in TransformRegistry; "
        "a style declares none",
    }

    # The post_processing settings the exporter reads, and where a removed one went.
    _POST_PROCESSING_SETTINGS: Final[frozenset[str]] = frozenset({"remove_override_attr"})
    _REMOVED_POST_PROCESSING_HINTS: Final[dict[str, str]] = {
        "handlers": "a Rule's metadata is model content (metadata_from_config); nothing "
        "is inserted after serialization",
        "strip_namespace_prefixes": "the serializer writes the namespaces declared in "
        "benchmark.namespaces; nothing rewrites prefixes afterwards",
        "preserve_namespaces": "a style declares exactly the namespaces its documents use in "
        "benchmark.namespaces, and all of them are declared on the root",
    }

    @staticmethod
    def _refuse_unread_post_processing_settings(
        config_path: Path, config_data: dict[str, Any]
    ) -> None:
        """A post_processing setting the exporter does not read is refused, by name, so a
        style cannot promise a behaviour nothing applies."""
        for name in config_data.get("post_processing") or {}:
            if name in ConfigLoader._POST_PROCESSING_SETTINGS:
                continue
            hint = ConfigLoader._REMOVED_POST_PROCESSING_HINTS.get(name)
            raise ValueError(
                f"{config_path.name}: post_processing.{name} is not a setting the exporter reads"
                + (f" ({hint})" if hint else "")
                + "; the settings are: "
                + ", ".join(sorted(ConfigLoader._POST_PROCESSING_SETTINGS))
            )

    # Namespaces in XML 1.0, section 3: the names no document may bind or rebind.
    _RESERVED_NAMESPACES: Final[dict[str, str]] = {
        "xml": "http://www.w3.org/XML/1998/namespace",
        "xmlns": "http://www.w3.org/2000/xmlns/",
    }

    @staticmethod
    def _refuse_undeclarable_namespaces(config_path: Path, config_data: dict[str, Any]) -> None:
        """Refuse a benchmark.namespaces binding an XML document cannot declare.

        A prefix is "default" (the default namespace) or an XML name without a colon, and
        never xml or xmlns; a URI is a non-empty string, never one of the two reserved
        namespaces, and is bound once (xsdata keeps one prefix per URI).
        """
        namespaces = (config_data.get("benchmark") or {}).get("namespaces") or {}
        where = f"{config_path.name}: benchmark.namespaces"
        bound: dict[str, str] = {}
        for prefix, uri in namespaces.items():
            if not isinstance(uri, str) or not uri:
                raise ValueError(f"{where}: prefix {prefix!r} needs a namespace URI")
            if prefix in ConfigLoader._RESERVED_NAMESPACES:
                raise ValueError(f"{where}: prefix {prefix!r} is reserved by XML")
            if uri in ConfigLoader._RESERVED_NAMESPACES.values():
                raise ValueError(f"{where}: prefix {prefix!r} is bound to a namespace XML reserves")
            if prefix != "default":
                try:
                    if not isinstance(prefix, str) or prefix.startswith("{"):
                        raise ValueError("an XML name without a colon is needed")
                    etree.QName(None, prefix)
                except ValueError as error:
                    raise ValueError(
                        f"{where}: {prefix!r} is not a namespace prefix ({error})"
                    ) from error
            if uri in bound:
                raise ValueError(
                    f"{where}: {prefix!r} and {bound[uri]!r} are both bound to {uri}; "
                    "a namespace is listed once"
                )
            bound[uri] = prefix

    @staticmethod
    def _refuse_unread_sections(config_path: Path, config_data: dict[str, Any]) -> None:
        """A top-level section the loader does not read is refused, by name.

        The loader fills one MappingConfig field per section; a section with no field would
        be ignored silently, and the style would promise a setting nothing applies.
        """
        sections = {section.name for section in fields(MappingConfig)} | {"extends"}
        for name in config_data:
            if name in sections:
                continue
            hint = ConfigLoader._UNREAD_SECTION_HINTS.get(name)
            raise ValueError(
                f"{config_path.name}: {name} is not a section the loader reads"
                + (f" ({hint})" if hint else "")
                + "; the sections are: "
                + ", ".join(sorted(sections - {"extends"}))
            )

    @staticmethod
    def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        """Deep merge two dictionaries, with override taking precedence.

        Args:
            base: Base dictionary (parent config)
            override: Override dictionary (child config)

        Returns:
            Merged dictionary where override values take precedence
        """
        from copy import deepcopy

        result = deepcopy(base)

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # Recursively merge nested dictionaries
                result[key] = ConfigLoader._deep_merge(result[key], value)
            else:
                # Override the value (lists, strings, etc. are replaced, not merged)
                result[key] = value

        return result

    @staticmethod
    def load(config_path: Path, _loading_stack: list[Path] | None = None) -> MappingConfig:
        """Load mapping configuration from YAML file with inheritance support.

        Config files can specify 'extends: base_style.yaml' to inherit from another file.
        Child configs override parent configs. Deep merge is used for nested dictionaries.

        Args:
            config_path: Path to the configuration file
            _loading_stack: Internal - tracks loading chain to detect circular inheritance

        Returns:
            MappingConfig with merged configuration

        Raises:
            ValueError: If circular inheritance is detected
            FileNotFoundError: If config file not found
        """
        if _loading_stack is None:
            _loading_stack = []

        # Check for circular inheritance
        if config_path in _loading_stack:
            cycle = " -> ".join(str(p) for p in _loading_stack)
            raise ValueError(f"Circular inheritance detected: {cycle} -> {config_path}")

        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        # Add to loading stack
        _loading_stack.append(config_path)

        try:
            # Load the current file
            with open(config_path) as f:
                config_data = yaml.safe_load(f) or {}
            ConfigLoader._refuse_unread_sections(config_path, config_data)
            ConfigLoader._refuse_unread_post_processing_settings(config_path, config_data)

            # Check for inheritance
            if "extends" in config_data:
                extends_path = Path(config_data.pop("extends"))

                # Resolve relative to current file's directory
                if not extends_path.is_absolute():
                    extends_path = config_path.parent / extends_path

                # Recursively load parent configuration
                parent_config_obj = ConfigLoader.load(extends_path, _loading_stack)

                # Convert parent MappingConfig back to dict for merging
                parent_dict = {
                    section.name: getattr(parent_config_obj, section.name)
                    for section in fields(MappingConfig)
                }

                # Deep merge parent with current (current overrides parent)
                config_data = ConfigLoader._deep_merge(parent_dict, config_data)

                logger.debug(f"Loaded {config_path.name} extending {extends_path.name}")
            else:
                logger.debug(f"Loaded {config_path.name} (no inheritance)")

            ConfigLoader._refuse_undeclarable_namespaces(config_path, config_data)
            return MappingConfig(
                **{
                    section.name: config_data[section.name]
                    for section in fields(MappingConfig)
                    if section.name in config_data
                }
            )

        finally:
            # Remove from loading stack
            _loading_stack.pop()


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


class VariableSubstituter:
    """Fills a style template's {variables} from a context, strictly: a name the context
    does not have, an attribute a value does not have, or a stray brace stops the export,
    since the alternative is an empty part written without a word. An empty value is data
    and substitutes as empty text."""

    @staticmethod
    def _pieces(template: str) -> list[tuple[str, str | None]]:
        """The template as (literal text, variable expression or None) pairs, parsed by the
        standard library's format-string parser, which refuses a stray or unclosed brace.

        Raises:
            ValueError: The template has a single "{" or "}" or an unclosed field.
        """
        try:
            parsed = list(string.Formatter().parse(template))
        except ValueError as error:
            raise ValueError(f"template {template!r}: {error}") from None
        pieces = []
        for literal, field_name, format_spec, conversion in parsed:
            expression = None
            if field_name is not None:
                # The parser splits "{name|filter:args}" at the ":"; put it back together.
                expression = field_name
                if conversion:
                    expression += f"!{conversion}"
                if format_spec:
                    expression += f":{format_spec}"
            pieces.append((literal, expression))
        return pieces

    @staticmethod
    def _resolve(expression: str, context: dict[str, Any], template: str) -> Any:
        """The value of one {expression}: a dotted path into the context, optionally piped
        through a registered transform with arguments ("item.control|dotted_number_path:
        subcontrol"). A None met along the path reads as empty text (an absent optional
        value, such as a recommendation without a MITRE mapping).

        Raises:
            ValueError: The path's first name is not in the context, a later name is not a
                key or attribute of the value before it, the filter names no registered
                transform, or the transform refuses the value.
        """
        path, pipe, filter_spec = expression.partition("|")
        path = path.strip()
        parts = path.split(".")
        if any(not part for part in parts):
            raise ValueError(f"template {template!r} has an empty name in {{{expression}}}")
        if parts[0] not in context:
            raise ValueError(
                f"template {template!r} names {path!r}; {parts[0]!r} is not a value this "
                f"template can use (it can use {', '.join(sorted(context))})"
            )
        value: Any = context[parts[0]]
        for depth, part in enumerate(parts[1:], 1):
            if value is None:
                value = ""
                break
            holder = ".".join(parts[:depth])
            if isinstance(value, dict):
                if part not in value:
                    raise ValueError(
                        f"template {template!r} names {path!r}; {part!r} is not a key of {holder}"
                    )
                value = value[part]
            elif hasattr(value, part):
                value = getattr(value, part)
            else:
                raise ValueError(
                    f"template {template!r} names {path!r}; {part!r} is not an attribute of "
                    f"{holder} ({type(value).__name__})"
                )
        if pipe:
            # "name" or "name:arg1, arg2"; the transform itself is called, so it decides
            # what an empty value means.
            raw_name, _, raw_args = filter_spec.partition(":")
            name = raw_name.strip()
            if not name:
                raise ValueError(f"filter without a transform name in {{{expression}}}")
            args = [arg.strip() for arg in raw_args.split(",")] if raw_args.strip() else []
            transform = TransformRegistry.get(name)
            try:
                inspect.signature(transform).bind(value, *args)
            except TypeError:
                raise ValueError(f"{name} does not take the arguments {args}") from None
            value = transform(value, *args)
        return value

    @staticmethod
    def substitute(template: str, context: dict[str, Any]) -> Any:
        """Replace {variables} in template with context values.

        Preserves type if template is a single variable (e.g., "{item.ig1}" returns bool).
        Converts to string if mixing text and variables (e.g., "F-{ref}" returns string).
        A None value is empty text in both cases. A variable may name a registered transform
        after a "|", with arguments after a ":", which is applied to its value:
        "{item.control|dotted_number_path:subcontrol}".

        Examples:
            template: "F-{ref_normalized}"
            context: {"ref_normalized": "3_1_1"}
            result: "F-3_1_1" (string)

            template: "{item.ig1}"
            context: {"item": obj with ig1=False}
            result: False (bool preserved!)

            template: "control/{item.control|dotted_number_path:subcontrol}"
            context: {"item": obj with control="8.5"}
            result: "control/8/subcontrol/5"

        Raises:
            ValueError: A stray brace, a name the context does not have, an attribute a
                value does not have, or a filter problem (see _resolve).
        """
        pieces = VariableSubstituter._pieces(template)
        if len(pieces) == 1 and pieces[0][0] == "" and pieces[0][1] is not None:
            # The whole template is one variable: keep the value's type; None is empty text
            value = VariableSubstituter._resolve(pieces[0][1], context, template)
            return "" if value is None else value
        out = []
        for literal, expression in pieces:
            out.append(literal)
            if expression is not None:
                value = VariableSubstituter._resolve(expression, context, template)
                out.append("" if value is None else str(value))
        return "".join(out)


class MappingEngine:
    """Main engine that applies config-based mappings."""

    def __init__(self, config_path: Path):
        """Initialize mapping engine with config.

        Args:
            config_path: Path to YAML configuration file
        """
        self.config = ConfigLoader.load(config_path)
        self._refuse_unknown_field_names()
        self._refuse_unknown_transforms()
        self._refuse_invalid_embedded_tags()
        self.cci_service = get_cci_service()

        # Dynamically load XCCDF models based on config version
        xccdf_version = self.config.metadata.get("xccdf_version", "1.2")
        self._load_xccdf_models(xccdf_version)

        # Pre-load all types specified in config (stable code, config-driven types)
        self._load_types_from_config()
        self._refuse_unwritable_metadata_mappings()

    # Structures whose source_field is read as a dotted path (_get_nested_field); every
    # other reader takes one field name.
    _DOTTED_PATH_STRUCTURES = frozenset({"ident_from_list", "metadata_from_config"})

    def _refuse_unknown_transforms(self) -> None:
        """Refuse a style that names a transform no function is registered under.

        A transform is looked up when a value reaches it, so a misspelled or withdrawn name
        would fail the first export that has a value for the field, not the style's load.

        Raises:
            ValueError: A transform (field_mappings, their children, a component source,
                group_elements, benchmark elements), benchmark.profiles.description_transform
                or a filter ({value|transform}) in any string the style holds names no
                registered transform, or is not a name.
        """
        named: list[tuple[str, Any]] = []
        for name, mapping in self.config.field_mappings.items():
            if not isinstance(mapping, dict):
                continue
            named.append((f"field_mappings.{name}", mapping.get("transform")))
            for i, child in enumerate(mapping.get("children") or []):
                if isinstance(child, dict):
                    named.append((f"field_mappings.{name}.children[{i}]", child.get("transform")))
            for i, component in enumerate(mapping.get("components") or []):
                if not isinstance(component, dict):
                    continue
                for j, source in enumerate(component.get("sources") or []):
                    if isinstance(source, dict):
                        named.append(
                            (
                                f"field_mappings.{name}.components[{i}].sources[{j}]",
                                source.get("transform"),
                            )
                        )
            for j, source in enumerate(mapping.get("sources") or []):
                if isinstance(source, dict):
                    named.append((f"field_mappings.{name}.sources[{j}]", source.get("transform")))
        for section in ("group_elements", "benchmark"):
            for name, element in getattr(self.config, section).items():
                if isinstance(element, dict):
                    named.append((f"{section}.{name}", element.get("transform")))
        profiles = self.config.benchmark.get("profiles")
        if isinstance(profiles, dict):
            named.append(
                ("benchmark.profiles.description_transform", profiles.get("description_transform"))
            )
        for where, transform in named:
            if transform is None:
                continue
            if not isinstance(transform, str):
                raise ValueError(f"{where}: transform must be a name, got {transform!r}")
            try:
                TransformRegistry.get(transform)
            except ValueError as error:
                raise ValueError(f"{where}: {error}") from error
        for config_section in fields(MappingConfig):
            self._refuse_unknown_template_filters(
                config_section.name, getattr(self.config, config_section.name)
            )

    @classmethod
    def _refuse_unknown_template_filters(cls, where: str, value: Any) -> None:
        """Refuse a filter ({value|transform}) that names no registered transform, or names
        none, in any string the style holds; walks nested sections.

        The engine substitutes strings under many keys (templates, content, href, system,
        attributes, prefixes), so every string is read as a template; one the template
        parser refuses is left alone here (it is refused where it is used, if it is used).

        Raises:
            ValueError: A filter names no registered transform, or has no name.
        """
        if isinstance(value, dict):
            for key, inner in value.items():
                cls._refuse_unknown_template_filters(f"{where}.{key}", inner)
        elif isinstance(value, list):
            for index, inner in enumerate(value):
                cls._refuse_unknown_template_filters(f"{where}[{index}]", inner)
        elif isinstance(value, str):
            try:
                pieces = VariableSubstituter._pieces(value)
            except ValueError:
                return
            for _, expression in pieces:
                if expression is None or "|" not in expression:
                    continue
                name = expression.partition("|")[2].partition(":")[0].strip()
                if not name:
                    raise ValueError(
                        f"{where}: filter without a transform name in {{{expression}}}"
                    )
                try:
                    TransformRegistry.get(name)
                except ValueError as error:
                    raise ValueError(f"{where}: {error}") from error

    def _refuse_invalid_embedded_tags(self) -> None:
        """Refuse a style whose embedded_xml_tags component names a tag that is no XML name.

        Such a tag would be written into an element's text and only fail for the reader that
        parses the tags, long after the export.

        Raises:
            ValueError: A component's tag is missing or is not a valid XML element name.
        """
        for name, mapping in self.config.field_mappings.items():
            if not isinstance(mapping, dict) or mapping.get("structure") != "embedded_xml_tags":
                continue
            for i, component in enumerate(mapping.get("components") or []):
                tag = component.get("tag") if isinstance(component, dict) else None
                try:
                    etree.Element(tag)
                except (ValueError, TypeError) as error:
                    raise ValueError(
                        f"field_mappings.{name}.components[{i}]: {tag!r} is not a valid XML tag "
                        f"name ({error})"
                    ) from error

    def _refuse_unknown_field_names(self) -> None:
        """Refuse a style that names a recommendation or benchmark field that does not exist.

        A name that is no field reads as empty, and an empty element is left out, so a
        misspelled name would drop the element without a word.

        Raises:
            ValueError: A source_field (field_mappings, their children, a cci_lookup), a
                component source's field (embedded_xml_tags) or a source (group_elements,
                benchmark elements) names no field.
        """
        named: list[tuple[str, str, type[BaseModel], bool]] = []
        for name, mapping in self.config.field_mappings.items():
            if not isinstance(mapping, dict):
                continue
            dotted = mapping.get("structure") in self._DOTTED_PATH_STRUCTURES
            if mapping.get("source_field"):
                named.append(
                    (f"field_mappings.{name}", mapping["source_field"], Recommendation, dotted)
                )
            lookup = mapping.get("cci_lookup")
            if isinstance(lookup, dict) and lookup.get("source_field"):
                # The CCI lookup reads CIS controls, so the field must be declared to hold
                # them; a list of anything else would read as no controls.
                field_info = Recommendation.model_fields.get(lookup["source_field"])
                if field_info is None or field_info.annotation != list[CISControl]:
                    raise ValueError(
                        f"field_mappings.{name}.cci_lookup names {lookup['source_field']!r}, "
                        f"which is not a field of Recommendation holding CIS controls"
                    )
            for i, child in enumerate(mapping.get("children") or []):
                if isinstance(child, dict) and child.get("source_field"):
                    named.append(
                        (
                            f"field_mappings.{name}.children[{i}]",
                            child["source_field"],
                            Recommendation,
                            False,
                        )
                    )
            for i, component in enumerate(mapping.get("components") or []):
                if not isinstance(component, dict):
                    continue
                for j, source in enumerate(component.get("sources") or []):
                    where = f"field_mappings.{name}.components[{i}].sources[{j}]"
                    if not isinstance(source, dict) or not source.get("field"):
                        raise ValueError(
                            f"{where}: a component source needs field, the field it reads"
                        )
                    named.append((where, source["field"], Recommendation, False))
            if mapping.get("structure") == "composite" and not (
                isinstance(mapping.get("sources"), list) and mapping["sources"]
            ):
                raise ValueError(
                    f"field_mappings.{name}: composite needs sources, the fields to join"
                )
            for j, source in enumerate(mapping.get("sources") or []):
                where = f"field_mappings.{name}.sources[{j}]"
                if not isinstance(source, dict) or not source.get("field"):
                    raise ValueError(f"{where}: a composite source needs field, the field it reads")
                named.append((where, source["field"], Recommendation, False))
        for name, element in self.config.group_elements.items():
            if isinstance(element, dict) and element.get("source"):
                named.append((f"group_elements.{name}", element["source"], Recommendation, False))
        for name, element in self.config.benchmark.items():
            if isinstance(element, dict) and element.get("source"):
                named.append((f"benchmark.{name}", element["source"], Benchmark, False))

        for where, path, model, dotted in named:
            parts = path.split(".") if dotted else [path]
            current: Any = model
            for part in parts:
                fields = (
                    current.model_fields
                    if isinstance(current, type) and issubclass(current, BaseModel)
                    else {}
                )
                if part not in fields:
                    holder = current.__name__ if isinstance(current, type) else model.__name__
                    raise ValueError(f"{where} names {path!r}: {part!r} is not a field of {holder}")
                current = _model_in(fields[part].annotation)

    def _load_xccdf_models(self, version: str):
        """Dynamically import XCCDF models based on version.

        Args:
            version: XCCDF version ('1.1.4' or '1.2')
        """
        self.xccdf_models: ModuleType
        if version == "1.1.4":
            # Import XCCDF 1.1.4 models
            from cis_bench.models.xccdf_v1_1 import xccdf_1_1_4

            self.xccdf_models = xccdf_1_1_4
            self.xccdf_namespace = "http://checklists.nist.gov/xccdf/1.1"

        elif version == "1.2":
            # Import XCCDF 1.2 models
            from cis_bench.models.xccdf import xccdf_1_2

            self.xccdf_models = xccdf_1_2
            self.xccdf_namespace = "http://checklists.nist.gov/xccdf/1.2"

        else:
            raise ValueError(f"Unsupported XCCDF version: {version}")

        self.xccdf_version = version
        self._xml_context = XmlContext()

    def rule_element(self, target: str) -> XmlVar | None:
        """The XCCDF model's description of the Rule element field `target` (its type, whether
        it repeats), read from the xsdata model of this style's XCCDF version; None when Rule
        has no such element."""
        for var in self._xml_context.build(self.get_xccdf_class("Rule")).get_all_vars():
            if var.name == target and var.is_element:
                return var
        return None

    def get_xccdf_class(self, class_name: str):
        """Get XCCDF class by name (version-agnostic).

        Args:
            class_name: Name of XCCDF class (e.g., 'Benchmark', 'Rule', 'Group')

        Returns:
            Class from appropriate XCCDF module
        """
        return getattr(self.xccdf_models, class_name)

    def normalize_ref(self, ref: str) -> str:
        """Normalize CIS ref for IDs (3.1.1 → 3_1_1)."""
        return ref.replace(".", "_")

    def ref_to_stig_number(self, ref: str) -> str:
        """Convert CIS ref to STIG-style 6-digit number.

        Converts hierarchical CIS refs like "1.1.1" or "3.2.1.1" to a
        STIG-style 6-digit number by padding each segment.

        Examples:
            "1.1.1"   → "010101" (2 digits per segment, 3 segments)
            "3.2.1"   → "030201"
            "1.1.1.1" → "01010101" (8 digits for 4 segments)
            "12.3.4"  → "120304"

        This creates a sortable, unique numeric ID from CIS refs.
        """
        parts = ref.split(".")
        # Pad each part to 2 digits, join without separator
        padded = "".join(p.zfill(2) for p in parts)
        return padded

    def create_embedded_xml_tags(
        self, components: list[dict[str, Any]], rec: Recommendation
    ) -> str:
        """The text of an element that carries tags inside it (a STIG rule description:
        VulnDiscussion and the tags after it), built from the style's components.

        Each component is one tag, in the order given, always written: its text is the
        component's ``content``, or its ``sources`` joined (each source names a ``field`` of
        the recommendation, a ``transform``, default none, and the ``separator`` that follows
        its text when another source's text comes after it). Each tag is built and written by
        the XML library, which escapes its text, so a reader that unescapes the element's text
        once and parses the tags gets the text as stored, a placeholder such as <user>
        included; a tag whose name is not a valid XML name is refused when the style loads.
        """
        parts = []
        for component in components:
            tag = component["tag"]
            if "sources" in component:
                texts: list[tuple[str, str]] = [
                    (text, source.get("separator", ""))
                    for source in component["sources"]
                    if (
                        text := TransformRegistry.apply(
                            source.get("transform", "none"), getattr(rec, source["field"])
                        )
                    )
                ]
                content = "".join(
                    text + (separator if i < len(texts) - 1 else "")
                    for i, (text, separator) in enumerate(texts)
                )
            else:
                content = component.get("content", "")
            element = etree.Element(tag)
            element.text = content  # "" keeps the <Tag></Tag> form official STIGs write
            parts.append(etree.tostring(element, encoding="unicode"))
        return "".join(parts)

    def get_ccis_with_deduplication(self, rec: Recommendation) -> tuple[list[str], list[str]]:
        """Get CCIs and extra NIST controls using deduplication.

        Returns:
            Tuple of (cci_list, extra_nist_list)
        """
        if not self.config.cci_deduplication.get("enabled"):
            # No deduplication - return empty CCIs, all NIST as extras
            return [], rec.nist_controls

        # Get extract parameter from ident field mapping (default: "all")
        ident_mapping = self.config.field_mappings.get("ident", {})
        cci_lookup_config = ident_mapping.get("cci_lookup", {})
        extract = cci_lookup_config.get("extract", "all")

        # The CIS controls come from the field the style names. The mapping file is keyed
        # by one CIS Controls version, named in the style (cci_lookup.cis_controls_version);
        # other versions reuse the same numbers for unrelated safeguards, so only that
        # version's controls are looked up.
        source_field = cci_lookup_config.get("source_field")
        if not source_field:
            raise ValueError(
                "ident.cci_lookup needs source_field, the field holding the CIS controls"
            )
        controls_version = cci_lookup_config.get("cis_controls_version")
        cis_control_ids = [
            c.control
            for c in getattr(rec, source_field)
            if controls_version is None or c.version == controls_version
        ]

        # Use CCI service for deduplication
        ccis, extra_nist = self.cci_service.deduplicate_nist_controls(
            cis_control_ids, rec.nist_controls, extract=extract
        )

        # Fallback CCI if no CCIs (even if NIST exists)
        # CRITICAL: DISA STIGs require at least one ident element per rule
        if not ccis:
            fallback_cci = cci_lookup_config.get("fallback_cci")
            if fallback_cci:
                ccis = [fallback_cci]
                logger.debug(f"No CCIs for {rec.ref}, using fallback {fallback_cci}")

        return ccis, extra_nist

    def apply_field_mapping(
        self, field_name: str, rec: Recommendation, context: dict[str, Any]
    ) -> Any:
        """Apply a single field mapping from config.

        Args:
            field_name: Name of field in config
            rec: Source recommendation
            context: Variable substitution context

        Returns:
            Transformed value(s) for XCCDF
        """
        mapping = self.config.field_mappings.get(field_name)
        if not mapping:
            return None

        # Get source field value
        source_field = mapping.get("source_field")
        if source_field:
            value = getattr(rec, source_field, None)

            # Apply transformation
            transform_name = mapping.get("transform", "none")
            return TransformRegistry.apply(transform_name, value)

        return None

    # ===== Benchmark-Level Element Creation (from config) =====

    def create_notice(self, benchmark: Benchmark):
        """Create notice element from config (version-agnostic).

        Resolves notice id, xml:lang, and optional variable-substituted text
        content from the style's benchmark.notice configuration while keeping
        content empty when omitted or blank.
        """
        raw_notice = self.config.benchmark.get("notice")
        notice_config = raw_notice if isinstance(raw_notice, dict) else {}
        raw_attrs = notice_config.get("attributes")
        attributes = raw_attrs if isinstance(raw_attrs, dict) else {}

        type_name = notice_config.get("xccdf_type", "NoticeType")
        NoticeType = self.get_xccdf_class(type_name)

        substitution_context = {"benchmark": benchmark}

        raw_id = notice_config.get("id") or attributes.get("id") or "terms-of-use"
        notice_id = str(VariableSubstituter.substitute(str(raw_id), substitution_context))

        raw_lang = notice_config.get("lang") or attributes.get("xml:lang")
        notice_lang = (
            str(VariableSubstituter.substitute(str(raw_lang), substitution_context))
            if raw_lang
            else None
        )

        raw_content = notice_config.get("content")
        content: list[object] = []
        if isinstance(raw_content, str) and raw_content.strip():
            resolved = str(
                VariableSubstituter.substitute(raw_content, substitution_context)
            ).strip()
            if resolved:
                content = [resolved]

        return NoticeType(
            id=notice_id,
            lang=notice_lang,
            content=content,
        )

    def create_front_matter(self, benchmark: Benchmark):
        """Create front-matter element from config (version-agnostic).

        Type specified in config (handles 1.1.4 vs 1.2 differences).
        """
        front_config = self.config.benchmark.get("front_matter", {})
        type_name = front_config.get("xccdf_type", "HtmlTextType")
        FrontMatterType = self.get_xccdf_class(type_name)
        return FrontMatterType(content=[])

    def create_rear_matter(self, benchmark: Benchmark):
        """Create rear-matter element from config (version-agnostic).

        Type specified in config (handles 1.1.4 vs 1.2 differences).
        """
        rear_config = self.config.benchmark.get("rear_matter", {})
        type_name = rear_config.get("xccdf_type", "HtmlTextType")
        RearMatterType = self.get_xccdf_class(type_name)
        return RearMatterType(content=[])

    def dublin_core_elements(
        self, dc_elements_config: list[dict], values: dict[str, Any]
    ) -> list[AnyElement]:
        """A reference's Dublin Core elements as xsdata content, from the style's dc_elements
        (element "dc:title", content template): the namespace is the one the style declares
        for the element's prefix (benchmark.namespaces), and each content template is
        filled from values. xsdata writes them as child elements of the reference.

        Raises:
            ValueError: An element's prefix has no namespace in the style.
        """
        elements = []
        for dc in dc_elements_config:
            prefix, _, local_name = dc["element"].partition(":")
            namespace = self.config.namespaces.get(prefix)
            if not namespace:
                raise ValueError(
                    f"dc_elements names {dc['element']!r} but benchmark.namespaces declares "
                    f"no {prefix!r} namespace"
                )
            text = str(VariableSubstituter.substitute(dc["content"], values))
            elements.append(AnyElement(qname=f"{{{namespace}}}{local_name}", text=text))
        return elements

    def create_reference(self, benchmark: Benchmark) -> tuple[str, list[AnyElement]]:
        """The Benchmark's own reference: its href from the style's
        benchmark.reference.attributes.href (the benchmark's URL when the style names none)
        and the Dublin Core elements of benchmark.reference.dc_elements (none when the style
        declares none)."""
        reference_config = self.config.benchmark.get("reference", {})
        href_template = (reference_config.get("attributes") or {}).get("href")
        values = {"benchmark": benchmark}
        href = (
            str(VariableSubstituter.substitute(href_template, values))
            if href_template
            else str(benchmark.url)
        )
        dc_elements_config = reference_config.get("dc_elements", [])
        return href, self.dublin_core_elements(dc_elements_config, values)

    def create_plain_texts(self, benchmark: Benchmark):
        """Create plain-text elements from config (version-agnostic).

        Per DISA conventions: release-info, generator, conventionsVersion
        """
        plain_text_configs = self.config.benchmark.get("plain_text", [])
        PlainTextType = self.get_xccdf_class("PlainTextType")
        plain_texts = []

        from datetime import datetime

        download_date = (
            benchmark.downloaded_at.strftime("%d %b %Y")
            if benchmark.downloaded_at
            else datetime.now().strftime("%d %b %Y")
        )

        for pt_config in plain_text_configs:
            pt_id = pt_config.get("id")
            content_template = pt_config.get("content", "")

            # Substitute variables
            content = VariableSubstituter.substitute(
                content_template, {"download_date": download_date, "benchmark": benchmark}
            )

            plain_texts.append(PlainTextType(id=pt_id, value=content))

        return plain_texts

    # OLD hard-coded methods removed - replaced with loop-driven methods:
    #   - create_rule() → map_rule()
    #   - create_group() → map_group()
    #   - create_benchmark() → map_benchmark()
    # These methods hard-coded field lists. New methods loop through config.

    def _load_types_from_config(self):
        """Pre-load all XCCDF types specified in config.

        Loads xsdata type classes for each element specification.
        Code is stable - all type changes happen in YAML.

        Hierarchy:
          Benchmark → Group → Rule → Elements (title, description, etc.)

        Each element needs an xsdata type class (e.g., TextWithSubType).
        """
        self.rule_element_types = {}
        self.group_element_types = {}
        self.benchmark_element_types = {}

        # Load Rule element types (from rule_elements section)
        for element_name, element_config in self.config.rule_elements.items():
            type_name = element_config.get("xccdf_type")
            if type_name:
                self.rule_element_types[element_name] = self.get_xccdf_class(type_name)

        # Load Group element types (from group_elements section)
        for element_name, element_config in self.config.group_elements.items():
            type_name = element_config.get("xccdf_type")
            if type_name:
                self.group_element_types[element_name] = self.get_xccdf_class(type_name)

        # Load Benchmark element types
        for element_name, element_config in self.config.benchmark.items():
            if isinstance(element_config, dict) and "xccdf_type" in element_config:
                type_name = element_config["xccdf_type"]
                self.benchmark_element_types[element_name] = self.get_xccdf_class(type_name)

    # ===== NEW: Loop-Driven Element Construction (Config-Driven) =====
    # Per MAPPING_ENGINE_DESIGN.md line 759 - Loop through config, don't hard-code fields

    def _construct_typed_element(self, ElementType, value):
        """Construct xsdata element with correct field (content vs value) - DRY helper.

        Different xsdata types use different field names:
          - TextType uses 'value'
          - TextWithSubType uses 'content'
          - HtmlTextWithSubType uses 'content'
          - etc.

        This method introspects the type and uses the correct field.

        Args:
            ElementType: xsdata type class
            value: Value to set

        Returns:
            Constructed element instance, or None if type doesn't have content/value
        """
        if not hasattr(ElementType, "__dataclass_fields__"):
            return None

        fields = ElementType.__dataclass_fields__

        if "content" in fields:
            return ElementType(content=[value])
        elif "value" in fields:
            return ElementType(value=value)
        else:
            # Fallback: try content
            return ElementType(content=[value])

    def _is_list_field(self, parent_class, field_name: str) -> bool:
        """Check if a field in parent class expects a list - DRY helper.

        Uses schema introspection instead of hard-coding field names.

        Args:
            parent_class: xsdata parent class (Rule, Group, Benchmark)
            field_name: Field name to check

        Returns:
            True if field expects list, False if single element

        Example:
            Rule.title → list[TextWithSubType] → True
            Rule.version → Optional[VersionType] → False
        """
        if not hasattr(parent_class, "__dataclass_fields__"):
            return True  # Default to list

        if field_name not in parent_class.__dataclass_fields__:
            return True  # Default to list

        field = parent_class.__dataclass_fields__[field_name]
        type_str = str(field.type)

        # Check if type annotation includes 'list[' or 'List['
        return "list[" in type_str.lower()

    def _element_name_to_type_name(self, element_name: str) -> str:
        """Convert element name to xsdata type class name.

        Examples:
            'check-content' → 'CheckContentType'
            'check' → 'CheckType'
            'title' → 'TitleType'

        Args:
            element_name: Element name from config (kebab-case or lowercase)

        Returns:
            Type class name (PascalCase + 'Type' suffix)
        """
        # Convert kebab-case to PascalCase
        parts = element_name.split("-")
        pascal = "".join(word.capitalize() for word in parts)

        # Add Type suffix if not present
        if not pascal.endswith("Type"):
            pascal += "Type"

        return pascal

    def _build_field_value(
        self, field_name: str, field_mapping: dict, rec: Recommendation, context: dict
    ) -> Any:
        """Build field value from config specification (DRY helper).

        Handles different field structures:
        - Simple fields (source + transform)
        - Embedded XML (VulnDiscussion structure)
        - CCI lookup with deduplication
        - Nested structures (check/check-content)

        Args:
            field_name: Field name in config
            field_mapping: Field mapping specification from config
            rec: Source Recommendation
            context: Variable substitution context

        Returns:
            Transformed value ready for xsdata type wrapping, or None
        """
        structure = field_mapping.get("structure")

        # Handle special structures
        if structure == "embedded_xml_tags":
            components = field_mapping.get("components")
            if not components:
                raise ValueError(
                    f"field_mappings.{field_name}: embedded_xml_tags needs components, the "
                    "tags to write and their sources"
                )
            return self.create_embedded_xml_tags(components, rec)

        elif field_mapping.get("source_logic") == "cci_lookup_with_deduplication":
            # CCI lookup - returns list of CCIs
            ccis, _ = self._cci_split(rec, context)
            return ccis  # Return raw list, caller will wrap in IdentType

        elif structure == "nested":
            # Handle nested structures (like check/check-content)
            # For now, return None - handle in specialized method
            return None

        elif structure == "composite":
            return self._composite_text(field_name, field_mapping, rec)

        # Simple field mapping
        source_field = field_mapping.get("source_field")
        if source_field:
            # Get value from recommendation
            value = getattr(rec, source_field, None)

            # Apply transformation
            transform = field_mapping.get("transform", "none")
            transformed_value = TransformRegistry.apply(transform, value)

            return transformed_value

        return None

    @staticmethod
    def _composite_text(field_name: str, field_mapping: dict, rec: Recommendation) -> str | None:
        """The text of a composite mapping: its sources' texts, each after its transform, joined
        by the separator (a blank line unless the mapping says otherwise); a source with a
        label writes the label, the separator and the text; a source without text adds
        nothing, and None is returned when no source has text.

        Config structure:
            structure: "composite"
            separator: "\n\n"
            sources:
              - field: "description"
              - field: "default_value"
                label: "Default Value:"
                transform: "none"

        Raises:
            ValueError: The mapping has no sources.
        """
        sources = field_mapping.get("sources")
        if not sources:
            raise ValueError(
                f"field_mappings.{field_name}: composite needs sources, the fields to join"
            )
        separator = field_mapping.get("separator", "\n\n")
        parts = []
        for source in sources:
            text = TransformRegistry.apply(
                source.get("transform", "none"), getattr(rec, source["field"])
            )
            if not text:
                continue
            label = source.get("label")
            parts.append(f"{label}{separator}{text}" if label else text)
        return separator.join(parts) or None

    def ref_values(self, ref: str) -> dict[str, str]:
        """The values made from a recommendation ref that templates use: {ref} ("3.1.1"),
        {ref_normalized} ("3_1_1") and {stig_number} ("030101")."""
        return {
            "ref": ref,
            "ref_normalized": self.normalize_ref(ref),
            "stig_number": self.ref_to_stig_number(ref),
        }

    def _id_from_ref(self, section: str, ref: str) -> str:
        """An id from the style's <section>.template (rule_id, group_id) and the ref's values.

        Raises:
            ValueError: The style has no template, the template names a value the ref does
                not give (VariableSubstituter refuses it), or the template gives no id.
        """
        template = (getattr(self.config, section) or {}).get("template")
        if not template:
            raise ValueError(f"the style has no {section}.template")
        made = VariableSubstituter.substitute(template, self.ref_values(ref))
        if not isinstance(made, str) or not made:
            raise ValueError(f"{section} template {template!r} gives no id for ref {ref!r}")
        return made

    def rule_id_for_ref(self, ref: str) -> str:
        """The Rule id for a recommendation ref: the one place a Rule id is made, so a Rule
        and every Profile select naming it agree."""
        return self._id_from_ref("rule_id", ref)

    def group_id_for_ref(self, ref: str) -> str:
        """The Group id for a recommendation ref, from the style's group_id template."""
        return self._id_from_ref("group_id", ref)

    def _cci_split(self, rec: Recommendation, context: dict) -> tuple[list[str], list[str]]:
        """The rule's (CCIs, NIST controls no CCI covers), computed once per rule by map_rule
        and shared by the CCI idents and the NIST references."""
        if "cci_split" not in context:
            context["cci_split"] = self.get_ccis_with_deduplication(rec)
        split: tuple[list[str], list[str]] = context["cci_split"]
        return split

    def map_rule(self, rec: Recommendation, context: dict):
        """Map Recommendation to Rule using config (LOOP-DRIVEN - no hard-coded fields).

        Implementation follows MAPPING_ENGINE_DESIGN.md line 722-776.
        Loops through field_mappings, applies transformations, constructs Rule dynamically.

        Args:
            rec: Source Recommendation (Pydantic model)
            context: Mapping context with variables (platform, benchmark, etc.)

        Returns:
            xsdata Rule object constructed from config

        Note:
            This is the CORRECT implementation. Old create_rule() hard-codes field list.
        """
        Rule = self.get_xccdf_class("Rule")

        # The ref's values serve every template below (ids, fixref, check systems)
        context.update({**self.ref_values(rec.ref), "rec": rec})
        # The context is shared across rules: drop the previous rule's CCI split.
        context.pop("cci_split", None)
        # What a rule's templates may name: the ref's values, the recommendation and the
        # benchmark; not the engine's working keys (the CCI split, the recommendation list)
        template_values: dict[str, Any] = {**self.ref_values(rec.ref), "rec": rec}
        if "benchmark" in context:
            template_values["benchmark"] = context["benchmark"]

        rule_id = self.rule_id_for_ref(rec.ref)

        # Start with required fields and defaults
        # Note: status belongs at Benchmark level, not Rule level
        rule_fields = {
            "id": rule_id,
            "severity": self.config.rule_defaults.get("severity", "medium"),
            "weight": float(self.config.rule_defaults.get("weight", "10.0")),
        }

        # THE KEY: Loop through config.field_mappings (NO HARD-CODED FIELD LIST)
        for field_name, field_mapping in self.config.field_mappings.items():
            # Skip null/disabled field mappings (used to override parent config)
            if field_mapping is None:
                continue

            # Metadata is model content in the type the XCCDF model gives the target element
            # (checked when the style loaded): one metadata element per mapping, in order
            if field_mapping.get("structure") == "metadata_from_config":
                metadata_root = self.generate_metadata_from_config(rec, field_mapping)
                if metadata_root is not None:
                    target, MetadataHolder, content_field = self._metadata_holders[field_name]
                    rule_fields.setdefault(target, []).append(
                        MetadataHolder(**{content_field: [metadata_root]})
                    )
                continue

            # Get xsdata type for this element
            FieldType = self.rule_element_types.get(field_name)
            if not FieldType:
                # Element not in rule_elements config - skip
                continue

            # Get target element name from config
            target_element = field_mapping.get("target_element", field_name)

            # Determine construction pattern based on CONFIG, not field name
            attributes_config = field_mapping.get("attributes", {})
            structure = field_mapping.get("structure")
            is_multiple = field_mapping.get("multiple", False)

            # For nested structures, handle specially (don't use _build_field_value)
            if structure == "nested":
                # Build nested structure from config
                children_config = field_mapping.get("children", [])
                if children_config:
                    child_config = children_config[0]
                    child_source = child_config.get("source_field")
                    child_transform = child_config.get("transform", "none")
                    child_element_name = child_config.get("element")

                    # Get source value
                    if child_source:
                        child_value = getattr(rec, child_source, None)
                        if child_value:
                            # Apply transform
                            transformed = TransformRegistry.apply(child_transform, child_value)

                            # Get child type dynamically
                            child_type_name = self._element_name_to_type_name(child_element_name)
                            ChildType = self.get_xccdf_class(child_type_name)

                            # Construct child element (DRY helper)
                            child_instance = self._construct_typed_element(ChildType, transformed)

                            # Get parent attributes
                            system_val = VariableSubstituter.substitute(
                                attributes_config.get("system", ""), template_values
                            )

                            # Construct nested structure
                            child_field_name = child_element_name.replace("-", "_")

                            # Check if child is single or list (check_content is single)
                            rule_fields[target_element] = [
                                FieldType(
                                    **{
                                        "system": system_val,
                                        child_field_name: child_instance,  # Single, not list
                                    }
                                )
                            ]
                continue

            # For dublin_core structures (NIST references), handle specially
            if structure == "dublin_core":
                # Build NIST references with Dublin Core elements
                source_field = field_mapping.get("source_field")
                source_logic = field_mapping.get("source_logic")
                if source_field:
                    nist_controls: list[str] | None
                    if source_logic == "nist_after_cci_deduplication":
                        # Only the NIST controls no CCI ident on this rule already covers
                        _, nist_controls = self._cci_split(rec, context)
                    elif source_logic is None:
                        nist_controls = getattr(rec, source_field, None)
                    else:
                        raise ValueError(
                            f"field {field_name!r}: unknown source_logic {source_logic!r} "
                            "for a dublin_core reference"
                        )
                    if nist_controls and isinstance(nist_controls, list):
                        dc_elements_config = field_mapping.get("dc_elements", [])
                        href = str(
                            VariableSubstituter.substitute(
                                field_mapping.get("attributes", {}).get("href", ""),
                                template_values,
                            )
                        )
                        # One reference per NIST control
                        rule_fields[target_element] = [
                            FieldType(
                                href=href,
                                content=self.dublin_core_elements(
                                    dc_elements_config, {"nist_control_id": nist_id}
                                ),
                            )
                            for nist_id in nist_controls
                        ]
                continue

            # For ident_from_list structure - generic ident generation (CIS, MITRE, PCI-DSS, etc.)
            if structure == "ident_from_list":
                logger.debug(f"Generating idents from config for {field_name}")
                idents = self.generate_idents_from_config(rec, field_mapping)

                if idents:
                    # Append to existing idents if any
                    existing_idents = rule_fields.get(target_element, [])
                    rule_fields[target_element] = existing_idents + idents
                    logger.debug(
                        ngettext(
                            "Added {count} ident to rule_fields[{target}]",
                            "Added {count} idents to rule_fields[{target}]",
                            len(idents),
                        ).format(count=len(idents), target=target_element)
                    )
                continue

            # Get field value using config
            value = self._build_field_value(field_name, field_mapping, rec, context)

            # Skip only if no value AND no attributes (empty elements with attributes are OK)
            if value is None and not attributes_config:
                continue

            # Pattern 1: Multiple values (like CCIs)
            if is_multiple and isinstance(value, list):
                # Build list of typed elements
                # Check what attributes this type needs
                if attributes_config:
                    # Substitute variables in attributes
                    attr_template = dict(attributes_config.items())
                    # For list items, need to handle per-item
                    if "system" in attr_template:
                        # ident case: system attribute
                        system_val = VariableSubstituter.substitute(
                            attr_template["system"], template_values
                        )
                        rule_fields[target_element] = [
                            FieldType(system=system_val, value=item) for item in value
                        ]
                    else:
                        rule_fields[target_element] = [FieldType(value=item) for item in value]
                else:
                    rule_fields[target_element] = [FieldType(value=item) for item in value]
                continue

            # Pattern 2: Has attributes (like fixtext/@fixref or fix/@id with empty content)
            if attributes_config:
                # Substitute variables in attributes
                attr_values = {
                    k: VariableSubstituter.substitute(v, template_values)
                    for k, v in attributes_config.items()
                }

                # Construct with attributes
                # NOTE: Can't use _construct_typed_element because we need to pass attributes
                # Handle empty elements (like <fix id="..." />) - value can be None or ""
                if hasattr(FieldType, "__dataclass_fields__"):
                    field_def = FieldType.__dataclass_fields__
                    if "content" in field_def:
                        # Use empty list if value is None/empty (for self-closing elements)
                        content_value = [value] if value else []
                        rule_fields[target_element] = [
                            FieldType(content=content_value, **attr_values)
                        ]
                    elif "value" in field_def:
                        # Use empty string if value is None
                        value_to_use = value if value is not None else ""
                        rule_fields[target_element] = [FieldType(value=value_to_use, **attr_values)]
                    else:
                        # Just attributes, no content field (rare)
                        rule_fields[target_element] = [FieldType(**attr_values)]
                continue

            # Pattern 3: Simple field (default)
            if value:
                # Construct element (DRY helper)
                elem_instance = self._construct_typed_element(FieldType, value)

                if elem_instance:
                    # Use schema introspection to determine list vs single (DRY helper)
                    Rule = self.get_xccdf_class("Rule")
                    is_list = self._is_list_field(Rule, target_element)

                    rule_fields[target_element] = [elem_instance] if is_list else elem_instance

        # Construct Rule dynamically from config
        return Rule(**rule_fields)

    def map_group(self, rec: Recommendation, rule, context: dict):
        """Map Recommendation + Rule to Group using config (LOOP-DRIVEN).

        Groups are DISA wrappers - one Group per Rule (STIG convention).

        Args:
            rec: Source Recommendation (for Group title/description)
            rule: Already-constructed Rule to wrap
            context: Mapping context

        Returns:
            xsdata Group object with Rule inside
        """
        Group = self.get_xccdf_class("Group")

        context.update({**self.ref_values(rec.ref), "rec": rec})
        group_id = self.group_id_for_ref(rec.ref)

        # Build Group fields from config
        group_fields = {
            "id": group_id,
            "rule": [rule],  # Wrap the Rule
        }

        # Loop through group_elements config
        for element_name, element_config in self.config.group_elements.items():
            # Get type
            ElementType = self.group_element_types.get(element_name)
            if not ElementType:
                continue

            # Get source value
            source = element_config.get("source")
            if source:
                # Source from rec - use getattr for all fields including 'ref'
                value = getattr(rec, source, None)
            else:
                # Static content (like GroupDescription)
                value = element_config.get("content", "<GroupDescription></GroupDescription>")

            # Apply transform if specified
            transform = element_config.get("transform", "none")
            if transform != "none" and value:
                value = TransformRegistry.apply(transform, value)

            # Construct element (DRY helper)
            if value:
                elem_instance = self._construct_typed_element(ElementType, value)
                if elem_instance:
                    # Groups: all elements are lists
                    group_fields[element_name] = [elem_instance]

        return Group(**group_fields)

    def map_benchmark(self, benchmark: Benchmark, groups: list, context: dict):
        """Map Benchmark and Groups to XCCDF Benchmark using config (LOOP-DRIVEN).

        Args:
            benchmark: Source Benchmark (Pydantic model)
            groups: List of Group objects (already constructed)
            context: Mapping context

        Returns:
            xsdata Benchmark object
        """
        XCCDFBenchmark = self.get_xccdf_class("Benchmark")
        Status = self.get_xccdf_class("Status")

        # Generate Benchmark ID from the style's template. Substitution values
        # that come from free text are reduced to NCName-safe segments so the
        # result satisfies XCCDF's benchmarkIdType whatever the title or
        # version contains.
        bench_id_template = self.config.benchmark.get("id_template")
        if not bench_id_template:
            raise ExportError(
                f"Style '{self.config.metadata.get('style_name', '?')}' has no "
                "benchmark.id_template; every style must name its Benchmark"
            )
        bench_id = VariableSubstituter.substitute(
            bench_id_template,
            {
                "benchmark_id": benchmark.benchmark_id,
                "version": ncname_slug(benchmark.version),
                "title_slug": ncname_slug(benchmark.title),
            },
        )

        # Start with required fields
        benchmark_fields = {
            "id": bench_id,
            "status": [Status(value="draft")],
            "group": groups,  # Add all Groups
        }

        # Loop through benchmark config elements
        for element_name, element_config in self.config.benchmark.items():
            if not isinstance(element_config, dict):
                continue

            # Skip special elements (handled by dedicated methods)
            if element_name in ["id_template", "namespaces"]:
                continue

            # Get xsdata type
            type_name = element_config.get("xccdf_type")
            if not type_name:
                # Special elements (notice, front_matter, etc.) handled below
                continue

            ElementType = self.benchmark_element_types.get(element_name)
            if not ElementType:
                ElementType = self.get_xccdf_class(type_name)

            # Get source value
            source = element_config.get("source")
            if source:
                value = getattr(benchmark, source, None)

                # Apply transform
                transform = element_config.get("transform", "none")
                transformed = TransformRegistry.apply(transform, value)

                # Apply prepend text if specified
                prepend = element_config.get("prepend_text")
                if prepend and transformed:
                    transformed = prepend + transformed

                # Construct element (DRY helper)
                if transformed:
                    elem_instance = self._construct_typed_element(ElementType, transformed)

                    if elem_instance:
                        # Use schema introspection (DRY helper)
                        XCCDFBenchmark = self.get_xccdf_class("Benchmark")
                        is_list = self._is_list_field(XCCDFBenchmark, element_name)

                        benchmark_fields[element_name] = (
                            [elem_instance] if is_list else elem_instance
                        )

        # Add DISA-required elements (using existing config-driven methods)
        benchmark_fields["notice"] = [self.create_notice(benchmark)]
        benchmark_fields["front_matter"] = [self.create_front_matter(benchmark)]
        benchmark_fields["rear_matter"] = [self.create_rear_matter(benchmark)]
        benchmark_fields["plain_text"] = self.create_plain_texts(benchmark)

        # Reference: its Dublin Core elements are xsdata content, as every Rule reference's
        ref_href, ref_content = self.create_reference(benchmark)
        ReferenceType = self.get_xccdf_class("ReferenceType")
        benchmark_fields["reference"] = [ReferenceType(href=ref_href, content=ref_content)]

        # Generate Profile elements if configured
        profile_config = self.config.benchmark.get("profiles")
        if profile_config:
            # Need to pass all recommendations to build profile select lists
            # Get recommendations from context (passed by exporter)
            recommendations = context.get("recommendations", [])
            if recommendations:
                profiles = self.generate_profiles_from_rules(
                    recommendations, profile_config, benchmark.profile_definitions
                )
                if profiles:
                    benchmark_fields["profile"] = profiles
                    logger.debug(
                        ngettext(
                            "Added {count} Profile element to benchmark",
                            "Added {count} Profile elements to benchmark",
                            len(profiles),
                        ).format(count=len(profiles))
                    )

        return XCCDFBenchmark(**benchmark_fields)

    def generate_idents_from_config(
        self, recommendation: "Recommendation", field_mapping: dict
    ) -> list:
        """Generic ident generation from YAML config - works for ANY organization.

        Generates <ident> elements for any compliance framework (CIS, MITRE, PCI-DSS, etc.)
        based on YAML configuration. Completely data-driven - no hard-coding.

        Config structure:
            source_field: "cis_controls"  # or "mitre_mapping.techniques", etc.
            transform: "lines"  # optional: a text field read as one item per line
            ident_spec:
                system_template: "https://org.com/framework/v{item.version}"
                value_template: "{item.id}"  # or just "{item}" for strings
                attributes:  # Optional custom namespace attributes
                  - name: "controlURI"
                    template: "https://..."
                    namespace_prefix: "cc{item.version}"

        Args:
            recommendation: Source recommendation data
            field_mapping: YAML field mapping config with ident_spec

        Returns:
            List of xsdata IdentType objects

        Examples:
            CIS Controls:
                system="https://www.cisecurity.org/controls/v8"
                value="8:3.14"

            MITRE ATT&CK:
                system="https://attack.mitre.org/techniques"
                value="T1565"

            PCI-DSS (future):
                system="https://www.pcisecuritystandards.org/pci_dss/v4.0"
                value="1.2.1"
        """
        IdentType = self.get_xccdf_class("IdentType")

        source_field = field_mapping.get("source_field")
        ident_spec = field_mapping.get("ident_spec", {})

        if not source_field or not ident_spec:
            logger.warning("ident_from_list missing source_field or ident_spec")
            return []

        # Get source data (supports nested paths like "mitre_mapping.techniques"); a
        # transform turns a text field into the list to read (lines: one ident per line)
        source_data = TransformRegistry.apply(
            field_mapping.get("transform", "none"),
            self._get_nested_field(recommendation, source_field),
        )
        if not source_data:
            return []

        # Handle both list and single value
        items = source_data if isinstance(source_data, list) else [source_data]

        idents = []
        system_template = ident_spec.get("system_template", "")
        value_template = ident_spec.get("value_template", "{item}")
        custom_attrs = ident_spec.get("attributes", [])
        # Checked before any prefix is resolved: declaring the attributes' namespaces would
        # not help a version whose ident takes no attributes from other namespaces.
        if custom_attrs and "other_attributes" not in {f.name for f in fields(IdentType)}:
            names = sorted(str(attr.get("name")) for attr in custom_attrs)
            raise ValueError(
                f"ident attributes {names} need an XCCDF version whose "
                "ident allows attributes from other namespaces"
            )

        for item in items:
            # Build context for template substitution
            # Supports both objects (item.version, item.control) and primitives (item)
            context = {"item": item}

            # Substitute templates using existing VariableSubstituter
            system = VariableSubstituter.substitute(system_template, context)
            value = VariableSubstituter.substitute(value_template, context)

            # Namespaced attributes (e.g. cc8:controlURI) go in IdentType's wildcard
            # attribute field, keyed by qualified name, so xsdata writes them.
            other_attributes: dict[str, str] = {}
            for attr_config in custom_attrs:
                attr_name = attr_config.get("name")
                if not attr_name:
                    raise ValueError(f"an ident attribute needs a name: {attr_config!r}")
                attr_value = VariableSubstituter.substitute(
                    attr_config.get("template", ""), context
                )
                prefix = VariableSubstituter.substitute(
                    attr_config.get("namespace_prefix", ""), context
                )
                other_attributes[f"{{{self._namespace_uri(prefix)}}}{attr_name}"] = str(attr_value)

            if other_attributes:
                idents.append(
                    IdentType(system=system, value=value, other_attributes=other_attributes)
                )
            else:
                idents.append(IdentType(system=system, value=value))

        logger.debug(
            ngettext(
                "Generated {count} ident from {field} (system={system})",
                "Generated {count} idents from {field} (system={system})",
                len(idents),
            ).format(count=len(idents), field=source_field, system=system_template)
        )
        return idents

    def _namespace_uri(self, prefix: str) -> str:
        """The namespace URI the style's config declares for a prefix (namespaces section).

        Raises:
            ValueError: The prefix is not declared, so the attribute could not be written
                in a namespace a reader would recognise.
        """
        declared = self.config.namespaces
        if prefix not in declared:
            raise ValueError(
                f"namespace prefix {prefix!r} is not declared in the style's namespaces"
            )
        return str(declared[prefix])

    def _get_nested_field(self, obj: Any, field_path: str) -> Any:
        """Get nested field from object using dot notation.

        Supports paths like:
        - "cis_controls" -> obj.cis_controls
        - "mitre_mapping.techniques" -> obj.mitre_mapping.techniques

        Args:
            obj: Source object (Recommendation, Benchmark, etc.)
            field_path: Dot-separated path to field

        Returns:
            Field value or None if not found
        """
        parts = field_path.split(".")
        value = obj

        for part in parts:
            if value is None:
                return None
            value = getattr(value, part, None)

        return value

    def generate_profiles_from_rules(
        self,
        recommendations: list["Recommendation"],
        profile_config: dict,
        profile_definitions: list[ProfileDefinition] | None = None,
    ) -> list:
        """XCCDF Profile elements at Benchmark level, each with a select for every rule in it.

        With the benchmark page's profile definitions, one Profile per definition: its
        title and description (through description_transform) from the page, its rules
        those naming it or an ancestor (parent); a definition with no such rule is left out
        with a warning. Without them (a copy saved before they were read), one Profile per
        profile name the rules use; a mapping for that name gives the title, description
        and the profiles it includes.

        Config structure:
            generate_from_rules: true
            id_template: "{profile.title|slug:-}"   # every Profile id
            description_transform: "none"                # for the page's descriptions
            profile_mappings:
              - match: "Level 2 - Server"                 # a profile name on the rules
                title: "Level 2 - Server"
                description: "CIS Level 2 for server environments"
                includes: ["Level 1 - Server"]

        Raises:
            ValueError: No id_template, a mapping without a match or with its own id, two
                mappings for one name, an include or parent that names no profile, profiles
                that include each other, or two profiles that get one id.
        """
        Profile = self.get_xccdf_class("Profile")
        ProfileSelectType = self.get_xccdf_class("ProfileSelectType")
        TextWithSubType = self.get_xccdf_class("TextWithSubType")
        HtmlTextWithSubType = self.get_xccdf_class("HtmlTextWithSubType")

        if not profile_config.get("generate_from_rules"):
            return []

        mappings = profile_config.get("profile_mappings", [])
        id_template = profile_config.get("id_template")
        if not id_template:
            raise ValueError("benchmark.profiles needs an id_template (a Profile id per title)")
        by_match: dict[str, dict] = {}
        for mapping in mappings:
            name = mapping.get("match")
            if not isinstance(name, str) or not name:
                raise ValueError(f"a profile mapping needs a match: {mapping!r}")
            if "id" in mapping:
                raise ValueError(
                    f"profile mapping {name!r} sets an id; profile ids come from "
                    "benchmark.profiles.id_template"
                )
            if name in by_match:
                raise ValueError(f"profile {name!r} has more than one profile mapping")
            by_match[name] = mapping

        entries = (
            self._defined_profiles(profile_definitions, profile_config)
            if profile_definitions
            else self._profiles_named_on_rules(recommendations, mappings, by_match)
        )

        profiles = []
        titles_by_id: dict[str, str] = {}
        for title, description, names in entries:
            profile_id = VariableSubstituter.substitute(id_template, {"profile": {"title": title}})
            if profile_id in titles_by_id:
                raise ValueError(
                    f"profiles {titles_by_id[profile_id]!r} and {title!r} both get the id "
                    f"{profile_id!r} from benchmark.profiles.id_template"
                )
            titles_by_id[profile_id] = title

            # Every rule in this profile or in a profile it includes
            select_list = []
            for rec in recommendations:
                if names.intersection(rec.profiles):
                    select_list.append(
                        ProfileSelectType(idref=self.rule_id_for_ref(rec.ref), selected=True)
                    )

            if not select_list:
                # Only a page definition can get here: a name on the rules selects its rules.
                logger.warning(
                    f"Profile {title!r} is defined for this benchmark but no recommendation "
                    "is in it or in a profile it extends; it is left out of the export"
                )
                continue

            # Create Profile element (use _construct_typed_element helper for DRY)
            title_elem = self._construct_typed_element(TextWithSubType, title)
            desc_elem = (
                self._construct_typed_element(HtmlTextWithSubType, description)
                if description
                else None
            )

            profiles.append(
                Profile(
                    id=profile_id,
                    title=[title_elem] if title_elem else [],
                    description=[desc_elem] if desc_elem else [],
                    select=select_list,
                )
            )
            logger.debug(
                ngettext(
                    "Generated profile '{profile}' with {count} rule",
                    "Generated profile '{profile}' with {count} rules",
                    len(select_list),
                ).format(count=len(select_list), profile=profile_id)
            )

        logger.debug(
            ngettext(
                "Generated {count} Profile element",
                "Generated {count} Profile elements",
                len(profiles),
            ).format(count=len(profiles))
        )
        return profiles

    def _defined_profiles(
        self, definitions: list[ProfileDefinition], profile_config: dict
    ) -> list[tuple[str, str | None, set[str]]]:
        """(title, description, profile names it selects) for each profile the benchmark's
        page defines; a profile selects its own name and every ancestor's, by parent. The
        description goes through the style's description_transform.

        Raises:
            ValueError: A parent is not one of the benchmark's profiles, or parents loop.
        """
        by_title = {definition.title: definition for definition in definitions}
        for definition in definitions:
            if definition.parent and definition.parent not in by_title:
                raise ValueError(
                    f"profile {definition.title!r} extends {definition.parent!r}, which is not "
                    "one of the benchmark's profiles"
                )
        transform = TransformRegistry.get(profile_config.get("description_transform", "none"))

        def parents(title: str) -> list[str]:
            parent = by_title[title].parent
            return [parent] if parent else []

        return [
            (
                definition.title,
                (transform(definition.description) or None) if definition.description else None,
                self._included_profiles(definition.title, parents),
            )
            for definition in definitions
        ]

    def _profiles_named_on_rules(
        self,
        recommendations: list["Recommendation"],
        mappings: list[dict],
        by_match: dict[str, dict],
    ) -> list[tuple[str, str | None, set[str]]]:
        """(title, description, profile names it selects) for a copy saved without the
        page's definitions: one entry per profile name its rules use, mapped names in the
        style's order, then the others in the order rules first use them. A mapping sets
        its title, description and the profiles it includes. Every mapping is checked,
        whether or not these rules use it.

        Raises:
            ValueError: An include names no profile mapping, or mappings include each other.
        """

        def includes(name: str) -> list[str]:
            if name not in by_match:
                return []
            listed = by_match[name].get("includes", [])
            for included in listed:
                if included not in by_match:
                    raise ValueError(
                        f"profile {name!r} includes {included!r}, which no profile mapping matches"
                    )
            return list(listed)

        named = dict.fromkeys(name for rec in recommendations for name in rec.profiles)
        entries = []
        for mapping in mappings:
            included = self._included_profiles(mapping["match"], includes)
            if mapping["match"] in named:
                entries.append(
                    (
                        mapping.get("title") or mapping["match"],
                        mapping.get("description") or None,
                        included,
                    )
                )
        entries.extend((name, None, {name}) for name in named if name not in by_match)
        return entries

    @staticmethod
    def _included_profiles(name: str, parents: Callable[[str], list[str]]) -> set[str]:
        """name and every profile it includes, directly or through another.

        Raises:
            ValueError: Profiles include each other.
        """
        names: set[str] = set()

        def visit(current: str, path: list[str]) -> None:
            if current in path:
                raise ValueError(f"profiles {path + [current]} include each other")
            names.add(current)
            for parent in parents(current):
                visit(parent, path + [current])

        visit(name, [])
        return names

    # The metadata_spec keys a removed setting used, and where it went.
    _REMOVED_METADATA_KEYS: Final[dict[str, str]] = {
        "requires_post_processing": "the Rule holds the metadata as model content; nothing "
        "is added after serialization",
        "metadata_spec.namespace": "the namespace comes from benchmark.namespaces by "
        "metadata_spec.namespace_prefix",
    }

    def _refuse_unwritable_metadata_mappings(self) -> None:
        """Refuse a metadata_from_config mapping that could not be written as XCCDF allows.

        XCCDF metadata holds only elements from another namespace than XCCDF's own
        (metadataType: xsd:any namespace="##other"), and only some XCCDF versions give a
        Rule a metadata element. Both are known from the style and the XCCDF models alone,
        so they are checked before any benchmark is exported.

        Raises:
            ValueError: A removed key is set; the XCCDF version's Rule has no element for the
                mapping's target; the mapping has no source_field; its namespace prefix is
                missing, undeclared or the XCCDF namespace; it has no group_by; or an element
                or attribute name is no XML name without a prefix.
        """
        # Mapping name -> (Rule field, the model type that holds the metadata content there,
        # that type's wildcard field)
        self._metadata_holders: dict[str, tuple[str, type, str]] = {}
        for name, mapping in self.config.field_mappings.items():
            if not isinstance(mapping, dict):
                continue
            where = f"field_mappings.{name}"
            if "requires_post_processing" in mapping:
                raise ValueError(
                    f"{where}.requires_post_processing is no longer read "
                    f"({self._REMOVED_METADATA_KEYS['requires_post_processing']})"
                )
            if mapping.get("structure") != "metadata_from_config":
                continue
            target = mapping.get("target_element", name)
            element = self.rule_element(target)
            if element is None:
                raise ValueError(
                    f"{where}: XCCDF {self.xccdf_version} Rules have no {target!r} element, so "
                    f"this metadata mapping cannot be written"
                )
            if not mapping.get("source_field"):
                raise ValueError(f"{where}: a metadata mapping needs a source_field")
            spec = mapping.get("metadata_spec") or {}
            where = f"{where}.metadata_spec"
            if "namespace" in spec:
                raise ValueError(
                    f"{where}.namespace is no longer read "
                    f"({self._REMOVED_METADATA_KEYS['metadata_spec.namespace']})"
                )
            prefix = spec.get("namespace_prefix")
            if not prefix:
                raise ValueError(f"{where}: a metadata mapping needs a namespace_prefix")
            try:
                namespace = self._namespace_uri(prefix)
            except ValueError as error:
                raise ValueError(f"{where}: {error}") from error
            if namespace == self.xccdf_namespace:
                raise ValueError(
                    f"{where}: namespace_prefix {prefix!r} is the XCCDF namespace; XCCDF "
                    "metadata holds only elements from another namespace"
                )
            if not spec.get("group_by"):
                raise ValueError(
                    f"{where}: a metadata mapping needs group_by (the builder writes items "
                    "only inside group elements)"
                )
            self._refuse_unknown_group_field(where, mapping["source_field"], spec["group_by"])
            # The content goes in the element-only wildcard of the target's type (text types
            # have a mixed one), which must take elements of the mapping's namespace; the
            # Rule must be able to repeat the target, one per mapping.
            holder = element.types[0] if len(element.types) == 1 else None
            wildcards = (
                [
                    var.name
                    for var in self._xml_context.build(holder).get_all_vars()
                    if var.is_wildcard
                    and not var.mixed
                    and var.match_namespace(f"{{{namespace}}}{spec.get('root_element')}")
                ]
                if holder is not None and is_dataclass(holder) and element.list_element
                else []
            )
            if holder is None or len(wildcards) != 1:
                raise ValueError(
                    f"field_mappings.{name}: the Rule's {target!r} element cannot hold "
                    f"repeated elements of the namespace {namespace}; metadata content goes "
                    "in metadata"
                )
            self._metadata_holders[name] = (target, holder, wildcards[0])
            group = spec.get("group_element") or {}
            self._refuse_invalid_metadata_names(
                where,
                [
                    ("root_element", spec.get("root_element"), {}),
                    ("group_element", group.get("element"), group.get("attributes") or {}),
                ],
            )
            self._refuse_invalid_metadata_element(
                f"{where}.group_element.item_element", group.get("item_element") or {}
            )

    @staticmethod
    def _refuse_unknown_group_field(where: str, source_field: str, group_by: str) -> None:
        """group_by names a field of the items source_field lists; a name that is no field
        would read as empty for every item and leave the metadata without groups."""
        current: Any = Recommendation
        *parents, last = source_field.split(".")
        for part in parents:
            current = _model_in(current.model_fields[part].annotation)
        annotation = current.model_fields[last].annotation
        while get_origin(annotation) is Annotated or get_origin(annotation) in (UnionType, Union):
            annotation = next(a for a in get_args(annotation) if a is not type(None))
        item = _model_in(get_args(annotation)[0]) if get_origin(annotation) is list else None
        for part in group_by.removeprefix("item.").split("."):
            if item is None or part not in item.model_fields:
                raise ValueError(
                    f"{where}.group_by names {group_by!r}: {part!r} is not a field of the "
                    f"items {source_field!r} lists"
                )
            item = _model_in(item.model_fields[part].annotation)

    def _refuse_invalid_metadata_element(self, where: str, spec: dict) -> None:
        """Check an item or child element spec and its children, recursively."""
        self._refuse_invalid_metadata_names(
            where, [("element", spec.get("element"), spec.get("attributes") or {})]
        )
        for i, child in enumerate(spec.get("children") or []):
            self._refuse_invalid_metadata_element(f"{where}.children[{i}]", child or {})

    @staticmethod
    def _refuse_invalid_metadata_names(
        where: str, elements: list[tuple[str, Any, dict[str, Any]]]
    ) -> None:
        """Each element name and attribute name must be an XML name without a prefix: the
        element takes the mapping's namespace, and an attribute has none."""
        for key, element, attributes in elements:
            for kind, name in [(key, element)] + [
                (f"{key} attribute", attribute) for attribute in attributes
            ]:
                try:
                    if not isinstance(name, str) or name.startswith("{") or name == "xmlns":
                        raise ValueError("an XML name without a prefix or namespace is needed")
                    etree.QName(None, name)
                except ValueError as error:
                    raise ValueError(
                        f"{where}: {kind} {name!r} is not an XML name ({error})"
                    ) from error

    def generate_metadata_from_config(
        self, recommendation: "Recommendation", field_mapping: dict
    ) -> AnyElement | None:
        """Build a metadata root element from a metadata_from_config mapping.

        Items of the source list are grouped by metadata_spec.group_by; groups are written
        in key order and each group's items in source order. Every element is in the
        namespace benchmark.namespaces declares for metadata_spec.namespace_prefix (the
        style was checked when it loaded).

        Args:
            recommendation: Source recommendation data
            field_mapping: YAML field mapping with metadata_spec

        Returns:
            The root element, an empty root when the source list is empty and allow_empty is
            set, or None.

        Raises:
            ValueError: An attribute value would be rewritten by the XML serializer.
        """
        spec = field_mapping["metadata_spec"]
        namespace = self._namespace_uri(spec["namespace_prefix"])

        def qname(name: str) -> str:
            return f"{{{namespace}}}{name}"

        source_data = self._get_nested_field(recommendation, field_mapping["source_field"])
        group_by = spec["group_by"].removeprefix("item.")
        groups: dict[Any, list[Any]] = {}
        for item in source_data or []:
            group_key = self._get_nested_field(item, group_by)
            if group_key:
                groups.setdefault(group_key, []).append(item)
        if not groups:
            # No data, or no item in any group: the same case, decided by allow_empty
            return (
                AnyElement(qname=qname(spec["root_element"])) if spec.get("allow_empty") else None
            )

        group_spec = spec["group_element"]
        return AnyElement(
            qname=qname(spec["root_element"]),
            children=[
                AnyElement(
                    qname=qname(group_spec["element"]),
                    attributes=self._metadata_attributes(
                        group_spec.get("attributes") or {}, {"group_key": group_key}
                    ),
                    children=[
                        self._build_config_element(item, group_spec["item_element"], qname)
                        for item in items
                    ],
                )
                for group_key, items in sorted(groups.items())
            ],
        )

    def _build_config_element(
        self, item: Any, spec: dict, qname: Callable[[str], str]
    ) -> AnyElement:
        """An item element, or one of its children, with its own children, from config."""
        content = spec.get("content")
        text = None
        if content:
            value = VariableSubstituter.substitute(content, {"item": item})
            text = None if value is None else str(value)
        return AnyElement(
            qname=qname(spec["element"]),
            text=text,
            attributes=self._metadata_attributes(spec.get("attributes") or {}, {"item": item}),
            children=[
                self._build_config_element(item, child, qname)
                for child in spec.get("children") or []
            ],
        )

    @staticmethod
    def _metadata_attributes(templates: dict[str, Any], context: dict[str, Any]) -> dict[str, str]:
        """Attribute values as text: booleans lowercase (XML Schema boolean), anything else
        as str().

        Raises:
            ValueError: A value the XML serializer would write as a type name (it starts with
                "{" and names an XML Schema type) instead of as the text given.
        """
        attributes: dict[str, str] = {}
        for name, template in templates.items():
            value = VariableSubstituter.substitute(template, context)
            if isinstance(value, bool) or (isinstance(value, str) and value in ("True", "False")):
                text = str(value).lower()
            else:
                text = str(value)
            if EventHandler.is_xsi_type(name, text):
                raise ValueError(
                    f"metadata attribute {name!r} has the value {text!r}, which the XML "
                    "serializer would write as an XML Schema type name, not as this text"
                )
            attributes[name] = text
        return attributes
