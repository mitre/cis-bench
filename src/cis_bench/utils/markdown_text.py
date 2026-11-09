"""The Markdown form of benchmark text.

WorkBench gives a recommendation's text as Markdown. A copy the v1 scraper saved holds the
page's rendered HTML instead; this module turns that HTML into the Markdown WorkBench
itself writes, so a loaded copy reads the same whichever scraper saved it.
"""

import warnings

from bs4 import MarkupResemblesLocatorWarning
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
