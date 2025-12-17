"""XML utilities for XCCDF processing.

Helpers for XML namespace handling, serialization, and post-processing.
"""

import logging

from lxml import etree

logger = logging.getLogger(__name__)


class XCCDFNamespaceFixer:
    """Fix xsdata namespace issues in generated XML.

    xsdata Issue #1079: Child elements sometimes get namespace=""
    This utility adds proper XCCDF namespace to all unnamespaced elements.
    """

    @staticmethod
    def fix_namespaces(xml_string: str, xccdf_namespace: str) -> str:
        """Fix xsdata namespace bug by adding XCCDF namespace to unnamespaced elements.

        Args:
            xml_string: XML output from xsdata serializer
            xccdf_namespace: XCCDF namespace URI (e.g., 'http://checklists.nist.gov/xccdf/1.1')

        Returns:
            Fixed XML string with proper namespaces on all elements

        Example:
            >>> xml = '<Benchmark><title xmlns="">Test</title></Benchmark>'
            >>> fixed = XCCDFNamespaceFixer.fix_namespaces(xml, 'http://checklists.nist.gov/xccdf/1.1')
            >>> # Result: <Benchmark xmlns="..."><title>Test</title></Benchmark>
        """
        root = etree.fromstring(xml_string.encode("utf-8"))

        # Add XCCDF namespace to all unnamespaced elements
        for elem in root.iter():
            if elem.tag and not elem.tag.startswith("{"):
                elem.tag = f"{{{xccdf_namespace}}}{elem.tag}"

        return etree.tostring(
            root, pretty_print=True, xml_declaration=True, encoding="UTF-8"
        ).decode("utf-8")


class XCCDFSerializer:
    """XCCDF XML serialization utilities."""

    @staticmethod
    def serialize_to_string(xccdf_obj, pretty: bool = True, indent: str = "  ") -> str:
        """Serialize xsdata XCCDF object to XML string.

        Args:
            xccdf_obj: xsdata XCCDF object (Benchmark, Rule, etc.)
            pretty: Enable pretty printing
            indent: Indentation string (default: 2 spaces)

        Returns:
            XML string

        Note:
            Uses xsdata's XmlSerializer with proper configuration.
        """
        from xsdata.formats.dataclass.serializers import XmlSerializer
        from xsdata.formats.dataclass.serializers.config import SerializerConfig

        logger.debug(f"Serializing {type(xccdf_obj).__name__} to XML")

        # Use 'indent' instead of deprecated 'pretty_print'
        config = SerializerConfig(indent=indent if pretty else None, xml_declaration=True)
        serializer = XmlSerializer(config=config)
        result = serializer.render(xccdf_obj)

        logger.debug(f"Serialization complete: {len(result)} chars")
        return result

    @staticmethod
    def tree_to_string(tree: etree.Element, pretty: bool = True) -> str:
        """Convert lxml tree to formatted XML string.

        Args:
            tree: lxml Element tree
            pretty: Enable pretty printing

        Returns:
            XML string with declaration

        Note:
            Used for post-processed XML (after namespace fixes, DC injection, etc.).
        """
        return etree.tostring(
            tree, pretty_print=pretty, xml_declaration=True, encoding="UTF-8"
        ).decode("utf-8")


