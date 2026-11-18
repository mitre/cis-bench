"""A style file is checked against one schema when it loads: a key nothing reads, or a
value of the wrong kind, is refused with the file and the dotted path of each mistake."""

from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from cis_bench.exporters.mapping_engine import ConfigLoader
from cis_bench.exporters.style_config import XmlName


def _style(tmp_path: Path, body: str, name: str = "style.yaml") -> Path:
    style = tmp_path / name
    style.write_text(f"metadata:\n  style_name: s\n{body}")
    return style


class TestUnknownKeys:
    """A key the exporter does not read is refused, never ignored."""

    def test_a_misspelled_key_is_refused_with_its_path_and_file(self, tmp_path):
        style = _style(tmp_path, "rule_defaults:\n  severty: high\n")

        with pytest.raises(ValueError, match=r"style\.yaml: rule_defaults\.severty"):
            ConfigLoader.load(style)

    def test_every_mistake_of_one_load_is_reported(self, tmp_path):
        style = _style(
            tmp_path,
            "rule_defaults:\n  severty: high\n"
            "cci_deduplication:\n  enabled: maybe\n"
            "group_elements:\n  title:\n    sorce: ref\n",
        )

        with pytest.raises(ValueError) as refused:
            ConfigLoader.load(style)

        message = str(refused.value)
        assert "style.yaml: rule_defaults.severty" in message
        assert "style.yaml: cci_deduplication.enabled" in message
        assert "style.yaml: group_elements.title.sorce" in message

    def test_a_mistake_in_a_parent_style_is_reported_with_the_parent_file(self, tmp_path):
        parent = _style(tmp_path, "rule_id:\n  templat: x\n", name="parent.yaml")
        child = tmp_path / "child.yaml"
        child.write_text(f"extends: {parent}\nmetadata:\n  style_name: child\n")

        with pytest.raises(ValueError, match=r"parent\.yaml: rule_id\.templat"):
            ConfigLoader.load(child)

    def test_the_keys_a_section_takes_are_listed(self, tmp_path):
        style = _style(tmp_path, "rule_defaults:\n  severty: high\n")

        with pytest.raises(ValueError, match=r"rule_defaults\.severty.*severity, weight"):
            ConfigLoader.load(style)


class TestRemovedKeys:
    """A key earlier styles carried that the exporter never applied is refused with what
    happens instead, so a style cannot promise a behaviour nothing performs."""

    @pytest.mark.parametrize(
        ("body", "path", "hint"),
        [
            pytest.param(
                "validation:\n  max_cci_per_rule: 50\n",
                "validation",
                "nothing checks an export against",
                id="validation section",
            ),
            pytest.param(
                'rule_defaults:\n  selected: "true"\n',
                r"rule_defaults\.selected",
                "XCCDF model",
                id="rule_defaults.selected",
            ),
            pytest.param(
                "rule_defaults:\n  role: full\n",
                r"rule_defaults\.role",
                "XCCDF model",
                id="rule_defaults.role",
            ),
            pytest.param(
                "cci_deduplication:\n  algorithm:\n    steps: []\n",
                r"cci_deduplication\.algorithm",
                "enabled",
                id="cci_deduplication.algorithm",
            ),
            pytest.param(
                "cci_deduplication:\n  matching_rules:\n    hierarchical: false\n",
                r"cci_deduplication\.matching_rules",
                "enabled",
                id="cci_deduplication.matching_rules",
            ),
        ],
    )
    def test_a_key_that_promised_a_behaviour_is_refused_with_what_happens_instead(
        self, tmp_path, body, path, hint
    ):
        style = _style(tmp_path, body)

        with pytest.raises(ValueError, match=rf"style\.yaml: {path}:.*{hint}"):
            ConfigLoader.load(style)

    def test_the_xccdf_namespace_key_is_refused_with_where_the_namespace_is_declared(
        self, tmp_path
    ):
        style = tmp_path / "style.yaml"
        style.write_text("metadata:\n  style_name: s\n  xccdf_namespace: urn:example\n")

        with pytest.raises(ValueError, match=r"metadata\.xccdf_namespace:.*benchmark\.namespaces"):
            ConfigLoader.load(style)

    @pytest.mark.parametrize(
        ("body", "path"),
        [
            pytest.param("rule_id:\n  description: text\n", r"rule_id\.description", id="rule_id"),
            pytest.param(
                "group_id:\n  description: text\n", r"group_id\.description", id="group_id"
            ),
            pytest.param(
                "cci_deduplication:\n  description: text\n",
                r"cci_deduplication\.description",
                id="cci_deduplication.description",
            ),
            pytest.param(
                "cci_deduplication:\n  rationale: text\n",
                r"cci_deduplication\.rationale",
                id="cci_deduplication.rationale",
            ),
        ],
    )
    def test_descriptive_text_is_refused_as_a_key_and_belongs_in_a_comment(
        self, tmp_path, body, path
    ):
        style = _style(tmp_path, body)

        with pytest.raises(ValueError, match=rf"{path}:.*YAML comment"):
            ConfigLoader.load(style)

    @pytest.mark.parametrize("key", ["description", "conventions", "target_tools"])
    def test_descriptive_metadata_is_refused_as_a_key_and_belongs_in_a_comment(self, tmp_path, key):
        style = tmp_path / "style.yaml"
        style.write_text(f"metadata:\n  style_name: s\n  {key}: text\n")

        with pytest.raises(ValueError, match=rf"metadata\.{key}:.*YAML comment"):
            ConfigLoader.load(style)


