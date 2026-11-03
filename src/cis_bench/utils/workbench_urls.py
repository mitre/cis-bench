"""Validation of CIS WorkBench benchmark URLs and references.

Every benchmark URL the tool fetches must sit on the configured WorkBench origin
and name a numeric benchmark, so a value from a catalog page, a user argument or
an input file can never send the session cookies somewhere else.
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urljoin, urlsplit

from cis_bench.config import Config

_BENCHMARK_PATH_RE = re.compile(r"^/benchmarks/([0-9]+)(?:/.*)?$")


def _has_dot_segment(path: str) -> bool:
    """True if any path segment is ``..`` once percent-encoding is decoded."""
    return any(segment == ".." for segment in unquote(path).split("/"))


def normalize_benchmark_url(
    raw_url: str, *, expected_benchmark_id: str | None = None
) -> tuple[str, str]:
    """Resolve, validate, and canonicalize a CIS WorkBench benchmark URL.

    Args:
        raw_url: Relative or absolute benchmark href/URL
        expected_benchmark_id: Optional catalog benchmark ID that the URL must match

    Returns:
        Tuple of (benchmark_id, canonical_url) where canonical_url is
        ``<workbench_base_url>/benchmarks/<digits>``

    Raises:
        ValueError: If raw_url is off-origin, uses another scheme, contains userinfo, control
            characters or a ``..`` segment (in any encoding), lacks a numeric ``/benchmarks/<digits>``
            path, or mismatches expected_benchmark_id
        ConfigurationError: If CIS_BENCH_WORKBENCH_URL itself is invalid
    """
    if not isinstance(raw_url, str):
        raise ValueError("Invalid benchmark URL: expected string")

    cleaned = raw_url.strip()
    if not cleaned or cleaned.startswith(("@", "//")) or "\\" in cleaned:
        raise ValueError(f"Invalid benchmark URL '{raw_url}'")
    # urlsplit silently strips embedded tabs and newlines, so reject control characters first
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in cleaned):
        raise ValueError(f"Invalid benchmark URL '{raw_url}': control characters are not allowed")

    base_url = Config.get_workbench_base_url()
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


def resolve_benchmark_reference(reference: str) -> tuple[str, str]:
    """Resolve a user-supplied benchmark reference, a numeric ID or a URL, to a canonical URL.

    Returns:
        Tuple of (benchmark_id, canonical_url)

    Raises:
        ValueError: If the reference is neither all digits nor a valid WorkBench benchmark URL
    """
    cleaned = reference.strip()
    # str.isdigit accepts non-ASCII digits; a benchmark ID is ASCII digits only
    if cleaned.isascii() and cleaned.isdigit():
        return normalize_benchmark_url(f"/benchmarks/{cleaned}")
    return normalize_benchmark_url(cleaned)
