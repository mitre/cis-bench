"""SQLite FTS5 query tokenization and quoting utilities."""

import re


def build_fts_query(query: str) -> str:
    """Convert raw user search text into a safe SQLite FTS5 prefix query.

    Strips non-word punctuation (and underscores, which SQLite's unicode61
    tokenizer treats as separators) into whitespace, splits into tokens, and
    wraps each token in double quotes with a trailing prefix wildcard so
    punctuation and uppercase FTS5 boolean keywords (AND, OR, NOT, NEAR) never
    trigger FTS5 syntax errors.
    """
    if not query or not query.strip():
        return ""

    cleaned = re.sub(r"[^\w\s]|_", " ", query, flags=re.UNICODE)
    terms = cleaned.split()
    if not terms:
        return ""

    return " ".join(f'"{term}"*' for term in terms)
