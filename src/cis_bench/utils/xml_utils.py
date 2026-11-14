"""XML utilities for XCCDF processing: identifiers, serialization and post-processing.

The namespaces of an XCCDF document are chosen when xsdata writes it (the namespace map a
style declares); nothing renames elements or rewrites namespace declarations afterwards.
"""

import logging
import re
from gettext import ngettext

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


class XCCDFSerializer:
    """XCCDF XML serialization utilities."""

    @staticmethod
    def serialize_to_string(
        xccdf_obj,
        ns_map: dict[str | None, str] | None = None,
        pretty: bool = True,
        indent: str = "  ",
    ) -> str:
        """Serialize xsdata XCCDF object to XML string.

        Args:
            xccdf_obj: xsdata XCCDF object (Benchmark, Rule, etc.)
            ns_map: Prefix -> namespace URI the document declares on its root (None for the
                default namespace); xsdata names every element and xsi:type value with these
                prefixes and makes up one only for a namespace the map does not hold
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
        result = serializer.render(xccdf_obj, ns_map=ns_map)

        logger.debug(
            ngettext(
                "Serialization complete: {count} char",
                "Serialization complete: {count} chars",
                len(result),
            ).format(count=len(result))
        )
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
            Used for post-processed XML (after metadata injection and attribute removal).
        """
        xml_bytes: bytes = etree.tostring(
            tree, pretty_print=pretty, xml_declaration=True, encoding="UTF-8"
        )
        return xml_bytes.decode("utf-8")


class XCCDFPostProcessor:
    """The post-processing that remains after serialization, driven by the style's
    post_processing settings. It changes attributes only; namespaces are the serializer's."""

    @staticmethod
    def process(xml_string: str, post_processing_config: dict | None = None) -> str:
        """Apply the style's post-processing to a serialized XCCDF document.

        Args:
            xml_string: XML as the serializer wrote it
            post_processing_config: The style's post_processing settings
                - remove_override_attr: bool (default: True)

        Returns:
            Fully processed XML ready for output
        """
        config = post_processing_config or {}
        root = etree.fromstring(xml_string.encode("utf-8"))

        if config.get("remove_override_attr", True):
            for element in root.iter("*"):
                element.attrib.pop("override", None)

        return XCCDFSerializer.tree_to_string(root)
