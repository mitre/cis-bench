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


class TestLinksAndEntities:
    def test_a_link_whose_text_is_its_address_is_written_as_text_and_address(self):
        html = '<p>See <a href="https://example.invalid/g">https://example.invalid/g</a>.</p>'

        assert (
            html_to_markdown(html) == "See [https://example.invalid/g](https://example.invalid/g)."
        )


class TestProseAngleBracketsAsText:
    """A placeholder in prose is written so a renderer with raw HTML on shows it as text; a
    placeholder in code and an autolink are left as they are."""

    def test_a_placeholder_in_a_sentence_is_escaped_and_one_in_a_code_span_is_not(self):
        from cis_bench.utils.markdown_text import prose_angle_brackets_as_text

        text = "Set deny=<n> and run `deny=<n>` here."

        assert prose_angle_brackets_as_text(text) == "Set deny=&lt;n> and run `deny=<n>` here."

    def test_a_fence_is_left_as_it_is(self):
        from cis_bench.utils.markdown_text import prose_angle_brackets_as_text

        text = "Run:\n\n```\n# chage --mindays <N> <user>\n```\n\nfor each <user>."

        assert prose_angle_brackets_as_text(text) == (
            "Run:\n\n```\n# chage --mindays <N> <user>\n```\n\nfor each &lt;user>."
        )

    def test_placeholders_in_list_items_quotes_and_continuation_lines_are_escaped(self):
        from cis_bench.utils.markdown_text import prose_angle_brackets_as_text

        text = "- item with <PATH TO FILE> inside\n  continued <x> line\n\n> quoted <y> text"

        assert prose_angle_brackets_as_text(text) == (
            "- item with &lt;PATH TO FILE> inside\n  continued &lt;x> line\n\n> quoted &lt;y> text"
        )

    def test_a_line_that_is_only_a_placeholder_no_longer_hides_the_lines_after_it(self):
        from cis_bench.utils.markdown_text import prose_angle_brackets_as_text

        text = "<PATH TO FILE>\nfollowing <z> line"

        assert prose_angle_brackets_as_text(text) == "&lt;PATH TO FILE>\nfollowing &lt;z> line"

    def test_an_autolink_and_a_placeholder_in_link_text_are_handled_by_the_parser(self):
        from cis_bench.utils.markdown_text import prose_angle_brackets_as_text

        text = "See <https://example.invalid/g> and [deny=<n>](https://example.invalid/d)."

        assert prose_angle_brackets_as_text(text) == (
            "See <https://example.invalid/g> and [deny=&lt;n>](https://example.invalid/d)."
        )

    def test_text_without_angle_brackets_is_unchanged(self):
        from cis_bench.utils.markdown_text import prose_angle_brackets_as_text

        text = "Plain **bold** text\n\n- one\n- two"

        assert prose_angle_brackets_as_text(text) == text

    def test_the_result_renders_every_placeholder_as_text(self):
        from markdown_it import MarkdownIt

        from cis_bench.utils.markdown_text import prose_angle_brackets_as_text

        text = "Set deny=<n>.\n\n<PATH TO FILE>\nnext <z>\n\n```\n<N>\n```"

        html = MarkdownIt("commonmark").render(prose_angle_brackets_as_text(text))

        assert "deny=&lt;n&gt;" in html and "&lt;PATH TO FILE&gt;" in html
        assert "next &lt;z&gt;" in html and "<code>&lt;N&gt;\n</code>" in html


class TestClosedFences:
    def test_a_fence_left_open_is_closed_at_the_end(self):
        from cis_bench.utils.markdown_text import closed_fences

        assert closed_fences("Run:\n\n```\n# stat <path>") == "Run:\n\n```\n# stat <path>\n```"

    def test_a_closed_fence_is_left_as_it_is(self):
        from cis_bench.utils.markdown_text import closed_fences

        text = "Run:\n\n```\n# stat <path>\n```\n\nthen <user>"

        assert closed_fences(text) == text

    def test_the_closing_marker_repeats_the_opening_one(self):
        from cis_bench.utils.markdown_text import closed_fences

        assert closed_fences("- item\n\n  ~~~~\n  code") == "- item\n\n  ~~~~\n  code\n  ~~~~"

    def test_the_closed_text_renders_as_one_code_block_followed_by_prose(self):
        from markdown_it import MarkdownIt

        from cis_bench.utils.markdown_text import closed_fences

        document = closed_fences("```\n# stat <path>") + "\n\n### Next\n\nprose <user>"

        html = MarkdownIt("commonmark").render(document)

        assert "<code># stat &lt;path&gt;\n</code>" in html
        assert "<h3>Next</h3>" in html


