"""A style file is checked against one schema when it loads: a key nothing reads, or a
value of the wrong kind, is refused with the file and the dotted path of each mistake."""

from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from cis_bench.exporters.mapping_engine import ConfigLoader, MappingEngine
from cis_bench.exporters.style_config import SimpleMapping, XmlName


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

        assert ConfigLoader.load(as_text).rule_defaults.weight == "10.0"
        assert ConfigLoader.load(as_number).rule_defaults.weight == 10.0


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

        assert config.rule_defaults.severity == "medium"


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

    def test_the_loaded_style_model_is_the_whole_merged_style(self, tmp_path):
        # The engine reads the model the last check built: a value the child replaces, a
        # mapping only the parent writes, and a mapping the child switches off with null.
        parent = _style(
            tmp_path,
            "field_mappings:\n"
            "  title:\n    source_field: title\n"
            "  rationale:\n    source_field: rationale\n"
            "  description:\n    source_field: description\n",
            name="parent.yaml",
        )
        child = self._child(
            tmp_path,
            parent,
            "field_mappings:\n  title:\n    source_field: description\n  rationale: null\n",
        )

        mappings = ConfigLoader.load(child).field_mappings

        assert isinstance(mappings["title"], SimpleMapping)
        assert mappings["title"].source_field == "description"
        assert mappings["rationale"] is None
        assert isinstance(mappings["description"], SimpleMapping)
        assert mappings["description"].source_field == "description"

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

        title = (ConfigLoader.load(child).benchmark.__pydantic_extra__ or {})["title"]
        assert (title.source, title.prepend_text) == ("title", "CIS: ")

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

        assert [
            (dc.element, dc.content)
            for dc in ConfigLoader.load(child).benchmark.reference.dc_elements
        ] == [("dc:publisher", "x")]


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

        mapping = ConfigLoader.load(style).field_mappings["title"]
        assert isinstance(mapping, SimpleMapping)
        assert mapping.attributes == {"fixref": "F-{ref_normalized}"}

    def test_a_mapping_of_any_structure_is_checked_against_its_keys(self, tmp_path):
        style = _style(tmp_path, _mapping("structure: embedded_xml_tags\ncomponents: [anything]"))

        with pytest.raises(
            ValueError, match=r"embedded_xml_tags\.components\[0\]: Input should be"
        ):
            ConfigLoader.load(style)

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


_EMBEDDED = """structure: embedded_xml_tags
components:
  - tag: VulnDiscussion
    sources:
      - field: description
        separator: "x"
      - field: rationale
  - tag: Documentable
    content: "false"
"""

_IDENT = """structure: ident_from_list
source_field: cis_controls
ident_spec:
  system_template: "s{item.version}"
  value_template: "{item.control}"
  attributes:
    - name: controlURI
      template: t
      namespace_prefix: "cc{item.version}"
"""

_METADATA = """structure: metadata_from_config
source_field: cis_controls
metadata_spec:
  root_element: cis_controls
  namespace_prefix: controls
  group_by: item.version
  group_element:
    element: framework
    attributes:
      urn: "u{group_key}"
    item_element:
      element: safeguard
      children:
        - element: groups
          children:
            - element: group
              content: "{item.ig1}"
"""


def _changed(body: str, old: str, new: str) -> str:
    """A mapping body with one exact line (or block of lines) replaced."""
    assert body.count(old) == 1, old
    return body.replace(old, new)


_NAMESPACES = """benchmark:
  namespaces:
    default: http://checklists.nist.gov/xccdf/1.2
    controls: urn:example:controls
    dc: http://purl.org/dc/elements/1.1/
"""


def _metadata_mapping(*changes: tuple[str, str]) -> str:
    """A style body with the declared namespaces and one metadata mapping aimed at the Rule's
    metadata element, with the given line changes."""
    body = _changed(
        _METADATA,
        "structure: metadata_from_config",
        "structure: metadata_from_config\ntarget_element: metadata",
    )
    for old, new in changes:
        body = _changed(body, old, new)
    return _NAMESPACES + _mapping(body)


