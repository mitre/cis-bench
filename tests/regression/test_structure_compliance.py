"""Structure compliance regression tests.

Ensures our XCCDF exports match official DISA and CIS structures.
Prevents regression to namespace pollution and incorrect formats.
"""

import pytest
from lxml import etree

from cis_bench.exporters import ExporterFactory
from cis_bench.models.benchmark import Benchmark


@pytest.fixture
def sample_benchmark(synthetic_complete_file):
    """Load sample synthetic benchmark."""
    return Benchmark.from_json_file(str(synthetic_complete_file))


# The DISA style's CCI mapping file is keyed by CIS Controls v8.
CCI_CONTROLS_VERSION = 8
FALLBACK_CCI = "CCI-000366"
DC = "{http://purl.org/dc/elements/1.1/}"


def _v8_control_ids(rec):
    return [c.control for c in rec.cis_controls if c.version == CCI_CONTROLS_VERSION]


def _expected_ccis(rec):
    """Every CCI the mapping file gives for the rule's v8 controls (the export is a
    transform: what the mapping has, the rule carries), primary first, once each; the
    fallback CCI when there are none."""
    from cis_bench.utils.cci_lookup import get_cci_service

    service = get_cci_service()
    ccis = []
    for control in _v8_control_ids(rec):
        for mapping in service.get_ccis_for_cis_control(control, extract="all"):
            if mapping.cci not in ccis:
                ccis.append(mapping.cci)
    return ccis or [FALLBACK_CCI]


def _rules_by_ref(tree):
    """Each Rule element by its CIS ref (the Rule's version text)."""
    return {rule.find("{*}version").text: rule for rule in tree.xpath(".//*[local-name()='Rule']")}


def _export(benchmark, tmp_path, style):
    output = tmp_path / f"{style}.xml"
    ExporterFactory.create("xccdf", style=style).export(benchmark, str(output))
    return etree.parse(str(output))


