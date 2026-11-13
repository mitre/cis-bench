"""Schema validation of XCCDF documents against the schemas shipped with cis-bench.

One check serves a file (``cis-bench validate``) and a document still in memory (an export
before it is written): the bytes are parsed once, with a parser that expands no entities and
loads no DTD or network resource; the version comes from the root element's namespace through
``cis_bench.utils.xccdf_versions``; and the document is validated against that version's
schema from OpenSCAP's schema tree under ``cis_bench/schemas``, so no network, no catalog and
no ``xmllint`` are needed. The result follows ``oscap xccdf validate``: valid, or invalid with
one message per error and its line. A document that is not XCCDF at all (unreadable, not XML,
carrying a DOCTYPE, another namespace, a version without a shipped schema) is
``NotXccdfError``.

Schema validity is not DISA or CIS convention compliance; ``disa_conventions`` checks those on
the same parsed document.
"""

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from lxml import etree

from cis_bench.utils.xccdf_versions import (
    XCCDF_NAMESPACE_PREFIX,
    XCCDF_VERSIONS,
    XccdfVersion,
    version_for_namespace,
)


class NotXccdfError(ValueError):
    """The document is not XCCDF this tool can validate; the message says why."""


@dataclass(frozen=True)
class XccdfDocument:
    """An XCCDF document parsed once, with the version its namespace names."""

    source: str
    tree: etree._ElementTree
    version: XccdfVersion

    @property
    def root(self) -> etree._Element:
        return self.tree.getroot()


@dataclass(frozen=True)
class XccdfValidation:
    """What validating one document found."""

    source: str
    version: str
    errors: list[str]

    @property
    def is_valid(self) -> bool:
        return not self.errors


def untrusted_xml_parser() -> etree.XMLParser:
    """A parser for XML we did not write: no entity expansion, no DTD loading, no network."""
    return etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)


_schemas: dict[str, etree.XMLSchema] = {}


def _schema(version: XccdfVersion) -> etree.XMLSchema:
    if version.label not in _schemas:
        _schemas[version.label] = etree.XMLSchema(
            etree.parse(str(version.schema), untrusted_xml_parser())
        )
    return _schemas[version.label]


def parse_xccdf(content: bytes, source: str) -> XccdfDocument:
    """Parse an XCCDF document once and name its version; ``source`` names it in messages.

    Raises:
        NotXccdfError: the bytes are not well-formed XML, carry a document type declaration,
            have a root element outside the XCCDF namespaces, or name an XCCDF version with no
            shipped schema.
    """
    try:
        tree = etree.parse(BytesIO(content), untrusted_xml_parser())
    except etree.XMLSyntaxError as error:
        raise NotXccdfError(f"{source}: not well-formed XML ({error.msg})") from error

    if tree.docinfo.internalDTD is not None or tree.docinfo.externalDTD is not None:
        # XCCDF carries no document type declaration; one here could only declare entities,
        # which this parser does not expand, so the document cannot be validated as written
        raise NotXccdfError(f"{source}: has a document type declaration, which XCCDF does not use")

    root = tree.getroot()
    namespace = etree.QName(root).namespace or ""
    if not namespace.startswith(XCCDF_NAMESPACE_PREFIX):
        raise NotXccdfError(f"{source}: not an XCCDF document (root element is {root.tag})")
    version = version_for_namespace(namespace)
    if version is None:
        named = namespace[len(XCCDF_NAMESPACE_PREFIX) :]
        known = ", ".join(sorted(known.label for known in XCCDF_VERSIONS))
        raise NotXccdfError(
            f"{source}: XCCDF {named} has no schema shipped with cis-bench (known: {known})"
        )
    return XccdfDocument(source=source, tree=tree, version=version)


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise NotXccdfError(f"{path}: cannot be read ({error.strerror or error})") from error


def read_xccdf(path: str | Path) -> XccdfDocument:
    """Read and parse one XCCDF file (see ``parse_xccdf``)."""
    path = Path(path)
    return parse_xccdf(_read(path), str(path))


def check_document(document: XccdfDocument) -> XccdfValidation:
    """Validate a parsed XCCDF document against the shipped schema for its version."""
    schema = _schema(document.version)
    try:
        schema.validate(document.tree)
    except etree.XMLSchemaError as error:
        raise NotXccdfError(f"{document.source}: could not be validated ({error})") from error
    errors = [f"line {entry.line}: {entry.message}" for entry in schema.error_log]
    return XccdfValidation(source=document.source, version=document.version.label, errors=errors)


def check_xccdf(content: bytes, source: str) -> XccdfValidation:
    """Validate an XCCDF document given as bytes, such as an export not yet written."""
    return check_document(parse_xccdf(content, source))


def validate_xccdf(path: str | Path) -> XccdfValidation:
    """Validate one XCCDF file against the shipped schema for its version.

    Raises:
        NotXccdfError: the file cannot be read, or is not an XCCDF document with a shipped
            schema (see ``parse_xccdf``).
    """
    path = Path(path)
    return check_xccdf(_read(path), str(path))
