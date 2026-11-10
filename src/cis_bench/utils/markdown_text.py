"""The Markdown form of benchmark text.

WorkBench gives a recommendation's text as Markdown. A copy the v1 scraper saved holds the
page's rendered HTML instead; this module turns that HTML into the Markdown WorkBench
itself writes, so a loaded copy reads the same whichever scraper saved it.
"""

import re
import warnings

from bs4 import MarkupResemblesLocatorWarning
from markdown_it import MarkdownIt
from markdown_it.rules_inline import html_inline as _html_inline_rule
from markdown_it.rules_inline import image as _image_rule
from markdown_it.rules_inline.state_inline import StateInline
from markdown_it.token import Token
from markdownify import ATX, MarkdownConverter

# The shapes the stored WorkBench Markdown uses (counted over the cached copies):
# ATX headings, "-" bullets, bare fences, links as [text](url) and never <url> (3 of 484
# URLs), and no "_" or "*" escaped in text (2,711 fields with a bare underscore, none
# escaped), so converted text looks like the rest.
_converter = MarkdownConverter(
    heading_style=ATX,
    bullets="-",
    autolinks=False,
    escape_asterisks=False,
    escape_underscores=False,
)


def html_to_markdown(html: str) -> str:
    """The Markdown for HTML a v1-era copy holds.

    Words, entities (``&lt;user&gt;`` is the placeholder ``<user>``), paragraphs, code
    blocks, lists, tables, emphasis and links are kept; leading and trailing blank lines
    are dropped. Text with no tags comes back as it is.
    """
    # A field that is only a URL or a path makes bs4 warn that the input looks like a
    # locator; here it is content, so that one warning is not wanted.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", MarkupResemblesLocatorWarning)
        return _converter.convert(html)


def unix_line_breaks(text: str) -> str:
    """The text with every line break as ``\\n`` (WorkBench's Markdown comes with ``\\r\\n``)."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def without_blank_boundary_lines(markdown: str) -> str:
    """The Markdown without the blank lines before its first and after its last block.

    The lines kept are as written, their indentation included: a text that opens with an
    indented code block keeps the indentation of its first line, which ``str.strip`` would
    take away. A blank line is one of spaces and tabs alone, as in Markdown (a line of
    other whitespace is text). The parser decides where the last block ends: a fence or
    HTML block left open runs to the end of the text, so the blank lines inside it are its
    content and stay.
    """
    lines = markdown.split("\n")
    content = [index for index, line in enumerate(lines) if line.strip(" \t")]
    if not content:
        return ""
    end = content[-1] + 1
    for token in _commonmark.parse(markdown):
        if token.map is not None:
            end = max(end, token.map[1])
    return "\n".join(lines[content[0] : end])


def _recording_html_inline(state: StateInline, silent: bool) -> bool:
    """The library's own raw-HTML rule; the token it pushes remembers its text and place."""
    start = state.pos
    if not _html_inline_rule(state, silent):
        return False
    if not silent:  # a silent run only measures (e.g. a link label) and pushes no token
        state.tokens[-1].meta["raw_html_span"] = (state.src, start, state.pos)
    return True


def _recording_image(state: StateInline, silent: bool) -> bool:
    """The library's own image rule; the token it pushes remembers where its label starts
    (after the two characters ``![``), so raw HTML inside the label can be placed."""
    start = state.pos
    if not _image_rule(state, silent):
        return False
    if not silent:
        state.tokens[-1].meta["label_offset"] = start + 2
    return True


# CommonMark as GitHub and MkDocs read it: raw HTML on, so a bare <word> in prose is a tag.
_commonmark = MarkdownIt("commonmark")
_commonmark.inline.ruler.at("html_inline", _recording_html_inline)
_commonmark.inline.ruler.at("image", _recording_image)

_CLOSING_HEADING_MARKERS = re.compile(r"[ \t]+#+$")
_LIST_MARKER = re.compile(r"[-+*]|\d+[.)]")


def _raw_html_spans(children: list[Token] | None, content: str) -> list[tuple[int, int]]:
    """Where in an inline token's text the parser found raw HTML, as (start, end)."""
    spans: list[tuple[int, int]] = []
    for child in children or []:
        if child.type == "image":
            # An image's label is parsed as text of its own, starting where the rule recorded.
            at = child.meta["label_offset"]
            spans.extend(
                (at + start, at + end)
                for start, end in _raw_html_spans(child.children, child.content)
            )
        elif child.type == "html_inline":
            _src, start, end = child.meta["raw_html_span"]
            spans.append((start, end))
    return spans


