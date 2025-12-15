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
    - custom: User-defined (create custom_style.yaml)
    """

    def __init__(self, style: str = "disa"):
        """Initialize with specified style.

        Args:
            style: Style name (matches config filename without _style.yaml)
                   Examples: 'disa', 'cis', 'pci-dss', 'banking'

        Raises:
            FileNotFoundError: If style config file doesn't exist
        """
        self.style = style
        config_filename = f"{style}_style.yaml"
        config_path = Path(__file__).parent / "configs" / config_filename

        if not config_path.exists():
            available_styles = self._get_available_styles()
            raise ValueError(
                f"Unknown XCCDF style: '{style}'. "
                f"Available styles: {', '.join(available_styles)}. "
                f"To add a new style, create configs/{config_filename}"
            )

        logger.info(f"Initializing XCCDF exporter with style: {style}")
        self.config = ConfigLoader.load(config_path)
        self.engine = MappingEngine(config_path)
        logger.debug(f"Loaded config: {config_filename}")

    @staticmethod
    def _get_available_styles():
        """Get list of available style configs."""
        configs_dir = Path(__file__).parent / "configs"
        style_files = configs_dir.glob("*_style.yaml")
        return [f.stem.replace("_style", "") for f in style_files]

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
        context = {"platform": platform, "benchmark": benchmark}

        # Build all Groups (each contains one Rule)
        groups = []
        for rec in benchmark.recommendations:
            rule = self.engine.map_rule(rec, context)
            group = self.engine.map_group(rec, rule, context)
            groups.append(group)

        # Build Benchmark
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

        # CIS Controls objects (CIS style)
        self._cis_controls_objects = getattr(self.engine, "_cis_controls_objects", [])

        # Enhanced metadata (CIS style)
        self._enhanced_metadata_components = getattr(
            self.engine, "_enhanced_metadata_components", []
        )

        logger.info(
            f"Stored post-processing data: "
            f"dc_elements={self._dc_elements}, "
            f"cis_controls={len(self._cis_controls_objects)}, "
            f"enhanced={len(self._enhanced_metadata_components)}"
        )

    def _apply_post_processing(self, xml_output: str, benchmark: Benchmark) -> str:
        """Apply post-processing pipeline based on style config.

        Different styles may need different post-processors.
        This method routes to the appropriate processors based on style.
        """
        # Get namespaces from config (MappingConfig is a dataclass)
        # CIS has top-level namespaces field, DISA has benchmark.namespaces
        namespaces_config = {}

        # Try loading from raw YAML (re-parse to get non-dataclass fields)
        from pathlib import Path

        import yaml

        config_file = Path(__file__).parent / "configs" / f"{self.style}_style.yaml"
        with open(config_file) as f:
            raw_config = yaml.safe_load(f)

        # Try top-level namespaces (CIS)
        if "namespaces" in raw_config:
            namespaces_config = raw_config["namespaces"]
        # Try benchmark.namespaces (DISA)
        elif "benchmark" in raw_config and "namespaces" in raw_config["benchmark"]:
            namespaces_config = raw_config["benchmark"]["namespaces"]

        logger.debug(f"Loaded namespaces config: {list(namespaces_config.keys())}")

        # Get XCCDF namespace (different for DISA vs CIS)
        if "default" in namespaces_config:
            xccdf_ns = namespaces_config["default"]
        elif "xccdf" in namespaces_config:
            xccdf_ns = namespaces_config["xccdf"]
        else:
            # Fallback based on style
            xccdf_ns = (
                "http://checklists.nist.gov/xccdf/1.1"
                if self.style == "disa"
                else "http://checklists.nist.gov/xccdf/1.2"
            )

        logger.debug(f"Applying post-processing for style: {self.style}, namespace: {xccdf_ns}")

        # Common post-processors (all styles)
        # Always try DC injection (references may have DC markers from rules)
        dc_ns = namespaces_config.get("dc", "http://purl.org/dc/elements/1.1/")
        logger.debug("Applying Dublin Core injection to all references with markers")
        xml_output = DublinCoreInjector.inject_dc_into_all_references(
            xml_output, xccdf_namespace=xccdf_ns, dc_namespace=dc_ns
        )
        logger.debug("Applied Dublin Core injection")

        # Style-specific post-processors
        if self.style == "cis":
            xml_output = self._apply_cis_post_processors(xml_output, namespaces_config)
        elif self.style == "disa":
            xml_output = self._apply_disa_post_processors(xml_output, namespaces_config)
        # Future: elif self.style == "pci-dss": ...

        # Final namespace cleanup (all styles)
        xml_output = XCCDFPostProcessor.process(
            xml_output,
            xccdf_namespace=xccdf_ns,
            dc_elements=self._dc_elements,
            namespace_map=namespaces_config,
        )
        logger.debug("Applied final post-processing")

        return xml_output

    def _apply_cis_post_processors(self, xml_output: str, namespaces: dict) -> str:
        """Apply CIS-specific post-processors."""
        xccdf_ns = namespaces.get("xccdf")
        controls_ns = namespaces.get("controls")
        enhanced_ns = namespaces.get("enhanced")
        cc7_ns = namespaces.get("cc7")
        cc8_ns = namespaces.get("cc8")

        # Inject CIS Controls metadata
        if self._cis_controls_objects:
            logger.debug(
                f"Injecting {len(self._cis_controls_objects)} CIS Controls metadata blocks"
            )
            xml_output = self._inject_cis_controls_metadata(xml_output, xccdf_ns, controls_ns)

        # Inject enhanced metadata (MITRE, profiles)
        if self._enhanced_metadata_components:
            logger.debug(
                f"Injecting enhanced metadata from {len(self._enhanced_metadata_components)} components"
            )
            xml_output = self._inject_enhanced_metadata(xml_output, xccdf_ns, enhanced_ns)

        # Add cc7/cc8 controlURI attributes
        xml_output = self._add_cis_controls_ident_uris(xml_output, xccdf_ns, cc7_ns, cc8_ns)

        return xml_output

    def _apply_disa_post_processors(self, xml_output: str, namespaces: dict) -> str:
        """Apply DISA-specific post-processors.

        Injects CIS Controls and enhanced metadata (MITRE, profiles) same as CIS style.
        The data is identical - only the XCCDF structure differs between styles.
        """
        logger.debug("Applying DISA post-processors: CIS Controls and enhanced metadata injection")

        # Get namespaces for metadata injection
        xccdf_ns = namespaces.get("default", "http://checklists.nist.gov/xccdf/1.2")
        controls_ns = "http://cisecurity.org/controls"
        enhanced_ns = "http://cisecurity.org/xccdf/enhanced/1.0"

        # Inject CIS Controls metadata (same data as CIS style)
        xml_output = self._inject_cis_controls_metadata(xml_output, xccdf_ns, controls_ns)

        # Inject enhanced metadata: MITRE ATT&CK, profiles, etc. (same data as CIS style)
        xml_output = self._inject_enhanced_metadata(xml_output, xccdf_ns, enhanced_ns)

        return xml_output

    def _inject_cis_controls_metadata(self, xml_str: str, xccdf_ns: str, controls_ns: str) -> str:
        """Inject CIS Controls official nested structure into metadata elements."""
        from lxml import etree
        from xsdata.formats.dataclass.serializers import XmlSerializer
        from xsdata.formats.dataclass.serializers.config import SerializerConfig

        if not self._cis_controls_objects:
            return xml_str

        root = etree.fromstring(xml_str.encode("utf-8"))
        # Find rules with any XCCDF namespace (1.1, 1.2, etc.) using local-name()
        rules = root.xpath(".//*[local-name()='Rule']")

        config = SerializerConfig(pretty_print=False)
        serializer = XmlSerializer(config=config)

        injected_count = 0

        for i, rule in enumerate(rules):
            if i >= len(self._cis_controls_objects):
                break

            cis_controls_obj = self._cis_controls_objects[i]

            if not cis_controls_obj.framework:
                continue

            # Serialize CisControls to XML
            cis_controls_xml = serializer.render(cis_controls_obj)
            cis_controls_elem = etree.fromstring(cis_controls_xml.encode("utf-8"))

            # Find or create metadata element
            ns = {"xccdf": xccdf_ns}
            metadata = rule.xpath("./xccdf:metadata", namespaces=ns)
            if not metadata:
                metadata = rule.xpath("./metadata")

            if not metadata:
                metadata_elem = etree.Element("{http://checklists.nist.gov/xccdf/1.2}metadata")
                # Insert after rationale
                rationale = rule.xpath("./xccdf:rationale | ./rationale", namespaces=ns)
                if rationale:
                    rationale_idx = list(rule).index(rationale[0])
                    rule.insert(rationale_idx + 1, metadata_elem)
                else:
                    rule.append(metadata_elem)
                metadata = [metadata_elem]

            metadata[0].append(cis_controls_elem)
            injected_count += 1

        logger.info(f"Injected CIS Controls metadata into {injected_count} rules")
        return etree.tostring(root, encoding="unicode", pretty_print=True)

    def _inject_enhanced_metadata(self, xml_str: str, xccdf_ns: str, enhanced_ns: str) -> str:
        """Inject enhanced metadata (MITRE, profiles) into metadata elements."""
        from collections import defaultdict

        from lxml import etree

        if not self._enhanced_metadata_components:
            return xml_str

        root = etree.fromstring(xml_str.encode("utf-8"))
        # Find rules with any XCCDF namespace (1.1, 1.2, etc.) using local-name()
        rules = root.xpath(".//*[local-name()='Rule']")
        ns = {"xccdf": xccdf_ns}

        # Group components by recommendation ref
        components_by_rule = defaultdict(list)
        for comp_data in self._enhanced_metadata_components:
            rec = comp_data["recommendation"]
            components_by_rule[rec.ref].append((rec, comp_data["config"]))

        added_mitre_count = 0
        added_profile_count = 0

        for rule in rules:
            version_elem = rule.xpath("./xccdf:version", namespaces=ns)
            if not version_elem:
                version_elem = rule.xpath("./version")
            if not version_elem or not version_elem[0].text:
                continue

            rule_ref = version_elem[0].text

            if rule_ref not in components_by_rule:
                continue

            rec, _ = components_by_rule[rule_ref][0]

            # Find or create metadata
            metadata = rule.xpath("./xccdf:metadata", namespaces=ns)
            if not metadata:
                metadata = rule.xpath("./metadata")
            if not metadata:
                metadata_elem = etree.Element(f"{{{xccdf_ns}}}metadata")
                rule.append(metadata_elem)
                metadata = [metadata_elem]

            metadata_elem = metadata[0]

            # Create enhanced container
            enhanced_elem = etree.SubElement(metadata_elem, f"{{{enhanced_ns}}}enhanced")

            # Add MITRE if present
            if rec.mitre_mapping:
                mitre_elem = etree.SubElement(enhanced_elem, f"{{{enhanced_ns}}}mitre")

                if rec.mitre_mapping.techniques:
                    for tech in rec.mitre_mapping.techniques:
                        tech_elem = etree.SubElement(mitre_elem, f"{{{enhanced_ns}}}technique")
                        tech_elem.set("id", tech)
                        tech_elem.text = tech

                if rec.mitre_mapping.tactics:
                    for tactic in rec.mitre_mapping.tactics:
                        tac_elem = etree.SubElement(mitre_elem, f"{{{enhanced_ns}}}tactic")
                        tac_elem.set("id", tactic)
                        tac_elem.text = tactic

                if rec.mitre_mapping.mitigations:
                    for mitigation in rec.mitre_mapping.mitigations:
                        mit_elem = etree.SubElement(mitre_elem, f"{{{enhanced_ns}}}mitigation")
                        mit_elem.set("id", mitigation)
                        mit_elem.text = mitigation

                added_mitre_count += 1

            # Add profiles
            if rec.profiles:
                for profile in rec.profiles:
                    profile_elem = etree.SubElement(enhanced_elem, f"{{{enhanced_ns}}}profile")
                    profile_elem.text = profile
                    added_profile_count += 1

        logger.info(
            f"Injected enhanced metadata: {added_mitre_count} MITRE blocks, {added_profile_count} profiles"
        )
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
