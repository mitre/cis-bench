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
    """Each file of an extends chain is checked alone, so a mistake is reported with its
    file; the merged style is checked once more for what only the files together get
    wrong."""

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

    def test_mistakes_in_parent_and_child_are_reported_together_each_with_its_file(self, tmp_path):
        parent = _style(tmp_path, "rule_id:\n  templat: x\n", name="parent.yaml")
        child = self._child(tmp_path, parent, "cci_deduplication:\n  enabled: maybe\n")

        with pytest.raises(ValueError) as refused:
            ConfigLoader.load(child)

        message = str(refused.value)
        assert "parent.yaml: rule_id.templat" in message
        assert "child.yaml: cci_deduplication.enabled" in message

    def test_a_key_the_child_adds_to_a_parent_section_is_reported_with_the_child_file(
        self, tmp_path
    ):
        parent = _style(tmp_path, "rule_defaults:\n  severity: low\n", name="parent.yaml")
        child = self._child(tmp_path, parent, "rule_defaults:\n  severty: high\n")

        with pytest.raises(ValueError, match=r"child\.yaml: rule_defaults\.severty"):
            ConfigLoader.load(child)

    def test_a_namespace_binding_is_reported_with_the_file_that_wrote_it(self, tmp_path):
        parent = _style(
            tmp_path, "benchmark:\n  namespaces:\n    xml: urn:example:bad\n", name="parent.yaml"
        )
        child = self._child(
            tmp_path,
            parent,
            'benchmark:\n  namespaces:\n    good: urn:example:good\n    "a:b": urn:example:b\n',
        )

        with pytest.raises(ValueError) as refused:
            ConfigLoader.load(child)

        message = str(refused.value)
        assert "parent.yaml: benchmark.namespaces.xml: prefix 'xml' is reserved" in message
        assert "child.yaml: benchmark.namespaces.a:b: 'a:b' is not a namespace prefix" in message

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
    def test_a_key_that_is_no_text_is_refused_with_its_place(self, tmp_path, key):
        style = _style(tmp_path, f"rule_defaults:\n  {key}: x\n")

        with pytest.raises(
            ValueError, match=r"style\.yaml: rule_defaults\..+: Keys should be strings"
        ):
            ConfigLoader.load(style)

    def test_a_group_element_name_that_is_no_text_is_refused(self, tmp_path):
        style = _style(tmp_path, "group_elements:\n  1:\n    source: ref\n")

        with pytest.raises(ValueError, match=r"style\.yaml: group_elements\.1: "):
            ConfigLoader.load(style)


class TestSelfContainingStyles:
    """YAML anchors can make a mapping that contains itself."""

    def test_a_section_that_contains_itself_is_refused_without_a_crash(self, tmp_path):
        style = _style(tmp_path, "rule_defaults: &defaults\n  severity: low\n  again: *defaults\n")

        with pytest.raises(ValueError, match=r"style\.yaml: rule_defaults\.again"):
            ConfigLoader.load(style)