class TestValueKinds:
    """A value of a kind the exporter would misread is refused when the style loads."""

    @pytest.mark.parametrize(
        ("body", "path"),
        [
            pytest.param(
                # a non-empty string is true to the exporter, so "false" would switch it on
                'cci_deduplication:\n  enabled: "false"\n',
                r"cci_deduplication\.enabled",
                id="a switch written as text",
            ),
            pytest.param(
                'post_processing:\n  remove_override_attr: "no"\n',
                r"post_processing\.remove_override_attr",
                id="a post-processing switch written as text",
            ),
            pytest.param(
                "rule_defaults:\n  weight: heavy\n",
                r"rule_defaults\.weight",
                id="a weight that is no number",
            ),
            pytest.param(
                "rule_id:\n  template: 7\n", r"rule_id\.template", id="a template that is no text"
            ),
            pytest.param(
                "group_elements:\n  title:\n    source: [ref]\n",
                r"group_elements\.title\.source",
                id="a source that is no field name",
            ),
            pytest.param(
                "rule_defaults: medium\n", "rule_defaults", id="a section that is no mapping"
            ),
        ],
    )
    def test_a_value_of_the_wrong_kind_is_refused_with_its_path(self, tmp_path, body, path):
        style = _style(tmp_path, body)

        with pytest.raises(ValueError, match=rf"style\.yaml: {path}:"):
            ConfigLoader.load(style)

    def test_a_weight_written_as_a_number_or_as_text_loads(self, tmp_path):
        as_text = _style(tmp_path, 'rule_defaults:\n  weight: "10.0"\n', name="text.yaml")
        as_number = _style(tmp_path, "rule_defaults:\n  weight: 10.0\n", name="number.yaml")

        assert ConfigLoader.load(as_text).rule_defaults == {"weight": "10.0"}
        assert ConfigLoader.load(as_number).rule_defaults == {"weight": 10.0}


class TestXmlName:
    """An XML name a style gives carries no prefix and no namespace, and is never xmlns."""

    @pytest.mark.parametrize("name", ["title", "check-content", "_x", "fix.text"])
    def test_an_xml_name_is_accepted(self, name):
        assert TypeAdapter(XmlName).validate_python(name) == name

    @pytest.mark.parametrize("name", ["a:b", "{urn:example}title", "xmlns", "two words", "", "1st"])
    def test_a_name_an_element_cannot_have_is_refused(self, name):
        with pytest.raises(ValidationError):
            TypeAdapter(XmlName).validate_python(name)

    def test_a_group_element_name_is_an_xml_name(self, tmp_path):
        style = _style(tmp_path, 'group_elements:\n  "dc:title":\n    source: ref\n')

        with pytest.raises(ValueError, match=r"group_elements.*dc:title"):
            ConfigLoader.load(style)