class TestNestedFieldMappings:
    """The mappings with nested specifications (embedded tags, idents from a list, metadata)
    take the keys the engine reads at every level."""

    @pytest.mark.parametrize(
        "body",
        [
            pytest.param(_mapping(_EMBEDDED), id="embedded tags"),
            pytest.param(_mapping(_IDENT), id="idents"),
            pytest.param(_metadata_mapping(), id="metadata"),
            pytest.param(
                _mapping(_changed(_EMBEDDED, '    content: "false"', "    sources: []")),
                id="a tag with no sources, written empty",
            ),
        ],
    )
    def test_a_mapping_the_engine_can_write_loads(self, tmp_path, body):
        style = _style(tmp_path, body)

        mapping = ConfigLoader.load(style).field_mappings["title"]
        assert mapping is not None and f"structure: {mapping.structure}" in body

    @pytest.mark.parametrize(
        ("body", "path"),
        [
            pytest.param(
                _changed(_METADATA, "  group_by:", "  attributes:\n    a: b\n  group_by:"),
                r"metadata_from_config\.metadata_spec\.attributes",
                id="metadata spec",
            ),
            pytest.param(
                _changed(_METADATA, "    element: framework", "    element: framework\n    x: y"),
                r"metadata_from_config\.metadata_spec\.group_element\.x",
                id="group element",
            ),
            pytest.param(
                _changed(
                    _METADATA, "      element: safeguard", "      element: safeguard\n      x: y"
                ),
                r"metadata_from_config\.metadata_spec\.group_element\.item_element\.x",
                id="item element",
            ),
            pytest.param(
                _changed(
                    _METADATA,
                    "              content:",
                    "              x: y\n              content:",
                ),
                r"metadata_from_config\.metadata_spec\.group_element\.item_element\.children\[0\]\.children\[0\]\.x",
                id="a child of a child",
            ),
            pytest.param(
                _METADATA + "transform: none",
                r"metadata_from_config\.transform",
                id="metadata mapping",
            ),
            pytest.param(
                _changed(_EMBEDDED, "  - tag: Documentable", "  - tag: Documentable\n    x: y"),
                r"embedded_xml_tags\.components\[1\]\.x",
                id="component",
            ),
            pytest.param(
                _changed(
                    _EMBEDDED, "      - field: rationale", "      - field: rationale\n        x: y"
                ),
                r"embedded_xml_tags\.components\[0\]\.sources\[1\]\.x",
                id="component source",
            ),
            pytest.param(
                _EMBEDDED + "source_field: title",
                r"embedded_xml_tags\.source_field",
                id="embedded mapping",
            ),
            pytest.param(
                _changed(_IDENT, "  value_template:", "  x: y\n  value_template:"),
                r"ident_from_list\.ident_spec\.x",
                id="ident spec",
            ),
            pytest.param(
                _changed(_IDENT, "      template: t", "      template: t\n      x: y"),
                r"ident_from_list\.ident_spec\.attributes\[0\]\.x",
                id="ident attribute",
            ),
            pytest.param(
                _IDENT + "attributes:\n  a: b",
                r"ident_from_list\.attributes",
                id="ident mapping",
            ),
        ],
    )
    def test_a_key_nothing_reads_is_refused_with_its_path(self, tmp_path, body, path):
        style = _style(tmp_path, _mapping(body))

        with pytest.raises(ValueError, match=rf"field_mappings\.title\.{path}: is not a key"):
            ConfigLoader.load(style)

    @pytest.mark.parametrize(
        ("body", "path"),
        [
            pytest.param(
                "structure: embedded_xml_tags", r"embedded_xml_tags\.components", id="components"
            ),
            pytest.param(
                _changed(_EMBEDDED, "  - tag: Documentable\n", "  - "),
                r"embedded_xml_tags\.components\[1\]\.tag",
                id="tag",
            ),
            pytest.param(
                _changed(_EMBEDDED, "      - field: rationale", "      - separator: x"),
                r"embedded_xml_tags\.components\[0\]\.sources\[1\]\.field",
                id="source field",
            ),
            pytest.param(
                _changed(_IDENT, "source_field: cis_controls\n", ""),
                r"ident_from_list\.source_field",
                id="ident source",
            ),
            pytest.param(
                "structure: ident_from_list\nsource_field: cis_controls",
                r"ident_from_list\.ident_spec",
                id="ident spec",
            ),
            pytest.param(
                _changed(_IDENT, "    - name: controlURI\n      template: t", "    - template: t"),
                r"ident_from_list\.ident_spec\.attributes\[0\]\.name",
                id="ident attribute name",
            ),
            pytest.param(
                _changed(_IDENT, '      namespace_prefix: "cc{item.version}"\n', ""),
                r"ident_from_list\.ident_spec\.attributes\[0\]\.namespace_prefix",
                id="ident attribute prefix",
            ),
            pytest.param(
                _changed(_METADATA, "source_field: cis_controls\n", ""),
                r"metadata_from_config\.source_field",
                id="metadata source",
            ),
            pytest.param(
                "structure: metadata_from_config\nsource_field: cis_controls",
                r"metadata_from_config\.metadata_spec",
                id="metadata spec",
            ),
        ]
        + [
            pytest.param(
                _changed(_METADATA, line, replacement),
                rf"metadata_from_config\.metadata_spec\.{path}",
                id=path,
            )
            for line, replacement, path in [
                ("  root_element: cis_controls\n", "", "root_element"),
                ("  namespace_prefix: controls\n", "", "namespace_prefix"),
                ("  group_by: item.version\n", "", "group_by"),
                ("    element: framework\n", "", r"group_element\.element"),
                ("      element: safeguard\n", "", r"group_element\.item_element\.element"),
                (
                    "        - element: groups\n",
                    "        - content: x\n",
                    r"group_element\.item_element\.children\[0\]\.element",
                ),
                (
                    "    item_element:\n      element: safeguard\n      children:\n",
                    "    x_element:\n      children:\n",
                    r"group_element\.item_element",
                ),
            ]
        ],
    )
    def test_a_required_key_left_out_is_refused(self, tmp_path, body, path):
        style = _style(tmp_path, _mapping(body))

        with pytest.raises(ValueError, match=rf"field_mappings\.title\.{path}: Field required"):
            ConfigLoader.load(style)

    def test_a_metadata_spec_without_a_group_element_is_refused(self, tmp_path):
        body = _METADATA.split("  group_element:")[0]
        style = _style(tmp_path, _mapping(body))

        with pytest.raises(
            ValueError, match=r"metadata_from_config\.metadata_spec\.group_element: Field required"
        ):
            ConfigLoader.load(style)

    @pytest.mark.parametrize(
        ("body", "path"),
        [
            pytest.param(
                _changed(_EMBEDDED, "tag: VulnDiscussion", "tag: Vuln Discussion"),
                r"embedded_xml_tags\.components\[0\]\.tag",
                id="tag",
            ),
            pytest.param(
                _changed(_IDENT, "name: controlURI", "name: cc8:controlURI"),
                r"ident_from_list\.ident_spec\.attributes\[0\]\.name",
                id="ident attribute",
            ),
            pytest.param(
                _changed(_METADATA, "root_element: cis_controls", "root_element: xmlns"),
                r"metadata_from_config\.metadata_spec\.root_element",
                id="root element",
            ),
            pytest.param(
                _changed(_METADATA, "    element: framework", "    element: '{urn:x}framework'"),
                r"metadata_from_config\.metadata_spec\.group_element\.element",
                id="group element",
            ),
            pytest.param(
                _changed(_METADATA, '      urn: "u{group_key}"', '      "xsi:type": x'),
                r"metadata_from_config\.metadata_spec\.group_element\.attributes\.xsi:type",
                id="group attribute",
            ),
            pytest.param(
                _changed(
                    _METADATA, "            - element: group", "            - element: 1group"
                ),
                r"metadata_from_config\.metadata_spec\.group_element\.item_element\.children\[0\]\.children\[0\]\.element",
                id="a child of a child",
            ),
        ],
    )
    def test_a_name_that_is_no_xml_name_is_refused(self, tmp_path, body, path):
        style = _style(tmp_path, _mapping(body))

        with pytest.raises(
            ValueError, match=rf"field_mappings\.title\.{path}: .* is not an XML name"
        ):
            ConfigLoader.load(style)

    @pytest.mark.parametrize(
        ("body", "path"),
        [
            pytest.param(
                _changed(_METADATA, "namespace_prefix: controls", 'namespace_prefix: ""'),
                r"metadata_from_config\.metadata_spec\.namespace_prefix",
                id="metadata",
            ),
            pytest.param(
                _changed(_IDENT, 'namespace_prefix: "cc{item.version}"', 'namespace_prefix: ""'),
                r"ident_from_list\.ident_spec\.attributes\[0\]\.namespace_prefix",
                id="ident attribute",
            ),
        ],
    )
    def test_an_empty_namespace_prefix_is_refused(self, tmp_path, body, path):
        style = _style(tmp_path, _mapping(body))

        with pytest.raises(ValueError, match=rf"field_mappings\.title\.{path}: String should have"):
            ConfigLoader.load(style)

    def test_a_component_gives_its_text_from_sources_or_content_not_both(self, tmp_path):
        body = _changed(
            _EMBEDDED,
            '    content: "false"',
            '    content: "false"\n    sources:\n      - field: title',
        )
        style = _style(tmp_path, _mapping(body))

        with pytest.raises(
            ValueError, match=r"embedded_xml_tags\.components\[1\]: .*sources or content"
        ):
            ConfigLoader.load(style)

    @pytest.mark.parametrize(
        ("body", "path", "hint"),
        [
            pytest.param(
                _METADATA + "requires_post_processing: true",
                r"metadata_from_config\.requires_post_processing",
                "model content",
                id="metadata",
            ),
            pytest.param(
                "source_field: title\nrequires_post_processing: true",
                r"simple\.requires_post_processing",
                "model content",
                id="simple",
            ),
            pytest.param(
                _IDENT + "requires_post_processing: true",
                r"ident_from_list\.requires_post_processing",
                "model content",
                id="ident",
            ),
            pytest.param(
                _changed(_METADATA, "  group_by:", "  namespace: urn:x\n  group_by:"),
                r"metadata_from_config\.metadata_spec\.namespace",
                r"benchmark\.namespaces",
                id="metadata namespace",
            ),
        ],
    )
    def test_a_removed_key_is_refused_with_what_happens_instead(self, tmp_path, body, path, hint):
        style = _style(tmp_path, _mapping(body))

        with pytest.raises(
            ValueError, match=rf"field_mappings\.title\.{path}: is not read \(.*{hint}"
        ):
            ConfigLoader.load(style)