class DublinCoreInjector:
    """Inject Dublin Core elements into XCCDF reference elements.

    xsdata limitation: Can't serialize lxml Elements in mixed content.
    This utility injects DC elements via post-processing.
    """

    @staticmethod
    def inject_dc_elements(
        xml_string: str,
        dc_elements: dict,
        xccdf_namespace: str,
        dc_namespace: str = "http://purl.org/dc/elements/1.1/",
    ) -> str:
        """Inject Dublin Core elements into reference element.

        Args:
            xml_string: XML with reference element
            dc_elements: Dict mapping DC element names to content
                        e.g., {'dc:publisher': 'CIS Security', 'dc:source': 'https://...'}
            xccdf_namespace: XCCDF namespace URI
            dc_namespace: Dublin Core namespace URI

        Returns:
            XML with DC elements injected into reference element

        Example:
            >>> dc_els = {'dc:publisher': 'CIS', 'dc:source': 'https://cis.org'}
            >>> xml = DublinCoreInjector.inject_dc_elements(xml, dc_els, xccdf_ns)
        """
        root = etree.fromstring(xml_string.encode("utf-8"))

        # Find reference element
        ref_elem = root.find(f".//{{{xccdf_namespace}}}reference")

        if ref_elem is not None:
            # Add DC elements
            for dc_elem_name, dc_content in dc_elements.items():
                # Extract element name (dc:publisher → publisher)
                elem_name = dc_elem_name.replace("dc:", "")

                # Create DC element with proper namespace
                dc_elem = etree.SubElement(ref_elem, f"{{{dc_namespace}}}{elem_name}")
                dc_elem.text = dc_content

        return XCCDFSerializer.tree_to_string(root)

    @staticmethod
    def inject_dc_into_all_references(
        xml_string: str,
        xccdf_namespace: str,
        dc_namespace: str = "http://purl.org/dc/elements/1.1/",
    ) -> str:
        """Inject Dublin Core elements into ALL reference elements with DC markers.

        Looks for reference content with DC markers like "DC:dc:title:NIST SP 800-53"
        and converts them to proper DC XML elements.

        Args:
            xml_string: XML string
            xccdf_namespace: XCCDF namespace URI
            dc_namespace: Dublin Core namespace URI

        Returns:
            XML with DC elements properly injected
        """
        logger.debug("Injecting Dublin Core elements into references")
        root = etree.fromstring(xml_string.encode("utf-8"))

        # Find ALL reference elements in the document
        # Try both with namespace and without (in case namespace already fixed)
        ref_elems = list(root.iter(f"{{{xccdf_namespace}}}reference")) + list(
            root.iter("reference")
        )

        logger.debug(f"Found {len(ref_elems)} reference elements to process")

        for ref_elem in ref_elems:
            # Check if content has DC markers
            if ref_elem.text and ref_elem.text.startswith("DC:"):
                # Parse DC markers from content
                # Format: "DC:dc:title:NIST SP 800-53||DC:dc:identifier:CM-7"
                content_text = ref_elem.text.strip()

                # Clear existing text content
                ref_elem.text = None
                for child in list(ref_elem):
                    ref_elem.remove(child)

                # Split by "||" to get each DC marker
                dc_markers = content_text.split("||")

                for marker in dc_markers:
                    if marker.startswith("DC:"):
                        # Remove "DC:" prefix and parse: "dc:title:NIST SP 800-53"
                        marker_content = marker[3:]  # Remove "DC:" prefix
                        parts = marker_content.split(":", 2)

                        if len(parts) >= 3:
                            # parts[0] is "dc" prefix
                            dc_elem_name = parts[1]  # "title" or "identifier"
                            dc_value = parts[2]  # "NIST SP 800-53" or "CM-7"

                            # Create DC element with proper namespace
                            dc_elem = etree.SubElement(
                                ref_elem, f"{{{dc_namespace}}}{dc_elem_name}"
                            )
                            dc_elem.text = dc_value

        return XCCDFSerializer.tree_to_string(root)

    @staticmethod
    def inject_cis_metadata(
        xml_string: str,
        xccdf_namespace: str,
        cis_namespace: str = "http://cisecurity.org/xccdf/metadata/1.0",
    ) -> str:
        """Inject CIS-specific metadata elements into metadata elements with markers.

        Looks for metadata content with META markers and converts to proper CIS XML.

        Args:
            xml_string: XML string
            xccdf_namespace: XCCDF namespace
            cis_namespace: CIS metadata namespace

        Returns:
            XML with CIS metadata elements injected
        """
        root = etree.fromstring(xml_string.encode("utf-8"))

        # Find ALL metadata elements
        metadata_elems = list(root.iter(f"{{{xccdf_namespace}}}metadata")) + list(
            root.iter("metadata")
        )

        for meta_elem in metadata_elems:
            if meta_elem.text and meta_elem.text.startswith("META:"):
                content_text = meta_elem.text.strip()

                # Clear existing content
                meta_elem.text = None
                for child in list(meta_elem):
                    meta_elem.remove(child)

                # Split by "||" to get each marker
                markers = content_text.split("||")

                for marker in markers:
                    if marker.startswith("META:"):
                        # Parse: "META:profile:Level 1" or "META:cis-control:version=8:id=4.8:title=..."
                        marker_content = marker[5:]  # Remove "META:" prefix
                        parts = marker_content.split(":", 1)

                        if len(parts) >= 2:
                            elem_name = parts[0]  # "cis-profile", "cis-control", "mitre-technique"
                            elem_content = parts[1]  # Rest of the content

                            # Check if this is a simple element or nested structure
                            if "=" in elem_content and (
                                "version=" in elem_content or "control-id=" in elem_content
                            ):
                                # Nested structure: "version=8:control-id=4.8:title=Uninstall..."
                                # Create parent element
                                cis_elem = etree.SubElement(
                                    meta_elem, f"{{{cis_namespace}}}{elem_name}"
                                )

                                # Parse key=value pairs
                                kv_parts = elem_content.split(":")
                                for kv in kv_parts:
                                    if "=" in kv:
                                        key, value = kv.split("=", 1)
                                        # Create child element
                                        child = etree.SubElement(
                                            cis_elem, f"{{{cis_namespace}}}{key}"
                                        )
                                        child.text = value
                            else:
                                # Simple element with text content
                                cis_elem = etree.SubElement(
                                    meta_elem, f"{{{cis_namespace}}}{elem_name}"
                                )
                                cis_elem.text = elem_content

        return XCCDFSerializer.tree_to_string(root)