class TestStylesInTheRepository:
    """Every style the project ships or tests with passes the schema."""

    @pytest.mark.parametrize(
        "relative",
        [
            "src/cis_bench/exporters/configs/base.yaml",
            "src/cis_bench/exporters/configs/styles/cis.yaml",
            "src/cis_bench/exporters/configs/styles/disa.yaml",
            "tests/fixtures/configs/mock_pci_dss.yaml",
        ],
    )
    def test_the_style_loads(self, project_root, relative):
        config = ConfigLoader.load(project_root / relative)

        assert config.rule_defaults["severity"] == "medium"


class TestInheritedStyles:
    """The chain is merged root first, and after each file the style built so far is checked:
    a mistake is reported with the file just merged, and loading stops at the first file
    with mistakes."""

    @staticmethod
    def _child(tmp_path: Path, parent: Path, body: str) -> Path:
        child = tmp_path / "child.yaml"
        child.write_text(f"extends: {parent}\n{body}")
        return child

    def test_a_parent_value_the_child_replaces_is_still_refused(self, tmp_path):
        parent = _style(tmp_path, "rule_defaults:\n  weight: heavy\n", name="parent.yaml")
        child = self._child(tmp_path, parent, "rule_defaults:\n  weight: 10.0\n")

        with pytest.raises(ValueError, match=r"parent\.yaml: rule_defaults\.weight"):
            ConfigLoader.load(child)

    def test_a_namespace_bound_in_parent_and_child_is_reported_with_the_loaded_style(
        self, tmp_path
    ):
        parent = _style(
            tmp_path, "benchmark:\n  namespaces:\n    a: urn:example:a\n", name="parent.yaml"
        )
        child = self._child(tmp_path, parent, "benchmark:\n  namespaces:\n    b: urn:example:a\n")

        with pytest.raises(
            ValueError, match=r"child\.yaml: benchmark\.namespaces\.b: 'b' and 'a' are both bound"
        ):
            ConfigLoader.load(child)

    def test_only_the_first_file_with_mistakes_is_reported(self, tmp_path):
        parent = _style(
            tmp_path, "rule_id:\n  templat: x\nrule_defaults:\n  severty: low\n", name="parent.yaml"
        )
        child = self._child(tmp_path, parent, "cci_deduplication:\n  enabled: maybe\n")

        with pytest.raises(ValueError) as refused:
            ConfigLoader.load(child)

        message = str(refused.value)
        assert "parent.yaml: rule_id.templat" in message
        assert "parent.yaml: rule_defaults.severty" in message
        assert "child.yaml" not in message

    def test_a_parent_that_is_no_valid_style_alone_is_refused(self, tmp_path):
        # the child would complete the element, but every file a style extends is a style
        parent = _style(tmp_path, "benchmark:\n  title:\n    transform: none\n", name="parent.yaml")
        child = self._child(tmp_path, parent, "benchmark:\n  title:\n    source: title\n")

        with pytest.raises(
            ValueError, match=r"parent\.yaml: benchmark\.title\.source: Field required"
        ):
            ConfigLoader.load(child)

    def test_a_key_the_child_adds_to_a_parent_section_is_reported_with_the_child_file(
        self, tmp_path
    ):
        parent = _style(tmp_path, "rule_defaults:\n  severity: low\n", name="parent.yaml")
        child = self._child(tmp_path, parent, "rule_defaults:\n  severty: high\n")

        with pytest.raises(ValueError, match=r"child\.yaml: rule_defaults\.severty"):
            ConfigLoader.load(child)

    def test_a_namespace_binding_is_reported_with_the_file_that_wrote_it(self, tmp_path):
        parent = _style(
            tmp_path, "benchmark:\n  namespaces:\n    good: urn:example:good\n", name="parent.yaml"
        )
        child = self._child(
            tmp_path, parent, 'benchmark:\n  namespaces:\n    "a:b": urn:example:b\n'
        )

        with pytest.raises(ValueError) as refused:
            ConfigLoader.load(child)

        message = str(refused.value)
        assert "child.yaml: benchmark.namespaces.a:b: 'a:b' is not a namespace prefix" in message
        assert "parent.yaml" not in message

    def test_parent_and_child_sections_that_contain_themselves_are_refused_without_a_crash(
        self, tmp_path
    ):
        looping = "rule_defaults: &defaults\n  severity: low\n  again: *defaults\n"
        parent = _style(tmp_path, looping, name="parent.yaml")
        child = self._child(tmp_path, parent, looping)

        with pytest.raises(ValueError) as refused:
            ConfigLoader.load(child)

        message = str(refused.value)
        assert "parent.yaml: rule_defaults.again: Recursion error" in message
        assert "child.yaml" not in message

    def test_a_section_that_contains_itself_only_in_the_child_is_refused_before_the_merge(
        self, tmp_path
    ):
        parent = _style(tmp_path, "rule_defaults:\n  severity: low\n", name="parent.yaml")
        child = self._child(
            tmp_path, parent, "rule_defaults: &defaults\n  severity: low\n  again: *defaults\n"
        )

        with pytest.raises(ValueError) as refused:
            ConfigLoader.load(child)

        message = str(refused.value)
        assert "child.yaml: rule_defaults.again: Recursion error" in message
        assert "parent.yaml" not in message

    def test_keys_a_merge_would_confuse_are_refused_in_the_first_file(self, tmp_path):
        # true and 1 are one key to a Python mapping; merged, they would be confused
        parent = _style(
            tmp_path, "benchmark:\n  namespaces:\n    true: urn:example:a\n", name="parent.yaml"
        )
        child = self._child(tmp_path, parent, "benchmark:\n  namespaces:\n    1: urn:example:b\n")

        with pytest.raises(ValueError) as refused:
            ConfigLoader.load(child)

        message = str(refused.value)
        assert "parent.yaml: benchmark.namespaces.true: is not text; write the key in quotes" in (
            message
        )
        assert "child.yaml" not in message

    @pytest.mark.parametrize("section", ["field_mappings", "benchmark"])
    def test_sections_that_contain_themselves_are_refused_without_a_crash(self, tmp_path, section):
        looping = f"{section}:\n  entry: &entry\n    again: *entry\n"
        parent = _style(tmp_path, looping, name="parent.yaml")
        child = self._child(tmp_path, parent, looping)

        with pytest.raises(ValueError) as refused:
            ConfigLoader.load(child)

        message = str(refused.value)
        assert f"parent.yaml: {section}.entry.again: Recursion error" in message
        assert "child.yaml" not in message

    @pytest.mark.parametrize(
        ("value", "reason"),
        [
            pytest.param("", "leave the key out", id="no value"),
            pytest.param(" 1", "valid string", id="number"),
            pytest.param(' ""', "at least 1 character", id="empty text"),
        ],
    )
    def test_an_extends_that_names_no_file_is_refused(self, tmp_path, value, reason):
        style = _style(tmp_path, f"extends:{value}\n")

        with pytest.raises(ValueError, match=rf"style\.yaml: extends: .*{reason}"):
            ConfigLoader.load(style)

    def test_a_chain_that_extends_itself_is_refused(self, tmp_path):
        (tmp_path / "a.yaml").write_text("metadata:\n  style_name: a\nextends: b.yaml\n")
        (tmp_path / "b.yaml").write_text("metadata:\n  style_name: b\nextends: a.yaml\n")

        with pytest.raises(ValueError, match=r"Circular inheritance detected: .*a\.yaml$"):
            ConfigLoader.load(tmp_path / "a.yaml")

    def test_a_parent_file_that_does_not_exist_is_reported(self, tmp_path):
        child = self._child(tmp_path, tmp_path / "parent.yaml", "")

        with pytest.raises(
            FileNotFoundError, match=r"Configuration file not found: .*parent\.yaml"
        ):
            ConfigLoader.load(child)

    def test_an_extends_that_names_a_folder_is_refused_with_the_file_that_wrote_it(self, tmp_path):
        style = _style(tmp_path, "extends: .\n")

        with pytest.raises(ValueError, match=r"style\.yaml: extends names .*, which is not a file"):
            ConfigLoader.load(style)

    def test_a_style_that_is_no_valid_yaml_is_refused_with_its_file(self, tmp_path):
        style = _style(tmp_path, "benchmark: [\n")

        with pytest.raises(ValueError, match=r"style\.yaml: not valid YAML"):
            ConfigLoader.load(style)

    def test_a_style_that_is_no_mapping_is_refused(self, tmp_path):
        style = tmp_path / "style.yaml"
        style.write_text("- metadata\n- benchmark\n")

        with pytest.raises(ValueError, match=r"style\.yaml"):
            ConfigLoader.load(style)


