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
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, fields
from gettext import ngettext
from pathlib import Path
from types import ModuleType
from typing import Any, assert_never

import yaml
from lxml import etree
from xsdata.formats.dataclass.models.elements import XmlVar
from xsdata.formats.dataclass.models.generics import AnyElement
from xsdata.formats.dataclass.serializers.mixins import EventHandler

from cis_bench.exceptions import ExportError
from cis_bench.exporters.style_config import (
    CompositeMapping,
    DublinCoreElement,
    DublinCoreMapping,
    EmbeddedTag,
    EmbeddedXmlTagsMapping,
    IdentFromListMapping,
    MetadataElement,
    MetadataFromConfigMapping,
    NestedMapping,
    SimpleMapping,
    StyleConfig,
    StyleModels,
    check_mergeable,
    extended_style,
    file_name,
    validate_style,
)
from cis_bench.models.benchmark import (
    Benchmark,
    CISControl,
    ProfileDefinition,
    Recommendation,
)

# Import XCCDF types for element creation (XCCDF 1.2 - for type hints only)
# Note: Engine dynamically loads version-specific types based on config
from cis_bench.utils.cci_lookup import CCILookupService, cci_service_for
from cis_bench.utils.xml_utils import ncname_slug

# Set up logger
logger = logging.getLogger(__name__)


