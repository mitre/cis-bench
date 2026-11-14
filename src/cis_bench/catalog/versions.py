"""Ordering of CIS WorkBench benchmark version strings.

WorkBench versions are free text. The catalog holds forms such as ``v1.0.0``,
``v1.0.0.1``, ``v8``, ``v7.1.0 (vNext)``, ``v1.1.0 NEXT`` and labels with no
number at all (``vNext``, ``vDev``, ``vOLD DO NOT USE``). Ordering uses the
leading dotted number and ignores any trailing label; strings without a leading
number are "unversioned" and sort below every numbered version, tying with each
other.
"""

from __future__ import annotations

import re

_LEADING_VERSION_RE = re.compile(r"^\s*v?(\d+(?:\.\d+)*)", re.IGNORECASE)

VersionTuple = tuple[int, ...]
VersionSortKey = tuple[int, VersionTuple]


def parse_version(raw: str | None) -> VersionTuple | None:
    """Return the leading dotted number of ``raw`` as a tuple of ints, or None.

    ``"v7.1.0 (vNext)"`` -> ``(7, 1, 0)``; ``"vNext"`` -> ``None``.
    """
    if raw is None:
        return None
    match = _LEADING_VERSION_RE.match(raw)
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def version_sort_key(raw: str | None) -> VersionSortKey:
    """Sort key: numbered versions order component-wise above all unversioned strings."""
    parsed = parse_version(raw)
    if parsed is None:
        return (0, ())
    return (1, parsed)


def is_newer_version(candidate: str | None, current: str | None) -> bool:
    """True only when both parse and ``candidate`` is strictly greater than ``current``."""
    candidate_parsed = parse_version(candidate)
    current_parsed = parse_version(current)
    if candidate_parsed is None or current_parsed is None:
        return False
    return candidate_parsed > current_parsed