class TestKeysWithoutAValue:
    """A key written with no value is refused: leaving the key out is how a style takes
    the default, and an empty value would reach the exporter as nothing."""

    @pytest.mark.parametrize(
        ("body", "path"),
        [
            pytest.param("rule_defaults:\n  weight:\n", r"rule_defaults\.weight", id="weight"),
            pytest.param(
                "rule_defaults:\n  severity: null\n", r"rule_defaults\.severity", id="severity"
            ),
            pytest.param(
                "group_elements:\n  title:\n    source: ref\n    transform:\n",
                r"group_elements\.title\.transform",
                id="transform",
            ),
            pytest.param(
                "post_processing:\n  remove_override_attr:\n",
                r"post_processing\.remove_override_attr",
                id="post-processing switch",
            ),
            pytest.param(
                "cci_deduplication:\n  enabled:\n", r"cci_deduplication\.enabled", id="switch"
            ),
            pytest.param("rule_id:\n  template:\n", r"rule_id\.template", id="template"),
            pytest.param("benchmark:\n  namespaces:\n", r"benchmark\.namespaces", id="namespaces"),
        ],
    )
    def test_a_key_with_no_value_is_refused_with_its_path(self, tmp_path, body, path):
        style = _style(tmp_path, body)

        with pytest.raises(ValueError, match=rf"style\.yaml: {path}:.*leave the key out"):
            ConfigLoader.load(style)

    def test_a_metadata_key_with_no_value_is_refused(self, tmp_path):
        style = tmp_path / "style.yaml"
        style.write_text("metadata:\n  style_name: s\n  xccdf_version:\n")

        with pytest.raises(ValueError, match=r"metadata\.xccdf_version:.*leave the key out"):
            ConfigLoader.load(style)