@dataclass
class MappingConfig:
    """Loaded mapping configuration: one field per top-level section of a style's YAML, and
    the merged style's model (style).

    ConfigLoader fills and inherits (extends) every section field the same way, so a section
    added here is loaded and inherited without further code.
    """

    metadata: dict[str, Any] = field(default_factory=dict)
    benchmark: dict[str, Any] = field(default_factory=dict)
    rule_defaults: dict[str, Any] = field(default_factory=dict)
    rule_id: dict[str, str] = field(default_factory=dict)
    group_id: dict[str, str] = field(default_factory=dict)  # Group ID template configuration
    field_mappings: dict[str, Any] = field(default_factory=dict)
    cci_deduplication: dict[str, Any] = field(default_factory=dict)
    # What each Group element is filled from (its type comes from the XCCDF model)
    group_elements: dict[str, Any] = field(default_factory=dict)
    # How the serialized XML is finished (remove_override_attr)
    post_processing: dict[str, Any] = field(default_factory=dict)
    # The whole style as the schema built it when it loaded (no section of the YAML)
    style: StyleConfig = field(default_factory=StyleConfig)

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
    """Loads mapping configuration from YAML with inheritance support: after each file of the
    extends chain is merged, root first, the style built so far is checked against the style
    schema (style_config.StyleConfig)."""

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
    def _chain(config_path: Path, loading_stack: list[Path]) -> list[tuple[Path, dict[str, Any]]]:
        """The files of a style's extends chain as written, root first. Only extends is read
        to find a file's parent; nothing else is checked here.

        Raises:
            ValueError: Circular inheritance, an extends that names a folder, a file that is
                not YAML, or a file that is not a mapping of sections
            FileNotFoundError: A file of the chain does not exist
        """
        if config_path in loading_stack:
            cycle = " -> ".join(str(p) for p in loading_stack)
            raise ValueError(f"Circular inheritance detected: {cycle} -> {config_path}")
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        if not config_path.is_file():
            named_by = f"{loading_stack[-1].name}: extends names " if loading_stack else ""
            raise ValueError(f"{named_by}{config_path}, which is not a file")
        try:
            with open(config_path) as f:
                config_data = yaml.safe_load(f) or {}
        except yaml.YAMLError as error:
            # compose-go's loader does the same: "failed to parse <file>: <error>"
            raise ValueError(f"{config_path.name}: not valid YAML: {error}") from error
        if not isinstance(config_data, dict):
            raise ValueError(f"{config_path.name}: a style is a mapping of sections")
        earlier: list[tuple[Path, dict[str, Any]]] = []
        extends = extended_style(config_data)
        if extends is not None:
            extends_path = Path(extends)
            # Resolve relative to current file's directory
            if not extends_path.is_absolute():
                extends_path = config_path.parent / extends_path
            earlier = ConfigLoader._chain(extends_path, [*loading_stack, config_path])
        return [*earlier, (config_path, config_data)]

    @staticmethod
    def _resolve_relative_paths(config_path: Path, config_data: dict[str, Any]) -> None:
        """Make a relative CCI mapping file a field mapping names (cci_lookup.mapping_file)
        relative to the folder of the style file that writes it, before the file is merged,
        as extends is; compose-go resolves relative paths per file the same way. A value
        that is no file name is left for validation to report. The file is still YAML as
        written (the schema checks it after the merge), so its shape is matched here."""
        match config_data:
            case {"field_mappings": dict(mappings)}:
                pass
            case _:
                return
        for mapping in mappings.values():
            match mapping:
                case {"cci_lookup": {"mapping_file": written} as lookup}:
                    name = file_name(written)
                    if name is not None and not Path(name).is_absolute():
                        lookup["mapping_file"] = str((config_path.parent / name).resolve())

    @staticmethod
    def _models_of(config_data: dict[str, Any]) -> StyleModels | None:
        """The models of the XCCDF version a style names (1.2 when it names none), for the
        checks that need them; None for a version with no models, which MappingEngine
        refuses when it starts."""
        metadata = config_data.get("metadata")
        version = metadata.get("xccdf_version", "1.2") if isinstance(metadata, dict) else "1.2"
        try:
            return style_models(str(version))
        except ValueError:
            return None

    @staticmethod
    def load(config_path: Path) -> MappingConfig:
        """Load mapping configuration from YAML file with inheritance support.

        Config files can specify 'extends: base_style.yaml' to inherit from another file.
        Child configs override parent configs. Deep merge is used for nested dictionaries.
        The chain is loaded root first, the order compose-go loads compose files in: each
        file is checked alone only for a safe merge (check_mergeable), merged onto the style
        built so far, and that style is checked against the style schema, its mistakes
        reported with the file just merged. Loading stops at the first file with mistakes,
        so every file a style extends is a whole style itself.

        Args:
            config_path: Path to the configuration file

        Returns:
            MappingConfig with merged configuration, and the merged style's model (style)

        Raises:
            ValueError: Circular inheritance, or a style the schema refuses
            FileNotFoundError: If config file not found
        """
        config_data: dict[str, Any] = {}
        style = StyleConfig()
        for path, written in ConfigLoader._chain(config_path, []):
            name = path.name
            check_mergeable(name, written)
            ConfigLoader._resolve_relative_paths(path, written)
            extends = {"extends": written["extends"]} if "extends" in written else {}
            config_data = ConfigLoader._deep_merge(
                config_data, {key: value for key, value in written.items() if key != "extends"}
            )
            style = validate_style(
                name, {**config_data, **extends}, ConfigLoader._models_of(config_data)
            )
            logger.debug(f"Loaded {name}")
        return MappingConfig(
            **{
                section.name: config_data[section.name]
                for section in fields(MappingConfig)
                if section.name in config_data
            },
            style=style,
        )


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
        path = VariableSubstituter._path(expression)
        pipe, filter_spec = expression.partition("|")[1:]
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
            name = VariableSubstituter._filter_name(expression)
            raw_args = filter_spec.partition(":")[2]
            args = [arg.strip() for arg in raw_args.split(",")] if raw_args.strip() else []
            transform = TransformRegistry.get(name)
            try:
                inspect.signature(transform).bind(value, *args)
            except TypeError:
                raise ValueError(f"{name} does not take the arguments {args}") from None
            value = transform(value, *args)
        return value

    @staticmethod
    def _path(expression: str) -> str:
        """The dotted path a {path|filter} expression reads ("item.control")."""
        return expression.partition("|")[0].strip()

    @staticmethod
    def variables(template: str) -> list[str]:
        """The dotted paths a template's variables read, in order: what a style is checked
        for when it loads. Text the parser refuses has none here; it is refused where it is
        filled."""
        try:
            pieces = VariableSubstituter._pieces(template)
        except ValueError:
            return []
        return [
            VariableSubstituter._path(expression)
            for _, expression in pieces
            if expression is not None
        ]

    @staticmethod
    def _filter_name(expression: str) -> str:
        """The transform a {value|name:args} expression's filter names.

        Raises:
            ValueError: The filter names no transform.
        """
        name = expression.partition("|")[2].partition(":")[0].strip()
        if not name:
            raise ValueError(f"filter without a transform name in {{{expression}}}")
        return name

    @staticmethod
    def filters(template: str) -> list[str]:
        """The transforms a template's filters name, in order: what a style is checked for
        when it loads. Text the parser refuses has none here; it is refused where it is
        filled.

        Raises:
            ValueError: A filter names no transform.
        """
        try:
            pieces = VariableSubstituter._pieces(template)
        except ValueError:
            return []
        return [
            VariableSubstituter._filter_name(expression)
            for _, expression in pieces
            if expression is not None and "|" in expression
        ]

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


