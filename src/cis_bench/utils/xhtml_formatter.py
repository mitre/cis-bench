"""XHTML formatting utilities for CIS XCCDF exports.

Provides XHTML element wrappers matching official CIS XCCDF format.
Uses lxml for proper namespace handling and XML generation.
"""

from __future__ import annotations

from lxml import etree


class XHTMLFormatter:
    """Format text content as XHTML elements for XCCDF.

    CIS official XCCDF files wrap description/rationale content in XHTML
    elements like <xhtml:p> for proper formatting and XML validation.
    """

    XHTML_NS = "http://www.w3.org/1999/xhtml"

    @classmethod
    def wrap_single_paragraph(cls, text: str | None) -> etree.Element | None:
        """Wrap text in a single XHTML <p> element.

        Convenience method for text that doesn't need paragraph breaks.

        Args:
            text: Plain text content

        Returns:
            Single lxml <xhtml:p> Element or None if text empty

        Example:
            >>> formatter = XHTMLFormatter()
            >>> elem = formatter.wrap_single_paragraph("Some text")
            >>> etree.tostring(elem)
            b'<p xmlns="http://www.w3.org/1999/xhtml">Some text</p>'
        """
        if not text or not text.strip():
            return None

        p_elem = etree.Element(f"{{{cls.XHTML_NS}}}p")
        p_elem.text = text.strip()
        return p_elem

    @classmethod
    def create_code_block(cls, code: str, language: str | None = None) -> etree.Element:
        """Create XHTML <code> element.

        Args:
            code: Code content
            language: Optional language hint (not used in XHTML, but kept for future)

        Returns:
            lxml <xhtml:code> Element

        Example:
            >>> formatter = XHTMLFormatter()
            >>> elem = formatter.create_code_block("#!/bin/bash")
            >>> etree.tostring(elem)
            b'<code xmlns="http://www.w3.org/1999/xhtml">#!/bin/bash</code>'
        """
        code_elem = etree.Element(f"{{{cls.XHTML_NS}}}code")
        code_elem.text = code
        return code_elem

    @classmethod
    def create_strong(cls, text: str) -> etree.Element:
        """Create XHTML <strong> element for bold text.

        Args:
            text: Text to make bold

        Returns:
            lxml <xhtml:strong> Element
        """
        strong_elem = etree.Element(f"{{{cls.XHTML_NS}}}strong")
        strong_elem.text = text
        return strong_elem

    @classmethod
    def create_emphasis(cls, text: str) -> etree.Element:
        """Create XHTML <em> element for italic text.

        Args:
            text: Text to emphasize

        Returns:
            lxml <xhtml:em> Element
        """
        em_elem = etree.Element(f"{{{cls.XHTML_NS}}}em")
        em_elem.text = text
        return em_elem

    @classmethod
    def elements_to_xml_string(cls, elements: list[etree.Element]) -> str:
        """Convert list of XHTML elements to XML string.

        Utility for testing and debugging.

        Args:
            elements: List of lxml Element objects

        Returns:
            Concatenated XML string of all elements
        """
        if not elements:
            return ""

        return "".join(
            etree.tostring(elem, encoding="unicode", pretty_print=False) for elem in elements
        )
