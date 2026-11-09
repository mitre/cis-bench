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
- metadata_from_config: Generic nested XML from config (with requires_post_processing)
- generate_profiles_from_rules: Generic profile generation from config

See ARCHITECTURE_PRINCIPLES.md for complete guidelines.

Adding PCI-DSS, ISO 27001, HIPAA, etc. MUST require ZERO code changes (YAML only).
"""

import inspect
import logging
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field, fields
from pathlib import Path
from types import ModuleType
from typing import Any, get_args

import yaml
from pydantic import BaseModel

from cis_bench.exceptions import ExportError
from cis_bench.models.benchmark import Benchmark, ProfileDefinition, Recommendation

# Import XCCDF types for element creation (XCCDF 1.2 - for type hints only)
# Note: Engine dynamically loads version-specific types based on config
from cis_bench.utils.cci_lookup import get_cci_service
from cis_bench.utils.html_parser import HTMLCleaner
from cis_bench.utils.xhtml_formatter import XHTMLFormatter
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
    transformations: dict[str, Any] = field(default_factory=dict)
    cci_deduplication: dict[str, Any] = field(default_factory=dict)
    # Specification of each Rule and Group element and its xsdata type
    rule_elements: dict[str, Any] = field(default_factory=dict)
    group_elements: dict[str, Any] = field(default_factory=dict)
    legacy_vms_tags: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    # How the serialized XML is finished (handlers, namespace prefixes, root declarations)
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
TransformRegistry.register("strip_html", HTMLCleaner.strip_html)
TransformRegistry.register("html_to_markdown", HTMLCleaner.html_to_markdown)
TransformRegistry.register("wrap_xhtml_paragraphs", XHTMLFormatter.wrap_paragraphs)


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


def strip_html_keep_code(html: str | None) -> str:
    """Strip HTML but preserve code blocks."""
    if not html:
        return ""
    # For now, use strip_html (enhance later to preserve <code>, <pre>)
    return HTMLCleaner.strip_html(html)


TransformRegistry.register("strip_html_keep_code", strip_html_keep_code)


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
        raise ValueError(
            f"{value!r} is not a dotted number of at most {len(labels) + 1} levels "
            "(such as 13 or 8.5)"
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
            if "namespaces" in config_data:
                raise ValueError(
                    f"{config_path.name}: declare namespaces in benchmark.namespaces "
                    "(a top-level namespaces section is not read)"
                )

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
    """The Pydantic model a field holds, inside "X | None" or "list[X]"; None for a value
    that is not a model (a str, a list of str)."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    for arg in get_args(annotation):
        model = _model_in(arg)
        if model is not None:
            return model
    return None