class TestProseAngleBracketsInHarderMarkdown:
    """Cases where the parser's view of a line is not the line itself."""

    def test_a_heading_with_closing_markers(self):
        from cis_bench.utils.markdown_text import prose_angle_brackets_as_text

        assert prose_angle_brackets_as_text("## Configure <user> ##") == "## Configure &lt;user> ##"

    def test_a_placeholder_in_an_image_label(self):
        from cis_bench.utils.markdown_text import prose_angle_brackets_as_text

        assert prose_angle_brackets_as_text("See ![<user> icon](icon.png) here <x>.") == (
            "See ![&lt;user> icon](icon.png) here &lt;x>."
        )

    def test_a_hard_break_and_a_tab_indented_continuation(self):
        from cis_bench.utils.markdown_text import prose_angle_brackets_as_text

        text = "first <a>  \n\tsecond <b>"

        assert prose_angle_brackets_as_text(text) == "first &lt;a>  \n\tsecond &lt;b>"


class TestClosedFencesInContainers:
    def test_a_closed_fence_in_a_blockquote_is_left_as_it_is(self):
        from cis_bench.utils.markdown_text import closed_fences

        text = "> ```\n> code <x>\n> ```"

        assert closed_fences(text) == text

    def test_an_open_fence_in_a_blockquote_is_closed_inside_the_quote(self):
        from cis_bench.utils.markdown_text import closed_fences

        assert closed_fences("> ```\n> code <x>") == "> ```\n> code <x>\n> ```"

    def test_a_marker_followed_by_text_is_content_not_a_closing_fence(self):
        from markdown_it import MarkdownIt

        from cis_bench.utils.markdown_text import closed_fences

        closed = closed_fences("```\n```not-a-close")

        assert closed == "```\n```not-a-close\n```"
        html = MarkdownIt("commonmark").render(closed + "\n\n### Next\n\ntext")
        assert "<h3>Next</h3>" in html

    def test_a_fence_opened_on_a_list_item_line_is_closed_at_the_item_indent(self):
        from markdown_it import MarkdownIt

        from cis_bench.utils.markdown_text import closed_fences

        closed = closed_fences("- ```\n  code <x>")

        assert closed == "- ```\n  code <x>\n  ```"
        html = MarkdownIt("commonmark").render(closed + "\n\n### Next\n\ntext")
        assert "<h3>Next</h3>" in html and "code &lt;x&gt;" in html


class TestProseAngleBracketsWithReferencesAndTabs:
    def test_a_reference_link_label_is_a_link_not_html(self):
        from cis_bench.utils.markdown_text import prose_angle_brackets_as_text

        text = "See [the guide][<ref>] and <x>.\n\n[<ref>]: https://example.invalid/g"

        assert prose_angle_brackets_as_text(text) == (
            "See [the guide][<ref>] and &lt;x>.\n\n[<ref>]: https://example.invalid/g"
        )

    def test_a_tab_indented_list_continuation(self):
        from cis_bench.utils.markdown_text import prose_angle_brackets_as_text

        assert prose_angle_brackets_as_text("- item\n\t<user> next") == "- item\n\t&lt;user> next"

    def test_a_tab_after_a_quote_marker(self):
        from cis_bench.utils.markdown_text import prose_angle_brackets_as_text

        assert prose_angle_brackets_as_text(">\t<user> quoted") == ">\t&lt;user> quoted"


class TestClosedFencesMidField:
    def test_a_fence_the_list_item_ends_is_not_closed_again_after_the_prose(self):
        from cis_bench.utils.markdown_text import closed_fences

        text = "- item\n\n  ```\n  code <x>\n\nprose after the list"

        assert closed_fences(text) == text