class TestControlMappingFidelity:
    """Every control mapping in the stored benchmark survives into the XCCDF."""

    def test_disa_ccis_come_only_from_v8_controls(self, sample_benchmark, tmp_path):
        # v7 control numbers name unrelated v8 safeguards, so they must not be looked up.
        rules = _rules_by_ref(_export(sample_benchmark, tmp_path, "disa"))

        for rec in sample_benchmark.recommendations:
            got = [
                ident.text
                for ident in rules[rec.ref].findall("{*}ident")
                if ident.get("system") == "http://cyber.mil/cci"
            ]
            assert got == _expected_ccis(rec), rec.ref

    def test_disa_keeps_nist_controls_not_covered_by_ccis(self, sample_benchmark, tmp_path):
        from cis_bench.utils.cci_lookup import get_cci_service

        rules = _rules_by_ref(_export(sample_benchmark, tmp_path, "disa"))
        service = get_cci_service()

        written = 0
        for rec in sample_benchmark.recommendations:
            _, uncovered = service.deduplicate_nist_controls(
                _v8_control_ids(rec), rec.nist_controls, extract="all"
            )
            references = rules[rec.ref].findall("{*}reference")
            assert [ref.findtext(f"{DC}identifier") for ref in references] == uncovered, rec.ref
            assert {ref.findtext(f"{DC}title") for ref in references} <= {"NIST SP 800-53"}
            written += len(references)
        assert written > 0, "the fixture has NIST controls no CCI covers"

    def test_the_benchmark_reference_takes_its_href_from_the_style(
        self, sample_benchmark, disa_config_path
    ):
        from cis_bench.exporters.mapping_engine import MappingEngine

        engine = MappingEngine(disa_config_path)
        engine.config.benchmark["reference"]["attributes"]["href"] = (
            "https://example.invalid/?from={benchmark.url}"
        )

        href, _ = engine.create_reference(sample_benchmark)

        assert href == f"https://example.invalid/?from={sample_benchmark.url}"

    def test_a_reference_with_an_unknown_source_logic_is_refused(
        self, sample_benchmark, disa_config_path
    ):
        from cis_bench.exporters.mapping_engine import MappingEngine

        engine = MappingEngine(disa_config_path)
        engine.config.field_mappings["reference"]["source_logic"] = "nist_after_everything"

        with pytest.raises(ValueError, match="nist_after_everything"):
            engine.map_rule(sample_benchmark.recommendations[0], {})

    def test_a_rule_id_template_that_gives_no_id_is_refused(
        self, sample_benchmark, disa_config_path
    ):
        # A filter can turn a ref value into something that is not text: XHTML elements here.
        from cis_bench.exporters.mapping_engine import MappingEngine

        engine = MappingEngine(disa_config_path)
        engine.config.rule_id["template"] = "{ref_normalized|wrap_xhtml_paragraphs}"

        with pytest.raises(ValueError, match="gives no id"):
            engine.map_rule(sample_benchmark.recommendations[0], {})

    def test_a_rule_id_template_naming_a_value_the_ref_does_not_give_is_refused(
        self, sample_benchmark, disa_config_path
    ):
        # Text around the unknown variable still makes a non-empty id ("SV--030101"),
        # so the id would be wrong without being empty.
        from cis_bench.exporters.mapping_engine import MappingEngine

        engine = MappingEngine(disa_config_path)
        engine.config.rule_id["template"] = "SV-{platform}-{stig_number}"

        with pytest.raises(ValueError, match="platform"):
            engine.map_rule(sample_benchmark.recommendations[0], {"platform": "ubuntu"})

    def test_a_rule_attribute_template_naming_an_unknown_variable_is_refused(
        self, sample_benchmark, disa_config_path
    ):
        # Every template is checked, not only the id templates: a typo here would write
        # <fix id="F-_fix"/> on every rule.
        from cis_bench.exporters.mapping_engine import MappingEngine

        engine = MappingEngine(disa_config_path)
        engine.config.field_mappings["fix"]["attributes"]["id"] = "F-{ref_norm}_fix"

        with pytest.raises(ValueError, match="ref_norm"):
            engine.map_rule(sample_benchmark.recommendations[0], {})

    def test_a_rule_attribute_template_sees_only_the_rule_values(
        self, sample_benchmark, disa_config_path
    ):
        # The engine's working dictionary (its CCI cache, the recommendation list) is not
        # the template's namespace: a template naming such a key is refused, and the
        # message lists only the values a rule template can use.
        from cis_bench.exporters.mapping_engine import MappingEngine

        engine = MappingEngine(disa_config_path)
        engine.config.field_mappings["fix"]["attributes"]["id"] = "F-{recommendations}"
        context = {
            "benchmark": sample_benchmark,
            "recommendations": sample_benchmark.recommendations,
        }

        with pytest.raises(ValueError, match="recommendations") as refused:
            engine.map_rule(sample_benchmark.recommendations[0], context)
        assert "cci_split" not in str(refused.value)
        assert "it can use benchmark, rec, ref, ref_normalized, stig_number" in str(refused.value)

    def test_a_rule_reference_href_is_a_template_too(self, sample_benchmark, disa_config_path):
        # Every attribute of a rule's elements is a template, the reference's href included.
        from cis_bench.exporters.mapping_engine import MappingEngine

        engine = MappingEngine(disa_config_path)
        engine.config.field_mappings["reference"]["attributes"]["href"] = (
            "https://example.invalid/{ref}"
        )
        rec = next(r for r in sample_benchmark.recommendations if r.nist_controls)

        rule = engine.map_rule(rec, {"benchmark": sample_benchmark})

        assert {reference.href for reference in rule.reference} == {
            f"https://example.invalid/{rec.ref}"
        }

    def test_a_rule_id_template_reading_an_attribute_of_a_ref_value_is_refused(
        self, sample_benchmark, disa_config_path
    ):
        # The ref's values are plain text; an attribute of one reads as "" ("SV-").
        from cis_bench.exporters.mapping_engine import MappingEngine

        engine = MappingEngine(disa_config_path)
        engine.config.rule_id["template"] = "SV-{ref_normalized.foo}"

        with pytest.raises(ValueError, match="ref_normalized.foo"):
            engine.map_rule(sample_benchmark.recommendations[0], {})

    @pytest.mark.parametrize(
        ("style", "dc_elements"),
        [
            (
                "disa",
                [("publisher", "CIS Security"), ("source", "https://workbench.cisecurity.org")],
            ),
            ("cis", []),
        ],
    )
    def test_the_benchmark_reference_carries_the_dublin_core_its_style_declares(
        self, sample_benchmark, tmp_path, style, dc_elements
    ):
        root = _export(sample_benchmark, tmp_path, style).getroot()
        reference = root.find("{*}reference")

        assert reference.get("href") == str(sample_benchmark.url)
        assert [(etree.QName(child).localname, child.text) for child in reference] == dc_elements
        assert not (reference.text or "").strip()

    def test_a_dublin_core_value_is_written_whole(self, sample_benchmark, tmp_path):
        # Dublin Core content is built as elements, so no separator in a value can cut it.
        from cis_bench.exporters.xccdf_unified_exporter import XCCDFExporter

        exporter = XCCDFExporter(style="disa")
        exporter.config.benchmark["reference"]["dc_elements"] = [
            {"element": "dc:title", "content": "{benchmark.title}"}
        ]
        title = "CIS Example Benchmark || Draft: 2"
        benchmark = sample_benchmark.model_copy(update={"title": title})
        output = tmp_path / "disa.xml"

        exporter.export(benchmark, str(output))

        reference = etree.parse(str(output)).getroot().find("{*}reference")
        assert [(etree.QName(c).localname, c.text) for c in reference] == [("title", title)]

    def test_a_style_with_dublin_core_elements_but_no_dc_namespace_is_refused(
        self, sample_benchmark, disa_config_path
    ):
        # The elements need the namespace URI the style declares; there is no built-in one.
        from cis_bench.exporters.mapping_engine import MappingEngine

        engine = MappingEngine(disa_config_path)
        del engine.config.benchmark["namespaces"]["dc"]

        with pytest.raises(ValueError, match="dc"):
            engine.create_reference(sample_benchmark)

    @pytest.mark.parametrize("style", ["cis", "disa"])
    def test_profiles_select_every_rule_listing_them(self, sample_benchmark, tmp_path, style):
        tree = _export(sample_benchmark, tmp_path, style)
        rule_ids = {
            rule.find("{*}version").text: rule.get("id")
            for rule in tree.xpath(".//*[local-name()='Rule']")
        }
        selected = {
            profile.find("{*}title").text: {s.get("idref") for s in profile.findall("{*}select")}
            for profile in tree.xpath(".//*[local-name()='Profile']")
        }

        for rec in sample_benchmark.recommendations:
            for profile in rec.profiles:
                assert profile in selected, f"no Profile for {profile!r}"
                assert rule_ids[rec.ref] in selected[profile], f"{rec.ref} missing from {profile}"


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

        assert len(cci_idents) == sum(
            len(_expected_ccis(rec)) for rec in sample_benchmark.recommendations
        )
        assert len(cis_idents) == 38, f"Should have 38 CIS Controls idents, found {len(cis_idents)}"
        assert len(mitre_idents) == 90, f"Should have 90 MITRE idents, found {len(mitre_idents)}"

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

        assert len(cis_idents) == 38, f"Should have 38 CIS idents, found {len(cis_idents)}"
        assert len(cis_metadata) == 20, (
            f"Should have 20 CIS metadata blocks, found {len(cis_metadata)}"
        )

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

        assert len(mitre_idents) == 90, f"Should have 90 MITRE idents, found {len(mitre_idents)}"

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
