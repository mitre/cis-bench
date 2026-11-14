"""Unified config-driven XCCDF exporter.

Single exporter class that handles all XCCDF styles (DISA, CIS, future styles)
through YAML configuration files. Adding a new style requires only creating
a new YAML config file - no Python code changes needed.
"""

import logging
from gettext import ngettext
from pathlib import Path

from lxml import etree
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

        # Step 2: Render to a tree, apply the style's post-processing on it, write it once
        root = self._render(xccdf_benchmark)
        XCCDFPostProcessor.process(root, self.config.post_processing)
        xml_output = XCCDFSerializer.tree_to_string(root)
        logger.debug(
            ngettext(
                "Serialized to XML ({count} char)",
                "Serialized to XML ({count} chars)",
                len(xml_output),
            ).format(count=len(xml_output))
        )

        # Step 3: Write to file
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(xml_output)

        logger.debug(f"Export successful: {output_path}")
        return output_path

    def _render(self, xccdf_benchmark) -> etree._Element:
        """The XCCDF Benchmark as an lxml tree, as xsdata renders it, declaring the style's
        namespaces (benchmark.namespaces; "default" is the default namespace) on the root."""
        ns_map = {
            (None if prefix == "default" else prefix): uri
            for prefix, uri in self.config.namespaces.items()
        }
        # The Benchmark's own namespace must be one the style names; xsdata would otherwise
        # make up a prefix (ns0) for every XCCDF element.
        xccdf_namespace = etree.QName(XmlContext().build(type(xccdf_benchmark)).qname).namespace
        if xccdf_namespace not in ns_map.values():
            raise ValueError(
                f"style '{self.style}' does not declare the XCCDF namespace {xccdf_namespace} "
                "in benchmark.namespaces"
            )
        return XCCDFSerializer.serialize_to_tree(xccdf_benchmark, ns_map)

    def _create_benchmark(self, benchmark: Benchmark):
        """Create XCCDF Benchmark using mapping engine (config-driven).

        The mapping engine handles all style-specific logic based on the
        loaded YAML configuration.
        """
        context = {
            "benchmark": benchmark,
            "recommendations": benchmark.recommendations,  # Needed for profile generation
        }

        # Build all Groups (each contains one Rule). Rule ids must be unique:
        # XCCDF forbids duplicates.
        groups = []
        recommendations_by_rule_id: dict[str, list[Recommendation]] = {}
        for rec in benchmark.recommendations:
            rule = self.engine.map_rule(rec, context)
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
