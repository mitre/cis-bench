"""The XCCDF versions cis-bench reads and writes, named once.

Each entry ties together what the rest of the code needs to know about one version: the
release a style config names (``1.1.4``), the namespace a document carries
(``http://checklists.nist.gov/xccdf/1.1``), the short label cis-bench reports (``1.1``), and
the schema in OpenSCAP's schema tree under ``cis_bench/schemas`` that validates it.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Final

SCHEMAS_DIR: Final = Path(__file__).resolve().parent.parent / "schemas"

XCCDF_NAMESPACE_PREFIX: Final = "http://checklists.nist.gov/xccdf/"
DUBLIN_CORE_NAMESPACE: Final = "http://purl.org/dc/elements/1.1/"


@dataclass(frozen=True)
class XccdfVersion:
    """One XCCDF version: how styles, documents and reports name it, and its schema."""

    release: str
    label: str
    schema: Path

    @property
    def namespace(self) -> str:
        return XCCDF_NAMESPACE_PREFIX + self.label


XCCDF_VERSIONS: Final = (
    XccdfVersion(
        release="1.1.4", label="1.1", schema=SCHEMAS_DIR / "xccdf" / "1.1" / "xccdf-schema.xsd"
    ),
    XccdfVersion(
        release="1.2", label="1.2", schema=SCHEMAS_DIR / "xccdf" / "1.2" / "xccdf_1.2.xsd"
    ),
)


def version_for_namespace(namespace: str) -> XccdfVersion | None:
    """The version whose namespace a document's root element carries, or None."""
    return next((version for version in XCCDF_VERSIONS if version.namespace == namespace), None)
