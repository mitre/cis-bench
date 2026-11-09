"""Tests for the Markdown form of benchmark text."""

import warnings

import pytest

from cis_bench.utils.markdown_text import html_to_markdown, unix_line_breaks


class TestHtmlToMarkdown:
    """HTML a v1-era copy holds becomes the Markdown WorkBench itself gives.

    The stored v2 text uses ATX headings, "-" bullets, bare fences and no escaped "_" or
    "*", so the conversion writes those shapes.
    """

    def test_paragraphs_are_set_apart_by_a_blank_line(self):
        assert html_to_markdown("<p>First.</p><p>Second.</p>") == "First.\n\nSecond."

    def test_inline_markup_becomes_markdown(self):
        html = '<p>See <strong>bold</strong>, <em>em</em>, <code>ls -la</code> and <a href="https://example.invalid/g">the guide</a>.</p>'

        assert (
            html_to_markdown(html)
            == "See **bold**, *em*, `ls -la` and [the guide](https://example.invalid/g)."
        )

    def test_a_code_block_is_fenced_with_its_text_decoded(self):
        html = "<pre><code># useradd &lt;user&gt; -G &lt;group&gt;\n# chmod 0644 &quot;/etc/x&quot;</code></pre>"

        assert (
            html_to_markdown(html) == '```\n# useradd <user> -G <group>\n# chmod 0644 "/etc/x"\n```'
        )

    def test_lists_use_dash_bullets_and_numbers(self):
        html = "<ul><li>one</li><li>two</li></ul><ol><li>first</li><li>second</li></ol>"

        assert html_to_markdown(html) == "- one\n- two\n\n1. first\n2. second"

    def test_headings_are_atx(self):
        assert html_to_markdown("<h2>Audit</h2><p>text</p>") == "## Audit\n\ntext"

    def test_a_table_becomes_a_pipe_table(self):
        html = "<table><tr><th>Setting</th><th>Value</th></tr><tr><td>enabled</td><td>no</td></tr></table>"

        assert html_to_markdown(html) == "| Setting | Value |\n| --- | --- |\n| enabled | no |"

    def test_underscores_and_asterisks_in_text_are_not_escaped(self):
        html = "<p>Set net.ipv4.ip_forward to 0; a glob such as *.conf matches.</p>"

        assert (
            html_to_markdown(html) == "Set net.ipv4.ip_forward to 0; a glob such as *.conf matches."
        )

    def test_text_without_tags_is_returned_as_it_is(self):
        assert html_to_markdown("A") == "A"

    def test_a_field_that_is_only_a_url_converts_without_a_parser_warning(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert (
                html_to_markdown("https://example.invalid/guide") == "https://example.invalid/guide"
            )

    def test_leading_and_trailing_blank_lines_are_dropped(self):
        assert html_to_markdown("\n<p>Only.</p>\n") == "Only."


class TestUnixLineBreaks:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("a\r\nb", "a\nb"),
            ("a\rb", "a\nb"),
            ("a\nb", "a\nb"),
            ("a\r\n\r\nb\rc\nd", "a\n\nb\nc\nd"),
            ("", ""),
        ],
    )
    def test_every_line_break_is_a_newline(self, text, expected):
        assert unix_line_breaks(text) == expected
