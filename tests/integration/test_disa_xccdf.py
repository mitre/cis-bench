"""Tests for DISA XCCDF export and validation."""

import pytest
from lxml import etree

from cis_bench.exporters import ExporterFactory
from cis_bench.models.benchmark import Benchmark
from cis_bench.validators.disa_conventions import DISAConventionsValidator
from cis_bench.validators.xccdf_schema import read_xccdf, validate_xccdf

# The DISA style writes XCCDF 1.1; lookups name it, so output in no namespace fails them
XCCDF = {"x": "http://checklists.nist.gov/xccdf/1.1"}


@pytest.fixture
def test_benchmark(synthetic_complete_file):
    """Load synthetic test benchmark (use conftest fixture)."""
    return Benchmark.from_json_file(str(synthetic_complete_file))


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


def test_disa_export_validates_nist_schema(disa_export_file):
    """Test DISA export validates against NIST XCCDF 1.1.4 schema."""
    result = validate_xccdf(disa_export_file)

    assert result.version == "1.1"
    assert result.is_valid, f"NIST schema validation failed: {result.errors[:5]}"


def test_disa_export_passes_conventions(disa_export_file):
    """Test DISA export follows DISA conventions v1.10.0."""
    validator = DISAConventionsValidator(read_xccdf(disa_export_file))
    is_valid, errors, warnings = validator.validate()

    assert is_valid, f"DISA conventions validation failed: {errors}"


def test_disa_export_has_ccis(disa_export_file):
    """Test DISA export contains CCI ident elements."""
    import re

    from lxml import etree

    tree = etree.parse(str(disa_export_file))
    root = tree.getroot()

    idents = root.xpath('.//x:ident[@system="http://cyber.mil/cci"]', namespaces=XCCDF)
    rules = root.xpath(".//x:Rule", namespaces=XCCDF)
    assert idents
    assert rules

    # Every DISA Rule carries at least one CCI (the fallback when its controls map to
    # none); which CCIs each rule gets is checked against the mapping file in
    # tests/regression/test_structure_compliance.py.
    for rule in rules:
        assert rule.xpath('./x:ident[@system="http://cyber.mil/cci"]', namespaces=XCCDF), rule.get(
            "id"
        )

    for ident in idents:
        assert re.fullmatch(r"CCI-\d{6}", ident.text or ""), f"Invalid CCI format: {ident.text}"


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
        "notice": root.xpath(".//x:notice", namespaces=XCCDF),
        "front-matter": root.xpath(".//x:front-matter", namespaces=XCCDF),
        "rear-matter": root.xpath(".//x:rear-matter", namespaces=XCCDF),
        "reference": root.xpath(".//x:reference", namespaces=XCCDF),
        "plain-text": root.xpath(".//x:plain-text", namespaces=XCCDF),
        "version": root.xpath(".//x:version", namespaces=XCCDF),
    }

    for name, elems in required.items():
        if name == "plain-text":
            assert len(elems) >= 3, f"Expected at least 3 plain-text elements, found {len(elems)}"
        else:
            assert len(elems) > 0, f"Missing required element: {name}"


def test_disa_export_populates_benchmark_notice_from_style_config(disa_export_file, test_benchmark):
    """DISA XCCDF 1.1.4 export emits configured <notice id='terms-of-use' xml:lang='en'>."""
    from lxml import etree

    tree = etree.parse(str(disa_export_file))
    ns = {"xccdf": "http://checklists.nist.gov/xccdf/1.1"}
    notices = tree.xpath("/xccdf:Benchmark/xccdf:notice", namespaces=ns)

    assert len(notices) == 1
    notice = notices[0]
    assert notice.get("id") == "terms-of-use"
    assert notice.get("{http://www.w3.org/XML/1998/namespace}lang") == "en"
    notice_text = (notice.text or "").strip()
    assert test_benchmark.title in notice_text
    assert str(test_benchmark.url) in notice_text
    assert "Center for Internet Security, Inc." in notice_text
    assert "https://workbench.cisecurity.org/terms-of-use" in notice_text
    assert "cis-bench" in notice_text


def test_disa_benchmark_id_is_cis_prefixed_workbench_id(disa_export_file):
    """DISA-style Benchmark/@id stays CIS_<WorkBench id>: Vulcan shows it as the STIG ID."""
    root = etree.parse(str(disa_export_file)).getroot()
    assert root.get("id") == "CIS_90001"


# The embedded tags of a STIG rule description, in the order DISA writes them
OFFICIAL_EMBEDDED_TAGS = (
    "VulnDiscussion",
    "FalsePositives",
    "FalseNegatives",
    "Documentable",
    "Mitigations",
    "SeverityOverrideGuidance",
    "PotentialImpacts",
    "ThirdPartyTools",
    "MitigationControl",
    "Responsibility",
    "IAControls",
)