class XCCDFPostProcessor:
    """Complete XCCDF post-processing pipeline.

    Combines namespace fixing, DC injection, and other workarounds
    for xsdata limitations.

    All behavior is CONFIG-DRIVEN via post_processing_config parameter.
    No hardcoded style-specific logic.
    """

    @staticmethod
    def process(
        xml_string: str,
        xccdf_namespace: str,
        dc_elements: dict | None = None,
        namespace_map: dict | None = None,
        post_processing_config: dict | None = None,
    ) -> str:
        """Apply XCCDF post-processing steps based on config.

        Args:
            xml_string: Raw XML from xsdata serializer
            xccdf_namespace: XCCDF namespace URI
            dc_elements: Dublin Core elements to inject (optional)
            namespace_map: All available namespaces from config
                          e.g., {None: xccdf_ns, 'dc': dc_ns, 'controls': ...}
            post_processing_config: Config-driven settings (from YAML)
                - strip_namespace_prefixes: bool (default: False)
                - preserve_namespaces: list or None (default: None = all)
                - remove_rule_status: bool (default: False)
                - remove_override_attr: bool (default: True)

        Returns:
            Fully processed XML ready for output
        """
        # Default config if not provided
        if post_processing_config is None:
            post_processing_config = {}

        # Extract config values with defaults
        strip_ns_prefixes = post_processing_config.get("strip_namespace_prefixes", False)
        preserve_ns_list = post_processing_config.get("preserve_namespaces", None)
        remove_override = post_processing_config.get("remove_override_attr", True)

        logger.debug(
            f"Post-processing config: strip_ns={strip_ns_prefixes}, preserve_ns={preserve_ns_list}"
        )

        # Step 1: Fix namespaces (always needed - xsdata bug workaround)
        xml_string = XCCDFNamespaceFixer.fix_namespaces(xml_string, xccdf_namespace)

        # Step 2: Inject DC elements if provided
        if dc_elements:
            dc_ns = "http://purl.org/dc/elements/1.1/"
            xml_string = DublinCoreInjector.inject_dc_elements(
                xml_string, dc_elements, xccdf_namespace, dc_ns
            )

        # Step 3: Parse XML for remaining processing
        root = etree.fromstring(xml_string.encode("utf-8"))

        # Step 4: Process elements based on config
        for elem in root.iter():
            # Remove 'override' attribute if configured
            if remove_override and "override" in elem.attrib:
                del elem.attrib["override"]

            # Strip namespace prefixes if configured
            if strip_ns_prefixes and elem.tag.startswith("{"):
                ns, local = elem.tag[1:].split("}", 1)
                # Always keep DC elements with their namespace (for proper serialization)
                if "purl.org/dc" not in ns:
                    elem.tag = local

        # Step 6: Rebuild root with appropriate namespaces
        if namespace_map:
            # Determine which namespaces to include
            if preserve_ns_list is not None:
                # Only include specified namespaces
                final_nsmap = {}
                for key in preserve_ns_list:
                    if key == "default":
                        # Default namespace uses None key in lxml
                        if None in namespace_map:
                            final_nsmap[None] = namespace_map[None]
                        elif "default" in namespace_map:
                            final_nsmap[None] = namespace_map["default"]
                    elif key in namespace_map:
                        final_nsmap[key] = namespace_map[key]
                logger.debug(f"Using filtered namespaces: {list(final_nsmap.keys())}")
            else:
                # Use all namespaces from config
                final_nsmap = namespace_map
                logger.debug(f"Using all namespaces: {list(final_nsmap.keys())}")

            # Create new root with correct namespace map
            new_root = etree.Element(root.tag, attrib=root.attrib, nsmap=final_nsmap)
            new_root.text = root.text

            # Copy all children
            for child in root:
                new_root.append(child)

            root = new_root

        return XCCDFSerializer.tree_to_string(root)