def _source_column(source_line: str, content_line: str, column: int) -> int:
    """The column in the source line of a column in the parser's text of that line.

    The parser's line is the source line without its leading indentation and list or quote
    markers (a tab it consumed in part is replaced by spaces) and, on a heading, without
    closing # markers; whitespace at either end is left out of the comparison, as no '<'
    sits in it.
    """
    source, content = source_line.rstrip(), content_line.strip()
    for candidate in (source, _CLOSING_HEADING_MARKERS.sub("", source)):
        if candidate.endswith(content):
            leading = len(content_line) - len(content_line.lstrip())
            return len(candidate) - len(content) + (column - leading)
    raise ValueError(f"the parser's text {content!r} is not the end of the source line {source!r}")


def prose_angle_brackets_as_text(markdown: str) -> str:
    """The Markdown with every angle-bracket token a CommonMark renderer would read as raw
    HTML, outside code, written as text: its ``<`` becomes ``&lt;``.

    The stored text has no HTML; an angle-bracket token in prose is a placeholder such as
    <user>, which a renderer with raw HTML on (GitHub, MkDocs) would otherwise show as
    nothing. The parser decides what is HTML: a placeholder inside a code span or a fence is
    left as it is (there the entity would show literally), and an autolink such as
    <https://example.invalid/> or a link label is a link, not HTML. A line that is a tag on
    its own starts an HTML block, which swallows the lines after it; its first ``<`` is
    escaped, and the pass repeats until the renderer sees no raw HTML.
    """
    lines = markdown.split("\n")
    # Each pass escapes at least one '<' or ends, so the passes are bounded by their number.
    for _ in range(markdown.count("<") + 1):
        edits: set[tuple[int, int]] = set()  # (line, column) of each '<' to write as &lt;
        for token in _commonmark.parse("\n".join(lines)):
            if token.map is None:
                continue
            if token.type == "html_block":
                first = token.map[0]
                edits.add((first, lines[first].index("<")))
            elif token.type == "inline":
                spans = _raw_html_spans(token.children, token.content)
                if not spans:
                    continue
                content_lines = token.content.split("\n")
                line_starts: list[int] = []
                offset = 0
                for content_line in content_lines:
                    line_starts.append(offset)
                    offset += len(content_line) + 1
                for span_start, _span_end in spans:
                    i = max(
                        k for k, line_start in enumerate(line_starts) if line_start <= span_start
                    )
                    line_no = token.map[0] + i
                    column = _source_column(
                        lines[line_no], content_lines[i], span_start - line_starts[i]
                    )
                    edits.add((line_no, column))
        if not edits:
            return "\n".join(lines)
        for line_no, column in sorted(edits, reverse=True):
            line = lines[line_no]
            if line[column] != "<":
                raise ValueError(f"line {line_no + 1}, column {column + 1}: expected '<'")
            lines[line_no] = line[:column] + "&lt;" + line[column + 1 :]
    raise ValueError("the text still reads as raw HTML after escaping every token")


def closed_fences(markdown: str) -> str:
    """The Markdown with a fence it ends inside closed, so that in a document made of several
    texts it cannot swallow the text that follows it.

    A stored field sometimes opens a code fence and never closes it; on its own it reads as
    code to the end, but written into a larger document it would turn the next fields inside
    out. The parser decides: a closed fence's lines are its opening marker, its content and
    its closing marker, an open one's end with its content; only a fence that runs to the
    end of the text is closed here (a list or quote ends one before that by itself). The
    closing marker repeats the opening one, after the same quote markers and indentation (a
    list marker on the opening line becomes the item's indent). Text whose fences are closed
    is returned as it is.
    """
    lines = markdown.split("\n")
    last_line = len(lines) - (1 if lines[-1] == "" else 0)
    for token in _commonmark.parse(markdown):
        if token.type != "fence" or token.map is None:
            continue
        # The parser ends each content line with a newline, except the last line of a text
        # that has none.
        content = token.content
        content_lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        if content_lines == token.map[1] - token.map[0] - 2:
            continue  # opening marker, content, closing marker
        if token.map[1] < last_line:
            continue  # ended by the list or quote around it, with text after it
        opening = lines[token.map[0]]
        prefix = opening[: opening.index(token.markup)]
        prefix = _LIST_MARKER.sub(lambda m: " " * len(m.group()), prefix)
        return markdown + "\n" + prefix + token.markup
    return markdown
