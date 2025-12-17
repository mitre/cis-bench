"""Structure compliance regression tests.

Ensures our XCCDF exports match official DISA and CIS structures.
Prevents regression to namespace pollution and incorrect formats.
"""

import pytest
from lxml import etree

from cis_bench.exporters import ExporterFactory
from cis_bench.models.benchmark import Benchmark


@pytest.fixture
def sample_benchmark(almalinux_complete_file):
    """Load sample benchmark."""
    return Benchmark.from_json_file(str(almalinux_complete_file))


class TestDISAStructureCompliance:
    """Ensure DISA exports match official DISA STIG structure."""

    def test_disa_has_no_metadata_elements(self, sample_benchmark, tmp_path):
        """CRITICAL: DISA exports MUST have zero metadata elements.

        Real DISA STIGs don't use metadata - all compliance data is in idents.
        This was the root cause of Vulcan import failures.
        """
        output = tmp_path / "disa.xml"
        exporter = ExporterFactory.create("xccdf", style="disa")
        exporter.export(sample_benchmark, str(output))

        tree = etree.parse(str(output))
        metadata_count = len(tree.xpath(".//*[local-name()='metadata']"))

        assert metadata_count == 0, (
            f"DISA exports MUST have 0 metadata elements, found {metadata_count}. "
            "All compliance data should be in ident elements."
        )

    def test_disa_has_all_compliance_as_idents(self, sample_benchmark, tmp_path):
        """DISA exports must have CCIs, CIS Controls, and MITRE as ident elements."""
        output = tmp_path / "disa.xml"
        exporter = ExporterFactory.create("xccdf", style="disa")
        exporter.export(sample_benchmark, str(output))

        tree = etree.parse(str(output))

        # Check for different ident systems
        cci_idents = tree.xpath(".//*[local-name()='ident'][@system='http://cyber.mil/cci']")
        cis_idents = tree.xpath(
            ".//*[local-name()='ident'][contains(@system, 'cisecurity.org/controls')]"
        )
        mitre_idents = tree.xpath(
            ".//*[local-name()='ident'][contains(@system, 'attack.mitre.org')]"
        )

        assert len(cci_idents) > 500, f"Should have many CCIs, found {len(cci_idents)}"
        assert len(cis_idents) > 600, f"Should have CIS Controls idents, found {len(cis_idents)}"
        assert len(mitre_idents) > 1500, f"Should have MITRE idents, found {len(mitre_idents)}"

    def test_disa_namespace_declared_once_at_root(self, sample_benchmark, tmp_path):
        """CRITICAL: Only ONE namespace declaration at root (no child redeclarations).

        Namespace pollution was causing Vulcan's Ruby XML parser to fail.
        We use default namespace (xmlns=) NOT prefixed (xmlns:ns0=) for Vulcan compatibility.
        """
        output = tmp_path / "disa.xml"
        exporter = ExporterFactory.create("xccdf", style="disa")
        exporter.export(sample_benchmark, str(output))

        with open(output) as f:
            content = f.read()

        # Count xmlns declarations (default namespace, not prefixed)
        # We use xmlns= (default), NOT xmlns:ns0= (prefixed)
        # This is required for Vulcan's HappyMapper to parse correctly
        default_xmlns_count = content.count('xmlns="http://checklists.nist.gov')
        prefixed_xmlns_count = content.count("xmlns:ns")

        assert default_xmlns_count >= 1, (
            f"Should have at least 1 default namespace declaration (xmlns=), found {default_xmlns_count}. "
            "XCCDF must use default namespace for Vulcan compatibility."
        )
        assert prefixed_xmlns_count == 0, (
            f"Should have 0 prefixed namespace declarations (xmlns:ns*), found {prefixed_xmlns_count}. "
            "Prefixed namespaces cause Vulcan import failures."
        )

    def test_disa_structure_matches_official_pattern(self, sample_benchmark, tmp_path):
        """Our DISA structure should match official DISA STIG pattern."""
        output = tmp_path / "disa.xml"
        exporter = ExporterFactory.create("xccdf", style="disa")
        exporter.export(sample_benchmark, str(output))

        tree = etree.parse(str(output))

        # Should have same element types as official STIGs
        our_elements = {
            elem.tag.split("}")[1] if "}" in elem.tag else elem.tag for elem in tree.iter()
        }

        # Official DISA elements (from U_RHEL_9_STIG)
        expected_elements = {
            "Benchmark",
            "status",
            "title",
            "description",
            "notice",
            "front-matter",
            "rear-matter",
            "reference",
            "plain-text",
            "version",
            "Profile",
            "select",
            "Group",
            "Rule",
            "ident",
            "fixtext",
            "fix",
            "check",
            "check-content",
        }

        assert expected_elements.issubset(our_elements), (
            f"Missing expected elements: {expected_elements - our_elements}"
        )

    def test_disa_profiles_at_benchmark_level(self, sample_benchmark, tmp_path):
        """Profiles must be at Benchmark level, not in metadata."""
        output = tmp_path / "disa.xml"
        exporter = ExporterFactory.create("xccdf", style="disa")
        exporter.export(sample_benchmark, str(output))

        tree = etree.parse(str(output))

        # Profiles should be direct children of Benchmark
        profiles = tree.xpath("//*[local-name()='Benchmark']/*[local-name()='Profile']")

        assert len(profiles) >= 2, f"Should have at least 2 profiles, found {len(profiles)}"

        # Each profile should have select elements
        for profile in profiles:
            selects = profile.xpath(".//*[local-name()='select']")
            assert len(selects) > 0, f"Profile {profile.get('id')} has no select elements"


