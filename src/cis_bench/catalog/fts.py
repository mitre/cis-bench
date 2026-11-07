"""SQLite FTS5 query tokenization and quoting utilities.

The catalog index (``benchmarks_fts``) has text columns and a version column. Every term
is looked up in the text columns as a word prefix ("ubunt" finds Ubuntu). A term shaped
like a version ("v2.1.0", "2.1", "v18") is also matched against the version column from
its start, number by number: "2.1" finds 2.1 and 2.1.3, not 2.10.0 or 1.2.1. A word is also
matched against a whole word of a version ("vNext", "NEXT" in "v1.1.0 NEXT"), so a name
pasted with its version is found. A plain number ("almalinux 8") is never matched against
a version: it means a number in a title.
"""

import re
import unicodedata

TEXT_COLUMNS = ("title", "platform", "community")
VERSION_COLUMN = "version"

_WORD_TOKEN_RE = re.compile(r"[^\W_]+")
# A dotted number with an optional leading v, or a single search word.
_TERM_RE = re.compile(r"[vV]?[0-9]+(?:\.[0-9]+)+|[^\W_]+")
# The numbers of a version-shaped term: "v2.1.0", "2.1", "v18"; not a plain "8" or a word.
_VERSION_TERM_RE = re.compile(r"[vV]?([0-9]+(?:\.[0-9]+)+)|[vV]([0-9]+)")
_LEADING_V_OF_A_NUMBER_RE = re.compile(r"^\s*[vV](?=[0-9])")
_NUMBER_RE = re.compile(r"[0-9]+")

_IN_TEXT = "{" + " ".join(TEXT_COLUMNS) + "}"
_IN_VERSION = "{" + VERSION_COLUMN + "}"


def version_index_text(version: str | None) -> str:
    """The text the index holds for a benchmark's version.

    The leading "v" of a numbered version is dropped ("v2.1.0" -> "2.1.0"), so the index
    tokens are the version's numbers and a query matches with or without the "v".
    """
    return _LEADING_V_OF_A_NUMBER_RE.sub("", version or "")


def _version_numbers(term: str) -> list[str] | None:
    """The numbers of a version-shaped term, or None for any other term."""
    match = _VERSION_TERM_RE.fullmatch(term)
    if match is None:
        return None
    return (match.group(1) or match.group(2)).split(".")


def _terms(query: str) -> list[str]:
    """The search terms of raw user text, NFC-normalized so accented characters stay whole."""
    return _TERM_RE.findall(unicodedata.normalize("NFC", query or ""))


def _in_version(numbers: list[str]) -> str:
    """The version column starts with these numbers, in this order."""
    return f'{_IN_VERSION} : ^"{" ".join(numbers)}"'


def _term_query(term: str) -> str:
    numbers = _version_numbers(term)
    if numbers is None:
        if _NUMBER_RE.fullmatch(term):
            return f'{_IN_TEXT} : "{term}"*'
        return f'({_IN_TEXT} : "{term}"* OR {_IN_VERSION} : "{term}")'

    # In the text columns the term is what the tokenizer makes of it: "v2.1.0" -> v2, 1, 0.
    words = [f'"{word}"*' for word in _WORD_TOKEN_RE.findall(term)]
    in_text = words[0] if len(words) == 1 else f"({' AND '.join(words)})"
    return f"({_IN_TEXT} : {in_text} OR {_in_version(numbers)})"


def build_fts_query(query: str) -> str:
    """Convert raw user search text into a safe SQLite FTS5 query.

    Extracts contiguous non-underscore word tokens (matching SQLite's unicode61 separator
    behavior) and wraps each in double quotes with a trailing prefix wildcard, so
    punctuation and uppercase FTS5 boolean keywords (AND, OR, NOT, NEAR) never trigger
    FTS5 syntax errors. Every term must match; see the module docstring for where each
    kind of term is looked up. Returns an empty string when there is nothing to search for.
    """
    return " AND ".join(_term_query(term) for term in _terms(query))


def build_version_match_query(query: str) -> str:
    """The FTS5 query for the rows a search matches through their version.

    The whole query must match, and at least one of its version-shaped terms must match the
    version column: "kubernetes 2.0.0" names the 2.0.0 releases, while "ubuntu 22.04" names
    none unless a benchmark is at version 22.04. Empty when the query has no such term.
    """
    versions = [
        numbers for term in _terms(query) if (numbers := _version_numbers(term)) is not None
    ]
    if not versions:
        return ""
    return f"{build_fts_query(query)} AND ({' OR '.join(map(_in_version, versions))})"
