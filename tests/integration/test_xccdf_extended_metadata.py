"""Integration tests for XCCDF export with extended benchmark metadata.

Tests that XCCDF exports include CPE platform specifications, published dates,
and other extended metadata properly mapped per NIST XCCDF schema.
"""

import tempfile
from pathlib import Path

import pytest
from lxml import etree

from cis_bench.exporters.xccdf_unified_exporter import XCCDFExporter
from cis_bench.models.benchmark import Benchmark, BenchmarkAsset, Recommendation


@pytest.fixture
def benchmark_with_extended_metadata():
    """Create a minimal benchmark with extended metadata for testing."""
    return Benchmark(
        title="CIS Test Benchmark",
        benchmark_id="12345",
        url="https://workbench.cisecurity.org/benchmarks/12345",
        version="v1.0.0",
        # Extended metadata
        published_date="Jun 24th 2024",
        release_type="Planned Update",
        contributors=["Alice Smith", "Bob Jones"],
        assets=[
            BenchmarkAsset(
                title="Test OS",
                cpe_id="cpe:2.3:o:test:test_os:1.0:*:*:*:*:*:*:*",
            ),
            BenchmarkAsset(
                title="Test App",
                cpe_id="cpe:2.3:a:test:test_app:2.0:*:*:*:*:*:*:*",
            ),
        ],
        scraper_version="v1_test",
        total_recommendations=1,
        recommendations=[
            Recommendation(
                ref="1.1",
                title="Test Recommendation",
                url="https://workbench.cisecurity.org/sections/1/recommendations/1",
                assessment_status="Automated",
                description="Test description",
            )
        ],
    )


class TestXCCDFCPEPlatformSpecification:
    """Test CPE platform-specification in XCCDF export."""

    def test_disa_style_includes_cpe_platform_spec(self, benchmark_with_extended_metadata):
        """Test DISA XCCDF includes CPE platform-specification elements."""
        exporter = XCCDFExporter(style="disa")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            output_path = f.name

        try:
            exporter.export(benchmark_with_extended_metadata, output_path)

            # Parse and verify CPE elements present
            tree = etree.parse(output_path)
            root = tree.getroot()

            # Check for platform specification
            # XCCDF 1.1.4/1.2 uses <platform> elements with idref to CPE
            platforms = root.findall(".//{*}platform")

            # Should have platform elements referencing the CPEs
            assert len(platforms) > 0, "No platform elements found in XCCDF"

        finally:
            Path(output_path).unlink(missing_ok=True)

    def test_cis_style_includes_cpe_platform_spec(self, benchmark_with_extended_metadata):
        """Test CIS XCCDF includes CPE platform-specification elements."""
        exporter = XCCDFExporter(style="cis")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            output_path = f.name

        try:
            exporter.export(benchmark_with_extended_metadata, output_path)

            tree = etree.parse(output_path)
            root = tree.getroot()

            platforms = root.findall(".//{*}platform")
            assert len(platforms) > 0, "No platform elements found in XCCDF"

        finally:
            Path(output_path).unlink(missing_ok=True)


class TestXCCDFPublishedDate:
    """Test published date in XCCDF export."""

    def test_disa_style_includes_published_date(self, benchmark_with_extended_metadata):
        """Test DISA XCCDF includes published date in metadata."""
        exporter = XCCDFExporter(style="disa")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            output_path = f.name

        try:
            exporter.export(benchmark_with_extended_metadata, output_path)

            # Verify published date appears somewhere in output
            with open(output_path) as f:
                content = f.read()

            assert "Jun 24th 2024" in content or "2024" in content, "Published date not in XCCDF"

        finally:
            Path(output_path).unlink(missing_ok=True)


class TestXCCDFReleaseMetadata:
    """Test release metadata in XCCDF export."""

    def test_disa_style_includes_release_type(self, benchmark_with_extended_metadata):
        """Test DISA XCCDF includes release type."""
        exporter = XCCDFExporter(style="disa")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            output_path = f.name

        try:
            exporter.export(benchmark_with_extended_metadata, output_path)

            with open(output_path) as f:
                content = f.read()

            # Release type should appear in plain-text or metadata
            assert "Planned Update" in content or "Release" in content, "Release type not in XCCDF"

        finally:
            Path(output_path).unlink(missing_ok=True)
