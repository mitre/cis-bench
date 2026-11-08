"""Integration tests for CIS Native XCCDF export."""

import tempfile
from pathlib import Path

import pytest
from lxml import etree

from cis_bench.exporters import ExporterFactory
from cis_bench.models.benchmark import Benchmark, CISControl
from cis_bench.validators.xccdf_schema import validate_xccdf

CC7 = "http://cisecurity.org/20-cc/v7.0"
CC8 = "http://cisecurity.org/20-cc/v8.0"
CC = {7: CC7, 8: CC8}


def _rule(root, ref_slug: str):
    return root.xpath(
        f".//*[local-name()='Rule'][@id='xccdf_org.cisecurity.benchmarks_rule_{ref_slug}']"
    )[0]


def _with_cis_controls(benchmark: Benchmark, mappings: list[tuple[int, str]]) -> Benchmark:
    """The benchmark with recommendation 3.2.1 mapped to exactly these (version, control)s."""
    controls = [
        CISControl(
            version=version,
            control=control,
            title="Synthetic control",
            ig1=True,
            ig2=True,
            ig3=True,
        )
        for version, control in mappings
    ]
    recs = [
        rec.model_copy(update={"cis_controls": controls}) if rec.ref == "3.2.1" else rec
        for rec in benchmark.recommendations
    ]
    return benchmark.model_copy(update={"recommendations": recs})


def _cis_idents(rule) -> list[tuple[str, str, str]]:
    """(system, controlURI namespace, controlURI) of each CIS Controls ident on a Rule."""
    found = []
    for ident in rule.xpath("./*[local-name()='ident']"):
        system = ident.get("system", "")
        if not system.startswith("http://cisecurity.org/20-cc/"):
            continue
        uris = [
            (etree.QName(name).namespace, value)
            for name, value in ident.attrib.items()
            if etree.QName(name).localname == "controlURI"
        ]
        assert len(uris) == 1, f"ident {system} has controlURI attributes {uris}"
        found.append((system, *uris[0]))
    return found


@pytest.fixture
def sample_benchmark(synthetic_complete_file):
    """Load synthetic test benchmark."""
    return Benchmark.from_json_file(str(synthetic_complete_file))


