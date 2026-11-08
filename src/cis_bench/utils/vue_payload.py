"""WorkBench's Vue web components carry their data as ``JSON.parse('...')`` attribute values."""

from __future__ import annotations

import re

_JSON_PARSE_RE = re.compile(r"^JSON\.parse\('(.*)'\)$", re.DOTALL)
# One escape of a JavaScript string literal: \uXXXX, \xXX, or a backslash and one character.
_JS_ESCAPE_RE = re.compile(r"\\(u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|[\s\S])")
_JS_SINGLE_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}


def _js_unescape(match: re.Match[str]) -> str:
    escape = match.group(1)
    if len(escape) in (3, 5) and escape[0] in "ux":
        return chr(int(escape[1:], 16))
    return _JS_SINGLE_ESCAPES.get(escape, escape)


def decode_vue_payload(raw: str | None) -> str | None:
    """The JSON text a Vue component attribute carries.

    WorkBench writes ``JSON.parse('...')``: a JavaScript string literal holding JSON text,
    with quotes as ``\\u0022``, ``/`` as ``\\/`` and the JSON text's own escapes (``\\u003C``
    for ``<``) behind an escaped backslash. Every escape of the literal is decoded in one
    pass, so the JSON text's escapes reach :func:`json.loads` intact. A value without the
    wrapper is JSON text already and is returned as it is.

    Returns:
        A JSON string for :func:`json.loads` (empty for ``JSON.parse('')``), or ``None``
        when the input is empty or blank.
    """
    stripped = (raw or "").strip()
    if not stripped:
        return None
    match = _JSON_PARSE_RE.search(stripped)
    if match is None:
        return stripped
    return _JS_ESCAPE_RE.sub(_js_unescape, match.group(1))
