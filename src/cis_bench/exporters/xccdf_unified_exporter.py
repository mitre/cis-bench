"""Unified config-driven XCCDF exporter.

Single exporter class that handles all XCCDF styles (DISA, CIS, future styles)
through YAML configuration files. Adding a new style requires only creating
a new YAML config file - no Python code changes needed.
"""

import logging
from gettext import ngettext
from pathlib import Path

from lxml.etree import QName
from xsdata.formats.dataclass.context import XmlContext

from cis_bench.exceptions import ExportError
from cis_bench.exporters.base import BaseExporter, ExporterFactory
from cis_bench.exporters.mapping_engine import MappingEngine
from cis_bench.models.benchmark import Benchmark, Recommendation
from cis_bench.utils.xml_utils import XCCDFPostProcessor, XCCDFSerializer

logger = logging.getLogger(__name__)


class XCCDFExporter(BaseExporter):
    """Config-driven XCCDF exporter supporting multiple styles.

    Styles are defined in YAML configuration files. To add a new style:
    1. Create new YAML config in exporters/configs/
    2. Use it with --format xccdf --style <name>

    No Python code changes required for new styles!

    Supported styles:
    - disa: DISA/DoD STIG-compatible (XCCDF 1.1.4)
    - cis: CIS native format (XCCDF 1.2)
    - disa_vulcan_compat: DISA with CCIs only (for Vulcan import)
    - custom: User-defined (create configs/styles/custom.yaml)
    """

    def __init__(self, style: str = "disa"):
        """Initialize with specified style.

        Args:
            style: Style name (matches config filename in configs/styles/)
                   Examples: 'disa', 'cis', 'disa_vulcan_compat'

        Raises:
            ValueError: If style config file doesn't exist
        """
        self.style = style
        config_filename = f"{style}.yaml"
        config_path = Path(__file__).parent / "configs" / "styles" / config_filename

        if not config_path.exists():
            available_styles = self._get_available_styles()
            raise ValueError(
                f"Unknown XCCDF style: '{style}'. "
                f"Available styles: {', '.join(available_styles)}. "
                f"To add a new style, create configs/styles/{config_filename}"
            )

        logger.debug(f"Initializing XCCDF exporter with style: {style}")
        self.engine = MappingEngine(config_path)
        # One loaded config (with its extends chain) drives mapping and post-processing.
        self.config = self.engine.config
        logger.debug(f"Loaded config: {config_filename}")

    @staticmethod
    def _get_available_styles():
        """Get list of available style configs from configs/styles/ directory."""
        styles_dir = Path(__file__).parent / "configs" / "styles"
        style_files = styles_dir.glob("*.yaml")
        return sorted([f.stem for f in style_files])

    def export(self, benchmark: Benchmark, output_path: str) -> str:
        """Export to XCCDF using configured style.

        Args:
            benchmark: Benchmark to export
            output_path: Output file path

        Returns:
            Path to created file
        """
        logger.debug(
            ngettext(
                "Exporting {count} recommendation to XCCDF ({style} style)",
                "Exporting {count} recommendations to XCCDF ({style} style)",
                len(benchmark.recommendations),
            ).format(count=len(benchmark.recommendations), style=self.style)
        )

        # Step 1: Create XCCDF Benchmark using mapping engine
        xccdf_benchmark = self._create_benchmark(benchmark)
        logger.debug("Created XCCDF Benchmark structure from mapping engine")

        # Step 2: Serialize to XML
        xml_output = self._render(xccdf_benchmark)
        logger.debug(
            ngettext(
                "Serialized to XML ({count} char)",
                "Serialized to XML ({count} chars)",
                len(xml_output),
            ).format(count=len(xml_output))
        )

        # Step 3: Post-processing pipeline (config-driven)
        xml_output = self._apply_post_processing(xml_output, benchmark)

        # Step 4: Write to file
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(xml_output)

        logger.debug(f"Export successful: {output_path}")
        return output_path

    def _render(self, xccdf_benchmark) -> str:
        """The XCCDF Benchmark as XML, as xsdata writes it, declaring the style's namespaces
        (benchmark.namespaces; "default" is the default namespace) on the root."""
        ns_map = {
            (None if prefix == "default" else prefix): uri
            for prefix, uri in self.config.namespaces.items()
        }
        # The Benchmark's own namespace must be one the style names; xsdata would otherwise
        # make up a prefix (ns0) for every XCCDF element.
        xccdf_namespace = QName(XmlContext().build(type(xccdf_benchmark)).qname).namespace
        if xccdf_namespace not in ns_map.values():
            raise ValueError(
                f"style '{self.style}' does not declare the XCCDF namespace {xccdf_namespace} "
                "in benchmark.namespaces"
            )
        return XCCDFSerializer.serialize_to_string(xccdf_benchmark, ns_map=ns_map)

    def _create_benchmark(self, benchmark: Benchmark):
        """Create XCCDF Benchmark using mapping engine (config-driven).

        The mapping engine handles all style-specific logic based on the
        loaded YAML configuration.
        """
        context = {
            "benchmark": benchmark,
            "recommendations": benchmark.recommendations,  # Needed for profile generation
        }

        # Reset per-export metadata state so repeated exports and rules without
        # metadata stay aligned 1-to-1 by Rule ID
        self.engine._metadata_for_post_processing = []
        self._rule_metadata_by_id: dict[str, list[object]] = {}

        # Build all Groups (each contains one Rule). Rule ids must be unique:
        # XCCDF forbids duplicates and per-Rule metadata is keyed by id, so a
        # collision would silently merge two recommendations into one Rule.
        groups = []
        recommendations_by_rule_id: dict[str, list[Recommendation]] = {}
        for rec in benchmark.recommendations:
            before_count = len(self.engine._metadata_for_post_processing)
            rule = self.engine.map_rule(rec, context)
            new_metadata = self.engine._metadata_for_post_processing[before_count:]
            if new_metadata and getattr(rule, "id", None):
                self._rule_metadata_by_id[str(rule.id)] = list(new_metadata)
            recommendations_by_rule_id.setdefault(str(rule.id), []).append(rec)
            group = self.engine.map_group(rec, rule, context)
            groups.append(group)

        collisions = {
            rule_id: recs for rule_id, recs in recommendations_by_rule_id.items() if len(recs) > 1
        }
        if collisions:
            details = "; ".join(
                f"{rule_id} <- " + ", ".join(f"{rec.ref} ({rec.title})" for rec in recs)
                for rule_id, recs in collisions.items()
            )
            raise ExportError(
                f"Duplicate Rule ids in style '{self.style}': {details}. "
                "XCCDF requires unique Rule ids; fix the colliding recommendations."
            )

        # Build Benchmark (will generate Profiles if configured)
        xccdf_bench = self.engine.map_benchmark(benchmark, groups, context)

        return xccdf_bench

    def _apply_post_processing(self, xml_output: str, benchmark: Benchmark) -> str:
        """Apply post-processing pipeline based on style config.

        All behavior is CONFIG-DRIVEN - no hardcoded style checks. Reads the post_processing
        section of the loaded style config, inherited through extends like every other
        section. Namespaces are not touched here: the serializer declared them.
        """
        post_processing_config = self.config.post_processing
        logger.debug(f"Post-processing config: {post_processing_config}")

        # Run handlers from config (in order)
        handlers = post_processing_config.get("handlers", [])

        for handler in handlers:
            if handler == "metadata_injection":
                logger.debug("Running handler: metadata_injection")
                xml_output = self._inject_metadata_from_config(xml_output)
            else:
                logger.warning(f"Unknown post-processing handler: {handler}")

        xml_output = XCCDFPostProcessor.process(xml_output, post_processing_config)

        logger.debug("Applied final post-processing")

        return xml_output

    def _inject_metadata_from_config(self, xml_output: str) -> str:
        """Generic metadata injection for elements marked requires_post_processing.

        This is a documented pattern for complex nested structures that can't be
        serialized directly by xsdata (lxml Elements).

        Pattern:
        1. Handler builds lxml Element from config
        2. Stores in _metadata_for_post_processing
        3. This method injects them after xsdata serialization

        Works for: CIS Controls, PCI-DSS hierarchies, ISO 27001, etc.
        """
        from lxml import etree

        # Rule children must stay in schema order, so metadata goes before the
        # first element the schema places after it. The order comes from the
        # XCCDF model of this style's version; a version whose Rule has no
        # metadata element (1.1.4) cannot carry injected metadata at all, so
        # enabling this handler on such a style is a configuration error even
        # when nothing happens to be queued.
        element_order = self.engine.rule_element_order()
        if "metadata" not in element_order:
            raise ExportError(
                f"XCCDF {self.engine.xccdf_version} Rules have no metadata element; "
                f"the metadata_injection handler is not valid for style '{self.style}'"
            )
        elements_after_metadata = set(element_order[element_order.index("metadata") + 1 :])

        metadata_by_rule_id = getattr(self, "_rule_metadata_by_id", None)
        metadata_elements = getattr(self.engine, "_metadata_for_post_processing", [])

        if not metadata_elements and not metadata_by_rule_id:
            logger.debug("No metadata for post-processing")
            return xml_output

        logger.debug(
            ngettext(
                "Injecting {count} metadata element (config-driven)",
                "Injecting {count} metadata elements (config-driven)",
                len(metadata_elements),
            ).format(count=len(metadata_elements))
        )

        root = etree.fromstring(xml_output.encode("utf-8"))
        rules = root.xpath(".//*[local-name()='Rule']")
        xccdf_ns = root.nsmap.get(None) or root.nsmap.get("default")

        for i, rule in enumerate(rules):
            rule_id = rule.get("id")
            if metadata_by_rule_id is not None:
                rule_metas = metadata_by_rule_id.get(rule_id or "", [])
            elif i < len(metadata_elements):
                rule_metas = [metadata_elements[i]]
            else:
                break

            if not rule_metas:
                continue

            insert_idx = len(rule)
            for child_idx, child in enumerate(rule):
                if etree.QName(child).localname in elements_after_metadata:
                    insert_idx = child_idx
                    break

            for offset, metadata_elem in enumerate(rule_metas):
                metadata_tag = f"{{{xccdf_ns}}}metadata" if xccdf_ns else "metadata"
                metadata_wrapper = etree.Element(metadata_tag)
                metadata_wrapper.append(metadata_elem)
                rule.insert(insert_idx + offset, metadata_wrapper)

        return str(etree.tostring(root, encoding="unicode", pretty_print=True))

    def format_name(self) -> str:
        """Return format name with style."""
        style_display = (
            self.style.upper()
            if self.style == "disa" or self.style == "cis"
            else self.style.title()
        )
        return f"XCCDF ({style_display})"

    def get_file_extension(self) -> str:
        """Return file extension."""
        return "xml"


# Register unified exporter
# Factory will need to pass style parameter
ExporterFactory.register("xccdf", XCCDFExporter)
ExporterFactory.register("xml", XCCDFExporter)
