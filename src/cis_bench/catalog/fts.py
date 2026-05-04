import re


def build_fts_query(query: str) -> str:
    """
    Convert a user query into a safe FTS5 query.

    - Removes characters that break FTS5 syntax (e.g. '.', ':', etc.)
    - Splits into tokens
    - Applies prefix matching (*) to each term

    Note:
        This may slightly change semantics for inputs like "20.04",
        which becomes "20* 04*".
    """
    if not query or not query.strip():
        return ""

    # Replace only problematic FTS characters
    # Keep alphanumerics, replace others with space
    cleaned = re.sub(r"[^\w\s]", " ", query, flags=re.UNICODE)

    terms = cleaned.split()

    # Note: FTS5 doesn't support leading wildcards (*word)
    # Only trailing wildcards work (word*)
    return " ".join(f"{t}*" for t in terms)
