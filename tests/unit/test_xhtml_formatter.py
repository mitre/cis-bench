"""Tests for XHTML formatting utilities.

Tests the XHTMLFormatter class which creates XHTML elements for XCCDF exports.
"""


class TestXHTMLFormatterWrapParagraphs:
    """Tests for wrap_paragraphs method."""

    def test_wrap_paragraphs_single(self):
        """Single paragraph text should create one <p> element."""
        from cis_bench.utils.xhtml_formatter import XHTMLFormatter

        elements = XHTMLFormatter.wrap_paragraphs("This is a single paragraph.")

        assert len(elements) == 1
        assert elements[0].text == "This is a single paragraph."
        assert elements[0].tag == "{http://www.w3.org/1999/xhtml}p"

    def test_wrap_paragraphs_multiple(self):
        """Text with double newlines should create multiple <p> elements."""
        from cis_bench.utils.xhtml_formatter import XHTMLFormatter

        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        elements = XHTMLFormatter.wrap_paragraphs(text)

        assert len(elements) == 3
        assert elements[0].text == "First paragraph."
        assert elements[1].text == "Second paragraph."
        assert elements[2].text == "Third paragraph."

    def test_wrap_paragraphs_none(self):
        """None input should return empty list."""
        from cis_bench.utils.xhtml_formatter import XHTMLFormatter

        elements = XHTMLFormatter.wrap_paragraphs(None)
        assert elements == []

    def test_wrap_paragraphs_empty_string(self):
        """Empty string should return empty list."""
        from cis_bench.utils.xhtml_formatter import XHTMLFormatter

        elements = XHTMLFormatter.wrap_paragraphs("")
        assert elements == []

    def test_wrap_paragraphs_whitespace_only(self):
        """Whitespace-only input should return empty list."""
        from cis_bench.utils.xhtml_formatter import XHTMLFormatter

        elements = XHTMLFormatter.wrap_paragraphs("   \n\n   ")
        assert elements == []

    def test_wrap_paragraphs_strips_whitespace(self):
        """Paragraph text should have whitespace stripped."""
        from cis_bench.utils.xhtml_formatter import XHTMLFormatter

        text = "  Leading spaces  \n\n  Trailing spaces  "
        elements = XHTMLFormatter.wrap_paragraphs(text)

        assert len(elements) == 2
        assert elements[0].text == "Leading spaces"
        assert elements[1].text == "Trailing spaces"

    def test_wrap_paragraphs_skips_empty_paragraphs(self):
        """Empty paragraphs (just newlines) should be skipped."""
        from cis_bench.utils.xhtml_formatter import XHTMLFormatter

        text = "First\n\n\n\nSecond"  # Extra newlines create empty paragraph
        elements = XHTMLFormatter.wrap_paragraphs(text)

        assert len(elements) == 2
        assert elements[0].text == "First"
        assert elements[1].text == "Second"


class TestXHTMLFormatterWrapSingleParagraph:
    """Tests for wrap_single_paragraph method."""

    def test_wrap_single_paragraph_basic(self):
        """Basic text should create single <p> element."""
        from cis_bench.utils.xhtml_formatter import XHTMLFormatter

        elem = XHTMLFormatter.wrap_single_paragraph("Some text")

        assert elem is not None
        assert elem.text == "Some text"
        assert elem.tag == "{http://www.w3.org/1999/xhtml}p"

    def test_wrap_single_paragraph_none(self):
        """None input should return None."""
        from cis_bench.utils.xhtml_formatter import XHTMLFormatter

        elem = XHTMLFormatter.wrap_single_paragraph(None)
        assert elem is None

    def test_wrap_single_paragraph_empty(self):
        """Empty string should return None."""
        from cis_bench.utils.xhtml_formatter import XHTMLFormatter

        elem = XHTMLFormatter.wrap_single_paragraph("")
        assert elem is None

    def test_wrap_single_paragraph_whitespace(self):
        """Whitespace-only should return None."""
        from cis_bench.utils.xhtml_formatter import XHTMLFormatter

        elem = XHTMLFormatter.wrap_single_paragraph("   ")
        assert elem is None

    def test_wrap_single_paragraph_strips(self):
        """Text should be stripped of whitespace."""
        from cis_bench.utils.xhtml_formatter import XHTMLFormatter

        elem = XHTMLFormatter.wrap_single_paragraph("  text with spaces  ")

        assert elem is not None
        assert elem.text == "text with spaces"