class VariableSubstituter:
    """Handles variable substitution in templates."""

    @staticmethod
    def _resolve(expression: str, context: dict[str, Any]) -> Any:
        """The value of one {expression}: a dotted path, optionally piped through a
        registered transform with arguments ("item.control|dotted_number_path:subcontrol").

        Raises:
            ValueError: The filter names no registered transform, or the transform refuses
                the value.
        """
        path, pipe, filter_spec = expression.partition("|")
        value: Any = context
        for part in path.strip().split("."):
            if isinstance(value, dict):
                value = value.get(part, "")
            else:
                value = getattr(value, part, "")
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
        A variable may name a registered transform after a "|", with arguments after a
        ":", which is applied to its value: "{item.control|dotted_number_path:subcontrol}".

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
        """
        # Check if template is a single variable (preserve type)
        single_var_match = re.fullmatch(r"\{([^}]+)\}", template)
        if single_var_match:
            return VariableSubstituter._resolve(single_var_match.group(1), context)

        # Mixed template - convert all to strings
        return re.sub(
            r"\{([^}]+)\}",
            lambda match: str(VariableSubstituter._resolve(match.group(1), context)),
            template,
        )


class MappingEngine:
    """Main engine that applies config-based mappings."""

    def __init__(self, config_path: Path):
        """Initialize mapping engine with config.

        Args:
            config_path: Path to YAML configuration file
        """
        self.config = ConfigLoader.load(config_path)
        self._refuse_unknown_field_names()
        self.cci_service = get_cci_service()

        # Dynamically load XCCDF models based on config version
        xccdf_version = self.config.metadata.get("xccdf_version", "1.2")
        self._load_xccdf_models(xccdf_version)

        # Pre-load all types specified in config (stable code, config-driven types)
        self._load_types_from_config()

    # Structures whose source_field is read as a dotted path (_get_nested_field); every
    # other reader takes one field name.
    _DOTTED_PATH_STRUCTURES = frozenset({"ident_from_list", "metadata_from_config"})

    def _refuse_unknown_field_names(self) -> None:
        """Refuse a style that names a recommendation or benchmark field that does not exist.

        A name that is no field reads as empty, and an empty element is left out, so a
        misspelled name would drop the element without a word.

        Raises:
            ValueError: A source_field (field_mappings, their children) or source
                (group_elements, benchmark elements) names no field.
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
                    raise ValueError(
                        f"{where} names {path!r}, which is not a field of {model.__name__}"
                    )
                current = _model_in(fields[part].annotation)

    def _load_xccdf_models(self, version: str):
        """Dynamically import XCCDF models based on version.

        Args:
            version: XCCDF version ('1.1.4' or '1.2')
        """
        self.xccdf_models: ModuleType
        self.dc_models: ModuleType | None
        if version == "1.1.4":
            # Import XCCDF 1.1.4 models
            from cis_bench.models.xccdf_v1_1 import dc, xccdf_1_1_4

            self.xccdf_models = xccdf_1_1_4
            self.dc_models = dc
            self.xccdf_namespace = "http://checklists.nist.gov/xccdf/1.1"

        elif version == "1.2":
            # Import XCCDF 1.2 models
            from cis_bench.models.xccdf import xccdf_1_2

            self.xccdf_models = xccdf_1_2
            self.dc_models = None  # 1.2 doesn't have separate DC module
            self.xccdf_namespace = "http://checklists.nist.gov/xccdf/1.2"

        else:
            raise ValueError(f"Unsupported XCCDF version: {version}")

        self.xccdf_version = version

    def get_xccdf_class(self, class_name: str):
        """Get XCCDF class by name (version-agnostic).

        Args:
            class_name: Name of XCCDF class (e.g., 'Benchmark', 'Rule', 'Group')

        Returns:
            Class from appropriate XCCDF module
        """
        return getattr(self.xccdf_models, class_name)

    def rule_element_order(self) -> list[str]:
        """Return the Rule child-element names in the order the XCCDF schema requires.

        The xsdata models are generated from the NIST XSD of this engine's
        version, so their field order is the schema sequence (itemType, then
        selectableItemType, then ruleType) and their metadata carries the XML
        names. The schema is therefore the single source of element order; no
        list is kept in code or config.
        """
        rule_class = self.get_xccdf_class("Rule")
        return [
            f.metadata.get("name") or f.name
            for f in fields(rule_class)
            if f.metadata.get("type") == "Element"
        ]

    def get_dc_class(self, class_name: str):
        """Get Dublin Core class by name.

        Args:
            class_name: Name of DC class (e.g., 'Publisher', 'Source')

        Returns:
            Class from DC module (if available)
        """
        if self.dc_models:
            return getattr(self.dc_models, class_name)
        else:
            # XCCDF 1.2 doesn't have separate DC module
            # Need to create elements manually
            return None

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

    def create_vuln_discussion(self, rec: Recommendation) -> str:
        """Create VulnDiscussion XML structure from CIS fields.

        Combines description + rationale with proper embedded XML tags.
        """
        parts = []

        # Add description
        if rec.description:
            desc_text = TransformRegistry.apply("strip_html", rec.description)
            parts.append(desc_text)

        # Add rationale
        if rec.rationale:
            rat_text = TransformRegistry.apply("strip_html", rec.rationale)
            parts.append(rat_text)

        vuln_discussion = "\n\n".join(parts)

        # Build complete description with embedded tags
        description_parts = [f"<VulnDiscussion>{vuln_discussion}</VulnDiscussion>"]

        # Add other sections
        if rec.impact:
            impact_text = TransformRegistry.apply("strip_html", rec.impact)
            description_parts.append(f"<PotentialImpacts>{impact_text}</PotentialImpacts>")

        if rec.additional_info:
            mitigations_text = TransformRegistry.apply("strip_html", rec.additional_info)
            description_parts.append(f"<Mitigations>{mitigations_text}</Mitigations>")

        # Add legacy VMS tags if config says so
        if self.config.legacy_vms_tags and self.config.legacy_vms_tags.get("include"):
            for tag in self.config.legacy_vms_tags.get("tags", []):
                if tag not in ["PotentialImpacts", "Mitigations", "VulnDiscussion"]:
                    if tag == "Documentable":
                        description_parts.append(f"<{tag}>false</{tag}>")
                    else:
                        description_parts.append(f"<{tag}></{tag}>")

        return "".join(description_parts)

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

        # The CCI mapping file is keyed by one CIS Controls version, named in the style
        # (cci_lookup.cis_controls_version); other versions reuse the same numbers for
        # unrelated safeguards, so only that version's controls are looked up.
        controls_version = cci_lookup_config.get("cis_controls_version")
        cis_control_ids = [
            c.control
            for c in rec.cis_controls
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

    @staticmethod
    def dublin_core_markers(dc_elements_config: list[dict], values: dict[str, Any]) -> str:
        """A reference's Dublin Core elements as the markers the dublin_core_injection
        post-processing handler turns into elements: "DC:dc:title:NIST SP 800-53||DC:dc:
        identifier:CM-7" (xsdata cannot serialize lxml elements in mixed content). Each
        element's content template is filled from values."""
        return "||".join(
            f"DC:{dc['element']}:{VariableSubstituter.substitute(dc['content'], values)}"
            for dc in dc_elements_config
        )

    def create_reference(self, benchmark: Benchmark) -> tuple[str, list[str]]:
        """The Benchmark's own reference: its href and content, the Dublin Core markers of
        the style's benchmark.reference.dc_elements (none when the style declares none)."""
        dc_elements_config = self.config.benchmark.get("reference", {}).get("dc_elements", [])
        if not dc_elements_config:
            return str(benchmark.url), []
        markers = self.dublin_core_markers(dc_elements_config, {"benchmark": benchmark.__dict__})
        return str(benchmark.url), [markers]

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
                content_template, {"download_date": download_date, "benchmark": benchmark.__dict__}
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
            # Build VulnDiscussion with embedded tags
            return self.create_vuln_discussion(rec)

        elif field_mapping.get("source_logic") == "cci_lookup_with_deduplication":
            # CCI lookup - returns list of CCIs
            ccis, _ = self._cci_split(rec, context)
            return ccis  # Return raw list, caller will wrap in IdentType

        elif structure == "nested":
            # Handle nested structures (like check/check-content)
            # For now, return None - handle in specialized method
            return None

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

    def ref_values(self, ref: str) -> dict[str, str]:
        """The values made from a recommendation ref that templates use: {ref_normalized}
        ("3_1_1") and {stig_number} ("030101")."""
        return {
            "ref_normalized": self.normalize_ref(ref),
            "stig_number": self.ref_to_stig_number(ref),
        }

    def _id_from_ref(self, section: str, ref: str) -> str:
        """An id from the style's <section>.template (rule_id, group_id) and the ref's values.

        Raises:
            ValueError: The style has no template, the template names a value the ref does
                not give, or the template gives no id.
        """
        template = (getattr(self.config, section) or {}).get("template")
        if not template:
            raise ValueError(f"the style has no {section}.template")
        values = self.ref_values(ref)
        # An unknown variable would resolve to "" and leave a wrong but non-empty id.
        unknown = sorted(
            {
                name
                for expression in re.findall(r"\{([^}]+)\}", template)
                if (name := expression.partition("|")[0].strip().split(".")[0]) not in values
            }
        )
        if unknown:
            raise ValueError(
                f"{section} template {template!r} names {', '.join(unknown)}; "
                f"it can use only {', '.join(sorted(values))}"
            )
        made = VariableSubstituter.substitute(template, values)
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
                                attributes_config.get("system", ""), context
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
                        href = field_mapping.get("attributes", {}).get("href", "")
                        # One reference per NIST control
                        rule_fields[target_element] = [
                            FieldType(
                                href=href,
                                content=[
                                    self.dublin_core_markers(
                                        dc_elements_config, {"nist_control_id": nist_id}
                                    )
                                ],
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
                    logger.debug(f"Added {len(idents)} idents to rule_fields[{target_element}]")
                continue

            # For metadata_from_config structure - generic metadata from YAML
            if structure == "metadata_from_config":
                logger.debug(f"Generating metadata from config for {field_name}")
                metadata_elem = self.generate_metadata_from_config(rec, field_mapping)

                if metadata_elem is not None:
                    # Check if requires post-processing (lxml can't serialize in xsdata)
                    if field_mapping.get("requires_post_processing", False):
                        # Store for post-processing injection
                        if not hasattr(self, "_metadata_for_post_processing"):
                            self._metadata_for_post_processing = []
                        self._metadata_for_post_processing.append(metadata_elem)
                        logger.debug("Stored metadata for post-processing injection")
                    else:
                        # Try to add directly (if xsdata compatible - currently not supported)
                        logger.warning(
                            "metadata_from_config without requires_post_processing not yet supported"
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
                            attr_template["system"], context
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
                    k: VariableSubstituter.substitute(v, context)
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

        # Reference: its Dublin Core markers are expanded by the dublin_core_injection
        # handler, the same one that expands every Rule reference
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
                    logger.debug(f"Added {len(profiles)} Profile elements to benchmark")

        return XCCDFBenchmark(**benchmark_fields)

    def generate_idents_from_config(
        self, recommendation: "Recommendation", field_mapping: dict
    ) -> list:
        """Generic ident generation from YAML config - works for ANY organization.

        Generates <ident> elements for any compliance framework (CIS, MITRE, PCI-DSS, etc.)
        based on YAML configuration. Completely data-driven - no hard-coding.

        Config structure:
            source_field: "cis_controls"  # or "mitre_mapping.techniques", etc.
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

        # Get source data (supports nested paths like "mitre_mapping.techniques")
        source_data = self._get_nested_field(recommendation, source_field)
        if not source_data:
            return []

        # Handle both list and single value
        items = source_data if isinstance(source_data, list) else [source_data]

        idents = []
        system_template = ident_spec.get("system_template", "")
        value_template = ident_spec.get("value_template", "{item}")
        custom_attrs = ident_spec.get("attributes", [])

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
                if "other_attributes" not in {f.name for f in fields(IdentType)}:
                    raise ValueError(
                        f"ident attributes {sorted(other_attributes)} need an XCCDF version whose "
                        "ident allows attributes from other namespaces"
                    )
                idents.append(
                    IdentType(system=system, value=value, other_attributes=other_attributes)
                )
            else:
                idents.append(IdentType(system=system, value=value))

        logger.debug(
            f"Generated {len(idents)} idents from {source_field} (system={system_template})"
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
            description_transform: "strip_html"          # for the page's descriptions
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
            logger.debug(f"Generated profile '{profile_id}' with {len(select_list)} rules")

        logger.debug(f"Generated {len(profiles)} Profile elements")
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
        self, recommendation: "Recommendation", field_mapping: dict
    ) -> Any:
        """Generate nested XML metadata from YAML config - GENERIC for ANY structure.

        Builds metadata using lxml based on YAML specification.
        Supports grouping, nesting, attributes, content - all config-driven.

        Args:
            recommendation: Source recommendation data
            field_mapping: YAML field mapping with metadata_spec

        Returns:
            lxml Element with metadata structure, or None if no data
        """
        from collections import defaultdict

        from lxml import etree

        source_field = field_mapping.get("source_field")
        metadata_spec = field_mapping.get("metadata_spec", {})

        if not source_field or not metadata_spec:
            logger.warning("metadata_from_config missing source_field or metadata_spec")
            return None

        # Get source data
        source_data = self._get_nested_field(recommendation, source_field)

        # Handle empty case
        allow_empty = metadata_spec.get("allow_empty", False)
        if not source_data:
            if allow_empty:
                # Create empty element
                root_element = metadata_spec.get("root_element")
                namespace = metadata_spec.get("namespace")
                if namespace:
                    return etree.Element(f"{{{namespace}}}{root_element}")
                else:
                    return etree.Element(root_element)
            else:
                return None

        # Create root element
        root_element = metadata_spec.get("root_element")
        namespace = metadata_spec.get("namespace")

        if namespace:
            root = etree.Element(f"{{{namespace}}}{root_element}")
        else:
            root = etree.Element(root_element)

        # Check for grouping
        group_by = metadata_spec.get("group_by")

        if group_by:
            # Group items by field (e.g., CIS Controls by version)
            groups = defaultdict(list)
            for item in source_data:
                group_key = self._get_nested_field(item, group_by.replace("item.", ""))
                if group_key:
                    groups[group_key].append(item)

            # Build group elements from config
            group_spec = metadata_spec.get("group_element", {})
            group_elem_name = group_spec.get("element", "group")
            group_attrs = group_spec.get("attributes", {})
            item_spec = group_spec.get("item_element", {})

            for group_key, group_items in sorted(groups.items()):
                # Create group element
                if namespace:
                    group_elem = etree.SubElement(root, f"{{{namespace}}}{group_elem_name}")
                else:
                    group_elem = etree.SubElement(root, group_elem_name)

                # Add group attributes from config
                for attr_name, attr_template in group_attrs.items():
                    attr_value = VariableSubstituter.substitute(
                        attr_template, {"group_key": group_key}
                    )
                    group_elem.set(attr_name, attr_value)

                # Build items in group
                for item in group_items:
                    self._build_config_item(group_elem, item, item_spec, namespace)

        return root

    def _build_config_item(self, parent, item, item_spec, namespace):
        """Build item element from config spec."""
        from lxml import etree

        elem_name = item_spec.get("element")
        attrs = item_spec.get("attributes", {})
        children = item_spec.get("children", [])

        # Create element
        if namespace:
            elem = etree.SubElement(parent, f"{{{namespace}}}{elem_name}")
        else:
            elem = etree.SubElement(parent, elem_name)

        # Add attributes from config
        for attr_name, attr_template in attrs.items():
            attr_value = VariableSubstituter.substitute(attr_template, {"item": item})
            elem.set(attr_name, str(attr_value))

        # Add children from config
        for child_spec in children:
            self._build_config_child(elem, item, child_spec, namespace)

        return elem

    def _build_config_child(self, parent, item, child_spec, namespace):
        """Build child element recursively from config."""
        from lxml import etree

        elem_name = child_spec.get("element")
        attrs = child_spec.get("attributes", {})
        content = child_spec.get("content")
        children = child_spec.get("children", [])

        # Create element
        if namespace:
            elem = etree.SubElement(parent, f"{{{namespace}}}{elem_name}")
        else:
            elem = etree.SubElement(parent, elem_name)

        # Add attributes from config
        for attr_name, attr_template in attrs.items():
            attr_value = VariableSubstituter.substitute(attr_template, {"item": item})
            # Boolean to lowercase string for XML (handle both bool and string "True"/"False")
            if isinstance(attr_value, bool):
                attr_value = str(attr_value).lower()
            elif isinstance(attr_value, str) and attr_value in ["True", "False"]:
                attr_value = attr_value.lower()
            else:
                attr_value = str(attr_value)
            elem.set(attr_name, attr_value)

        # Add content from config
        if content:
            elem.text = str(VariableSubstituter.substitute(content, {"item": item}))

        # Recursive children
        for grandchild_spec in children:
            self._build_config_child(elem, item, grandchild_spec, namespace)

        return elem
