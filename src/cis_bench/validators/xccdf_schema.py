"""Schema validation of XCCDF documents against the schemas shipped with cis-bench.

The schema is chosen from the document's root namespace (``http://checklists.nist.gov/xccdf/1.1``
or ``.../1.2``); the files come from OpenSCAP's schema tree under ``cis_bench/schemas``, so no
network, no catalog and no ``xmllint`` are needed. The result follows ``oscap xccdf validate``:
valid, or invalid with one message per error and its line. A document that is not XCCDF at all
(unreadable, not XML, carrying a DOCTYPE, another namespace, a version without a shipped schema) is ``NotXccdfError``.

Schema validity is not DISA or CIS convention compliance; see ``disa_conventions``.
"""

from dataclasses import dataclass
from pathlib import Path

from lxml import etree

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"
XCCDF_NAMESPACE_PREFIX = "http://checklists.nist.gov/xccdf/"
SCHEMA_FILES: dict[str, Path] = {
    "1.1": SCHEMAS_DIR / "xccdf" / "1.1" / "xccdf-schema.xsd",
    "1.2": SCHEMAS_DIR / "xccdf" / "1.2" / "xccdf_1.2.xsd",
}


class NotXccdfError(ValueError):
    """The file is not an XCCDF document this tool can validate; the message says why."""


@dataclass(frozen=True)
class XccdfValidation:
    """What validating one file found."""

    path: Path
    version: str
    errors: list[str]

    @property
    def is_valid(self) -> bool:
        return not self.errors


def untrusted_xml_parser() -> etree.XMLParser:
    """A parser for a file we did not write: no entity expansion, no DTD loading, no network."""
    return etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)


_schemas: dict[str, etree.XMLSchema] = {}


def _schema(version: str) -> etree.XMLSchema:
    if version not in _schemas:
        _schemas[version] = etree.XMLSchema(
            etree.parse(str(SCHEMA_FILES[version]), untrusted_xml_parser())
        )
    return _schemas[version]


def validate_xccdf(path: str | Path) -> XccdfValidation:
    """Validate one XCCDF file against the shipped schema for its version.

    Raises:
        NotXccdfError: the file cannot be read, is not well-formed XML, its root element is
            not in an XCCDF namespace, or names an XCCDF version with no shipped schema.
    """
    path = Path(path)
    try:
        document = etree.parse(str(path), untrusted_xml_parser())
    except OSError as error:
        raise NotXccdfError(f"{path}: cannot be read ({error.strerror or error})") from error
    except etree.XMLSyntaxError as error:
        raise NotXccdfError(f"{path}: not well-formed XML ({error.msg})") from error

    if document.docinfo.internalDTD is not None or document.docinfo.externalDTD is not None:
        # XCCDF carries no document type declaration; one here could only declare entities,
        # which this parser does not expand, so the document cannot be validated as written
        raise NotXccdfError(f"{path}: has a document type declaration, which XCCDF does not use")

    root = document.getroot()
    namespace = etree.QName(root).namespace or ""
    if not namespace.startswith(XCCDF_NAMESPACE_PREFIX):
        raise NotXccdfError(f"{path}: not an XCCDF document (root element is {root.tag})")
    version = namespace[len(XCCDF_NAMESPACE_PREFIX) :]
    if version not in SCHEMA_FILES:
        known = ", ".join(sorted(SCHEMA_FILES))
        raise NotXccdfError(
            f"{path}: XCCDF {version} has no schema shipped with cis-bench (known: {known})"
        )

    schema = _schema(version)
    try:
        schema.validate(document)
    except etree.XMLSchemaError as error:
        raise NotXccdfError(f"{path}: could not be validated ({error})") from error
    errors = [f"line {entry.line}: {entry.message}" for entry in schema.error_log]
    return XccdfValidation(path=path, version=version, errors=errors)