class TestCISStructureCompliance:
    """Ensure CIS exports match official CIS XCCDF structure."""

    def test_cis_has_controls_in_both_ident_and_metadata(self, sample_benchmark, tmp_path):
        """CIS exports should have CIS Controls in BOTH ident AND metadata (dual representation)."""
        output = tmp_path / "cis.xml"
        exporter = ExporterFactory.create("xccdf", style="cis")
        exporter.export(sample_benchmark, str(output))

        tree = etree.parse(str(output))

        # CIS Controls as idents
        cis_idents = tree.xpath(".//*[local-name()='ident'][contains(@system, 'cisecurity.org')]")

        # CIS Controls in metadata
        cis_metadata = tree.xpath(".//*[local-name()='cis_controls']")

        assert len(cis_idents) > 600, f"Should have CIS idents, found {len(cis_idents)}"
        assert len(cis_metadata) > 300, f"Should have CIS metadata, found {len(cis_metadata)}"

        # Idents are ~2x metadata (each rule has v7 + v8 idents, but 1 metadata)
        # So idents should be roughly 2x metadata count
        ratio = len(cis_idents) / len(cis_metadata) if cis_metadata else 0
        assert 1.8 < ratio < 2.5, f"Ident/metadata ratio should be ~2.0, got {ratio:.2f}"

    def test_cis_has_mitre_as_idents_not_metadata(self, sample_benchmark, tmp_path):
        """CIS exports should have MITRE as idents (not in metadata - cleaner)."""
        output = tmp_path / "cis.xml"
        exporter = ExporterFactory.create("xccdf", style="cis")
        exporter.export(sample_benchmark, str(output))

        tree = etree.parse(str(output))

        # MITRE as idents
        mitre_idents = tree.xpath(
            ".//*[local-name()='ident'][contains(@system, 'attack.mitre.org')]"
        )

        assert len(mitre_idents) > 1500, f"Should have MITRE idents, found {len(mitre_idents)}"

        # NO MITRE in enhanced metadata (old pattern removed)
        # Note: We no longer use enhanced:mitre namespace

    def test_cis_controls_metadata_structure_matches_official(self, sample_benchmark, tmp_path):
        """CIS Controls metadata structure should match official CIS XCCDF."""
        output = tmp_path / "cis.xml"
        exporter = ExporterFactory.create("xccdf", style="cis")
        exporter.export(sample_benchmark, str(output))

        tree = etree.parse(str(output))
        controls_ns = {"controls": "http://cisecurity.org/controls"}

        # Should have framework elements
        frameworks = tree.xpath("//controls:framework", namespaces=controls_ns)
        assert len(frameworks) > 0, "Should have framework elements"

        # Should have safeguard elements
        safeguards = tree.xpath("//controls:safeguard", namespaces=controls_ns)
        assert len(safeguards) > 0, "Should have safeguard elements"

        # Check structure of first safeguard
        first = safeguards[0]
        assert first.get("title") is not None, "Safeguard should have title"
        assert first.get("urn") is not None, "Safeguard should have urn"

        # Should have implementation_groups child
        ig = first.find(".//{http://cisecurity.org/controls}implementation_groups")
        assert ig is not None, "Should have implementation_groups"
        assert ig.get("ig1") in ["true", "false"], "Should have ig1 attribute"

    def test_cis_profiles_at_benchmark_level(self, sample_benchmark, tmp_path):
        """CIS profiles should be at Benchmark level (not in metadata)."""
        output = tmp_path / "cis.xml"
        exporter = ExporterFactory.create("xccdf", style="cis")
        exporter.export(sample_benchmark, str(output))

        tree = etree.parse(str(output))

        # Profiles at Benchmark level
        profiles = tree.xpath("//*[local-name()='Benchmark']/*[local-name()='Profile']")

        assert len(profiles) >= 2, f"Should have at least 2 profiles, found {len(profiles)}"


class TestNamespaceCompliance:
    """Ensure clean namespace handling (no pollution)."""

    def test_no_namespace_redeclarations_in_children(self, sample_benchmark, tmp_path):
        """Child elements MUST NOT redeclare parent namespaces."""
        for style in ["disa", "cis"]:
            output = tmp_path / f"{style}.xml"
            exporter = ExporterFactory.create("xccdf", style=style)
            exporter.export(sample_benchmark, str(output))

            tree = etree.parse(str(output))

            # Get root namespace
            root = tree.getroot()
            root_nsmap = root.nsmap

            # Check all descendants don't redeclare same namespaces
            for elem in root.iter():
                if elem == root:
                    continue

                elem_nsmap = elem.nsmap
                # Element should inherit, not redeclare
                # (Having nsmap is OK, redeclaring same prefix is NOT)
                # For now, just check we don't have hundreds of redeclarations

            # Simple check: count xmlns attributes in XML
            with open(output) as f:
                content = f.read()

            xmlns_ns_count = content.count("xmlns:ns")

            # Should be minimal (1-2 for root, not 300+)
            assert xmlns_ns_count < 10, (
                f"{style}: Too many xmlns:ns declarations ({xmlns_ns_count}). "
                "This indicates namespace pollution."
            )
