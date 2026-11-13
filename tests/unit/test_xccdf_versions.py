"""One table names each XCCDF version cis-bench reads and writes: the version a style names,
the namespace a document carries, and the schema that validates it."""

import pytest
from lxml import etree

from cis_bench.utils.xccdf_versions import XCCDF_VERSIONS, version_for_namespace
from cis_bench.validators.xccdf_schema import untrusted_xml_parser


@pytest.mark.parametrize(
    ("namespace", "release", "label"),
    [
        ("http://checklists.nist.gov/xccdf/1.1", "1.1.4", "1.1"),
        ("http://checklists.nist.gov/xccdf/1.2", "1.2", "1.2"),
    ],
)
def test_a_documents_namespace_and_a_styles_version_name_the_same_entry(namespace, release, label):
    version = version_for_namespace(namespace)

    assert version is not None
    assert version.release == release
    assert version.label == label


def test_a_namespace_no_entry_names_has_no_version():
    assert version_for_namespace("http://checklists.nist.gov/xccdf/1.0") is None


@pytest.mark.parametrize("version", XCCDF_VERSIONS, ids=lambda version: version.label)
def test_every_versions_schema_compiles_from_the_shipped_files(version):
    """The schema and everything it imports ship with cis-bench; nothing is fetched."""
    etree.XMLSchema(etree.parse(str(version.schema), untrusted_xml_parser()))