class TestChecksAgainstTheModels:
    """What needs the XCCDF and Benchmark models is checked when the style loads, with the
    path of the key: the fields a style names, the transforms and filters, the elements a
    mapping writes, and where Rule metadata can go."""

    @pytest.mark.parametrize(
        ("body", "path", "reason"),
        [
            pytest.param(
                _mapping("source_field: titel"),
                r"field_mappings\.title\.simple\.source_field",
                "'titel' is not a field of Recommendation",
                id="simple",
            ),
            pytest.param(
                _mapping("source_field: mitre_mapping.techniques"),
                r"field_mappings\.title\.simple\.source_field",
                "'mitre_mapping.techniques' is not a field of Recommendation",
                id="a dotted path where one field is read",
            ),
            pytest.param(
                _mapping(
                    "structure: nested\nchildren:\n  - source_field: audt\n    element: check-content"
                ),
                r"field_mappings\.title\.nested\.children\[0\]\.source_field",
                "'audt' is not a field of Recommendation",
                id="nested child",
            ),
            pytest.param(
                _mapping("structure: composite\nsources:\n  - field: defualt_value"),
                r"field_mappings\.title\.composite\.sources\[0\]\.field",
                "'defualt_value' is not a field of Recommendation",
                id="composite source",
            ),
            pytest.param(
                _mapping(_changed(_EMBEDDED, "field: rationale", "field: rationle")),
                r"field_mappings\.title\.embedded_xml_tags\.components\[0\]\.sources\[1\]\.field",
                "'rationle' is not a field of Recommendation",
                id="embedded tag source",
            ),
            pytest.param(
                _mapping(
                    _changed(
                        _IDENT,
                        "source_field: cis_controls",
                        "source_field: mitre_mapping.techiques",
                    )
                ),
                r"field_mappings\.title\.ident_from_list\.source_field",
                "'techiques' is not a field of MITREMapping",
                id="ident list, a dotted path",
            ),
            pytest.param(
                _mapping("structure: dublin_core\nsource_field: nist_contrls"),
                r"field_mappings\.title\.dublin_core\.source_field",
                "'nist_contrls' is not a field of Recommendation",
                id="dublin core",
            ),
            pytest.param(
                _mapping("cci_lookup:\n  source_field: artifacts"),
                r"field_mappings\.title\.simple\.cci_lookup\.source_field",
                "'artifacts' is not a field of Recommendation holding CIS controls",
                id="cci lookup",
            ),
            pytest.param(
                "group_elements:\n  title:\n    source: titel\n",
                r"group_elements\.title\.source",
                "'titel' is not a field of Recommendation",
                id="group element",
            ),
            pytest.param(
                "benchmark:\n  title:\n    source: titel\n",
                r"benchmark\.title\.source",
                "'titel' is not a field of Benchmark",
                id="benchmark element",
            ),
        ],
    )
    def test_a_field_the_models_do_not_have_is_refused(self, tmp_path, body, path, reason):
        style = _style(tmp_path, body)

        with pytest.raises(ValueError, match=rf"style\.yaml: {path}: .*{reason}"):
            ConfigLoader.load(style)

    @pytest.mark.parametrize(
        ("body", "path"),
        [
            pytest.param(
                _mapping("source_field: title\ntransform: nope"),
                r"field_mappings\.title\.simple\.transform",
                id="field mapping",
            ),
            pytest.param(
                "group_elements:\n  title:\n    source: title\n    transform: nope\n",
                r"group_elements\.title\.transform",
                id="group element",
            ),
            pytest.param(
                "benchmark:\n  title:\n    source: title\n    transform: nope\n",
                r"benchmark\.title\.transform",
                id="benchmark element",
            ),
            pytest.param(
                "benchmark:\n  profiles:\n    description_transform: nope\n",
                r"benchmark\.profiles\.description_transform",
                id="profile description",
            ),
            pytest.param(
                "rule_id:\n  template: 'R-{ref|nope}'\n",
                r"rule_id\.template",
                id="a filter in a rule id template",
            ),
            pytest.param(
                "benchmark:\n  notice:\n    content: '{benchmark.url|nope}'\n",
                r"benchmark\.notice\.content",
                id="a filter in the notice",
            ),
            pytest.param(
                _mapping(
                    _changed(
                        _IDENT,
                        'value_template: "{item.control}"',
                        'value_template: "{item.control|nope}"',
                    )
                ),
                r"field_mappings\.title\.ident_from_list\.ident_spec\.value_template",
                id="a filter in an ident template",
            ),
        ],
    )
    def test_a_transform_no_function_is_registered_under_is_refused(self, tmp_path, body, path):
        style = _style(tmp_path, body)

        with pytest.raises(
            ValueError, match=rf"style\.yaml: {path}: .*Unknown transformation: nope"
        ):
            ConfigLoader.load(style)

    def test_a_filter_without_a_name_is_refused(self, tmp_path):
        style = _style(tmp_path, "rule_id:\n  template: 'R-{ref|}'\n")

        with pytest.raises(ValueError, match=r"rule_id\.template: filter without a transform name"):
            ConfigLoader.load(style)

    def test_a_string_nothing_fills_is_text(self, tmp_path):
        style = _style(tmp_path, "rule_defaults:\n  severity: '{x|nope}'\n")

        assert ConfigLoader.load(style).rule_defaults.severity == "{x|nope}"

    def test_an_empty_cci_lookup_field_names_no_field_and_the_mapping_writes(
        self, tmp_path, sample_recommendation_minimal
    ):
        style = _style(
            tmp_path,
            "rule_id:\n  template: R-{ref}\n"
            + _mapping("source_field: title\ncci_lookup:\n  source_field: ''"),
        )
        rec = sample_recommendation_minimal

        rule = MappingEngine(style).map_rule(rec, {"benchmark": None, "recommendations": []})

        assert [title.content for title in rule.title] == [[rec.title]]

    @pytest.mark.parametrize(
        ("body", "path", "reason"),
        [
            pytest.param(
                "field_mappings:\n  bogus:\n    source_field: title\n",
                r"field_mappings\.bogus\.simple",
                r"XCCDF 1\.2 has no 'bogus' element in Rule",
                id="a mapping named after no Rule element",
            ),
            pytest.param(
                _mapping("source_field: title\ntarget_element: bogus"),
                r"field_mappings\.title\.simple\.target_element",
                r"XCCDF 1\.2 has no 'bogus' element in Rule",
                id="a target that is no Rule element",
            ),
            pytest.param(
                _mapping("source_field: title\ntarget_element: impact_metric"),
                r"field_mappings\.title\.simple\.target_element",
                ".*holds a plain value",
                id="a target that holds a plain value",
            ),
            pytest.param(
                _mapping(
                    "structure: nested\ntarget_element: check\nchildren:\n"
                    "  - source_field: audit\n    element: check-contnet"
                ),
                r"field_mappings\.title\.nested\.children\[0\]\.element",
                r"the XCCDF 1\.2 'check' element has no 'check-contnet' element",
                id="a nested child the target's type does not have",
            ),
            pytest.param(
                _mapping(
                    "structure: nested\nchildren:\n  - source_field: audit\n    element: check-content"
                ),
                r"field_mappings\.title\.nested\.children\[0\]\.element",
                r"the XCCDF 1\.2 'title' element has no 'check-content' element",
                id="a nested child in a target that holds no such element",
            ),
            pytest.param(
                "group_elements:\n  bogus:\n    source: title\n",
                r"group_elements\.bogus",
                r"XCCDF 1\.2 has no 'bogus' element in Group",
                id="group element",
            ),
            pytest.param(
                "benchmark:\n  bogus:\n    source: title\n",
                r"benchmark\.bogus",
                r"XCCDF 1\.2 has no 'bogus' element in Benchmark",
                id="benchmark element",
            ),
        ],
    )
    def test_an_element_the_xccdf_version_does_not_have_is_refused(
        self, tmp_path, body, path, reason
    ):
        style = _style(tmp_path, body)

        with pytest.raises(ValueError, match=rf"style\.yaml: {path}: {reason}"):
            ConfigLoader.load(style)

    def test_a_metadata_mapping_the_rule_can_hold_loads(self, tmp_path):
        style = _style(tmp_path, _metadata_mapping())

        mapping = ConfigLoader.load(style).field_mappings["title"]
        assert mapping is not None and mapping.target_element == "metadata"

    @pytest.mark.parametrize(
        ("changes", "path", "reason"),
        [
            pytest.param(
                [("namespace_prefix: controls", "namespace_prefix: nope")],
                r"metadata_spec\.namespace_prefix",
                "'nope' is not declared in benchmark.namespaces",
                id="undeclared prefix",
            ),
            pytest.param(
                [("namespace_prefix: controls", "namespace_prefix: default")],
                r"metadata_spec\.namespace_prefix",
                "is the XCCDF namespace",
                id="the XCCDF namespace",
            ),
            pytest.param(
                [("group_by: item.version", "group_by: item.versoin")],
                r"metadata_spec\.group_by",
                "'versoin' is not a field of the items 'cis_controls' lists",
                id="grouping by no field of the items",
            ),
            pytest.param(
                [("target_element: metadata", "target_element: title")],
                r"metadata_from_config\.target_element",
                "cannot hold repeated elements of the namespace",
                id="an element with text content",
            ),
            pytest.param(
                [
                    ("target_element: metadata", "target_element: dc_status"),
                    ("namespace_prefix: controls", "namespace_prefix: dc"),
                ],
                r"metadata_from_config\.target_element",
                "cannot hold repeated elements of the namespace",
                id="an element of Dublin Core elements only, with the Dublin Core prefix",
            ),
            pytest.param(
                [("target_element: metadata", "target_element: signature")],
                r"metadata_from_config\.target_element",
                "cannot hold repeated elements of the namespace",
                id="a single element",
            ),
        ],
    )
    def test_metadata_the_rule_cannot_hold_as_written_is_refused(
        self, tmp_path, changes, path, reason
    ):
        style = _style(tmp_path, _metadata_mapping(*changes))

        with pytest.raises(
            ValueError, match=rf"field_mappings\.title\.(metadata_from_config\.)?{path}: .*{reason}"
        ):
            ConfigLoader.load(style)