class TestKeysOfTypedSections:
    """YAML reads an unquoted true, 1 or null as a boolean, a number or nothing; a section
    the schema types takes text keys only."""

    @pytest.mark.parametrize("key", ["1", "true", "null", "2026-01-01"])
    def test_a_key_that_is_no_text_is_refused_as_written(self, tmp_path, key):
        style = _style(tmp_path, f"rule_defaults:\n  {key}: x\n")

        with pytest.raises(
            ValueError,
            match=rf"style\.yaml: rule_defaults\.{key}: is not text; write the key in quotes",
        ):
            ConfigLoader.load(style)

    def test_a_group_element_name_that_is_no_text_is_refused(self, tmp_path):
        style = _style(tmp_path, "group_elements:\n  1:\n    source: ref\n")

        with pytest.raises(ValueError, match=r"style\.yaml: group_elements\.1: "):
            ConfigLoader.load(style)

    @pytest.mark.parametrize(
        "body",
        [
            pytest.param("field_mappings:\n  title:\n    1: x\n", id="field mapping"),
            pytest.param("benchmark:\n  title:\n    true: x\n", id="benchmark entry"),
        ],
    )
    def test_a_key_that_is_no_text_below_a_section_is_refused(self, tmp_path, body):
        style = _style(tmp_path, body)

        with pytest.raises(ValueError, match=r"style\.yaml: (field_mappings|benchmark)\.title"):
            ConfigLoader.load(style)


class TestSelfContainingStyles:
    """YAML anchors can make a mapping that contains itself."""

    def test_a_section_that_contains_itself_is_refused_without_a_crash(self, tmp_path):
        style = _style(tmp_path, "rule_defaults: &defaults\n  severity: low\n  again: *defaults\n")

        with pytest.raises(ValueError, match=r"style\.yaml: rule_defaults\.again"):
            ConfigLoader.load(style)