class TestCISXCCDFExport:
    """Test CIS Native XCCDF export functionality."""

    def test_cis_exporter_creation(self):
        """Test that CIS exporter can be created."""
        exporter = ExporterFactory.create("xccdf", style="cis")
        assert exporter is not None
        assert exporter.format_name() == "XCCDF (CIS)"

    def test_cis_xccdf_export_basic(self, sample_benchmark):
        """Test basic CIS XCCDF export."""
        exporter = ExporterFactory.create("xccdf", style="cis")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            output_path = f.name

        try:
            exporter.export(sample_benchmark, output_path)

            # Verify file was created
            assert Path(output_path).exists()

            # Verify it's valid XML
            tree = etree.parse(output_path)
            root = tree.getroot()

            assert root.tag.endswith("Benchmark")

        finally:
            Path(output_path).unlink()

    def test_cis_xccdf_namespaces(self, sample_benchmark):
        """Test that all required namespaces are declared."""
        exporter = ExporterFactory.create("xccdf", style="cis")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            output_path = f.name

        try:
            exporter.export(sample_benchmark, output_path)

            tree = etree.parse(output_path)
            root = tree.getroot()

            # Check all required namespaces are present
            nsmap = root.nsmap

            assert "http://checklists.nist.gov/xccdf/1.2" in nsmap.values()
            assert "http://www.w3.org/1999/xhtml" in nsmap.values()
            assert "http://cisecurity.org/controls" in nsmap.values()
            assert "http://cisecurity.org/20-cc/v7.0" in nsmap.values()
            assert "http://cisecurity.org/20-cc/v8.0" in nsmap.values()
            assert "http://purl.org/dc/elements/1.1/" in nsmap.values()
            assert "http://cisecurity.org/xccdf/enhanced/1.0" in nsmap.values()

        finally:
            Path(output_path).unlink()

    def test_cis_controls_metadata_structure(self, sample_benchmark):
        """Test that CIS Controls have the correct nested structure."""
        exporter = ExporterFactory.create("xccdf", style="cis")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            output_path = f.name

        try:
            exporter.export(sample_benchmark, output_path)

            tree = etree.parse(output_path)

            # Find CIS Controls elements
            ns = {
                "xccdf": "http://checklists.nist.gov/xccdf/1.2",
                "controls": "http://cisecurity.org/controls",
            }

            cis_controls = tree.xpath("//controls:cis_controls", namespaces=ns)
            assert len(cis_controls) > 0, "Should have CIS Controls metadata"

            # Check nested structure: cis_controls > framework > safeguard
            frameworks = tree.xpath("//controls:framework", namespaces=ns)
            assert len(frameworks) > 0, "Should have framework elements"

            safeguards = tree.xpath("//controls:safeguard", namespaces=ns)
            assert len(safeguards) > 0, "Should have safeguard elements"

            # Check first safeguard has required attributes and elements
            first_safeguard = safeguards[0]
            assert first_safeguard.get("title") is not None
            assert first_safeguard.get("urn") is not None

            # Check safeguard has required child elements
            ig = first_safeguard.find(".//{http://cisecurity.org/controls}implementation_groups")
            assert ig is not None
            assert ig.get("ig3") is not None

            asset_type = first_safeguard.find(".//{http://cisecurity.org/controls}asset_type")
            assert asset_type is not None

            sec_func = first_safeguard.find(".//{http://cisecurity.org/controls}security_function")
            assert sec_func is not None

        finally:
            Path(output_path).unlink()

    def test_cis_controls_ident_elements(self, sample_benchmark, tmp_path):
        """Each CIS Controls mapping is an ident in the CIS-CAT form: system names the
        Controls version, the cc7/cc8 controlURI names the safeguard, the value is empty."""
        output_path = tmp_path / "cis.xml"
        ExporterFactory.create("xccdf", style="cis").export(sample_benchmark, str(output_path))

        root = etree.parse(str(output_path)).getroot()
        cis_idents = root.xpath(
            ".//*[local-name()='ident'][starts-with(@system, 'http://cisecurity.org/20-cc/')]"
        )
        mapped = sum(len(rec.cis_controls) for rec in sample_benchmark.recommendations)
        assert mapped == 38
        assert len(cis_idents) == mapped

        rule = root.xpath(
            ".//*[local-name()='Rule'][@id='xccdf_org.cisecurity.benchmarks_rule_3_2_1']"
        )[0]
        assert _cis_idents(rule) == [
            (
                "http://cisecurity.org/20-cc/v8.0",
                CC8,
                "http://cisecurity.org/20-cc/v8.0/control/13/subcontrol/1",
            ),
            (
                "http://cisecurity.org/20-cc/v7.0",
                CC7,
                "http://cisecurity.org/20-cc/v7.0/control/12/subcontrol/4",
            ),
        ]
        assert all((ident.text or "") == "" for ident in cis_idents)

        xml_content = output_path.read_text()
        assert (
            '<ident system="http://cisecurity.org/20-cc/v8.0" '
            'cc8:controlURI="http://cisecurity.org/20-cc/v8.0/control/13/subcontrol/1"/>'
        ) in xml_content

    @pytest.mark.parametrize(
        ("version", "control", "control_uri"),
        [
            (8, "3.10", "http://cisecurity.org/20-cc/v8.0/control/3/subcontrol/10"),
            (8, "13.1", "http://cisecurity.org/20-cc/v8.0/control/13/subcontrol/1"),
            (8, "16", "http://cisecurity.org/20-cc/v8.0/control/16"),
            (7, "13.6", "http://cisecurity.org/20-cc/v7.0/control/13/subcontrol/6"),
            (7, "8.11", "http://cisecurity.org/20-cc/v7.0/control/8/subcontrol/11"),
            (7, "13", "http://cisecurity.org/20-cc/v7.0/control/13"),
        ],
    )
    def test_each_cis_controls_mapping_is_written_in_the_cis_cat_form(
        self, sample_benchmark, tmp_path, version, control, control_uri
    ):
        # CIS-CAT names a safeguard as .../control/N/subcontrol/M and a whole control
        # (WorkBench maps some recommendations to one, such as "13") as .../control/N.
        benchmark = _with_cis_controls(sample_benchmark, [(version, control)])
        output_path = tmp_path / "cis.xml"

        ExporterFactory.create("xccdf", style="cis").export(benchmark, str(output_path))

        root = etree.parse(str(output_path)).getroot()
        assert _cis_idents(_rule(root, "3_2_1")) == [
            (f"http://cisecurity.org/20-cc/v{version}.0", CC[version], control_uri)
        ]

    def test_a_rule_mapped_to_every_form_keeps_its_order_and_validates(
        self, sample_benchmark, tmp_path
    ):
        mappings = [(8, "3.10"), (8, "16"), (7, "13"), (7, "8.11")]
        benchmark = _with_cis_controls(sample_benchmark, mappings)
        output_path = tmp_path / "cis.xml"

        ExporterFactory.create("xccdf", style="cis").export(benchmark, str(output_path))

        root = etree.parse(str(output_path)).getroot()
        assert _cis_idents(_rule(root, "3_2_1")) == [
            (
                "http://cisecurity.org/20-cc/v8.0",
                CC8,
                "http://cisecurity.org/20-cc/v8.0/control/3/subcontrol/10",
            ),
            (
                "http://cisecurity.org/20-cc/v8.0",
                CC8,
                "http://cisecurity.org/20-cc/v8.0/control/16",
            ),
            (
                "http://cisecurity.org/20-cc/v7.0",
                CC7,
                "http://cisecurity.org/20-cc/v7.0/control/13",
            ),
            (
                "http://cisecurity.org/20-cc/v7.0",
                CC7,
                "http://cisecurity.org/20-cc/v7.0/control/8/subcontrol/11",
            ),
        ]
        assert {root.nsmap.get("cc7"), root.nsmap.get("cc8")} == {CC7, CC8}
        result = validate_xccdf(output_path)
        assert result.is_valid, f"XCCDF 1.2 schema validation failed: {result.errors[:5]}"

    def test_mitre_as_ident_elements(self, sample_benchmark):
        """Test that MITRE ATT&CK is exported as ident elements (not metadata)."""
        exporter = ExporterFactory.create("xccdf", style="cis")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            output_path = f.name

        try:
            exporter.export(sample_benchmark, output_path)

            tree = etree.parse(output_path)
            root = tree.getroot()

            # MITRE now as ident elements (cleaner, no namespace pollution)
            mitre_technique_idents = root.xpath(
                ".//*[local-name()='ident'][@system='https://attack.mitre.org/techniques']"
            )
            mitre_tactic_idents = root.xpath(
                ".//*[local-name()='ident'][@system='https://attack.mitre.org/tactics']"
            )
            mitre_mitigation_idents = root.xpath(
                ".//*[local-name()='ident'][@system='https://attack.mitre.org/mitigations']"
            )

            assert len(mitre_technique_idents) > 0, "Should have MITRE technique idents"
            assert len(mitre_tactic_idents) > 0, "Should have MITRE tactic idents"
            assert len(mitre_mitigation_idents) > 0, "Should have MITRE mitigation idents"

            # Verify format
            first_tech = mitre_technique_idents[0]
            assert first_tech.text.startswith("T"), "MITRE technique IDs start with T"

        finally:
            Path(output_path).unlink()

    def test_profiles_at_benchmark_level(self, sample_benchmark):
        """Test that Profiles are generated at Benchmark level (proper XCCDF standard)."""
        exporter = ExporterFactory.create("xccdf", style="cis")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            output_path = f.name

        try:
            exporter.export(sample_benchmark, output_path)

            tree = etree.parse(output_path)
            root = tree.getroot()

            # Profiles now at Benchmark level (proper XCCDF standard)
            profile_elements = root.xpath(".//*[local-name()='Profile']")
            assert len(profile_elements) > 0, "Should have Profile elements"

            # Verify at least 2 profiles (Level 1 Server/Workstation)
            assert len(profile_elements) >= 2, (
                f"Expected at least 2 profiles, found {len(profile_elements)}"
            )

            # Verify profiles have select elements
            for profile in profile_elements:
                selects = profile.xpath(".//*[local-name()='select']")
                assert len(selects) > 0, "Profiles should have select elements"

        finally:
            Path(output_path).unlink()

    @pytest.mark.parametrize(
        ("style", "profile_id"),
        [
            ("cis", "xccdf_org.cisecurity.benchmarks_profile_{}".format),
            ("disa", "{}".format),
        ],
    )
    def test_profiles_select_their_rules_and_level_2_includes_level_1(
        self, sample_benchmark, tmp_path, style, profile_id
    ):
        # Profiles as WorkBench's page gives them: one text, a Markdown line break between.
        recs = [
            rec.model_copy(update={"profiles": ["  \n".join(rec.profiles)]})
            if rec.profiles
            else rec
            for rec in sample_benchmark.recommendations
        ]
        joined = Benchmark.model_validate(
            sample_benchmark.model_copy(update={"recommendations": recs}).model_dump()
        )
        output_path = tmp_path / f"{style}.xml"

        ExporterFactory.create("xccdf", style=style).export(joined, str(output_path))

        root = etree.parse(str(output_path)).getroot()
        counts = {
            p.get("id"): len(p.xpath("./*[local-name()='select'][@selected='true']"))
            for p in root.xpath("./*[local-name()='Profile']")
        }
        separator = "_" if style == "cis" else "-"

        def name(level: str, kind: str) -> str:
            return profile_id(separator.join(["level", level, kind]))

        # synthetic_complete.json: 14 rules in both Level 1 profiles, 3 in both Level 2
        # profiles, none in a Level 1 and a Level 2 profile of the same platform.
        assert counts == {
            name("1", "server"): 14,
            name("2", "server"): 17,
            name("1", "workstation"): 14,
            name("2", "workstation"): 17,
        }

    @pytest.mark.parametrize(
        ("style", "prefix"), [("cis", "xccdf_org.cisecurity.benchmarks_profile_"), ("disa", "")]
    )
    def test_the_page_profile_definitions_decide_the_profiles(
        self, sample_benchmark, tmp_path, style, prefix
    ):
        from cis_bench.models.benchmark import ProfileDefinition

        # The page defines two profiles under names no style mapping knows; Beta extends Alpha.
        names = {"1.1.1": ["Alpha"], "2.1.1": ["Beta"]}
        recs = [
            rec.model_copy(update={"profiles": names.get(rec.ref, [])})
            for rec in sample_benchmark.recommendations
        ]
        benchmark = sample_benchmark.model_copy(
            update={
                "recommendations": recs,
                "profile_definitions": [
                    ProfileDefinition(title="Alpha", description="<p>First tier.</p>"),
                    ProfileDefinition(title="Beta", parent="Alpha"),
                ],
            }
        )
        output_path = tmp_path / f"{style}.xml"

        ExporterFactory.create("xccdf", style=style).export(benchmark, str(output_path))

        root = etree.parse(str(output_path)).getroot()
        rule_ids = {
            "".join(rule.xpath("./*[local-name()='title']//text()")).strip(): rule.get("id")
            for rule in root.xpath("//*[local-name()='Rule']")
        }
        rule_1_1_1, rule_2_1_1 = (
            rule_ids[rec.title] for rec in recs if rec.ref in ("1.1.1", "2.1.1")
        )
        profiles = {
            p.get("id"): (
                [
                    "".join(d.xpath(".//text()")).strip()
                    for d in p.xpath("./*[local-name()='description']")
                ],
                [
                    (s.get("idref"), s.get("selected"))
                    for s in p.xpath("./*[local-name()='select']")
                ],
            )
            for p in root.xpath("./*[local-name()='Profile']")
        }
        assert profiles == {
            f"{prefix}alpha": (["First tier."], [(rule_1_1_1, "true")]),
            f"{prefix}beta": ([], [(rule_1_1_1, "true"), (rule_2_1_1, "true")]),
        }

    def test_nist_references_dublin_core(self, sample_benchmark):
        """Test that NIST references use Dublin Core."""
        exporter = ExporterFactory.create("xccdf", style="cis")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            output_path = f.name

        try:
            exporter.export(sample_benchmark, output_path)

            tree = etree.parse(output_path)
            ns = {
                "xccdf": "http://checklists.nist.gov/xccdf/1.2",
                "dc": "http://purl.org/dc/elements/1.1/",
            }

            # Find references with Dublin Core (namespace-agnostic)
            dc_titles = tree.xpath(
                '//*[local-name()="title" and namespace-uri()="http://purl.org/dc/elements/1.1/"]'
            )
            assert len(dc_titles) > 0, "Should have Dublin Core titles"

            dc_identifiers = tree.xpath(
                '//*[local-name()="identifier" and namespace-uri()="http://purl.org/dc/elements/1.1/"]'
            )
            assert len(dc_identifiers) > 0, "Should have Dublin Core identifiers"

            # Verify content
            assert any("NIST" in title.text for title in dc_titles if title.text)

        finally:
            Path(output_path).unlink()

    def test_output_file_size_reasonable(self, sample_benchmark):
        """Test that output file size is reasonable (includes metadata)."""
        exporter = ExporterFactory.create("xccdf", style="cis")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            output_path = f.name

        try:
            exporter.export(sample_benchmark, output_path)

            file_size = Path(output_path).stat().st_size

            # With 20 synthetic recommendations and full dual metadata, should be > 25 KB
            assert file_size > 25_000, (
                f"File size {file_size} seems too small for 20 recs with metadata"
            )

            # And compact (< 500 KB)
            assert file_size < 500_000, f"File size {file_size} seems too large"

        finally:
            Path(output_path).unlink()

    def test_xml_well_formed(self, sample_benchmark):
        """Test that generated XML is well-formed."""
        exporter = ExporterFactory.create("xccdf", style="cis")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            output_path = f.name

        try:
            exporter.export(sample_benchmark, output_path)

            # Parse should succeed without errors
            tree = etree.parse(output_path)
            root = tree.getroot()

            assert root is not None

            # Verify basic structure
            assert root.tag.endswith("Benchmark")

            # Should have Groups
            groups = tree.findall(".//Group") + tree.findall(
                ".//{http://checklists.nist.gov/xccdf/1.2}Group"
            )
            assert len(groups) == 20

            # Should have Rules
            rules = tree.findall(".//Rule") + tree.findall(
                ".//{http://checklists.nist.gov/xccdf/1.2}Rule"
            )
            assert len(rules) == 20

        finally:
            Path(output_path).unlink()

    def test_cis_export_validates_nist_xccdf_1_2_schema(self, sample_benchmark, tmp_path):
        """CIS XCCDF 1.2 export must validate against NIST XCCDF 1.2 XSD schema."""
        output_file = tmp_path / "test_cis.xml"
        exporter = ExporterFactory.create("xccdf", style="cis")
        exporter.export(sample_benchmark, str(output_file))

        result = validate_xccdf(output_file)

        assert result.version == "1.2"
        assert result.is_valid, f"XCCDF 1.2 schema validation failed: {result.errors[:5]}"

    def test_cis_metadata_aligned_by_rule_id_and_repeatable(self, sample_benchmark, tmp_path):
        """Metadata injection aligns 1-to-1 by Rule ID and resets across repeated exports."""
        exporter = ExporterFactory.create("xccdf", style="cis")
        first_out = tmp_path / "cis_first.xml"
        second_out = tmp_path / "cis_second.xml"

        exporter.export(sample_benchmark, str(first_out))
        exporter.export(sample_benchmark, str(second_out))

        tree = etree.parse(str(second_out))
        ns = {
            "xccdf": "http://checklists.nist.gov/xccdf/1.2",
            "controls": "http://cisecurity.org/controls",
        }

        # Rule 6.2.1 has no CIS Controls so its allow_empty cis_controls container has zero frameworks
        unmapped_rule = tree.xpath(
            "//xccdf:Rule[@id='xccdf_org.cisecurity.benchmarks_rule_6_2_1']",
            namespaces=ns,
        )
        assert len(unmapped_rule) == 1
        unmapped_metas = unmapped_rule[0].xpath("./xccdf:metadata", namespaces=ns)
        assert len(unmapped_metas) == 1
        assert len(unmapped_metas[0].xpath(".//controls:framework", namespaces=ns)) == 0

        # Mapped rules must each have exactly one metadata block with v7+v8 frameworks before ident
        mapped_rules = tree.xpath(
            "//xccdf:Rule[@id!='xccdf_org.cisecurity.benchmarks_rule_6_2_1']",
            namespaces=ns,
        )
        assert len(mapped_rules) == 19
        for rule in mapped_rules:
            metas = rule.xpath("./xccdf:metadata", namespaces=ns)
            assert len(metas) == 1
            assert len(metas[0].xpath(".//controls:framework", namespaces=ns)) == 2
            child_names = [etree.QName(child).localname for child in rule]
            assert child_names.index("metadata") < child_names.index("ident")

    def test_cis_export_populates_benchmark_notice_from_style_config(
        self, sample_benchmark, tmp_path
    ):
        """CIS XCCDF 1.2 export emits configured <notice id='terms-of-use' xml:lang='en'>."""
        output_file = tmp_path / "test_cis_notice.xml"
        exporter = ExporterFactory.create("xccdf", style="cis")
        exporter.export(sample_benchmark, str(output_file))

        tree = etree.parse(str(output_file))
        ns = {"xccdf": "http://checklists.nist.gov/xccdf/1.2"}
        notices = tree.xpath("/xccdf:Benchmark/xccdf:notice", namespaces=ns)

        assert len(notices) == 1
        notice = notices[0]
        assert notice.get("id") == "terms-of-use"
        assert notice.get("{http://www.w3.org/XML/1998/namespace}lang") == "en"
        notice_text = (notice.text or "").strip()
        assert sample_benchmark.title in notice_text
        assert str(sample_benchmark.url) in notice_text
        assert "Center for Internet Security, Inc." in notice_text
        assert "https://workbench.cisecurity.org/terms-of-use" in notice_text
        assert "cis-bench" in notice_text


