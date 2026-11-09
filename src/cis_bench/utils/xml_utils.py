"""XML utilities for XCCDF processing.

Helpers for XML namespace handling, serialization, and post-processing.
"""

import logging
import re

from lxml import etree

logger = logging.getLogger(__name__)

# Characters allowed inside an XML NCName segment, as used in XCCDF ids. Letters,
# digits, '.', '-' and '_'; everything else (whitespace, ':', '(', '/', ...) is
# a separator. Restricted to ASCII so ids are stable across tools.
_NCNAME_SEPARATORS = re.compile(r"[^A-Za-z0-9._-]+")


def ncname_slug(text: str) -> str:
    """Reduce text to an XML NCName-safe identifier segment.

    Runs of characters that may not appear in an NCName become one underscore,
    and leading or trailing underscores are dropped, so "CIS Ubuntu Linux 22.04
    LTS Benchmark" becomes "CIS_Ubuntu_Linux_22.04_LTS_Benchmark" and
    "v7.1.0 (vNext)" becomes "v7.1.0_vNext". NCName-safe text is returned as is.
    """
    return _NCNAME_SEPARATORS.sub("_", text).strip("_")


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

        xml_bytes: bytes = etree.tostring(
            root, pretty_print=True, xml_declaration=True, encoding="UTF-8"
        )
        return xml_bytes.decode("utf-8")


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
            Used for post-processed XML (after namespace fixes, metadata injection, etc.).
        """
        xml_bytes: bytes = etree.tostring(
            tree, pretty_print=pretty, xml_declaration=True, encoding="UTF-8"
        )
        return xml_bytes.decode("utf-8")


class XCCDFPostProcessor:
    """Complete XCCDF post-processing pipeline.

    Combines namespace fixing and the other output workarounds for xsdata limitations.

    All behavior is CONFIG-DRIVEN via post_processing_config parameter.
    No hardcoded style-specific logic.
    """

    @staticmethod
    def process(
        xml_string: str,
        xccdf_namespace: str,
        namespace_map: dict | None = None,
        post_processing_config: dict | None = None,
    ) -> str:
        """Apply XCCDF post-processing steps based on config.

        Args:
            xml_string: Raw XML from xsdata serializer
            xccdf_namespace: XCCDF namespace URI
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

        # Step 2: Parse XML for remaining processing
        root = etree.fromstring(xml_string.encode("utf-8"))

        # Step 3: Process elements based on config
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

        # Step 4: Rebuild root with appropriate namespaces
        if namespace_map:
            # Determine which namespaces to include
            if preserve_ns_list is not None:
                # Only include specified namespaces
                final_nsmap: dict[str | None, str] = {}
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