class TestBenchmarkSection:
    """Each benchmark entry takes the keys the engine reads; every other entry is an element
    filled from a benchmark field."""

    def test_a_misspelled_notice_key_is_refused_with_its_path(self, tmp_path):
        style = _style(tmp_path, "benchmark:\n  notice:\n    contnt: x\n")

        with pytest.raises(
            ValueError, match=r"style\.yaml: benchmark\.notice\.contnt: .*content, id, lang"
        ):
            ConfigLoader.load(style)

    @pytest.mark.parametrize(
        ("body", "path", "hint"),
        [
            pytest.param(
                "notice:\n    element: notice\n",
                r"notice\.element",
                "XCCDF model",
                id="notice element",
            ),
            pytest.param(
                "notice:\n    attributes:\n      id: x\n",
                r"notice\.attributes",
                "id and lang",
                id="notice attributes",
            ),
            pytest.param(
                "reference:\n    element: reference\n",
                r"reference\.element",
                "XCCDF model",
                id="reference element",
            ),
        ],
    )
    def test_a_key_nothing_reads_is_refused_with_what_happens_instead(
        self, tmp_path, body, path, hint
    ):
        style = _style(tmp_path, f"benchmark:\n  {body}")

        with pytest.raises(ValueError, match=rf"benchmark\.{path}: is not read \(.*{hint}"):
            ConfigLoader.load(style)

    def test_an_element_filled_from_a_field_needs_its_source(self, tmp_path):
        style = _style(tmp_path, "benchmark:\n  title:\n    transform: none\n")

        with pytest.raises(
            ValueError, match=r"style\.yaml: benchmark\.title\.source: Field required"
        ):
            ConfigLoader.load(style)

    def test_a_child_may_change_an_element_whose_source_the_parent_names(self, tmp_path):
        parent = _style(tmp_path, "benchmark:\n  title:\n    source: title\n", name="parent.yaml")
        child = tmp_path / "child.yaml"
        child.write_text(f"extends: {parent}\nbenchmark:\n  title:\n    prepend_text: 'CIS: '\n")

        assert ConfigLoader.load(child).benchmark["title"] == {
            "source": "title",
            "prepend_text": "CIS: ",
        }

    def test_an_element_no_file_of_the_chain_gives_a_source_is_refused_with_its_file(
        self, tmp_path
    ):
        parent = _style(tmp_path, "metadata:\n  xccdf_version: '1.2'\n", name="parent.yaml")
        child = tmp_path / "child.yaml"
        child.write_text(f"extends: {parent}\nbenchmark:\n  title:\n    prepend_text: x\n")

        with pytest.raises(
            ValueError, match=r"child\.yaml: benchmark\.title\.source: Field required"
        ):
            ConfigLoader.load(child)

    def test_front_matter_settings_are_refused(self, tmp_path):
        # nothing reads them: the front-matter is written empty from the XCCDF model
        style = _style(tmp_path, 'benchmark:\n  front_matter:\n    content: ""\n')

        with pytest.raises(ValueError, match=r"benchmark\.front_matter\.content"):
            ConfigLoader.load(style)

    @pytest.mark.parametrize(
        ("body", "path"),
        [
            pytest.param(
                "plain_text:\n    - content: x\n", r"plain_text\[0\]\.id", id="plain text id"
            ),
            pytest.param(
                "profiles:\n    profile_mappings:\n      - title: x\n",
                r"profiles\.profile_mappings\[0\]\.match",
                id="profile match",
            ),
            pytest.param(
                "reference:\n    dc_elements:\n      - content: x\n",
                r"reference\.dc_elements\[0\]\.element",
                id="dc element",
            ),
        ],
    )
    def test_a_required_key_left_out_is_refused_with_its_path(self, tmp_path, body, path):
        style = _style(tmp_path, f"benchmark:\n  {body}")

        with pytest.raises(ValueError, match=rf"style\.yaml: benchmark\.{path}: Field required"):
            ConfigLoader.load(style)

    def test_a_profile_mapping_with_an_id_is_refused_with_where_ids_come_from(self, tmp_path):
        style = _style(
            tmp_path,
            "benchmark:\n  profiles:\n    profile_mappings:\n      - match: x\n        id: y\n",
        )

        with pytest.raises(
            ValueError, match=r"profile_mappings\[0\]\.id: is not read \(.*id_template"
        ):
            ConfigLoader.load(style)

    def test_a_dublin_core_element_needs_a_prefix(self, tmp_path):
        style = _style(
            tmp_path,
            "benchmark:\n  namespaces:\n    dc: urn:example:dc\n"
            "  reference:\n    dc_elements:\n      - element: publisher\n        content: x\n",
        )

        with pytest.raises(ValueError, match=r"reference\.dc_elements\[0\]\.element: "):
            ConfigLoader.load(style)

    def test_a_dublin_core_prefix_the_style_does_not_declare_is_refused(self, tmp_path):
        style = _style(
            tmp_path,
            "benchmark:\n  reference:\n    dc_elements:\n"
            "      - element: dc:publisher\n        content: x\n",
        )

        with pytest.raises(
            ValueError,
            match=r"style\.yaml: benchmark\.reference\.dc_elements\[0\]\.element: .*'dc'",
        ):
            ConfigLoader.load(style)

    def test_a_dublin_core_prefix_declared_by_the_parent_style_is_accepted(self, tmp_path):
        parent = _style(
            tmp_path, "benchmark:\n  namespaces:\n    dc: urn:example:dc\n", name="parent.yaml"
        )
        child = tmp_path / "child.yaml"
        child.write_text(
            f"extends: {parent}\nbenchmark:\n  reference:\n    dc_elements:\n"
            "      - element: dc:publisher\n        content: x\n"
        )

        assert ConfigLoader.load(child).benchmark["reference"]["dc_elements"] == [
            {"element": "dc:publisher", "content": "x"}
        ]