class TestXHTMLFormatterCreateCodeBlock:
    """Tests for create_code_block method."""

    def test_create_code_block_basic(self):
        """Basic code should create <code> element."""
        from cis_bench.utils.xhtml_formatter import XHTMLFormatter

        elem = XHTMLFormatter.create_code_block("#!/bin/bash")

        assert elem.text == "#!/bin/bash"
        assert elem.tag == "{http://www.w3.org/1999/xhtml}code"

    def test_create_code_block_with_language(self):
        """Language parameter should be accepted (for future use)."""
        from cis_bench.utils.xhtml_formatter import XHTMLFormatter

        elem = XHTMLFormatter.create_code_block("print('hello')", language="python")

        assert elem.text == "print('hello')"
        assert elem.tag == "{http://www.w3.org/1999/xhtml}code"

    def test_create_code_block_multiline(self):
        """Multiline code should be preserved."""
        from cis_bench.utils.xhtml_formatter import XHTMLFormatter

        code = "line1\nline2\nline3"
        elem = XHTMLFormatter.create_code_block(code)

        assert elem.text == code
        assert "\n" in elem.text


class TestXHTMLFormatterCreateStrong:
    """Tests for create_strong method."""

    def test_create_strong_basic(self):
        """Basic text should create <strong> element."""
        from cis_bench.utils.xhtml_formatter import XHTMLFormatter

        elem = XHTMLFormatter.create_strong("Important")

        assert elem.text == "Important"
        assert elem.tag == "{http://www.w3.org/1999/xhtml}strong"

    def test_create_strong_empty(self):
        """Empty string should still create element."""
        from cis_bench.utils.xhtml_formatter import XHTMLFormatter

        elem = XHTMLFormatter.create_strong("")

        assert elem.text == ""
        assert elem.tag == "{http://www.w3.org/1999/xhtml}strong"


class TestXHTMLFormatterCreateEmphasis:
    """Tests for create_emphasis method."""

    def test_create_emphasis_basic(self):
        """Basic text should create <em> element."""
        from cis_bench.utils.xhtml_formatter import XHTMLFormatter

        elem = XHTMLFormatter.create_emphasis("Emphasized")

        assert elem.text == "Emphasized"
        assert elem.tag == "{http://www.w3.org/1999/xhtml}em"

    def test_create_emphasis_empty(self):
        """Empty string should still create element."""
        from cis_bench.utils.xhtml_formatter import XHTMLFormatter

        elem = XHTMLFormatter.create_emphasis("")

        assert elem.text == ""
        assert elem.tag == "{http://www.w3.org/1999/xhtml}em"


class TestXHTMLFormatterElementsToXMLString:
    """Tests for elements_to_xml_string method."""

    def test_elements_to_xml_string_single(self):
        """Single element should serialize correctly."""
        from cis_bench.utils.xhtml_formatter import XHTMLFormatter

        elem = XHTMLFormatter.wrap_single_paragraph("Test")
        result = XHTMLFormatter.elements_to_xml_string([elem])

        assert "Test" in result
        # Element may be serialized as <p>, <html:p>, or with namespace prefix
        assert ":p" in result or "<p " in result or "<p>" in result
        assert "http://www.w3.org/1999/xhtml" in result

    def test_elements_to_xml_string_multiple(self):
        """Multiple elements should concatenate."""
        from cis_bench.utils.xhtml_formatter import XHTMLFormatter

        elements = XHTMLFormatter.wrap_paragraphs("First\n\nSecond")
        result = XHTMLFormatter.elements_to_xml_string(elements)

        assert "First" in result
        assert "Second" in result

    def test_elements_to_xml_string_empty_list(self):
        """Empty list should return empty string."""
        from cis_bench.utils.xhtml_formatter import XHTMLFormatter

        result = XHTMLFormatter.elements_to_xml_string([])
        assert result == ""

    def test_elements_to_xml_string_none_list(self):
        """None should be handled (via empty check)."""
        from cis_bench.utils.xhtml_formatter import XHTMLFormatter

        # wrap_paragraphs returns [] for None, so test that flow
        elements = XHTMLFormatter.wrap_paragraphs(None)
        result = XHTMLFormatter.elements_to_xml_string(elements)
        assert result == ""


class TestXHTMLFormatterNamespace:
    """Tests for XHTML namespace handling."""

    def test_xhtml_namespace_constant(self):
        """XHTML_NS should be the standard XHTML namespace."""
        from cis_bench.utils.xhtml_formatter import XHTMLFormatter

        assert XHTMLFormatter.XHTML_NS == "http://www.w3.org/1999/xhtml"

    def test_elements_have_correct_namespace(self):
        """All created elements should use XHTML namespace."""
        from cis_bench.utils.xhtml_formatter import XHTMLFormatter

        ns = XHTMLFormatter.XHTML_NS

        p = XHTMLFormatter.wrap_single_paragraph("test")
        assert p.tag.startswith(f"{{{ns}}}")

        code = XHTMLFormatter.create_code_block("test")
        assert code.tag.startswith(f"{{{ns}}}")

        strong = XHTMLFormatter.create_strong("test")
        assert strong.tag.startswith(f"{{{ns}}}")

        em = XHTMLFormatter.create_emphasis("test")
        assert em.tag.startswith(f"{{{ns}}}")
