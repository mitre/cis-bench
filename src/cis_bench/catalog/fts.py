"""SQLite FTS5 query tokenization and quoting utilities."""

import re
import unicodedata

_WORD_TOKEN_RE = re.compile(r"[^\W_]+")


def build_fts_query(query: str) -> str:
    """Convert raw user search text into a safe SQLite FTS5 prefix query.

    Normalizes Unicode to NFC so decomposed accented characters stay intact,
    extracts contiguous non-underscore word tokens (matching SQLite's unicode61
    separator behavior), and wraps each token in double quotes with a trailing
    prefix wildcard so punctuation and uppercase FTS5 boolean keywords (AND,
    OR, NOT, NEAR) never trigger FTS5 syntax errors.
    """
    if not query or not query.strip():
        return ""

    normalized = unicodedata.normalize("NFC", query)
    terms = _WORD_TOKEN_RE.findall(normalized)
    if not terms:
        return ""

    return " ".join(f'"{term}"*' for term in terms)