def _mapping(body: str) -> str:
    """A style body with one field mapping, title, written in the given lines."""
    return "field_mappings:\n  title:\n" + "".join(f"    {line}\n" for line in body.splitlines())


class TestFieldMappings:
    """A field mapping takes the keys the engine reads for its structure."""

    def test_a_key_of_another_structure_is_refused_with_the_mapping_and_the_key(self, tmp_path):
        style = _style(
            tmp_path,
            _mapping("structure: composite\nsource_field: title\nsources:\n  - field: title"),
        )

        with pytest.raises(
            ValueError,
            match=r"style\.yaml: field_mappings\.title\.composite\.source_field: is not a key",
        ):
            ConfigLoader.load(style)

    def test_an_unknown_structure_is_refused_with_the_known_ones(self, tmp_path):
        style = _style(tmp_path, _mapping("structure: composit"))

        with pytest.raises(ValueError) as refused:
            ConfigLoader.load(style)

        message = str(refused.value)
        assert "style.yaml: field_mappings.title: Input tag 'composit'" in message
        for known in ("simple", "composite", "nested", "dublin_core", "embedded_xml_tags"):
            assert f"'{known}'" in message

    @pytest.mark.parametrize(
        ("body", "path"),
        [
            pytest.param("structure: composite", r"composite\.sources", id="composite sources"),
            pytest.param("structure: nested", r"nested\.children", id="nested children"),
            pytest.param(
                "structure: nested\nchildren:\n  - element: check-content",
                r"nested\.children\[0\]\.source_field",
                id="nested child source",
            ),
            pytest.param(
                "structure: dublin_core", r"dublin_core\.source_field", id="dublin core source"
            ),
            pytest.param(
                "structure: composite\nsources:\n  - label: x",
                r"composite\.sources\[0\]\.field",
                id="composite source field",
            ),
        ],
    )
    def test_a_required_key_left_out_is_refused(self, tmp_path, body, path):
        style = _style(tmp_path, _mapping(body))

        with pytest.raises(ValueError, match=rf"field_mappings\.title\.{path}: Field required"):
            ConfigLoader.load(style)

    def test_a_nested_mapping_takes_one_child(self, tmp_path):
        child = "  - source_field: audit\n    element: check-content"
        style = _style(tmp_path, _mapping(f"structure: nested\nchildren:\n{child}\n{child}"))

        with pytest.raises(
            ValueError, match=r"field_mappings\.title\.nested\.children: List should have at most 1"
        ):
            ConfigLoader.load(style)

    @pytest.mark.parametrize(
        ("body", "path", "hint"),
        [
            pytest.param("description: words", r"simple\.description", "comment", id="description"),
            pytest.param("optional: true", r"simple\.optional", "left out", id="optional"),
            pytest.param("content: ''", r"simple\.content", "written empty", id="content"),
            pytest.param(
                "structure: dublin_core\nsource_field: nist_controls\nmultiple: true",
                r"dublin_core\.multiple",
                "one reference",
                id="dublin core multiple",
            ),
            pytest.param(
                "structure: composite\nsources:\n  - field: title\nmultiple: true",
                r"composite\.multiple",
                "simple mapping",
                id="composite multiple",
            ),
            pytest.param(
                "cci_lookup:\n  enabled: true",
                r"simple\.cci_lookup\.enabled",
                "source_logic",
                id="cci lookup enabled",
            ),
            pytest.param(
                "cci_lookup:\n  deduplicate_nist: true",
                r"simple\.cci_lookup\.deduplicate_nist",
                "cci_deduplication",
                id="cci lookup deduplicate",
            ),
        ],
    )
    def test_a_key_nothing_reads_is_refused_with_what_happens_instead(
        self, tmp_path, body, path, hint
    ):
        style = _style(tmp_path, _mapping(body))

        with pytest.raises(
            ValueError, match=rf"field_mappings\.title\.{path}: is not read \(.*{hint}"
        ):
            ConfigLoader.load(style)

    @pytest.mark.parametrize(
        ("body", "path"),
        [
            pytest.param("source_logic: nist", r"simple\.source_logic", id="simple"),
            pytest.param(
                "structure: dublin_core\nsource_field: nist_controls\nsource_logic: cci",
                r"dublin_core\.source_logic",
                id="dublin core",
            ),
        ],
    )
    def test_a_source_logic_the_structure_does_not_act_on_is_refused(self, tmp_path, body, path):
        style = _style(tmp_path, _mapping(body))

        with pytest.raises(ValueError, match=rf"field_mappings\.title\.{path}: Input should be"):
            ConfigLoader.load(style)

    @pytest.mark.parametrize(
        ("body", "path"),
        [
            pytest.param(
                "structure: nested\nchildren:\n  - source_field: audit\n    element: check-content"
                "\nattributes:\n  href: x",
                r"nested\.attributes\.href",
                id="nested",
            ),
            pytest.param(
                "structure: dublin_core\nsource_field: nist_controls\nattributes:\n  system: x",
                r"dublin_core\.attributes\.system",
                id="dublin core",
            ),
        ],
    )
    def test_an_attribute_the_structure_does_not_write_is_refused(self, tmp_path, body, path):
        style = _style(tmp_path, _mapping(body))

        with pytest.raises(ValueError, match=rf"field_mappings\.title\.{path}: is not a key"):
            ConfigLoader.load(style)

    def test_a_simple_mapping_takes_any_attribute(self, tmp_path):
        style = _style(tmp_path, _mapping("attributes:\n  fixref: F-{ref_normalized}"))

        assert ConfigLoader.load(style).field_mappings["title"]["attributes"] == {
            "fixref": "F-{ref_normalized}"
        }

    def test_a_structure_typed_by_a_later_card_is_accepted_as_written(self, tmp_path):
        style = _style(tmp_path, _mapping("structure: embedded_xml_tags\ncomponents: [anything]"))

        assert ConfigLoader.load(style).field_mappings["title"]["components"] == ["anything"]

    def test_a_child_style_may_switch_off_a_mapping_with_null(self, tmp_path):
        parent = _style(tmp_path, _mapping("source_field: title"), name="parent.yaml")
        child = tmp_path / "child.yaml"
        child.write_text(f"extends: {parent}\nfield_mappings:\n  title: null\n")

        assert ConfigLoader.load(child).field_mappings["title"] is None

    def test_a_dublin_core_prefix_the_style_does_not_bind_is_refused(self, tmp_path):
        style = _style(
            tmp_path,
            _mapping(
                "structure: dublin_core\nsource_field: nist_controls\n"
                "dc_elements:\n  - element: dc:title\n    content: x"
            ),
        )

        with pytest.raises(
            ValueError,
            match=r"field_mappings\.title\.dublin_core\.dc_elements\[0\]\.element: the prefix 'dc'",
        ):
            ConfigLoader.load(style)

    def test_a_dublin_core_content_with_no_value_is_refused(self, tmp_path):
        style = _style(
            tmp_path,
            "benchmark:\n  namespaces:\n    dc: urn:example:dc\n"
            + _mapping(
                "structure: dublin_core\nsource_field: nist_controls\n"
                "dc_elements:\n  - element: dc:title\n    content:"
            ),
        )

        with pytest.raises(
            ValueError,
            match=r"dublin_core\.dc_elements\[0\]\.content: has no value; leave the key out",
        ):
            ConfigLoader.load(style)

    def test_a_template_with_no_value_is_refused(self, tmp_path):
        style = _style(tmp_path, _mapping("attributes:\n  fixref:"))

        with pytest.raises(
            ValueError, match=r"field_mappings\.title\.simple\.attributes\.fixref: has no value"
        ):
            ConfigLoader.load(style)
