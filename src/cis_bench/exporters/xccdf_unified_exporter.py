"""Unified config-driven XCCDF exporter.

Single exporter class that handles all XCCDF styles (DISA, CIS, future styles)
through YAML configuration files. Adding a new style requires only creating
a new YAML config file - no Python code changes needed.
"""

import logging
from pathlib import Path

from cis_bench.exporters.base import BaseExporter, ExporterFactory
from cis_bench.exporters.mapping_engine import ConfigLoader, MappingEngine
from cis_bench.models.benchmark import Benchmark
from cis_bench.utils.xml_utils import DublinCoreInjector, XCCDFPostProcessor, XCCDFSerializer

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

        logger.info(f"Initializing XCCDF exporter with style: {style}")
        self.config = ConfigLoader.load(config_path)
        self.engine = MappingEngine(config_path)
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
        logger.info(
            f"Exporting {len(benchmark.recommendations)} recommendations to XCCDF ({self.style} style)"
        )

        # Step 1: Create XCCDF Benchmark using mapping engine
        xccdf_benchmark = self._create_benchmark(benchmark)
        logger.debug("Created XCCDF Benchmark structure from mapping engine")

        # Step 2: Serialize to XML
        xml_output = XCCDFSerializer.serialize_to_string(xccdf_benchmark)
        logger.debug(f"Serialized to XML ({len(xml_output)} chars)")

        # Step 3: Post-processing pipeline (config-driven)
        xml_output = self._apply_post_processing(xml_output, benchmark)

        # Step 4: Write to file
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(xml_output)

        logger.info(f"Export successful: {output_path}")
        return output_path

    def _create_benchmark(self, benchmark: Benchmark):
        """Create XCCDF Benchmark using mapping engine (config-driven).

        The mapping engine handles all style-specific logic based on the
        loaded YAML configuration.
        """
        platform = benchmark.title.lower().split()[0] if benchmark.title else "CIS"
        context = {
            "platform": platform,
            "benchmark": benchmark,
            "recommendations": benchmark.recommendations,  # Needed for profile generation
        }

        # Build all Groups (each contains one Rule)
        groups = []
        for rec in benchmark.recommendations:
            rule = self.engine.map_rule(rec, context)
            group = self.engine.map_group(rec, rule, context)
            groups.append(group)

        # Build Benchmark (will generate Profiles if configured)
        xccdf_bench = self.engine.map_benchmark(benchmark, groups, context)

        # Store elements needed for post-processing
        logger.debug(
            f"Before storing, engine._dc_elements exists: {hasattr(self.engine, '_dc_elements')}"
        )
        if hasattr(self.engine, "_dc_elements"):
            logger.debug(f"Before storing, engine._dc_elements value: {self.engine._dc_elements}")

        self._store_post_processing_data()

        return xccdf_bench

    def _store_post_processing_data(self):
        """Store data from mapping engine needed for post-processing."""
        # Dublin Core elements (all styles)
        has_dc = hasattr(self.engine, "_dc_elements")
        self._dc_elements = getattr(self.engine, "_dc_elements", [])
        logger.debug(f"Engine has _dc_elements: {has_dc}, value: {self._dc_elements}")

        # Post-processing data (Dublin Core for NIST references)
        logger.info("Post-processing setup: Dublin Core elements ready for injection")

    def _apply_post_processing(self, xml_output: str, benchmark: Benchmark) -> str:
        """Apply post-processing pipeline based on style config.

        All behavior is CONFIG-DRIVEN - no hardcoded style checks.
        Reads post_processing section from YAML config.
        """
        from pathlib import Path

        import yaml

        # Load raw config to get post_processing and namespaces sections
        config_file = Path(__file__).parent / "configs" / "styles" / f"{self.style}.yaml"
        with open(config_file) as f:
            raw_config = yaml.safe_load(f)

        # Get namespaces config (CIS: top-level, DISA: benchmark.namespaces)
        namespaces_config = {}
        if "namespaces" in raw_config:
            namespaces_config = raw_config["namespaces"]
        elif "benchmark" in raw_config and "namespaces" in raw_config["benchmark"]:
            namespaces_config = raw_config["benchmark"]["namespaces"]

        # Get post_processing config (with defaults from base.yaml via inheritance)
        post_processing_config = raw_config.get("post_processing", {})

        logger.debug(f"Loaded namespaces: {list(namespaces_config.keys())}")
        logger.debug(f"Post-processing config: {post_processing_config}")

        # Get XCCDF namespace from config (NO HARDCODING)
        if "default" in namespaces_config:
            xccdf_ns = namespaces_config["default"]
        elif "xccdf" in namespaces_config:
            xccdf_ns = namespaces_config["xccdf"]
        else:
            raise ValueError(f"No XCCDF namespace found in config for style '{self.style}'")

        logger.debug(f"Applying post-processing for style: {self.style}, namespace: {xccdf_ns}")

        # Run handlers from config (in order)
        handlers = post_processing_config.get("handlers", [])
        dc_ns = namespaces_config.get("dc", "http://purl.org/dc/elements/1.1/")

        for handler in handlers:
            if handler == "dublin_core_injection":
                logger.debug("Running handler: dublin_core_injection")
                xml_output = DublinCoreInjector.inject_dc_into_all_references(
                    xml_output, xccdf_namespace=xccdf_ns, dc_namespace=dc_ns
                )
            elif handler == "metadata_injection":
                logger.debug("Running handler: metadata_injection")
                xml_output = self._inject_metadata_from_config(xml_output)
            else:
                logger.warning(f"Unknown post-processing handler: {handler}")

        # Build namespace map for lxml (convert "default" key to None)
        nsmap_for_lxml = {}
        for key, value in namespaces_config.items():
            if key == "default":
                nsmap_for_lxml[None] = value
            else:
                nsmap_for_lxml[key] = value

        # Final processing (namespace cleanup, attribute removal, etc.)
        # All behavior driven by post_processing_config
        xml_output = XCCDFPostProcessor.process(
            xml_output,
            xccdf_namespace=xccdf_ns,
            dc_elements=self._dc_elements,
            namespace_map=nsmap_for_lxml,
            post_processing_config=post_processing_config,
        )
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

        metadata_elements = getattr(self.engine, "_metadata_for_post_processing", [])

        if not metadata_elements:
            logger.debug("No metadata for post-processing")
            return xml_output

        logger.info(f"Injecting {len(metadata_elements)} metadata elements (config-driven)")

        root = etree.fromstring(xml_output.encode("utf-8"))
        rules = root.xpath(".//*[local-name()='Rule']")

        # Inject metadata into corresponding rules
        for i, rule in enumerate(rules):
            if i >= len(metadata_elements):
                break

            metadata_elem = metadata_elements[i]

            # Wrap in xccdf:metadata element
            xccdf_ns = root.nsmap.get(None) or root.nsmap.get("default")
            if xccdf_ns:
                metadata_wrapper = etree.SubElement(rule, f"{{{xccdf_ns}}}metadata")
            else:
                metadata_wrapper = etree.SubElement(rule, "metadata")

            metadata_wrapper.append(metadata_elem)

        return etree.tostring(root, encoding="unicode", pretty_print=True)

    def _add_cis_controls_ident_uris(
        self, xml_str: str, xccdf_ns: str, cc7_ns: str, cc8_ns: str
    ) -> str:
        """Add cc7:controlURI and cc8:controlURI attributes to ident elements."""
        from lxml import etree

        root = etree.fromstring(xml_str.encode("utf-8"))
        ns = {"xccdf": xccdf_ns}
        ns_controls = {"controls": "http://cisecurity.org/controls"}

        rules = root.xpath(".//xccdf:Rule", namespaces=ns)
        added_count = 0

        for rule in rules:
            # Find metadata with CIS Controls
            metadata = rule.xpath("./xccdf:metadata", namespaces=ns)
            if not metadata:
                metadata = rule.xpath("./metadata")
            if not metadata:
                continue

            metadata = metadata[0]

            # Find CIS Controls
            cis_controls_list = metadata.xpath(".//controls:cis_controls", namespaces=ns_controls)
            if not cis_controls_list:
                continue

            cis_controls = cis_controls_list[0]
            safeguards = cis_controls.xpath(".//controls:safeguard", namespaces=ns_controls)

            # Build control URI mapping from safeguard URNs
            control_uris_by_version = {}
            for safeguard in safeguards:
                urn = safeguard.get("urn")
                if not urn:
                    continue

                # Parse: urn:cisecurity.org:controls:VERSION:CONTROL:SUBCONTROL
                urn_parts = urn.split(":")
                if len(urn_parts) >= 5:
                    version = urn_parts[3]
                    control = urn_parts[4]
                    subcontrol = urn_parts[5] if len(urn_parts) > 5 else None

                    if subcontrol:
                        control_uri = f"http://cisecurity.org/20-cc/v{version}.0/control/{control}/subcontrol/{subcontrol}"
                    else:
                        control_uri = f"http://cisecurity.org/20-cc/v{version}.0/control/{control}"

                    if version not in control_uris_by_version:
                        control_uris_by_version[version] = []
                    control_uris_by_version[version].append(control_uri)

            # Find idents and add controlURI attributes
            idents = rule.xpath("./xccdf:ident", namespaces=ns)
            if not idents:
                idents = rule.xpath("./ident")

            for ident in idents:
                system = ident.get("system", "")

                if "/v7" in system:
                    version = "7"
                    ns_prefix = f"{{{cc7_ns}}}controlURI"
                elif "/v8" in system:
                    version = "8"
                    ns_prefix = f"{{{cc8_ns}}}controlURI"
                else:
                    continue

                if version in control_uris_by_version and control_uris_by_version[version]:
                    control_uri = control_uris_by_version[version].pop(0)
                    ident.set(ns_prefix, control_uri)
                    added_count += 1

        logger.info(f"Added cc7/cc8 controlURI attributes to {added_count} ident elements")
        return etree.tostring(root, encoding="unicode", pretty_print=True)

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