class TestTemplateVariables:
    """A template's variables are checked when the style loads, against the values the engine
    gives that template and the models behind them, with the template's path."""

    @pytest.mark.parametrize(
        ("body", "path", "reason"),
        [
            pytest.param(
                _mapping(
                    _changed(
                        _IDENT,
                        'value_template: "{item.control}"',
                        'value_template: "{item.contrl}"',
                    )
                ),
                r"field_mappings\.title\.ident_from_list\.ident_spec\.value_template",
                "'contrl' is not a field of CISControl",
                id="ident value, an item field",
            ),
            pytest.param(
                _mapping(
                    _changed(
                        _IDENT,
                        'system_template: "s{item.version}"',
                        'system_template: "s{itm.version}"',
                    )
                ),
                r"field_mappings\.title\.ident_from_list\.ident_spec\.system_template",
                "'itm' is not a value this template can use",
                id="ident system, the item misspelled",
            ),
            pytest.param(
                _mapping(_changed(_IDENT, "template: t", "template: 't{item.versoin}'")),
                r"ident_from_list\.ident_spec\.attributes\[0\]\.template",
                "'versoin' is not a field of CISControl",
                id="ident attribute",
            ),
            pytest.param(
                _mapping(
                    _changed(
                        _IDENT,
                        'namespace_prefix: "cc{item.version}"',
                        'namespace_prefix: "cc{item.versoin}"',
                    )
                ),
                r"ident_from_list\.ident_spec\.attributes\[0\]\.namespace_prefix",
                "'versoin' is not a field of CISControl",
                id="ident attribute prefix",
            ),
            pytest.param(
                _mapping(
                    "structure: ident_from_list\nsource_field: parent\nident_spec:\n  value_template: '{item.titel}'"
                ),
                r"ident_from_list\.ident_spec\.value_template",
                "'titel' is not a field of ParentReference",
                id="ident over one value, not a list",
            ),
            pytest.param(
                _metadata_mapping(('content: "{item.ig1}"', 'content: "{item.ig9}"')),
                r"metadata_from_config\.metadata_spec\.group_element\.item_element\.children\[0\]\.children\[0\]\.content",
                "'ig9' is not a field of CISControl",
                id="metadata item content, a child of a child",
            ),
            pytest.param(
                _metadata_mapping(('urn: "u{group_key}"', 'urn: "u{group_ky}"')),
                r"metadata_from_config\.metadata_spec\.group_element\.attributes\.urn",
                "'group_ky' is not a value this template can use",
                id="metadata group attribute",
            ),
            pytest.param(
                _mapping("source_field: title\nattributes:\n  fixref: 'F-{rec.titel}'"),
                r"field_mappings\.title\.simple\.attributes\.fixref",
                "'titel' is not a field of Recommendation",
                id="rule attribute",
            ),
            pytest.param(
                _mapping(
                    "structure: nested\nchildren:\n  - source_field: audit\n    element: check-content\nattributes:\n  system: 'C-{reff}'"
                ),
                r"field_mappings\.title\.nested\.attributes\.system",
                "'reff' is not a value this template can use",
                id="nested system",
            ),
            pytest.param(
                _mapping(
                    "structure: dublin_core\nsource_field: nist_controls\nattributes:\n  href: '{benchmark.ur}'"
                ),
                r"field_mappings\.title\.dublin_core\.attributes\.href",
                "'ur' is not a field of Benchmark",
                id="dublin core href",
            ),
            pytest.param(
                "benchmark:\n  namespaces:\n    dc: http://purl.org/dc/elements/1.1/\n"
                + _mapping(
                    "structure: dublin_core\nsource_field: nist_controls\ndc_elements:\n  - element: dc:identifier\n    content: '{nist_id}'"
                ),
                r"field_mappings\.title\.dublin_core\.dc_elements\[0\]\.content",
                "'nist_id' is not a value this template can use",
                id="dublin core element",
            ),
            pytest.param(
                "benchmark:\n  notice:\n    content: '{benchmark.titel}'\n",
                r"benchmark\.notice\.content",
                "'titel' is not a field of Benchmark",
                id="notice",
            ),
            pytest.param(
                "benchmark:\n  namespaces:\n    dc: http://purl.org/dc/elements/1.1/\n  reference:\n    dc_elements:\n      - element: dc:identifier\n        content: '{nist_control_id}'\n",
                r"benchmark\.reference\.dc_elements\[0\]\.content",
                "'nist_control_id' is not a value this template can use",
                id="benchmark reference element",
            ),
            pytest.param(
                "benchmark:\n  plain_text:\n    - id: release-info\n      content: '{download_dat}'\n",
                r"benchmark\.plain_text\[0\]\.content",
                "'download_dat' is not a value this template can use",
                id="plain text",
            ),
            pytest.param(
                "benchmark:\n  id_template: 'B_{benchmark_ids}'\n",
                r"benchmark\.id_template",
                "'benchmark_ids' is not a value this template can use",
                id="benchmark id",
            ),
            pytest.param(
                "rule_id:\n  template: 'R-{rec.title}'\n",
                r"rule_id\.template",
                "'rec' is not a value this template can use",
                id="rule id, a value only rule attributes have",
            ),
            pytest.param(
                "benchmark:\n  profiles:\n    id_template: 'p_{profile.titel}'\n",
                r"benchmark\.profiles\.id_template",
                "'titel' is not a key of profile",
                id="profile id",
            ),
            pytest.param(
                _mapping(
                    _changed(
                        _IDENT,
                        'value_template: "{item.control}"',
                        'value_template: "{item..control}"',
                    )
                ),
                r"ident_from_list\.ident_spec\.value_template",
                "empty name",
                id="an empty name",
            ),
        ],
    )
    def test_a_variable_the_template_does_not_have_is_refused(self, tmp_path, body, path, reason):
        style = _style(tmp_path, body)

        with pytest.raises(
            ValueError, match=rf"style\.yaml: (field_mappings\.title\.)?{path}: .*{reason}"
        ):
            ConfigLoader.load(style)

    @pytest.mark.parametrize(
        "body",
        [
            pytest.param(
                _mapping(
                    _changed(
                        _IDENT,
                        'value_template: "{item.control}"',
                        'value_template: "{item.control|dotted_number_path:subcontrol}"',
                    )
                ),
                id="a filter after a field",
            ),
            pytest.param(
                _mapping(
                    _changed(
                        _changed(
                            _IDENT,
                            "source_field: cis_controls",
                            "source_field: mitre_mapping.techniques",
                        ),
                        '  attributes:\n    - name: controlURI\n      template: t\n      namespace_prefix: "cc{item.version}"\n',
                        "",
                    )
                ),
                id="items that are text",
            ),
            pytest.param(
                _mapping(
                    "source_field: title\nattributes:\n  fixref: 'F-{rec.title}-{benchmark.title}-{stig_number}'"
                ),
                id="rule attribute values",
            ),
            pytest.param(
                _mapping(
                    "structure: ident_from_list\nsource_field: parent\nident_spec:\n  value_template: '{item.title}'"
                ),
                id="ident over one value, not a list",
            ),
        ],
    )
    def test_a_variable_the_template_has_loads(self, tmp_path, body):
        style = _style(tmp_path, body)

        assert ConfigLoader.load(style).field_mappings["title"]