def xccdf_models(version: str) -> tuple[ModuleType, str]:
    """The generated XCCDF models of a version and the version's namespace.

    Raises:
        ValueError: No models are generated for the version.
    """
    if version == "1.1.4":
        from cis_bench.models.xccdf_v1_1 import xccdf_1_1_4

        return xccdf_1_1_4, "http://checklists.nist.gov/xccdf/1.1"
    if version == "1.2":
        from cis_bench.models.xccdf import xccdf_1_2

        return xccdf_1_2, "http://checklists.nist.gov/xccdf/1.2"
    raise ValueError(f"Unsupported XCCDF version: {version}")


def style_models(version: str) -> StyleModels:
    """The models a style of an XCCDF version is checked against: the version's XCCDF
    models, the benchmark models, and the engine's own transform lookup and template parser.

    Raises:
        ValueError: No models are generated for the version.
    """
    module, namespace = xccdf_models(version)
    return StyleModels(
        xccdf=module,
        xccdf_version=version,
        xccdf_namespace=namespace,
        recommendation=Recommendation,
        benchmark=Benchmark,
        cis_control=CISControl,
        transform=TransformRegistry.get,
        template_filters=VariableSubstituter.filters,
        template_variables=VariableSubstituter.variables,
    )


class MappingEngine:
    """Main engine that applies config-based mappings."""

    def __init__(self, config_path: Path):
        """Initialize mapping engine with config.

        The style is checked against the schema and the models of its XCCDF version when
        ConfigLoader loads it, so what follows reads a style that can be written.

        Args:
            config_path: Path to YAML configuration file

        Raises:
            ValueError: The style is refused, or names an XCCDF version with no models.
        """
        self.config = ConfigLoader.load(config_path)
        self.cci_service = self._cci_service(config_path)
        self.style_models = style_models(self.config.metadata.get("xccdf_version", "1.2"))
        self.xccdf_models: ModuleType = self.style_models.xccdf
        self.xccdf_version = self.style_models.xccdf_version
        self.xccdf_namespace = self.style_models.xccdf_namespace
        # Mapping name -> (Rule field, the type that holds the metadata content there, that
        # type's wildcard field); every metadata mapping has one (checked when it loaded)
        self._metadata_holders: dict[str, tuple[str, type, str]] = {}
        for name, mapping in self.config.style.field_mappings.items():
            if isinstance(mapping, MetadataFromConfigMapping):
                target = mapping.target_element or name
                holder = self.style_models.metadata_holder(target)
                if holder is not None:
                    self._metadata_holders[name] = (target, *holder)

    def get_xccdf_class(self, class_name: str):
        """Get XCCDF class by name (version-agnostic).

        Args:
            class_name: Name of XCCDF class (e.g., 'Benchmark', 'Rule', 'Group')

        Returns:
            Class from appropriate XCCDF module
        """
        return getattr(self.xccdf_models, class_name)

    def model_element(self, parent: str, target: str) -> XmlVar | None:
        """The XCCDF model's description of the element field `target` of Rule, Group or
        Benchmark (its type, whether it repeats), read from the xsdata model of this style's
        XCCDF version; None when the parent has no such element."""
        return self.style_models.element(parent, target)

    def element_type(self, parent: str, target: str) -> type:
        """The type the XCCDF model gives the element field `target` of Rule, Group or
        Benchmark. The schema is the one source of element types; a style declares none.

        Raises:
            ValueError: The parent has no such element in this XCCDF version, or the element
                holds a plain value, not an element type.
        """
        problem = self.style_models.element_problem(parent, target)
        element = self.model_element(parent, target)
        if problem is not None or element is None:
            raise ValueError(problem)
        return element.types[0]

    def _repeats(self, parent: str, target: str) -> bool:
        """Whether the XCCDF model lets `parent` hold more than one `target` element."""
        element = self.model_element(parent, target)
        return element is not None and element.list_element

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

    def create_embedded_xml_tags(self, components: list[EmbeddedTag], rec: Recommendation) -> str:
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
            if component.sources is not None:
                texts: list[tuple[str, str]] = [
                    (text, source.separator)
                    for source in component.sources
                    if (
                        text := TransformRegistry.apply(
                            source.transform, getattr(rec, source.field)
                        )
                    )
                ]
                content = "".join(
                    text + (separator if i < len(texts) - 1 else "")
                    for i, (text, separator) in enumerate(texts)
                )
            else:
                content = component.content
            element = etree.Element(component.tag)
            element.text = content  # "" keeps the <Tag></Tag> form official STIGs write
            parts.append(etree.tostring(element, encoding="unicode"))
        return "".join(parts)

    def _cci_service(self, config_path: Path) -> CCILookupService:
        """The CCI lookup of the mapping file the style's ident mapping names
        (cci_lookup.mapping_file, resolved against the style file that wrote it when the
        style loaded), or of the bundled mapping file when it names none.

        Raises:
            ValueError: The mapping file is no file name, cannot be read, or is not a CCI
                mapping file; the error names the style and the mapping file.
        """
        written = self.config.style.cci_lookup.mapping_file
        if written is None:
            return cci_service_for()
        name = file_name(written)
        if name is None:
            raise ValueError(
                f"{config_path.name}: ident.cci_lookup.mapping_file must name a file, "
                f"not {written!r}"
            )
        try:
            return cci_service_for(Path(name))
        except (OSError, ValueError) as error:
            raise ValueError(
                f"{config_path.name}: ident.cci_lookup.mapping_file {name}: {error}"
            ) from error

    def get_ccis_with_deduplication(self, rec: Recommendation) -> tuple[list[str], list[str]]:
        """Get CCIs and extra NIST controls using deduplication.

        Returns:
            Tuple of (cci_list, extra_nist_list)
        """
        if not self.config.cci_deduplication.get("enabled"):
            # No deduplication - return empty CCIs, all NIST as extras
            return [], rec.nist_controls

        # The ident mapping's lookup: which CCIs of a control to take (extract)
        cci_lookup_config = self.config.style.cci_lookup

        # The CIS controls come from the field the style names. The mapping file is keyed
        # by one CIS Controls version, named in the style (cci_lookup.cis_controls_version);
        # other versions reuse the same numbers for unrelated safeguards, so only that
        # version's controls are looked up.
        source_field = cci_lookup_config.source_field
        if not source_field:
            raise ValueError(
                "ident.cci_lookup needs source_field, the field holding the CIS controls"
            )
        controls_version = cci_lookup_config.cis_controls_version
        cis_control_ids = [
            c.control
            for c in getattr(rec, source_field)
            if controls_version is None or c.version == controls_version
        ]

        # Use CCI service for deduplication
        ccis, extra_nist = self.cci_service.deduplicate_nist_controls(
            cis_control_ids, rec.nist_controls, extract=cci_lookup_config.extract
        )

        # Fallback CCI if no CCIs (even if NIST exists)
        # CRITICAL: DISA STIGs require at least one ident element per rule
        if not ccis:
            fallback_cci = cci_lookup_config.fallback_cci
            if fallback_cci:
                ccis = [fallback_cci]
                logger.debug(f"No CCIs for {rec.ref}, using fallback {fallback_cci}")

        return ccis, extra_nist

    def create_notice(self, benchmark: Benchmark):
        """Create notice element from config (version-agnostic).

        Resolves the notice's id (terms-of-use when the style names none), its language
        (lang, written as xml:lang) and its variable-substituted text from the style's
        benchmark.notice, keeping the content empty when it is left out or blank.
        """
        raw_notice = self.config.benchmark.get("notice")
        notice_config = raw_notice if isinstance(raw_notice, dict) else {}

        NoticeType = self.element_type("Benchmark", "notice")

        substitution_context = {"benchmark": benchmark}

        raw_id = notice_config.get("id") or "terms-of-use"
        notice_id = str(VariableSubstituter.substitute(str(raw_id), substitution_context))

        raw_lang = notice_config.get("lang")
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

        Its type is the one the XCCDF model of the style's version gives the element.
        """
        FrontMatterType = self.element_type("Benchmark", "front_matter")
        return FrontMatterType(content=[])

    def create_rear_matter(self, benchmark: Benchmark):
        """Create rear-matter element from config (version-agnostic).

        Its type is the one the XCCDF model of the style's version gives the element.
        """
        RearMatterType = self.element_type("Benchmark", "rear_matter")
        return RearMatterType(content=[])

    def dublin_core_elements(
        self, dc_elements_config: list[DublinCoreElement], values: dict[str, Any]
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
            prefix, _, local_name = dc.element.partition(":")
            namespace = self.config.namespaces.get(prefix)
            if not namespace:
                raise ValueError(
                    f"dc_elements names {dc.element!r} but benchmark.namespaces declares "
                    f"no {prefix!r} namespace"
                )
            text = str(VariableSubstituter.substitute(dc.content, values))
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
        return href, self.dublin_core_elements(
            self.config.style.benchmark.reference.dc_elements, values
        )

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

    def _build_field_value(
        self,
        field_mapping: SimpleMapping | CompositeMapping | EmbeddedXmlTagsMapping,
        rec: Recommendation,
        context: dict,
    ) -> Any:
        """The value a simple, composite or embedded_xml_tags mapping writes: the text with
        tags of an embedded mapping, the joined text of a composite, the rule's CCIs for a
        simple mapping with source_logic cci_lookup_with_deduplication, or the source field
        after its transform; None when a simple mapping names no source field.
        """
        match field_mapping:
            case EmbeddedXmlTagsMapping():
                return self.create_embedded_xml_tags(field_mapping.components, rec)
            case CompositeMapping():
                return self._composite_text(field_mapping, rec)
            case SimpleMapping(source_logic="cci_lookup_with_deduplication"):
                # A list; the caller writes one ident per CCI
                ccis, _ = self._cci_split(rec, context)
                return ccis
            case SimpleMapping():
                if not field_mapping.source_field:
                    return None
                return TransformRegistry.apply(
                    field_mapping.transform, getattr(rec, field_mapping.source_field, None)
                )
            case _:
                assert_never(field_mapping)

    @staticmethod
    def _composite_text(field_mapping: CompositeMapping, rec: Recommendation) -> str | None:
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
        """
        separator = field_mapping.separator
        parts = []
        for source in field_mapping.sources:
            text = TransformRegistry.apply(source.transform, getattr(rec, source.field))
            if not text:
                continue
            parts.append(f"{source.label}{separator}{text}" if source.label else text)
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

        # One element per field mapping, in the style's order, built the way its structure
        # says; the style was checked against the XCCDF models when it loaded, and a mapping
        # set to null is switched off
        for field_name, mapping in self.config.style.field_mappings.items():
            if mapping is None:
                continue
            target_element = mapping.target_element or field_name
            match mapping:
                case MetadataFromConfigMapping():
                    # Metadata is model content in the type the XCCDF model gives the target
                    # element: one metadata element per mapping, in order
                    metadata_root = self.generate_metadata_from_config(rec, mapping)
                    if metadata_root is not None:
                        target, MetadataHolder, content_field = self._metadata_holders[field_name]
                        rule_fields.setdefault(target, []).append(
                            MetadataHolder(**{content_field: [metadata_root]})
                        )
                case NestedMapping():
                    FieldType = self.element_type("Rule", target_element)
                    nested = self._nested_element(mapping, FieldType, rec, template_values)
                    if nested is not None:
                        rule_fields[target_element] = [nested]
                case DublinCoreMapping():
                    FieldType = self.element_type("Rule", target_element)
                    references = self._references(mapping, FieldType, rec, context, template_values)
                    if references:
                        rule_fields[target_element] = references
                case IdentFromListMapping():
                    logger.debug(f"Generating idents from config for {field_name}")
                    idents = self.generate_idents_from_config(rec, mapping)
                    if idents:
                        # After the idents an earlier mapping wrote, if any
                        rule_fields.setdefault(target_element, []).extend(idents)
                        logger.debug(
                            ngettext(
                                "Added {count} ident to rule_fields[{target}]",
                                "Added {count} idents to rule_fields[{target}]",
                                len(idents),
                            ).format(count=len(idents), target=target_element)
                        )
                case SimpleMapping() | CompositeMapping() | EmbeddedXmlTagsMapping():
                    element = self._element_from_value(
                        mapping,
                        target_element,
                        self._build_field_value(mapping, rec, context),
                        template_values,
                    )
                    if element is not None:
                        rule_fields[target_element] = element
                case _:
                    assert_never(mapping)

        # Construct Rule dynamically from config
        return Rule(**rule_fields)

    def _nested_element(
        self, mapping: NestedMapping, FieldType: type, rec: Recommendation, template_values: dict
    ) -> Any:
        """The element of a nested mapping (check) holding its one child (check-content), or
        None when the child's field has no value."""
        (child,) = mapping.children
        child_value = getattr(rec, child.source_field, None)
        if not child_value:
            return None
        # The child's field and type in the target's XCCDF type (checked when the style loaded)
        child_element = self.style_models.child_element(FieldType, child.element)
        if child_element is None:
            raise ValueError(f"the {FieldType.__name__} type has no {child.element!r} element")
        child_instance = self._construct_typed_element(
            child_element.types[0], TransformRegistry.apply(child.transform, child_value)
        )
        system = VariableSubstituter.substitute(mapping.attributes.system, template_values)
        # The child is one element, not a list (check_content)
        return FieldType(**{"system": system, child_element.name: child_instance})

    def _references(
        self,
        mapping: DublinCoreMapping,
        FieldType: type,
        rec: Recommendation,
        context: dict,
        template_values: dict,
    ) -> list:
        """One reference per NIST control of a dublin_core mapping, each holding its Dublin
        Core elements; none when the mapping names no source field or there are no controls."""
        if not mapping.source_field:
            return []
        nist_controls: list[str] | None
        match mapping.source_logic:
            case "nist_after_cci_deduplication":
                # Only the NIST controls no CCI ident on this rule already covers
                _, nist_controls = self._cci_split(rec, context)
            case None:
                nist_controls = getattr(rec, mapping.source_field, None)
            case _:
                assert_never(mapping.source_logic)
        if not (nist_controls and isinstance(nist_controls, list)):
            return []
        href = str(VariableSubstituter.substitute(mapping.attributes.href, template_values))
        return [
            FieldType(
                href=href,
                content=self.dublin_core_elements(
                    mapping.dc_elements, {"nist_control_id": nist_id}
                ),
            )
            for nist_id in nist_controls
        ]

    def _element_from_value(
        self,
        mapping: SimpleMapping | CompositeMapping | EmbeddedXmlTagsMapping,
        target_element: str,
        value: Any,
        template_values: dict,
    ) -> Any:
        """What a simple, composite or embedded_xml_tags mapping writes on the Rule for its
        value, in the type the XCCDF model gives its element; None for nothing.

        A list value of a mapping with multiple gives one element per item (CCI idents, with
        the mapping's system); a mapping with attributes writes its element even with no
        value (fix/@id, fixtext/@fixref); otherwise a value gives one element.
        """
        FieldType = self.element_type("Rule", target_element)
        attributes = mapping.attributes
        if value is None and not attributes:
            return None

        if isinstance(mapping, SimpleMapping) and mapping.multiple and isinstance(value, list):
            if "system" in attributes:
                system = VariableSubstituter.substitute(attributes["system"], template_values)
                return [FieldType(system=system, value=item) for item in value]
            return [FieldType(value=item) for item in value]

        if attributes:
            attr_values = {
                name: VariableSubstituter.substitute(template, template_values)
                for name, template in attributes.items()
            }
            if not hasattr(FieldType, "__dataclass_fields__"):
                return None
            field_def = FieldType.__dataclass_fields__
            if "content" in field_def:
                # An empty list writes the element self-closing
                return [FieldType(content=[value] if value else [], **attr_values)]
            if "value" in field_def:
                return [FieldType(value=value if value is not None else "", **attr_values)]
            # Just attributes, no content field (rare)
            return [FieldType(**attr_values)]

        if not value:
            return None
        element = self._construct_typed_element(FieldType, value)
        if not element:
            return None
        return [element] if self._repeats("Rule", target_element) else element

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
            ElementType = self.element_type("Group", element_name)

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
                    group_fields[element_name] = (
                        [elem_instance] if self._repeats("Group", element_name) else elem_instance
                    )

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

            # Elements read from a benchmark field; the others (notice, front_matter,
            # profiles, reference) are built by their own methods below
            source = element_config.get("source")
            if source:
                ElementType = self.element_type("Benchmark", element_name)
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
                        benchmark_fields[element_name] = (
                            [elem_instance]
                            if self._repeats("Benchmark", element_name)
                            else elem_instance
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
        self, recommendation: "Recommendation", field_mapping: IdentFromListMapping
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
            field_mapping: The style's ident_from_list mapping

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

        source_field = field_mapping.source_field
        ident_spec = field_mapping.ident_spec

        # An empty source field, or an ident_spec written with no key, writes nothing
        if not source_field or not ident_spec.model_fields_set:
            logger.warning("ident_from_list missing source_field or ident_spec")
            return []

        # Get source data (supports nested paths like "mitre_mapping.techniques"); a
        # transform turns a text field into the list to read (lines: one ident per line)
        source_data = TransformRegistry.apply(
            field_mapping.transform, self._get_nested_field(recommendation, source_field)
        )
        if not source_data:
            return []

        # Handle both list and single value
        items = source_data if isinstance(source_data, list) else [source_data]

        idents = []
        system_template = ident_spec.system_template
        value_template = ident_spec.value_template
        custom_attrs = ident_spec.attributes
        # Checked before any prefix is resolved: declaring the attributes' namespaces would
        # not help a version whose ident takes no attributes from other namespaces.
        if custom_attrs and "other_attributes" not in {f.name for f in fields(IdentType)}:
            names = sorted(attr.name for attr in custom_attrs)
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
                attr_value = VariableSubstituter.substitute(attr_config.template, context)
                prefix = VariableSubstituter.substitute(attr_config.namespace_prefix, context)
                other_attributes[f"{{{self._namespace_uri(prefix)}}}{attr_config.name}"] = str(
                    attr_value
                )

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

    def generate_metadata_from_config(
        self, recommendation: "Recommendation", field_mapping: MetadataFromConfigMapping
    ) -> AnyElement | None:
        """Build a metadata root element from a metadata_from_config mapping.

        Items of the source list are grouped by metadata_spec.group_by; groups are written
        in key order and each group's items in source order. Every element is in the
        namespace benchmark.namespaces declares for metadata_spec.namespace_prefix (the
        style was checked when it loaded).

        Args:
            recommendation: Source recommendation data
            field_mapping: The style's metadata_from_config mapping

        Returns:
            The root element, an empty root when the source list is empty and allow_empty is
            set, or None.

        Raises:
            ValueError: An attribute value would be rewritten by the XML serializer.
        """
        spec = field_mapping.metadata_spec
        namespace = self._namespace_uri(spec.namespace_prefix)

        def qname(name: str) -> str:
            return f"{{{namespace}}}{name}"

        source_data = self._get_nested_field(recommendation, field_mapping.source_field)
        group_by = spec.group_by.removeprefix("item.")
        groups: dict[Any, list[Any]] = {}
        for item in source_data or []:
            group_key = self._get_nested_field(item, group_by)
            if group_key:
                groups.setdefault(group_key, []).append(item)
        if not groups:
            # No data, or no item in any group: the same case, decided by allow_empty
            return AnyElement(qname=qname(spec.root_element)) if spec.allow_empty else None

        group_spec = spec.group_element
        return AnyElement(
            qname=qname(spec.root_element),
            children=[
                AnyElement(
                    qname=qname(group_spec.element),
                    attributes=self._metadata_attributes(
                        group_spec.attributes, {"group_key": group_key}
                    ),
                    children=[
                        self._build_config_element(item, group_spec.item_element, qname)
                        for item in items
                    ],
                )
                for group_key, items in sorted(groups.items())
            ],
        )

    def _build_config_element(
        self, item: Any, spec: MetadataElement, qname: Callable[[str], str]
    ) -> AnyElement:
        """An item element, or one of its children, with its own children, from config."""
        text = None
        if spec.content:
            value = VariableSubstituter.substitute(spec.content, {"item": item})
            text = None if value is None else str(value)
        return AnyElement(
            qname=qname(spec.element),
            text=text,
            attributes=self._metadata_attributes(spec.attributes, {"item": item}),
            children=[self._build_config_element(item, child, qname) for child in spec.children],
        )

    @staticmethod
    def _metadata_attributes(
        templates: Mapping[str, str], context: dict[str, Any]
    ) -> dict[str, str]:
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
