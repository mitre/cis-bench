"""Validation of CIS WorkBench benchmark URLs and references.

Every benchmark URL the tool fetches must sit on the WorkBench origin the caller
gives (the CLI passes the validated CIS_BENCH_WORKBENCH_URL) and name a numeric
benchmark, so a value from a catalog page, a user argument or an input file can
never send the session cookies somewhere else.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlsplit, urlunsplit

_BENCHMARK_PATH_RE = re.compile(r"^/benchmarks/([0-9]+)(?:/.*)?$")


def _has_dot_segment(path: str) -> bool:
    """True if any path segment is ``..`` once percent-encoding is decoded."""
    return any(segment == ".." for segment in unquote(path).split("/"))


def normalize_benchmark_url(
    raw_url: str, *, base_url: str, expected_benchmark_id: str | None = None
) -> tuple[str, str]:
    """Resolve, validate, and canonicalize a CIS WorkBench benchmark URL.

    Args:
        raw_url: Relative or absolute benchmark href/URL
        base_url: The WorkBench origin (already validated), e.g. https://workbench.cisecurity.org
        expected_benchmark_id: Optional catalog benchmark ID that the URL must match

    Returns:
        Tuple of (benchmark_id, canonical_url) where canonical_url is
        ``<workbench_base_url>/benchmarks/<digits>``

    Raises:
        ValueError: If raw_url is off-origin, uses another scheme, contains userinfo, control
            characters or a ``..`` segment (in any encoding), lacks a numeric ``/benchmarks/<digits>``
            path, or mismatches expected_benchmark_id
    """
    if not isinstance(raw_url, str):
        raise ValueError("Invalid benchmark URL: expected string")

    cleaned = raw_url.strip()
    if not cleaned or cleaned.startswith(("@", "//")) or "\\" in cleaned:
        raise ValueError(f"Invalid benchmark URL '{raw_url}'")
    # urlsplit silently strips embedded tabs and newlines, so reject control characters first
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in cleaned):
        raise ValueError(f"Invalid benchmark URL '{raw_url}': control characters are not allowed")

    base_parsed = urlsplit(base_url)

    raw_parsed = urlsplit(cleaned)
    # Dot segments are rejected on the input as written (including percent-encoded forms),
    # before urljoin can collapse them into something that looks legitimate.
    if _has_dot_segment(raw_parsed.path):
        raise ValueError(
            f"Invalid benchmark URL '{raw_url}': must match configured WorkBench origin {base_url}"
        )
    if raw_parsed.scheme == "" and raw_parsed.netloc == "":
        resolved = urljoin(f"{base_url}/", cleaned)
    else:
        resolved = cleaned

    parsed = urlsplit(resolved)
    if (
        parsed.scheme.lower() != base_parsed.scheme.lower()
        or parsed.username is not None
        or parsed.password is not None
        or "@" in parsed.netloc
        or parsed.netloc.lower() != base_parsed.netloc.lower()
        or _has_dot_segment(parsed.path)
    ):
        raise ValueError(
            f"Invalid benchmark URL '{raw_url}': must match configured WorkBench origin {base_url}"
        )

    path_match = _BENCHMARK_PATH_RE.match(parsed.path)
    if not path_match:
        raise ValueError(f"Invalid benchmark URL '{raw_url}': path must match /benchmarks/<digits>")

    benchmark_id = path_match.group(1)
    if expected_benchmark_id is not None and benchmark_id != expected_benchmark_id:
        raise ValueError(
            f"Invalid benchmark URL '{raw_url}': benchmark ID '{benchmark_id}' "
            f"does not match '{expected_benchmark_id}'"
        )

    return benchmark_id, f"{base_url}/benchmarks/{benchmark_id}"


def resolve_benchmark_reference(reference: str, *, base_url: str) -> tuple[str, str]:
    """Resolve a user-supplied benchmark reference, a numeric ID or a URL, to a canonical URL.

    Returns:
        Tuple of (benchmark_id, canonical_url)

    Raises:
        ValueError: If the reference is neither all digits nor a valid WorkBench benchmark URL
    """
    cleaned = reference.strip()
    if is_benchmark_id(cleaned):
        return normalize_benchmark_url(f"/benchmarks/{cleaned}", base_url=base_url)
    return normalize_benchmark_url(cleaned, base_url=base_url)


def is_benchmark_id(reference: str) -> bool:
    """Whether user text is a benchmark ID: ASCII digits only (str.isdigit accepts more)."""
    cleaned = reference.strip()
    return cleaned.isascii() and cleaned.isdigit()


def _workbench_id(value: object, what: str) -> str:
    """Return value as a WorkBench numeric id, or raise ValueError.

    Ids come from user input and from WorkBench's own JSON; either way they go into a URL
    path, so only ASCII digits are accepted (no separators, dot segments or whitespace).
    """
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"Invalid {what}: {value!r} is not a numeric WorkBench id")
    text = str(value)
    if not (text.isascii() and text.isdigit()):
        raise ValueError(f"Invalid {what}: {value!r} is not a numeric WorkBench id")
    return text


def catalog_listing_url(*, base_url: str) -> str:
    """The catalog listing page on the given WorkBench origin."""
    return f"{base_url}/benchmarks"


def navtree_url(benchmark_id: object, *, base_url: str) -> str:
    """The navigation-tree API for one benchmark."""
    benchmark = _workbench_id(benchmark_id, "benchmark id")
    return f"{base_url}/api/v1/benchmarks/{benchmark}/navtree"


def recommendation_url(section_id: object, recommendation_id: object, *, base_url: str) -> str:
    """One recommendation's page, from the section and recommendation ids in the navtree."""
    section = _workbench_id(section_id, "section id")
    recommendation = _workbench_id(recommendation_id, "recommendation id")
    return f"{base_url}/sections/{section}/recommendations/{recommendation}"


# Query parameters that say which page was asked for and nothing else. The redirect URLs of
# the SSO handshake carry state and code parameters, which must never be printed.
_PRINTABLE_QUERY_KEYS = frozenset({"page"})


def printable_url(url: str) -> str:
    """url as it may be shown in a log line or an error message.

    The fragment and any user name or password are dropped, and of the query only the
    parameters known to be harmless are kept (the catalog listing's page number, when it is
    a number).
    """
    parts = urlsplit(url)
    host = parts.netloc.rpartition("@")[2]
    kept = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key in _PRINTABLE_QUERY_KEYS and value.isdigit()
    ]
    return urlunsplit((parts.scheme, host, parts.path, urlencode(kept), ""))


def without_query_strings(text: str) -> str:
    """text with the query string and fragment removed from every URL or path it quotes (a
    library's error message, for example), so that nothing a redirect carried is printed."""
    return re.sub(r"(?<=[\w/%.~-])[?#][^\s'\")]*", "", text)