def _benchmark_id(exporter, benchmark, output_path: Path) -> str:
    exporter.export(benchmark, str(output_path))
    root = etree.parse(str(output_path)).getroot()
    assert root.tag.endswith("Benchmark")
    return root.get("id")


def test_benchmark_id_follows_cis_convention(sample_benchmark, tmp_path):
    """CIS-style Benchmark/@id is the CIS-published form: namespace, version, title slug.

    Reference form from CIS's own XCCDF: xccdf_org.cisecurity.benchmarks_benchmark_
    1.0.0_CIS_Ubuntu_Linux_22.04_LTS_Benchmark. Version is the benchmark version as
    given (NCName-safe); the title has whitespace and other non-NCName characters
    replaced by single underscores.
    """
    exporter = ExporterFactory.create("xccdf", style="cis")

    bench_id = _benchmark_id(exporter, sample_benchmark, tmp_path / "first.xml")
    assert bench_id == (
        "xccdf_org.cisecurity.benchmarks_benchmark_v1.0.0"
        "_CIS_Synthetic_Enterprise_Platform_Benchmark_v1.0.0"
    )

    # Same input, same id.
    assert _benchmark_id(exporter, sample_benchmark, tmp_path / "again.xml") == bench_id

    # A different title is a different benchmark and must get a different id.
    other = sample_benchmark.model_copy(update={"title": "CIS Other Platform Benchmark"})
    other_id = _benchmark_id(exporter, other, tmp_path / "other.xml")
    assert (
        other_id == "xccdf_org.cisecurity.benchmarks_benchmark_v1.0.0_CIS_Other_Platform_Benchmark"
    )
    assert other_id != bench_id


def test_benchmark_id_slugs_a_version_that_is_not_ncname_safe(sample_benchmark, tmp_path):
    """WorkBench carries versions like 'v7.1.0 (vNext)'; the id stays an NCName."""
    exporter = ExporterFactory.create("xccdf", style="cis")
    vnext = sample_benchmark.model_copy(update={"version": "v7.1.0 (vNext)"})

    bench_id = _benchmark_id(exporter, vnext, tmp_path / "vnext.xml")
    assert bench_id == (
        "xccdf_org.cisecurity.benchmarks_benchmark_v7.1.0_vNext"
        "_CIS_Synthetic_Enterprise_Platform_Benchmark_v1.0.0"
    )
