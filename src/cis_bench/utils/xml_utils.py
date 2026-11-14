"""XML utilities for XCCDF processing: identifiers, serialization and post-processing.

The namespaces of an XCCDF document are chosen when xsdata writes it (the namespace map a
style declares); nothing renames elements or rewrites namespace declarations afterwards.
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


class XCCDFSerializer:
    """XCCDF XML serialization utilities."""

    @staticmethod
    def serialize_to_tree(xccdf_obj, ns_map: dict[str | None, str] | None = None) -> etree._Element:
        """Render an xsdata XCCDF object to an lxml element tree (xsdata's TreeSerializer).

        The export works on this tree and writes it once (tree_to_string); no step parses
        text the export itself wrote.

        Args:
            xccdf_obj: xsdata XCCDF object (Benchmark, Rule, etc.)
            ns_map: Prefix -> namespace URI the document declares on its root (None for the
                default namespace); xsdata names every element and xsi:type value with these
                prefixes and makes up one only for a namespace the map does not hold

        Returns:
            The root element
        """
        from xsdata.formats.dataclass.serializers.tree import TreeSerializer

        logger.debug(f"Rendering {type(xccdf_obj).__name__} to an XML tree")
        return TreeSerializer().render(xccdf_obj, ns_map=ns_map).getroot()

    @staticmethod
    def tree_to_string(tree: etree.Element, pretty: bool = True) -> str:
        """Convert lxml tree to formatted XML string.

        Args:
            tree: lxml Element tree
            pretty: Enable pretty printing

        Returns:
            XML string with declaration

        Note:
            Writes the exported tree once, after post-processing.
        """
        xml_bytes: bytes = etree.tostring(
            tree, pretty_print=pretty, xml_declaration=True, encoding="UTF-8"
        )
        return xml_bytes.decode("utf-8")


class XCCDFPostProcessor:
    """The post-processing that remains after rendering, driven by the style's
    post_processing settings. It changes attributes only; namespaces are the serializer's."""

    @staticmethod
    def process(root: etree._Element, post_processing_config: dict | None = None) -> None:
        """Apply the style's post-processing to the rendered tree, in place.

        Args:
            root: The root of the tree as xsdata rendered it
            post_processing_config: The style's post_processing settings
                - remove_override_attr: bool (default: True)
        """
        config = post_processing_config or {}
        if config.get("remove_override_attr", True):
            # override is an XCCDF attribute: only the document's own XCCDF elements lose it,
            # never content of another namespace (a Rule's metadata)
            xccdf_namespace = etree.QName(root).namespace or ""
            for element in root.iter(f"{{{xccdf_namespace}}}*"):
                element.attrib.pop("override", None)
