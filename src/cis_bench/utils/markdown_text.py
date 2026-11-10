"""The Markdown form of benchmark text.

WorkBench gives a recommendation's text as Markdown. A copy the v1 scraper saved holds the
page's rendered HTML instead; this module turns that HTML into the Markdown WorkBench
itself writes, so a loaded copy reads the same whichever scraper saved it.
"""

import warnings
from typing import Any

from bs4 import MarkupResemblesLocatorWarning
from markdown_it import MarkdownIt
from markdown_it.rules_inline import html_inline as _html_inline_rule
from markdown_it.rules_inline.state_inline import StateInline
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


def _recording_html_inline(state: StateInline, silent: bool) -> bool:
    """The library's own raw-HTML rule, recording where in the inline text each token sits."""
    start = state.pos
    if not _html_inline_rule(state, silent):
        return False
    if not silent:  # a silent run only measures (e.g. a link label); the real run records
        state.env.setdefault("html_inline_spans", []).append((start, state.pos))
    return True


# CommonMark as GitHub and MkDocs read it: raw HTML on, so a bare <word> in prose is a tag.
_commonmark = MarkdownIt("commonmark")
_commonmark.inline.ruler.at("html_inline", _recording_html_inline)


def prose_angle_brackets_as_text(markdown: str) -> str:
    """The Markdown with every angle-bracket token a CommonMark renderer would read as raw
    HTML, outside code, written as text: its ``<`` becomes ``&lt;``.

    The stored text has no HTML; an angle-bracket token in prose is a placeholder such as
    <user>, which a renderer with raw HTML on (GitHub, MkDocs) would otherwise show as
    nothing. The parser decides what is HTML: a placeholder inside a code span or a fence is
    left as it is (there the entity would show literally), and an autolink such as
    <https://example.invalid/> is a link, not HTML. A line that is a tag on its own starts an
    HTML block, which swallows the lines after it; its first ``<`` is escaped, and the pass
    repeats until the renderer sees no raw HTML.
    """
    lines = markdown.split("\n")
    # Each pass escapes at least one '<' or ends, so the passes are bounded by their number.
    for _ in range(markdown.count("<") + 1):
        edits: list[tuple[int, int]] = []  # (line, column) of each '<' to write as &lt;
        for token in _commonmark.parse("\n".join(lines)):
            if token.type == "html_block" and token.map is not None:
                first = token.map[0]
                edits.append((first, lines[first].index("<")))
            elif token.type == "inline" and token.map is not None:
                # Tokenize this token's text once more, with its own state, so the spans the
                # rule records are this token's alone.
                env: dict[str, Any] = {}
                _commonmark.inline.tokenize(StateInline(token.content, _commonmark, env, []))
                spans: list[tuple[int, int]] = env.get("html_inline_spans", [])
                if not spans:
                    continue
                # The inline text's lines are the source lines without their leading
                # indentation and list or quote markers: each is a suffix of its source line.
                content_lines = token.content.split("\n")
                starts: list[int] = []
                offset = 0
                for i, content_line in enumerate(content_lines):
                    # Trailing whitespace is left out of the comparison: the parser trims it,
                    # and no '<' sits in it.
                    source_line = lines[token.map[0] + i].rstrip()
                    if not source_line.endswith(content_line.rstrip()):
                        raise ValueError(
                            f"line {token.map[0] + i + 1}: the parser's text {content_line!r} "
                            f"is not the end of the source line {source_line!r}"
                        )
                    starts.append(offset)
                    offset += len(content_line) + 1
                for span_start, _span_end in spans:
                    i = max(k for k, line_start in enumerate(starts) if line_start <= span_start)
                    column = span_start - starts[i]
                    source_line = lines[token.map[0] + i].rstrip()
                    content_line = content_lines[i].rstrip()
                    edits.append((token.map[0] + i, column + len(source_line) - len(content_line)))
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
    out. The parser decides whether the text ends inside a fence; the closing marker repeats
    the opening one (its characters and indentation) on a new line. Text whose fences are
    closed is returned as it is.
    """
    lines = markdown.split("\n")
    for token in _commonmark.parse(markdown):
        if token.type != "fence" or token.map is None:
            continue
        first, last = token.map[0], token.map[1] - 1
        if last > first and lines[last].strip().startswith(token.markup):
            continue  # closed by its own marker
        opening = lines[first]
        indent = opening[: len(opening) - len(opening.lstrip())]
        return markdown + "\n" + indent + token.markup
    return markdown
