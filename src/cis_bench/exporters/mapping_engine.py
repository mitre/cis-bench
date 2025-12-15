"""Configuration-driven XCCDF mapping engine.

Reads YAML configs and applies transformations to convert
Pydantic Benchmark models to XCCDF format.
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from cis_bench.models.benchmark import Benchmark, Recommendation

# Import XCCDF types for element creation (XCCDF 1.2 - for type hints only)
# Note: Engine dynamically loads version-specific types based on config
from cis_bench.utils.cci_lookup import get_cci_service
from cis_bench.utils.html_parser import HTMLCleaner
from cis_bench.utils.xhtml_formatter import XHTMLFormatter

# Set up logger
logger = logging.getLogger(__name__)


@dataclass
class MappingConfig:
    """Loaded mapping configuration."""

    metadata: dict[str, Any]
    benchmark: dict[str, Any]
    rule_defaults: dict[str, Any]
    rule_id: dict[str, str]
    field_mappings: dict[str, Any]
    transformations: dict[str, Any]
    cci_deduplication: dict[str, Any]
    rule_elements: dict[str, Any]  # Specification of each Rule element and its xsdata type
    group_elements: dict[str, Any]  # Specification of each Group element and its xsdata type
    legacy_vms_tags: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None


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


def strip_html_keep_code(html: str | None) -> str:
    """Strip HTML but preserve code blocks."""
    if not html:
        return ""
    # For now, use strip_html (enhance later to preserve <code>, <pre>)
    return HTMLCleaner.strip_html(html)


TransformRegistry.register("strip_html_keep_code", strip_html_keep_code)


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

            # Check for inheritance
            if "extends" in config_data:
                extends_path = config_data.pop("extends")

                # Resolve relative to current file's directory
                if not Path(extends_path).is_absolute():
                    extends_path = config_path.parent / extends_path

                # Recursively load parent configuration
                parent_config_obj = ConfigLoader.load(extends_path, _loading_stack)

                # Convert parent MappingConfig back to dict for merging
                parent_dict = {
                    "metadata": parent_config_obj.metadata,
                    "benchmark": parent_config_obj.benchmark,
                    "rule_defaults": parent_config_obj.rule_defaults,
                    "rule_id": parent_config_obj.rule_id,
                    "field_mappings": parent_config_obj.field_mappings,
                    "transformations": parent_config_obj.transformations,
                    "cci_deduplication": parent_config_obj.cci_deduplication,
                    "rule_elements": parent_config_obj.rule_elements,
                    "group_elements": parent_config_obj.group_elements,
                    "legacy_vms_tags": parent_config_obj.legacy_vms_tags,
                    "validation": parent_config_obj.validation,
                }

                # Deep merge parent with current (current overrides parent)
                config_data = ConfigLoader._deep_merge(parent_dict, config_data)

                logger.info(f"Loaded {config_path.name} extending {extends_path.name}")
            else:
                logger.debug(f"Loaded {config_path.name} (no inheritance)")

            # Extract sections
            return MappingConfig(
                metadata=config_data.get("metadata", {}),
                benchmark=config_data.get("benchmark", {}),
                rule_defaults=config_data.get("rule_defaults", {}),
                rule_id=config_data.get("rule_id", {}),
                field_mappings=config_data.get("field_mappings", {}),
                transformations=config_data.get("transformations", {}),
                cci_deduplication=config_data.get("cci_deduplication", {}),
                rule_elements=config_data.get("rule_elements", {}),
                group_elements=config_data.get("group_elements", {}),
                legacy_vms_tags=config_data.get("legacy_vms_tags"),
                validation=config_data.get("validation"),
            )

        finally:
            # Remove from loading stack
            _loading_stack.pop()


class VariableSubstituter:
    """Handles variable substitution in templates."""

    @staticmethod
    def substitute(template: str, context: dict[str, Any]) -> str:
        """Replace {variables} in template with context values.

        Examples:
            template: "F-{ref_normalized}"
            context: {"ref_normalized": "3_1_1"}
            result: "F-3_1_1"
        """

        def replacer(match):
            var_name = match.group(1)
            # Handle nested: {control.version}
            parts = var_name.split(".")
            value = context

            for part in parts:
                if isinstance(value, dict):
                    value = value.get(part, "")
                else:
                    value = getattr(value, part, "")

            return str(value)

        return re.sub(r"\{([^}]+)\}", replacer, template)


class MappingEngine:
    """Main engine that applies config-based mappings."""

    def __init__(self, config_path: Path):
        """Initialize mapping engine with config.

        Args:
            config_path: Path to YAML configuration file
        """
        self.config = ConfigLoader.load(config_path)
        self.cci_service = get_cci_service()

        # Dynamically load XCCDF models based on config version
        xccdf_version = self.config.metadata.get("xccdf_version", "1.2")
        self._load_xccdf_models(xccdf_version)

        # Pre-load all types specified in config (stable code, config-driven types)
        self._load_types_from_config()

    def _load_xccdf_models(self, version: str):
        """Dynamically import XCCDF models based on version.

        Args:
            version: XCCDF version ('1.1.4' or '1.2')
        """
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

        # Get CIS control IDs
        cis_control_ids = [c.control for c in rec.cis_controls]

        # Get extract parameter from ident field mapping (default: "all")
        ident_mapping = self.config.field_mappings.get("ident", {})
        cci_lookup_config = ident_mapping.get("cci_lookup", {})
        extract = cci_lookup_config.get("extract", "all")

        # Use CCI service for deduplication
        ccis, extra_nist = self.cci_service.deduplicate_nist_controls(
            cis_control_ids, rec.nist_controls, extract=extract
        )

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

        Per DISA conventions: Required but can be empty.
        """
        notice_config = self.config.benchmark.get("notice", {})
        NoticeType = self.get_xccdf_class("NoticeType")

        return NoticeType(
            id=notice_config.get("id", "terms-of-use"),
            content=[],  # Empty per config
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

    def create_reference(self, benchmark: Benchmark) -> tuple:
        """Create reference configuration (for post-processing).

        xsdata can't serialize lxml Elements in mixed content,
        so return config for post-processing injection.

        Returns:
            (href, dc_elements_dict) for post-processing
        """
        ref_config = self.config.benchmark.get("reference", {})

        # Prepare DC element data
        dc_elements = {}
        for dc_elem_config in ref_config.get("dc_elements", []):
            elem_name = dc_elem_config["element"]  # 'dc:publisher', 'dc:source'
            content = dc_elem_config["content"]

            # Substitute variables
            content = VariableSubstituter.substitute(content, {"benchmark": benchmark.__dict__})

            dc_elements[elem_name] = content

        return str(benchmark.url), dc_elements

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
            ccis, _ = self.get_ccis_with_deduplication(rec)
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
        Status = self.get_xccdf_class("Status")

        # Generate ID
        ref_norm = self.normalize_ref(rec.ref)
        context.update(
            {"ref_normalized": ref_norm, "rec": rec, "platform": context.get("platform", "")}
        )

        rule_id = VariableSubstituter.substitute(
            self.config.rule_id.get("template", "CIS-{ref_normalized}_rule"), context
        )

        # Start with required fields and defaults
        rule_fields = {
            "id": rule_id,
            "severity": self.config.rule_defaults.get("severity", "medium"),
            "weight": float(self.config.rule_defaults.get("weight", "10.0")),
            "status": [Status(value="draft")],
        }

        # THE KEY: Loop through config.field_mappings (NO HARD-CODED FIELD LIST)
        for field_name, field_mapping in self.config.field_mappings.items():
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
                if source_field:
                    nist_controls = getattr(rec, source_field, None)
                    if nist_controls and isinstance(nist_controls, list):
                        dc_elements_config = field_mapping.get("dc_elements", [])
                        href = field_mapping.get("attributes", {}).get("href", "")

                        # Create one reference per NIST control
                        # Build content with DC markers that post-processor handles
                        references = []
                        for nist_id in nist_controls:
                            # Build content string with DC element markers
                            # Format: "DC:dc:title:NIST SP 800-53||DC:dc:identifier:CM-7"
                            # Using || as separator to avoid confusion with colons in values
                            content_parts = []
                            for dc_config in dc_elements_config:
                                dc_elem = dc_config["element"]  # "dc:title" or "dc:identifier"
                                dc_template = dc_config[
                                    "content"
                                ]  # "NIST SP 800-53" or "{nist_control_id}"

                                # Substitute variables
                                dc_value = dc_template.replace("{nist_control_id}", nist_id)

                                # Store as marker for post-processing
                                content_parts.append(f"DC:{dc_elem}:{dc_value}")

                            # Create ReferenceType with concatenated marker as single string
                            marker_string = "||".join(content_parts)
                            references.append(FieldType(href=href, content=[marker_string]))

                        rule_fields[target_element] = references
                        # Store DC element names for post-processing
                        if not hasattr(self, "_dc_elements"):
                            self._dc_elements = []
                        self._dc_elements = [dc["element"] for dc in dc_elements_config]
                continue

            # For official_cis_controls structure - use dataclass serialization
            if structure == "official_cis_controls":
                logger.debug(f"Processing official_cis_controls for rec {rec.ref}")
                # Call build_cis_controls method to create proper nested structure
                cis_controls_obj = self.build_cis_controls(rec)
                logger.debug(
                    f"Created CIS Controls with {len(cis_controls_obj.framework)} frameworks"
                )

                # Store in a special field for post-processing injection
                # Can't add directly to rule_fields because MetadataType doesn't support it
                if not hasattr(self, "_cis_controls_objects"):
                    self._cis_controls_objects = []
                    logger.info("Initialized _cis_controls_objects list for CIS Controls metadata")
                self._cis_controls_objects.append(cis_controls_obj)
                logger.debug(
                    f"Total CIS Controls objects stored: {len(self._cis_controls_objects)}"
                )
                # Will be injected in exporter post-processing
                continue

            # For cis_controls_ident structure - generate ident elements
            if structure == "cis_controls_ident":
                logger.debug(f"Generating CIS Controls idents for rec {rec.ref}")
                # Call generate_cis_idents to create ident list
                idents = self.generate_cis_idents(rec)
                logger.debug(f"Generated {len(idents)} ident elements")

                # Add to rule_fields (these are proper IdentType objects)
                if idents:
                    # Append to existing idents if any
                    existing_idents = rule_fields.get(target_element, [])
                    rule_fields[target_element] = existing_idents + idents
                    logger.debug(f"Added {len(idents)} idents to rule_fields[{target_element}]")
                continue

            # For enhanced_namespace structures (MITRE, profiles)
            if structure == "enhanced_namespace":
                # Store for post-processing injection (similar to CIS Controls)
                components = field_mapping.get("components", [])

                if components:
                    # Build enhanced metadata object
                    # Store in special field for post-processing
                    if not hasattr(self, "_enhanced_metadata_components"):
                        self._enhanced_metadata_components = []

                    # Store component configs and source data for serialization
                    for component_config in components:
                        self._enhanced_metadata_components.append(
                            {"config": component_config, "recommendation": rec}
                        )
                # Will be injected in exporter post-processing
                continue

            # For custom_namespace structures (CIS metadata), build from config
            if structure == "custom_namespace":
                components = field_mapping.get("components", [])
                # namespace from config used by post-processor

                if components:
                    # Build metadata markers from config (NO HARDCODING)
                    metadata_markers = []

                    # Loop through each component definition in config
                    for component_config in components:
                        element_name = component_config.get("element")  # From config
                        source_field = component_config.get("source_field")  # From config
                        is_multiple = component_config.get("multiple", False)
                        content_template = component_config.get("content", "{value}")
                        component_structure = component_config.get("structure")

                        # Get source value
                        source_value = getattr(rec, source_field, None)

                        if source_value:
                            # Handle simple list (like profiles)
                            if (
                                is_multiple
                                and isinstance(source_value, list)
                                and not component_structure
                            ):
                                # Simple list of strings
                                for item in source_value:
                                    # Substitute template - find variable name from template
                                    # Config might use {profile}, {value}, {item}, etc.
                                    import re

                                    var_match = re.search(r"\{(\w+)\}", content_template)
                                    if var_match:
                                        # Template has variable, substitute it
                                        content = content_template.replace(
                                            f"{{{var_match.group(1)}}}", str(item)
                                        )
                                    else:
                                        # No template, use item directly
                                        content = str(item)

                                    metadata_markers.append(f"META:{element_name}:{content}")

                            # Handle nested structure (like CIS Controls)
                            elif component_structure == "nested":
                                children_config = component_config.get("children", [])
                                attributes_config = component_config.get("attributes", {})

                                # For each item in list
                                if isinstance(source_value, list):
                                    for item in source_value:
                                        # Build marker for this control
                                        # Format: META:cis-control:version=8:id=4.8:title=Uninstall Unnecessary
                                        marker_parts = [f"META:{element_name}"]

                                        # Add attributes
                                        for attr_name, attr_template in attributes_config.items():
                                            attr_value = VariableSubstituter.substitute(
                                                attr_template, {"item": item}
                                            )
                                            if hasattr(item, attr_name):
                                                attr_value = str(getattr(item, attr_name))
                                            marker_parts.append(f"{attr_name}={attr_value}")

                                        # Add children
                                        for child_config in children_config:
                                            child_elem = child_config.get("element")
                                            child_content_template = child_config.get("content", "")

                                            # Extract value from item
                                            # Handle {control.field} syntax
                                            if "{" in child_content_template:
                                                # Parse {control.field}
                                                import re

                                                matches = re.findall(
                                                    r"\{(\w+)\.(\w+)\}", child_content_template
                                                )
                                                if matches:
                                                    obj_name, field_name = matches[0]
                                                    if hasattr(item, field_name):
                                                        child_value = getattr(item, field_name)
                                                        marker_parts.append(
                                                            f"{child_elem}={child_value}"
                                                        )
                                            else:
                                                marker_parts.append(
                                                    f"{child_elem}={child_content_template}"
                                                )

                                        metadata_markers.append(":".join(marker_parts))

                                # Handle object with sub-fields (like MITRE mapping)
                                elif not isinstance(source_value, (list, str)):
                                    # Loop through child definitions
                                    for child_config in children_config:
                                        child_element = child_config.get("element")
                                        child_source = child_config.get("source_field")
                                        child_multiple = child_config.get("multiple", False)

                                        # Extract nested value
                                        if "." in child_source:
                                            # Handle "mitre_mapping.techniques" syntax
                                            parts = child_source.split(".")
                                            child_value = source_value
                                            for part in parts[1:]:
                                                if hasattr(child_value, part):
                                                    child_value = getattr(child_value, part)
                                                else:
                                                    child_value = None
                                                    break

                                            if (
                                                child_value
                                                and child_multiple
                                                and isinstance(child_value, list)
                                            ):
                                                for item in child_value:
                                                    metadata_markers.append(
                                                        f"META:{child_element}:{item}"
                                                    )
                                            elif child_value and not child_multiple:
                                                # Single value
                                                metadata_markers.append(
                                                    f"META:{child_element}:{child_value}"
                                                )

                    if metadata_markers:
                        # Store enhanced metadata for post-processing injection
                        # Don't add to rule_fields - will be injected after serialization
                        if not hasattr(self, "_enhanced_metadata_components"):
                            self._enhanced_metadata_components = []

                        # Store component configs and source data for post-processing
                        for component_config in components:
                            self._enhanced_metadata_components.append(
                                {"config": component_config, "recommendation": rec}
                            )
                        logger.debug(
                            f"Stored {len(components)} enhanced metadata components for rec {rec.ref}"
                        )
                # Will be injected in exporter post-processing
                continue

            # Get field value using config
            value = self._build_field_value(field_name, field_mapping, rec, context)

            if value is None:
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

            # Pattern 2: Has attributes (like fixtext/@fixref)
            if attributes_config and value:
                # Substitute variables in attributes
                attr_values = {
                    k: VariableSubstituter.substitute(v, context)
                    for k, v in attributes_config.items()
                }

                # Construct with attributes
                # NOTE: Can't use _construct_typed_element because we need to pass attributes
                # Keep this specialized for now
                if hasattr(FieldType, "__dataclass_fields__"):
                    field_def = FieldType.__dataclass_fields__
                    if "content" in field_def:
                        rule_fields[target_element] = [FieldType(content=[value], **attr_values)]
                    elif "value" in field_def:
                        rule_fields[target_element] = [FieldType(value=value, **attr_values)]
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

        # Generate Group ID
        ref_norm = context.get("ref_normalized", self.normalize_ref(rec.ref))
        platform = context.get("platform", "")

        # Group ID pattern
        if self.xccdf_version == "1.1.4":
            group_id = f"CIS-{ref_norm}"
        else:
            group_id = f"xccdf_org.cisecurity_group_{platform}{ref_norm}"

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
                # Source from rec
                if source == "ref":
                    value = f"CIS {rec.ref}"
                else:
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

        # Generate Benchmark ID
        platform = context.get("platform", "")
        bench_id_template = self.config.benchmark.get(
            "id_template", "CIS_{platform}_{benchmark_id}"
        )
        bench_id = VariableSubstituter.substitute(
            bench_id_template,
            {"platform": platform.title(), "benchmark_id": benchmark.benchmark_id},
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

        # Reference (returns tuple for post-processing)
        ref_href, dc_elements = self.create_reference(benchmark)
        ReferenceType = self.get_xccdf_class("ReferenceType")
        benchmark_fields["reference"] = [
            ReferenceType(href=ref_href, content=[])
        ]  # List per schema

        # Store DC elements for post-processing
        self._dc_elements = dc_elements

        return XCCDFBenchmark(**benchmark_fields)

    def build_cis_controls(self, recommendation: "Recommendation"):
        """Build official nested CIS Controls structure.

        Creates the proper CIS Controls hierarchy matching CIS-CAT format:
        CisControls > Framework (v7.0, v8.0) > Safeguard > ImplementationGroups

        Args:
            recommendation: Recommendation with cis_controls list

        Returns:
            CisControls object with nested framework/safeguard structure

        Example:
            <cis_controls xmlns="http://cisecurity.org/controls">
              <framework urn="urn:cisecurity.org:controls:8.0">
                <safeguard title="Use Unique Passwords"
                           urn="urn:cisecurity.org:controls:8.0:5:2">
                  <implementation_groups ig1="true" ig2="true" ig3="true"/>
                  <asset_type>Users</asset_type>
                  <security_function>Protect</security_function>
                </safeguard>
              </framework>
            </cis_controls>
        """
        from cis_bench.models.cis_controls_official import (
            CisControls,
            Framework,
            ImplementationGroups,
            Safeguard,
        )

        if not recommendation.cis_controls:
            # Return empty structure if no controls
            return CisControls(framework=[])

        # Group controls by version (7.0 and 8.0)
        controls_by_version = {}
        for control in recommendation.cis_controls:
            version = control.version
            if version not in controls_by_version:
                controls_by_version[version] = []
            controls_by_version[version].append(control)

        # Build Framework objects for each version
        frameworks = []
        for version in sorted(controls_by_version.keys()):
            controls = controls_by_version[version]
            safeguards = []

            for control in controls:
                # Create ImplementationGroups
                ig = ImplementationGroups(
                    ig1=control.ig1 if control.ig1 is not None else False,
                    ig2=control.ig2 if control.ig2 is not None else False,
                    ig3=control.ig3 if control.ig3 is not None else True,  # Default true per schema
                )

                # Parse control_id for URN (e.g., "5.2" -> control=5, subcontrol=2)
                control_id_parts = control.control.split(".")
                if len(control_id_parts) == 2:
                    control_num, subcontrol_num = control_id_parts
                    urn = f"urn:cisecurity.org:controls:{version}:{control_num}:{subcontrol_num}"
                else:
                    # Single-level control (e.g., "5")
                    urn = f"urn:cisecurity.org:controls:{version}:{control.control}"

                # Create Safeguard
                safeguard = Safeguard(
                    title=control.title,
                    urn=urn,
                    implementation_groups=ig,
                    asset_type="Unknown",  # We don't have this data from WorkBench
                    security_function="Protect",  # Default per CIS convention
                )
                safeguards.append(safeguard)

            # Create Framework for this version
            framework = Framework(
                urn=f"urn:cisecurity.org:controls:{version}",
                safeguard=safeguards,
            )
            frameworks.append(framework)

        return CisControls(framework=frameworks)

    def generate_cis_idents(self, recommendation: "Recommendation") -> list:
        """Generate CIS Controls <ident> elements with cc7/cc8 controlURI attributes.

        Creates XCCDF ident elements for each CIS Control with proper namespace attributes:
        - cc7:controlURI for v7 controls
        - cc8:controlURI for v8 controls

        Args:
            recommendation: Recommendation with cis_controls list

        Returns:
            List of xsdata Ident objects (empty if no controls)

        Example:
            <ident cc8:controlURI="http://cisecurity.org/20-cc/v8.0/control/5/subcontrol/2"
                   system="http://cisecurity.org/20-cc/v8.0"/>
            <ident cc7:controlURI="http://cisecurity.org/20-cc/v7.0/control/16/subcontrol/2"
                   system="http://cisecurity.org/20-cc/v7.0"/>

        Note:
            The cc7:controlURI and cc8:controlURI attributes need to be added
            post-serialization because xsdata doesn't support dynamic namespace
            attributes directly in the model.
        """
        IdentType = self.get_xccdf_class("IdentType")

        if not recommendation.cis_controls:
            return []

        idents = []

        for control in recommendation.cis_controls:
            version = control.version

            # Parse control_id for URI (e.g., "5.2" -> control=5, subcontrol=2)
            control_id_parts = control.control.split(".")

            if len(control_id_parts) == 2:
                control_num, subcontrol_num = control_id_parts
                control_uri = f"http://cisecurity.org/20-cc/v{version}/control/{control_num}/subcontrol/{subcontrol_num}"
            else:
                # Single-level control
                control_uri = f"http://cisecurity.org/20-cc/v{version}/control/{control.control}"

            # Create ident element
            # Note: system attribute is standard, controlURI needs post-processing
            ident = IdentType(
                system=f"http://cisecurity.org/20-cc/v{version}",
                value="",  # Empty per CIS convention
            )

            # Store controlURI for post-processing
            # This will be added as cc{version}:controlURI attribute
            ident._control_uri = control_uri  # Store for post-processing
            ident._cc_version = version  # Store version for namespace prefix

            idents.append(ident)

        return idents
