"""Tests for DISA XCCDF export and validation."""

import subprocess
from pathlib import Path

import pytest

from cis_bench.exporters import ExporterFactory
from cis_bench.models.benchmark import Benchmark
from cis_bench.validators.disa_conventions import DISAConventionsValidator


@pytest.fixture
def test_benchmark(almalinux_complete_file):
    """Load test benchmark (use conftest fixture)."""
    return Benchmark.from_json_file(str(almalinux_complete_file))


@pytest.fixture
def disa_export_file(test_benchmark, tmp_path):
    """Export to DISA XCCDF using unified exporter."""
    output_file = tmp_path / "test_disa.xml"
    exporter = ExporterFactory.create("xccdf", style="disa")
    exporter.export(test_benchmark, str(output_file))
    return output_file


def test_disa_export_creates_file(disa_export_file):
    """Test DISA exporter creates output file."""
    assert disa_export_file.exists()
    assert disa_export_file.stat().st_size > 0


@pytest.mark.skip(
    reason="Schema dependencies missing (platform-0.2.3.xsd, xccdfp-1.1.xsd, cpe-1.0.xsd)"
)
def test_disa_export_validates_nist_schema(disa_export_file):
    """Test DISA export validates against NIST XCCDF 1.1.4 schema."""
    schema_dir = Path(__file__).parent.parent / "schemas"
    schema_file = schema_dir / "xccdf-1.1.4.xsd"  # DISA uses 1.1.4, not 1.2
    catalog_file = schema_dir / "catalog.xml"

    result = subprocess.run(
        ["xmllint", "--schema", str(schema_file), str(disa_export_file), "--noout"],
        env={"XML_CATALOG_FILES": str(catalog_file)},
        capture_output=True,
        text=True,
        cwd=str(schema_dir),
    )

    assert result.returncode == 0, f"NIST schema validation failed: {result.stderr}"


@pytest.mark.skip(reason="DISAConventionsValidator needs namespace update for XCCDF 1.1.4")
def test_disa_export_passes_conventions(disa_export_file):
    """Test DISA export follows DISA conventions v1.10.0."""
    validator = DISAConventionsValidator(str(disa_export_file))
    is_valid, errors, warnings = validator.validate()

    assert is_valid, f"DISA conventions validation failed: {errors}"


def test_disa_export_has_ccis(disa_export_file):
    """Test DISA export contains CCI ident elements."""
    from lxml import etree

    tree = etree.parse(str(disa_export_file))
    root = tree.getroot()

    # Use namespace-agnostic XPath (works with any namespace prefix)
    idents = root.xpath('.//*[local-name()="ident"][@system="http://cyber.mil/cci"]')

    assert len(idents) > 0, "No CCI ident elements found"
    assert len(idents) > 100, f"Expected many CCIs, found only {len(idents)}"

    # Check CCI format
    import re

    for ident in idents[:10]:  # Check first 10
        assert re.match(r"CCI-\d{6}", ident.text), f"Invalid CCI format: {ident.text}"


def test_disa_export_has_vuln_discussion(disa_export_file):
    """Test DISA export has VulnDiscussion structure."""
    content = disa_export_file.read_text()

    assert "&lt;VulnDiscussion&gt;" in content or "<VulnDiscussion>" in content, (
        "VulnDiscussion tags not found in descriptions"
    )


def test_disa_export_has_dublin_core(disa_export_file):
    """Test DISA export has Dublin Core reference."""
    from lxml import etree

    tree = etree.parse(str(disa_export_file))
    root = tree.getroot()

    dc_publisher = root.find(".//{http://purl.org/dc/elements/1.1/}publisher")
    dc_source = root.find(".//{http://purl.org/dc/elements/1.1/}source")

    assert dc_publisher is not None, "Missing dc:publisher"
    assert dc_source is not None, "Missing dc:source"
    assert dc_publisher.text, "dc:publisher is empty"
    assert dc_source.text, "dc:source is empty"


def test_disa_export_has_all_required_elements(disa_export_file):
    """Test all STIG-required elements present."""
    from lxml import etree

    tree = etree.parse(str(disa_export_file))
    root = tree.getroot()

    # Use namespace-agnostic XPath
    required = {
        "notice": root.xpath('.//*[local-name()="notice"]'),
        "front-matter": root.xpath('.//*[local-name()="front-matter"]'),
        "rear-matter": root.xpath('.//*[local-name()="rear-matter"]'),
        "reference": root.xpath('.//*[local-name()="reference"]'),
        "plain-text": root.xpath('.//*[local-name()="plain-text"]'),
        "version": root.xpath('.//*[local-name()="version"]'),
    }

    for name, elems in required.items():
        if name == "plain-text":
            assert len(elems) >= 3, f"Expected at least 3 plain-text elements, found {len(elems)}"
        else:
            assert len(elems) > 0, f"Missing required element: {name}"