def _embedded_tags(description) -> list[tuple[str, str]]:
    """The description read as DISA tools read it: its text (which the XML parser has
    unescaped once) parsed as the embedded tags, each with its own text."""
    fragment = etree.fromstring(f"<description>{description.text}</description>")
    return [(child.tag, child.text or "") for child in fragment]


def _text(element, name: str) -> str:
    """The text of the element's child named name (a check's check-content: pass the check)."""
    return "".join(element.xpath(f"./x:{name}//text()", namespaces=XCCDF))


class TestTheStoredMarkdownIsWrittenAsItIs:
    """The DISA export carries the stored Markdown; a placeholder such as <user> survives
    in every text field, including inside the description's embedded tags."""

    @pytest.fixture
    def exported(self, test_benchmark, tmp_path):
        from cis_bench.models.benchmark import ProfileDefinition

        first, *rest = test_benchmark.recommendations
        rule = first.model_copy(
            update={
                "title": "Ensure <path> is owned by <user>",
                "description": "Owned by the account named in `<user>`.",
                "rationale": "Keep _<partition>_ separate & mounted.",
                "impact": "Users in <group> lose access.",
                "additional_info": "See <path> for the vendor's notes.",
                "audit": "Run:\n\n```\n# stat -c %U <path>\n```",
                "remediation": "Run:\n\n```\n# chage --mindays <N> <user>\n```",
                "profiles": ["Alpha"],
            }
        )
        benchmark = test_benchmark.model_copy(
            update={
                "recommendations": [rule, *rest],
                "profile_definitions": [
                    ProfileDefinition(title="Alpha", description="Items for every <user>.")
                ],
            }
        )
        output_path = tmp_path / "disa.xml"
        ExporterFactory.create("xccdf", style="disa").export(benchmark, str(output_path))
        root = etree.parse(str(output_path)).getroot()
        return root, root.xpath("//x:Rule", namespaces=XCCDF)[0]

    def test_the_description_holds_every_official_tag_with_each_part_as_stored(self, exported):
        _, rule = exported

        tags = _embedded_tags(rule.xpath("./x:description", namespaces=XCCDF)[0])

        assert tags == [
            (
                "VulnDiscussion",
                "Owned by the account named in `<user>`.\n\nKeep _<partition>_ separate & mounted.",
            ),
            ("FalsePositives", ""),
            ("FalseNegatives", ""),
            ("Documentable", "false"),
            ("Mitigations", "See <path> for the vendor's notes."),
            ("SeverityOverrideGuidance", ""),
            ("PotentialImpacts", "Users in <group> lose access."),
            ("ThirdPartyTools", ""),
            ("MitigationControl", ""),
            ("Responsibility", ""),
            ("IAControls", ""),
        ]

    def test_the_other_text_fields_are_written_as_stored(self, exported):
        root, rule = exported

        assert _text(rule, "title") == "Ensure <path> is owned by <user>"
        assert _text(rule, "fixtext") == "Run:\n\n```\n# chage --mindays <N> <user>\n```"
        check = rule.xpath("./x:check", namespaces=XCCDF)[0]
        assert _text(check, "check-content") == "Run:\n\n```\n# stat -c %U <path>\n```"
        assert _text(root.xpath("//x:Profile", namespaces=XCCDF)[0], "description") == (
            "Items for every <user>."
        )
        # The group's description is the rule's title, as stored
        group = rule.getparent()
        assert etree.QName(group).localname == "Group"
        assert _text(group, "description") == "Ensure <path> is owned by <user>"

    def test_a_rule_whose_optional_fields_are_empty_writes_their_tags_empty(
        self, test_benchmark, tmp_path
    ):
        first, *rest = test_benchmark.recommendations
        rule = first.model_copy(update={"impact": None, "additional_info": None})
        benchmark = test_benchmark.model_copy(update={"recommendations": [rule, *rest]})
        output_path = tmp_path / "disa.xml"

        ExporterFactory.create("xccdf", style="disa").export(benchmark, str(output_path))

        root = etree.parse(str(output_path)).getroot()
        description = root.xpath("//x:Rule", namespaces=XCCDF)[0].xpath(
            "./x:description", namespaces=XCCDF
        )[0]
        tags = _embedded_tags(description)
        assert [tag for tag, _ in tags] == list(OFFICIAL_EMBEDDED_TAGS)
        assert dict(tags)["Mitigations"] == "" and dict(tags)["PotentialImpacts"] == ""
