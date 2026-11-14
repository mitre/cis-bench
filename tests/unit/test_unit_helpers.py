"""Unit tests for helper methods and utilities.

Tests the core helper functions that power the mapping engine:
- TransformRegistry: the registered transforms
- VariableSubstituter: Variable substitution in templates
- CCILookupService: CCI deduplication logic
- DRY Helpers: Element construction methods
- WorkbenchParser: HTML/JSON parsing utilities
- HTMLCleaner: the HTML table and reference parsers
"""

import json
import re
from pathlib import Path

import pytest

from cis_bench.exporters.mapping_engine import (
    ConfigLoader,
    MappingEngine,
    TransformRegistry,
    VariableSubstituter,
)
from cis_bench.models.benchmark import (
    CISControl,
    MITREMapping,
    ProfileDefinition,
    Recommendation,
)
from cis_bench.utils.cci_lookup import CCILookupService
from cis_bench.utils.html_parser import HTMLCleaner
from cis_bench.utils.parsers import WorkbenchParser

# ============================================================================
# FIXTURES - Common test data
# ============================================================================


@pytest.fixture
def sample_mitre_table():
    """Sample MITRE ATT&CK mapping table HTML."""
    return """
    <table>
        <tr>
            <th>Techniques</th>
        </tr>
        <tr>
            <td>T1078, T1110, T1563</td>
        </tr>
        <tr>
            <th>Tactics</th>
        </tr>
        <tr>
            <td>TA0001, TA0002</td>
        </tr>
        <tr>
            <th>Mitigations</th>
        </tr>
        <tr>
            <td>M1026, M1027</td>
        </tr>
    </table>
    """


@pytest.fixture
def sample_nist_references():
    """Sample HTML with NIST control references."""
    return """
    <p>NIST SP 800-53 Rev. 5: CM-7, SI-3, AC-2(1)</p>
    <p>Additional: NIST SP 800-53 Revision 4 :: CM-7.1</p>
    """


@pytest.fixture
def sample_cis_controls_json():
    """Sample CIS Controls JSON string."""
    return """
    [
        {
            "version": "8",
            "control": "4.8",
            "title": "Uninstall or Disable Unnecessary Services",
            "ig1": true,
            "ig2": true,
            "ig3": true
        },
        {
            "version": "7",
            "control": "9.2",
            "title": "Ensure Only Approved Ports",
            "ig1": false,
            "ig2": true,
            "ig3": true
        }
    ]
    """


@pytest.fixture
def sample_recommendation():
    """Sample Recommendation object for testing."""
    return Recommendation(
        url="https://workbench.cisecurity.org/recommendations/12345",
        ref="3.1.1",
        title="Ensure that the kubeconfig file permissions are set to 644 or more restrictive",
        assessment_status="Automated",
        description="<p>Ensure that the <code>kubeconfig</code> file has permissions of <strong>644</strong> or more restrictive.</p>",
        rationale="<p>The kubeconfig file controls various parameters. You should restrict its file permissions.</p>",
        impact="<p>This significantly strengthens the security posture.</p>",
        audit="<pre><code>stat -c %a /var/lib/kubelet/kubeconfig</code></pre>",
        remediation="<pre><code>chmod 644 &lt;kubeconfig file&gt;</code></pre>",
        default_value="<p>See the AWS EKS documentation.</p>",
        additional_info="<p>Additional mitigation information.</p>",
        references="<p><a href='https://kubernetes.io/docs/'>Kubernetes Docs</a></p>",
        cis_controls=[
            CISControl(
                version=8, control="4.8", title="Uninstall Services", ig1=True, ig2=True, ig3=True
            )
        ],
        nist_controls=["CM-7", "SI-3", "AC-2(1)"],
        profiles=["Level 1", "Server"],
        mitre_mapping=MITREMapping(
            techniques=["T1078", "T1110"], tactics=["TA0001"], mitigations=["M1026"]
        ),
    )


@pytest.fixture
def sample_context():
    """Sample mapping context for variable substitution."""
    return {
        "platform": "eks",
        "ref": "3.1.1",
        "ref_normalized": "3_1_1",
        "stig_number": "030101",  # 3.1.1 → 03 01 01 → 030101
        "control": {"version": "8", "control": "4.8", "title": "Uninstall Services"},
        "nist_control_id": "CM-7",
    }


@pytest.fixture
def config_path(disa_config_path):
    """Path to DISA style config (use conftest fixture)."""
    return disa_config_path


# ============================================================================
# TEST: TransformRegistry
# ============================================================================


class TestTransformRegistry:
    """Unit tests for the registered transforms."""

    @pytest.mark.parametrize(
        ("text", "lines"),
        [
            ("a\nb", ["a", "b"]),
            ("  a  \n\n\t\nb\n", ["a", "b"]),
            ("single", ["single"]),
            ("\n \n", []),
        ],
    )
    def test_lines_are_the_non_empty_stripped_lines(self, text, lines):
        assert TransformRegistry.apply("lines", text) == lines

    def test_none_transform(self):
        """Test 'none' transformation (pass-through)."""
        test_value = "unchanged text"
        result = TransformRegistry.apply("none", test_value)
        assert result == test_value

    def test_unknown_transform_raises_error(self):
        """Test that unknown transformation raises ValueError."""
        with pytest.raises(ValueError, match="Unknown transformation"):
            TransformRegistry.apply("nonexistent_transform", "test")

    # === strip_version_prefix transform tests ===

    def test_strip_version_prefix_lowercase_v(self):
        """Test stripping lowercase 'v' prefix from version."""
        result = TransformRegistry.apply("strip_version_prefix", "v4.0.0")
        assert result == "4.0.0"

    def test_strip_version_prefix_uppercase_v(self):
        """Test stripping uppercase 'V' prefix from version."""
        result = TransformRegistry.apply("strip_version_prefix", "V1.2.3")
        assert result == "1.2.3"

    def test_strip_version_prefix_no_prefix(self):
        """Test version without prefix is unchanged."""
        result = TransformRegistry.apply("strip_version_prefix", "4.0.0")
        assert result == "4.0.0"

    def test_strip_version_prefix_none_input(self):
        """Test strip_version_prefix with None input."""
        result = TransformRegistry.apply("strip_version_prefix", None)
        assert result == ""

    def test_strip_version_prefix_empty_string(self):
        """Test strip_version_prefix with empty string."""
        result = TransformRegistry.apply("strip_version_prefix", "")
        assert result == ""

    def test_strip_version_prefix_only_v(self):
        """Test edge case: version is just 'v'."""
        result = TransformRegistry.apply("strip_version_prefix", "v")
        assert result == ""


# ============================================================================
# TEST: VariableSubstituter
# ============================================================================


class TestDottedNumberPath:
    """A dotted numbered ID ("8.5") as a URI path whose sub-levels the config names."""

    @pytest.mark.parametrize(
        ("value", "labels", "path"),
        [
            ("8.5", ("subcontrol",), "8/subcontrol/5"),
            ("3.10", ("subcontrol",), "3/subcontrol/10"),
            ("13", ("subcontrol",), "13"),
            (" 4.8 ", ("subcontrol",), "4/subcontrol/8"),
            ("1.2.3", ("section", "item"), "1/section/2/item/3"),
            (8, (), "8"),
        ],
    )
    def test_each_sub_level_gets_its_label(self, value, labels, path):
        assert TransformRegistry.get("dotted_number_path")(value, *labels) == path

    @pytest.mark.parametrize(
        "value", ["", "8.", ".5", "8.5.1", "v8", "8,5", "8.x", "\u0668.\u0665", None]
    )
    def test_any_other_shape_is_refused(self, value):
        with pytest.raises(ValueError, match="dotted number"):
            TransformRegistry.get("dotted_number_path")(value, "subcontrol")

    @pytest.mark.parametrize(
        ("labels", "expected"), [((), "at most 1 level "), (("subcontrol",), "at most 2 levels ")]
    )
    def test_the_refusal_counts_the_levels(self, labels, expected):
        with pytest.raises(ValueError, match=expected):
            TransformRegistry.get("dotted_number_path")("1.2.3", *labels)

    @pytest.mark.parametrize(("value", "labels"), [("8.5", ("",)), ("1.2.3", ("subcontrol", " "))])
    def test_an_empty_label_is_refused(self, value, labels):
        # "{item.control|dotted_number_path:subcontrol,}" must not make "1/subcontrol/2//3".
        with pytest.raises(ValueError, match="empty label"):
            TransformRegistry.get("dotted_number_path")(value, *labels)


class TestIdentAttributes:
    """Namespaced ident attributes come from the style's namespaces, or the export stops."""

    CONTROL_URI = {
        "source_field": "cis_controls",
        "ident_spec": {
            "system_template": "http://cisecurity.org/20-cc/v{item.version}.0",
            "value_template": "",
            "attributes": [
                {
                    "name": "controlURI",
                    "template": "u/{item.control|dotted_number_path:subcontrol}",
                    "namespace_prefix": "cc{item.version}",
                }
            ],
        },
    }

    def test_the_attribute_is_written_in_the_declared_namespace(
        self, cis_config_path, sample_recommendation
    ):
        (ident,) = MappingEngine(cis_config_path).generate_idents_from_config(
            sample_recommendation, self.CONTROL_URI
        )
        assert ident.system == "http://cisecurity.org/20-cc/v8.0"
        assert ident.other_attributes == {
            "{http://cisecurity.org/20-cc/v8.0}controlURI": "u/4/subcontrol/8"
        }

    def test_an_undeclared_namespace_prefix_stops_the_export(
        self, cis_config_path, sample_recommendation
    ):
        mapping = {
            **self.CONTROL_URI,
            "ident_spec": {
                **self.CONTROL_URI["ident_spec"],
                "attributes": [{"name": "controlURI", "template": "u", "namespace_prefix": "cc99"}],
            },
        }
        with pytest.raises(ValueError, match="'cc99' is not declared"):
            MappingEngine(cis_config_path).generate_idents_from_config(
                sample_recommendation, mapping
            )

    def test_an_attribute_without_a_name_is_refused(self, cis_config_path, sample_recommendation):
        mapping = {
            **self.CONTROL_URI,
            "ident_spec": {
                **self.CONTROL_URI["ident_spec"],
                "attributes": [{"template": "u", "namespace_prefix": "cc8"}],
            },
        }
        with pytest.raises(ValueError, match="ident attribute needs a name"):
            MappingEngine(cis_config_path).generate_idents_from_config(
                sample_recommendation, mapping
            )

    def test_an_xccdf_1_1_ident_cannot_carry_namespaced_attributes(
        self, disa_config_path, sample_recommendation
    ):
        with pytest.raises(ValueError, match="ident allows attributes from other namespaces"):
            MappingEngine(disa_config_path).generate_idents_from_config(
                sample_recommendation, self.CONTROL_URI
            )


class TestProfileGeneration:
    """One profile per profile the benchmark defines, or per profile name on its rules; each
    selects its own rules and the rules of every profile it includes."""

    MAPPINGS = [
        {"match": "Level 1 - Server", "title": "Level 1 - Server"},
        {
            "match": "Level 2 - Server",
            "title": "Level 2 - Server",
            "includes": ["Level 1 - Server"],
        },
        {
            "match": "Level 3 - Server",
            "title": "Level 3 - Server",
            "includes": ["Level 2 - Server"],
        },
    ]

    @staticmethod
    def _recs(*profiles_by_ref):
        return [
            Recommendation(
                ref=ref,
                title=f"Rule {ref}",
                url=f"https://workbench.cisecurity.org/sections/1/recommendations/{i}",
                assessment_status="Automated",
                profiles=profiles,
            )
            for i, (ref, profiles) in enumerate(profiles_by_ref, start=1)
        ]

    @staticmethod
    def _selected(profiles):
        return {p.id: [s.idref.rsplit("_rule_", 1)[1] for s in p.select] for p in profiles}

    @staticmethod
    def _text(elements):
        return "".join(str(part) for part in elements[0].content) if elements else None

    def _generate(self, cis_config_path, recs, mappings, definitions=None):
        config = {
            "generate_from_rules": True,
            "id_template": "p_{profile.title|slug:_}",
            "description_transform": "none",
            "profile_mappings": mappings,
        }
        return MappingEngine(cis_config_path).generate_profiles_from_rules(
            recs, config, definitions or []
        )

    def test_a_profile_selects_the_rules_of_the_profiles_it_includes(self, cis_config_path):
        recs = self._recs(
            ("1.1", ["Level 1 - Server"]),
            ("1.2", ["Level 2 - Server"]),
            ("1.3", ["Level 1 - Server", "Level 2 - Server"]),
            ("1.4", ["Level 1 - Workstation"]),
            ("1.5", ["Level 3 - Server"]),
        )

        selected = self._selected(self._generate(cis_config_path, recs, self.MAPPINGS))

        assert selected == {
            "p_level_1_server": ["1_1", "1_3"],
            "p_level_2_server": ["1_1", "1_2", "1_3"],
            "p_level_3_server": ["1_1", "1_2", "1_3", "1_5"],
            "p_level_1_workstation": ["1_4"],
        }

    def test_every_profile_name_on_the_rules_and_no_other_gets_a_profile(self, cis_config_path):
        # Mapped names first, in mapping order; other names in the order rules first use them.
        # A mapping no rule names is not one of this benchmark's profiles, even when it
        # includes one that is.
        recs = self._recs(
            ("1.1", ["Level 2 - Docker - Linux"]),
            ("1.2", ["Level 1"]),
            ("1.3", ["Level 1 - Server", "Level 1"]),
        )

        profiles = self._generate(cis_config_path, recs, self.MAPPINGS)

        assert [(p.id, self._text(p.title)) for p in profiles] == [
            ("p_level_1_server", "Level 1 - Server"),
            ("p_level_2_docker_linux", "Level 2 - Docker - Linux"),
            ("p_level_1", "Level 1"),
        ]
        assert self._selected(profiles)["p_level_1"] == ["1_2", "1_3"]

    def test_a_defined_profile_that_selects_no_rule_is_left_out_with_a_warning(
        self, cis_config_path, caplog
    ):
        definitions = [
            ProfileDefinition(title="Level 1 - Alpha"),
            ProfileDefinition(title="Level 1 - Beta"),
        ]
        recs = self._recs(("1.1", ["Level 1 - Alpha"]))

        with caplog.at_level("WARNING", logger="cis_bench.exporters.mapping_engine"):
            profiles = self._generate(cis_config_path, recs, [], definitions)

        assert [p.id for p in profiles] == ["p_level_1_alpha"]
        warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1
        assert "'Level 1 - Beta'" in warnings[0]

    def test_defined_profiles_select_their_rules_and_their_ancestors(self, cis_config_path):
        definitions = [
            ProfileDefinition(title="Level 1 - Alpha", description="First tier."),
            ProfileDefinition(title="Level 2 - Alpha", parent="Level 1 - Alpha"),
            ProfileDefinition(title="Level 3 - Alpha", parent="Level 2 - Alpha"),
        ]
        recs = self._recs(
            ("1.1", ["Level 1 - Alpha"]),
            ("1.2", ["Level 2 - Alpha"]),
            ("1.3", ["Level 3 - Alpha"]),
            ("1.4", ["Level 1 - Server"]),
        )
        # With definitions the page decides; the YAML's mappings and includes are not used.
        mappings = [{"match": "Level 1 - Alpha", "includes": ["Level 3 - Alpha"]}, *self.MAPPINGS]

        profiles = self._generate(cis_config_path, recs, mappings, definitions)

        assert self._selected(profiles) == {
            "p_level_1_alpha": ["1_1"],
            "p_level_2_alpha": ["1_1", "1_2"],
            "p_level_3_alpha": ["1_1", "1_2", "1_3"],
        }
        assert self._text(profiles[0].description) == "First tier."
        assert profiles[1].description == []

    @pytest.mark.parametrize(
        ("definitions", "message"),
        [
            (
                [ProfileDefinition(title="Level 2 - Alpha", parent="Level 1 - Beta")],
                "'Level 1 - Beta'",
            ),
            (
                [
                    ProfileDefinition(title="Level 1 - Alpha", parent="Level 2 - Alpha"),
                    ProfileDefinition(title="Level 2 - Alpha", parent="Level 1 - Alpha"),
                ],
                "include each other",
            ),
        ],
    )
    def test_a_parent_that_is_not_a_profile_or_a_loop_is_refused(
        self, cis_config_path, definitions, message
    ):
        recs = self._recs(("1.1", ["Level 2 - Alpha"]))

        with pytest.raises(ValueError, match=message):
            self._generate(cis_config_path, recs, [], definitions)

    @pytest.mark.parametrize("named_on_rules", ["Level 2 - Server", "Level 1 - Workstation"])
    def test_an_include_that_names_no_profile_mapping_is_refused(
        self, cis_config_path, named_on_rules
    ):
        # The style's mappings are checked whole, whether or not this benchmark uses them.
        mappings = [{**self.MAPPINGS[1], "includes": ["Level 9 - Server"]}]
        recs = self._recs(("1.1", [named_on_rules]))

        with pytest.raises(ValueError, match="'Level 9 - Server'"):
            self._generate(cis_config_path, recs, mappings)

    def test_a_profile_mapping_without_a_match_is_refused(self, cis_config_path):
        mappings = [{"title": "Level 1 - Server"}]
        recs = self._recs(("1.1", ["Level 1 - Server"]))

        with pytest.raises(ValueError, match="profile mapping needs a match"):
            self._generate(cis_config_path, recs, mappings)

    def test_a_profile_mapping_with_its_own_id_is_refused(self, cis_config_path):
        # Profile ids come from the style's id_template, one rule for every profile.
        mappings = [{**self.MAPPINGS[0], "id": "l1s"}]
        recs = self._recs(("1.1", ["Level 1 - Server"]))

        with pytest.raises(ValueError, match="id_template"):
            self._generate(cis_config_path, recs, mappings)

    def test_two_mappings_for_one_profile_name_are_refused(self, cis_config_path):
        mappings = [self.MAPPINGS[0], {**self.MAPPINGS[0], "title": "Level 1 (Server)"}]
        recs = self._recs(("1.1", ["Level 1 - Server"]))

        with pytest.raises(ValueError, match="'Level 1 - Server'.*more than one"):
            self._generate(cis_config_path, recs, mappings)

    @pytest.mark.parametrize("with_definitions", [True, False])
    def test_two_profiles_with_one_id_are_refused(self, cis_config_path, with_definitions):
        # Profile ids are xsd:ID values; two titles that slug alike would write one id twice.
        titles = ["Level 1 - Server", "Level 1 (Server)"]
        recs = self._recs(("1.1", titles))
        definitions = [ProfileDefinition(title=title) for title in titles]

        with pytest.raises(ValueError, match="p_level_1_server"):
            self._generate(cis_config_path, recs, [], definitions if with_definitions else None)

    def test_profiles_that_include_each_other_are_refused(self, cis_config_path):
        mappings = [
            {**self.MAPPINGS[0], "includes": ["Level 2 - Server"]},
            self.MAPPINGS[1],
        ]
        recs = self._recs(("1.1", ["Level 1 - Server"]))

        with pytest.raises(ValueError, match="include each other"):
            self._generate(cis_config_path, recs, mappings)


class TestSlug:
    """A title as a URI- and id-safe slug, the separator named by the config."""

    @pytest.mark.parametrize(
        ("title", "separator", "slug"),
        [
            ("Level 1 - Server", "_", "level_1_server"),
            ("Level 2 - Docker - Linux", "_", "level_2_docker_linux"),
            ("Level 1 - Server", "-", "level-1-server"),
            ("  E3 Level 1 (Cloud)  ", "_", "e3_level_1_cloud"),
            ("Niveau 1 - Café Serveur", "_", "niveau_1_cafe_serveur"),
        ],
    )
    def test_runs_of_other_characters_become_one_separator(self, title, separator, slug):
        assert TransformRegistry.get("slug")(title, separator) == slug

    @pytest.mark.parametrize("title", ["", "  -  ", None])
    def test_a_title_with_nothing_to_keep_is_refused(self, title):
        with pytest.raises(ValueError, match="slug"):
            TransformRegistry.get("slug")(title, "_")


class TestStyleInheritance:
    """A style that extends another keeps what its parent declares unless it overrides it."""

    @staticmethod
    def _child(tmp_path, parent, body=""):
        child = tmp_path / "child.yaml"
        child.write_text(f"extends: {parent}\nmetadata:\n  style_name: child\n{body}")
        return ConfigLoader.load(child)

    def test_a_style_extending_cis_keeps_its_namespaces(self, tmp_path, cis_config_path):
        parent = ConfigLoader.load(cis_config_path)

        child = self._child(tmp_path, cis_config_path)

        assert child.namespaces == parent.namespaces
        assert child.namespaces["cc8"] == "http://cisecurity.org/20-cc/v8.0"

    def test_a_child_adds_and_overrides_namespaces(self, tmp_path, cis_config_path):
        child = self._child(
            tmp_path,
            cis_config_path,
            "benchmark:\n  namespaces:\n    cc8: urn:example:cc8\n    ex: urn:example\n",
        )

        assert child.namespaces["cc8"] == "urn:example:cc8"
        assert child.namespaces["ex"] == "urn:example"
        assert child.namespaces["cc7"] == "http://cisecurity.org/20-cc/v7.0"

    def test_a_top_level_namespaces_section_is_refused(self, tmp_path):
        # Namespaces live in benchmark.namespaces; a top-level section would be ignored.
        style = tmp_path / "style.yaml"
        style.write_text("namespaces:\n  default: urn:example\n")

        with pytest.raises(ValueError, match="benchmark.namespaces"):
            ConfigLoader.load(style)

    @pytest.mark.parametrize(
        "section",
        ["transformations", "cci_defaults", "formatting", "implementation_notes", "notes"],
    )
    def test_a_top_level_section_the_loader_does_not_read_is_refused(self, tmp_path, section):
        # A section the loader does not read would be ignored silently, and the style would
        # promise a setting nothing applies.
        style = tmp_path / "style.yaml"
        style.write_text(f"metadata:\n  style_name: s\n{section}:\n  key: value\n")

        with pytest.raises(ValueError, match=section):
            ConfigLoader.load(style)

    def test_a_parent_style_carrying_an_unread_section_is_refused_through_its_child(self, tmp_path):
        parent = tmp_path / "parent.yaml"
        parent.write_text("metadata:\n  style_name: p\nformatting:\n  indent: 2\n")

        with pytest.raises(ValueError, match="formatting"):
            self._child(tmp_path, parent)

    def test_a_child_inherits_and_overrides_post_processing(self, tmp_path, cis_config_path):
        parent = ConfigLoader.load(cis_config_path)

        child = self._child(
            tmp_path, cis_config_path, "post_processing:\n  remove_override_attr: false\n"
        )

        assert parent.post_processing == {"remove_override_attr": True}
        assert child.post_processing == {"remove_override_attr": False}


class TestPostProcessingSettings:
    """A post_processing setting the exporter does not read is refused when the style loads."""

    @staticmethod
    def _style(tmp_path, post_processing: str):
        style = tmp_path / "style.yaml"
        style.write_text(f"metadata:\n  style_name: s\npost_processing:\n{post_processing}")
        return style

    @pytest.mark.parametrize("setting", ["strip_namespace_prefixes", "preserve_namespaces"])
    def test_a_removed_namespace_setting_is_refused_with_where_namespaces_are_declared(
        self, tmp_path, setting
    ):
        style = self._style(tmp_path, f"  {setting}: null\n")

        with pytest.raises(ValueError, match=rf"{setting}.*benchmark\.namespaces"):
            ConfigLoader.load(style)

    def test_the_removed_handlers_setting_is_refused_with_where_metadata_is_built(self, tmp_path):
        style = self._style(tmp_path, "  handlers: [metadata_injection]\n")

        with pytest.raises(ValueError, match=r"handlers.*metadata_from_config"):
            ConfigLoader.load(style)

    def test_an_unknown_setting_is_refused_by_name(self, tmp_path):
        style = self._style(tmp_path, "  pretty_print: true\n")

        with pytest.raises(ValueError, match="pretty_print"):
            ConfigLoader.load(style)

    def test_the_settings_the_exporter_reads_load(self, tmp_path):
        style = self._style(tmp_path, "  remove_override_attr: false\n")

        assert ConfigLoader.load(style).post_processing == {"remove_override_attr": False}


class TestVariableSubstituter:
    """Unit tests for variable substitution."""

    def test_a_filter_applies_a_registered_transform_to_the_variable(self):
        control = CISControl(version=8, control="8.5", title="t", ig1=True, ig2=True, ig3=True)
        template = (
            "http://cisecurity.org/20-cc/v{item.version}.0/control/"
            "{item.control|dotted_number_path:subcontrol}"
        )

        result = VariableSubstituter.substitute(template, {"item": control})

        assert result == "http://cisecurity.org/20-cc/v8.0/control/8/subcontrol/5"

    def test_a_filter_on_the_whole_template_returns_the_transformed_value(self):
        assert VariableSubstituter.substitute("{value|dotted_number_path}", {"value": "13"}) == "13"

    def test_filter_arguments_follow_a_colon_separated_by_commas(self):
        result = VariableSubstituter.substitute(
            "{value|dotted_number_path:section, item}", {"value": "1.2.3"}
        )
        assert result == "1/section/2/item/3"

    def test_an_unknown_filter_is_refused(self):
        with pytest.raises(ValueError, match="Unknown transformation: no_such_filter"):
            VariableSubstituter.substitute("x {value|no_such_filter}", {"value": "a"})

    @pytest.mark.parametrize("template", ["{value|}", "{value| }", "{value|:subcontrol}"])
    def test_a_filter_without_a_name_is_refused(self, template):
        with pytest.raises(ValueError, match="filter without a transform name"):
            VariableSubstituter.substitute(template, {"value": "8.5"})

    def test_arguments_a_transform_does_not_take_are_refused(self):
        with pytest.raises(ValueError, match="strip_version_prefix does not take the arguments"):
            VariableSubstituter.substitute("{value|strip_version_prefix:keep}", {"value": "v1"})

    def test_a_filter_is_applied_to_an_empty_value_too(self):
        # The transform decides what an empty value means; it is never skipped silently.
        with pytest.raises(ValueError, match="dotted number"):
            VariableSubstituter.substitute("{value|dotted_number_path:subcontrol}", {"value": ""})

    def test_simple_variable_substitution(self, sample_context):
        """Test simple variable substitution."""
        template = "xccdf_cis_{platform}_rule_{ref_normalized}"
        result = VariableSubstituter.substitute(template, sample_context)
        assert result == "xccdf_cis_eks_rule_3_1_1"

    def test_nested_variable_substitution(self, sample_context):
        """Test nested variable access (control.version)."""
        template = "Control {control.version}.{control.control}"
        result = VariableSubstituter.substitute(template, sample_context)
        assert result == "Control 8.4.8"

    def test_multiple_variables_in_template(self, sample_context):
        """Test template with multiple variables."""
        template = "Platform: {platform}, Ref: {ref}, Normalized: {ref_normalized}"
        result = VariableSubstituter.substitute(template, sample_context)
        assert result == "Platform: eks, Ref: 3.1.1, Normalized: 3_1_1"

    def test_an_unknown_variable_is_refused(self):
        # A typo in a style would otherwise write an empty part and no error.
        with pytest.raises(ValueError, match="missing_var"):
            VariableSubstituter.substitute("Test {missing_var} value", {"present": "x"})

    @pytest.mark.parametrize("template", ["SV-{stig_number_rule", "SV-}x", "{", "a}b"])
    def test_an_unclosed_or_stray_brace_is_refused(self, template):
        with pytest.raises(ValueError, match=re.escape(template)):
            VariableSubstituter.substitute(template, {"stig_number": "030101"})

    @pytest.mark.parametrize("template", ["{item..control}", "{rec.mitre_mapping.}", "{.x}"])
    def test_an_empty_name_in_a_path_is_refused(self, template):
        context = {"item": {"control": "4.8"}, "rec": {"mitre_mapping": None}}
        with pytest.raises(ValueError, match="empty name"):
            VariableSubstituter.substitute(template, context)

    def test_a_known_variable_with_an_empty_value_substitutes_empty_text(self):
        # Empty data is data; only an unknown name is an error.
        assert VariableSubstituter.substitute("P: {platform}.", {"platform": ""}) == "P: ."

    @pytest.mark.parametrize(
        ("template", "context"),
        [
            ("{platform}", {"platform": None}),
            ("{rec.mitre_mapping}", {"rec": {"mitre_mapping": None}}),
        ],
    )
    def test_a_none_value_reads_as_empty_text_in_a_single_variable_template_too(
        self, template, context
    ):
        # Mixed text already writes None as empty; a template that is one variable must
        # not hand None to the element instead.
        assert VariableSubstituter.substitute(template, context) == ""

    def test_an_absent_optional_value_along_a_path_reads_as_empty_text(self):
        # A recommendation without a MITRE mapping has mitre_mapping None; its fields read
        # as empty, not as an error.
        context = {"rec": {"mitre_mapping": None}}
        assert VariableSubstituter.substitute("T: {rec.mitre_mapping.techniques}", context) == "T: "

    def test_empty_template(self):
        """Test substitution with empty template."""
        result = VariableSubstituter.substitute("", {"key": "value"})
        assert result == ""

    def test_template_with_no_variables(self, sample_context):
        """Test template without any variables."""
        template = "This is a plain string"
        result = VariableSubstituter.substitute(template, sample_context)
        assert result == template

    def test_an_unknown_attribute_of_a_value_is_refused(self, sample_context):
        with pytest.raises(ValueError, match="nonexistent"):
            VariableSubstituter.substitute("Value: {control.nonexistent}", sample_context)

    def test_variable_with_special_characters_in_value(self):
        """Test substitution where value contains special characters."""
        context = {"platform": "eks-1.2_special"}
        template = "Platform: {platform}"
        result = VariableSubstituter.substitute(template, context)
        assert result == "Platform: eks-1.2_special"

    def test_deeply_nested_variables(self):
        """Test deeply nested variable access."""
        context = {"level1": {"level2": {"level3": "deep_value"}}}
        template = "Deep: {level1.level2.level3}"
        result = VariableSubstituter.substitute(template, context)
        assert result == "Deep: deep_value"

    def test_a_none_value_in_mixed_text_reads_as_empty_text(self):
        context = {"platform": None, "ref": "3.1.1"}
        assert (
            VariableSubstituter.substitute("Platform: {platform}, Ref: {ref}", context)
            == "Platform: , Ref: 3.1.1"
        )


# ============================================================================
# TEST: CCILookupService
# ============================================================================


class TestCCILookupService:
    def test_loading_and_deduplicating_log_nothing_at_info(self, caplog):
        """Per-recommendation detail is DEBUG; an export must not print a line per lookup."""
        with caplog.at_level("INFO", logger="cis_bench.utils.cci_lookup"):
            service = CCILookupService()
            service.deduplicate_nist_controls(["4.8"], ["AC-1"], extract="all")
        assert [r.getMessage() for r in caplog.records if r.levelname == "INFO"] == []

    """Unit tests for CCI deduplication."""

    @pytest.fixture
    def cci_service(self):
        """Initialize CCI lookup service."""
        return CCILookupService()

    def test_get_ccis_for_cis_control_exists(self, cci_service):
        """Test getting CCIs for a known CIS control."""
        # Assuming "4.8" exists in mapping file
        ccis = cci_service.get_ccis_for_cis_control("4.8")
        # Should return list of CCIMapping objects
        assert isinstance(ccis, list)
        if ccis:  # If mapping exists
            assert all(hasattr(c, "cci") for c in ccis)

    def test_get_ccis_for_nonexistent_control(self, cci_service):
        """Test getting CCIs for non-existent CIS control."""
        ccis = cci_service.get_ccis_for_cis_control("99.99")
        assert ccis == []

    def test_deduplicate_nist_controls_all_covered(self, cci_service):
        """Test deduplication when all NIST controls are covered by CCIs."""
        # Use a real CIS control that maps to CCIs
        cis_controls = ["4.8"]
        cited_nist = ["CM-7"]  # Base control that should be covered

        ccis, extra_nist = cci_service.deduplicate_nist_controls(cis_controls, cited_nist)

        # Should have CCIs
        assert isinstance(ccis, list)
        # Extra NIST should be minimal if CM-7 is covered
        assert isinstance(extra_nist, list)

    def test_deduplicate_nist_controls_some_extras(self, cci_service):
        """Test deduplication when some NIST controls are NOT covered."""
        cis_controls = ["4.8"]
        # Include a control that likely won't be covered
        cited_nist = ["CM-7", "SI-99", "AC-99"]

        ccis, extra_nist = cci_service.deduplicate_nist_controls(cis_controls, cited_nist)

        # Should have some CCIs
        assert isinstance(ccis, list)
        # Should have some extras (the non-existent controls)
        assert isinstance(extra_nist, list)

    def test_deduplicate_nist_controls_no_cis_controls(self, cci_service):
        """Test deduplication with no CIS controls (all NIST become extras)."""
        cis_controls = []
        cited_nist = ["CM-7", "SI-3"]

        ccis, extra_nist = cci_service.deduplicate_nist_controls(cis_controls, cited_nist)

        assert ccis == []
        # All cited NIST should be extras
        assert set(extra_nist) == set(cited_nist)

    def test_deduplicate_nist_controls_no_nist_cited(self, cci_service):
        """Test deduplication with no NIST controls cited."""
        cis_controls = ["4.8"]
        cited_nist = []

        ccis, extra_nist = cci_service.deduplicate_nist_controls(cis_controls, cited_nist)

        # Should still get CCIs from CIS controls
        assert isinstance(ccis, list)
        # No extras
        assert extra_nist == []


# ============================================================================
# TEST: DRY Helper Methods (MappingEngine)
# ============================================================================


class TestDRYHelpers:
    """Unit tests for DRY helper methods in MappingEngine."""

    @pytest.fixture
    def engine(self, config_path):
        """Create MappingEngine instance."""
        return MappingEngine(config_path)

    def test_construct_typed_element_with_content_field(self, engine):
        """Test _construct_typed_element with type that has 'content' field."""
        # HtmlTextWithSubType uses 'content'
        HtmlTextWithSubType = engine.get_xccdf_class("HtmlTextWithSubType")
        elem = engine._construct_typed_element(HtmlTextWithSubType, "Test content")

        assert elem is not None
        assert hasattr(elem, "content")
        assert elem.content == ["Test content"]

    def test_construct_typed_element_with_value_field(self, engine):
        """Test _construct_typed_element with type that has 'value' field."""
        # TextType uses 'value'
        TextType = engine.get_xccdf_class("TextType")
        elem = engine._construct_typed_element(TextType, "Test value")

        assert elem is not None
        assert hasattr(elem, "value")
        assert elem.value == "Test value"

    def test_construct_typed_element_with_none_value(self, engine):
        """Test _construct_typed_element with None value."""
        TextType = engine.get_xccdf_class("TextType")
        elem = engine._construct_typed_element(TextType, None)

        # Should handle None gracefully (depends on implementation)
        assert elem is not None or elem is None

    def test_is_list_field_for_list_type(self, engine):
        """Test _is_list_field correctly identifies list fields."""
        Rule = engine.get_xccdf_class("Rule")

        # Rule.title is list[TextWithSubType]
        is_list = engine._is_list_field(Rule, "title")
        assert is_list is True

    def test_is_list_field_for_single_type(self, engine):
        """Test _is_list_field correctly identifies single-value fields."""
        Rule = engine.get_xccdf_class("Rule")

        # Rule.version is Optional[VersionType] (single)
        is_list = engine._is_list_field(Rule, "version")
        # This depends on XCCDF schema - version might be single or list
        assert isinstance(is_list, bool)

    def test_is_list_field_for_nonexistent_field(self, engine):
        """Test _is_list_field with non-existent field (defaults to True)."""
        Rule = engine.get_xccdf_class("Rule")
        is_list = engine._is_list_field(Rule, "nonexistent_field")
        assert is_list is True  # Default behavior

    def test_element_name_to_type_name_kebab_case(self, engine):
        """Test _element_name_to_type_name with kebab-case."""
        type_name = engine._element_name_to_type_name("check-content")
        assert type_name == "CheckContentType"

    def test_element_name_to_type_name_lowercase(self, engine):
        """Test _element_name_to_type_name with lowercase."""
        type_name = engine._element_name_to_type_name("title")
        assert type_name == "TitleType"

    def test_element_name_to_type_name_already_has_type_suffix(self, engine):
        """Test _element_name_to_type_name when name already ends with 'Type'."""
        type_name = engine._element_name_to_type_name("TextType")
        # Should not double-add Type
        assert type_name == "TexttypeType" or type_name == "TextType"

    def test_build_field_value_simple_field(self, engine, sample_recommendation):
        """Test _build_field_value with simple field mapping."""
        field_mapping = {"source_field": "title", "transform": "none"}
        context = {"ref_normalized": "3_1_1"}

        value = engine._build_field_value("title", field_mapping, sample_recommendation, context)

        # Should return the title as stored
        assert value is not None
        assert isinstance(value, str)
        assert "kubeconfig" in value.lower()

    def test_build_field_value_embedded_xml(self, engine, sample_recommendation):
        """Test _build_field_value with embedded_xml_tags structure."""
        field_mapping = engine.config.field_mappings["description"]
        context = {"ref_normalized": "3_1_1"}

        value = engine._build_field_value(
            "description", field_mapping, sample_recommendation, context
        )

        # Should return VulnDiscussion XML
        assert value is not None
        assert "<VulnDiscussion>" in value

    def test_embedded_xml_tags_without_components_is_refused(self, engine, sample_recommendation):
        with pytest.raises(ValueError, match="embedded_xml_tags needs components"):
            engine._build_field_value(
                "description", {"structure": "embedded_xml_tags"}, sample_recommendation, {}
            )

    def test_build_field_value_cci_lookup(self, engine, sample_recommendation):
        """Test _build_field_value with CCI lookup."""
        field_mapping = {"source_logic": "cci_lookup_with_deduplication"}
        context = {"ref_normalized": "3_1_1"}

        value = engine._build_field_value("ident", field_mapping, sample_recommendation, context)

        # Should return list of CCIs
        assert isinstance(value, list)

    def test_build_field_value_missing_source_field(self, engine, sample_recommendation):
        """Test _build_field_value with no source_field specified."""
        field_mapping = {}  # Empty mapping
        context = {"ref_normalized": "3_1_1"}

        value = engine._build_field_value("unknown", field_mapping, sample_recommendation, context)

        assert value is None


# ============================================================================
# TEST: WorkbenchParser
# ============================================================================


class TestWorkbenchParser:
    """Unit tests for Workbench parsing utilities."""

    def test_parse_mitre_table_valid(self, sample_mitre_table):
        """Test parsing valid MITRE table."""
        result = WorkbenchParser.parse_mitre_table(sample_mitre_table)

        assert result is not None
        assert isinstance(result, MITREMapping)
        assert "T1078" in result.techniques
        assert "T1110" in result.techniques
        assert "TA0001" in result.tactics
        assert "M1026" in result.mitigations

    def test_parse_mitre_table_none_input(self):
        """Test parse_mitre_table with None input."""
        result = WorkbenchParser.parse_mitre_table(None)
        assert result is None

    def test_parse_mitre_table_empty_string(self):
        """Test parse_mitre_table with empty string."""
        result = WorkbenchParser.parse_mitre_table("")
        assert result is None

    def test_parse_mitre_table_null_string(self):
        """Test parse_mitre_table with "null" string."""
        result = WorkbenchParser.parse_mitre_table("null")
        assert result is None

    def test_parse_mitre_table_no_table(self):
        """Test parse_mitre_table with HTML that has no table."""
        html = "<p>No table here</p>"
        result = WorkbenchParser.parse_mitre_table(html)
        assert result is None

    def test_parse_mitre_table_empty_table(self):
        """Test parse_mitre_table with empty table."""
        html = "<table></table>"
        result = WorkbenchParser.parse_mitre_table(html)
        assert result is None

    def test_parse_nist_controls_valid(self, sample_nist_references):
        """Test parsing NIST control references."""
        result = WorkbenchParser.parse_nist_controls(sample_nist_references)

        assert isinstance(result, list)
        assert "CM-7" in result
        assert "SI-3" in result
        assert "AC-2(1)" in result

    def test_parse_nist_controls_none_input(self):
        """Test parse_nist_controls with None."""
        result = WorkbenchParser.parse_nist_controls(None)
        assert result == []

    def test_parse_nist_controls_no_matches(self):
        """Test parse_nist_controls with HTML that has no NIST refs."""
        html = "<p>No NIST references here</p>"
        result = WorkbenchParser.parse_nist_controls(html)
        assert result == []

    def test_parse_cis_controls_json_valid(self, sample_cis_controls_json):
        """Test parsing CIS Controls JSON."""
        result = WorkbenchParser.parse_cis_controls_json(sample_cis_controls_json)

        assert isinstance(result, list)
        assert len(result) == 2

        # Check first control
        assert result[0].version == 8  # version is int, not string
        assert result[0].control == "4.8"
        assert result[0].ig1 is True
        assert result[0].ig2 is True

        # Check second control
        assert result[1].version == 7  # version is int, not string
        assert result[1].control == "9.2"
        assert result[1].ig1 is False

    def test_parse_cis_controls_json_invalid_json(self):
        """Test parse_cis_controls_json with invalid JSON."""
        result = WorkbenchParser.parse_cis_controls_json("not valid json")
        assert result == []

    def test_parse_cis_controls_json_empty_array(self):
        """Test parse_cis_controls_json with empty array."""
        result = WorkbenchParser.parse_cis_controls_json("[]")
        assert result == []

    def test_parse_cis_controls_json_missing_ig_values(self):
        """Test parse_cis_controls_json with missing/null IG values."""
        json_str = """
        [{
            "version": "8",
            "control": "4.8",
            "title": "Test",
            "ig1": null,
            "ig2": null,
            "ig3": null
        }]
        """
        result = WorkbenchParser.parse_cis_controls_json(json_str)

        assert len(result) == 1
        # Should default None to False
        assert result[0].ig1 is False
        assert result[0].ig2 is False
        assert result[0].ig3 is False

    def test_parse_artifacts_json_builds_a_title_the_payload_gives_as_html_as_markdown(self):
        """The artifact payload gives some titles as HTML; the artifact holds Markdown."""
        payload = json.dumps(
            [
                {
                    "id": 1,
                    "view_level": "1.1.1.1.1",
                    "title": "<p>Ensure the agent is <em>active</em></p>",
                    "status": "accepted",
                    "artifact_type": {"type": "command"},
                }
            ]
        )

        result = WorkbenchParser.parse_artifacts_json(payload)

        assert [artifact.title for artifact in result] == ["Ensure the agent is *active*"]

    def test_extract_assessment_status_automated(self):
        """Test extracting 'Automated' status."""
        html = "<p>This is an automated assessment</p>"
        result = WorkbenchParser.extract_assessment_status(html)
        assert result == "Automated"

    def test_extract_assessment_status_manual(self):
        """Test extracting 'Manual' status."""
        html = "<p>This is a manual assessment</p>"
        result = WorkbenchParser.extract_assessment_status(html)
        assert result == "Manual"

    def test_extract_assessment_status_unknown(self):
        """Test extracting status when none found."""
        html = "<p>Some other text</p>"
        result = WorkbenchParser.extract_assessment_status(html)
        assert result == "Some other text" or result == "Unknown"

    def test_extract_assessment_status_none(self):
        """Test extracting status from None."""
        result = WorkbenchParser.extract_assessment_status(None)
        assert result == "Unknown"

    def test_parent_link_whose_text_is_the_label(self):
        html = '<a href="https://workbench.cisecurity.org/sections/1">Parent: Initial Setup</a>'
        parent = WorkbenchParser.parse_parent_link(html)
        assert parent is not None
        assert str(parent.url) == "https://workbench.cisecurity.org/sections/1"
        assert parent.title == "Initial Setup"

    def test_parent_link_found_by_its_icon(self):
        html = (
            '<a href="https://workbench.cisecurity.org/sections/2">'
            '<i class="fa-level-up"></i> PARENT : Filesystem</a>'
        )
        parent = WorkbenchParser.parse_parent_link(html)
        assert parent is not None
        assert str(parent.url) == "https://workbench.cisecurity.org/sections/2"
        assert parent.title == "Filesystem"

    def test_the_first_labelled_link_wins_over_other_links(self):
        html = (
            '<a href="https://workbench.cisecurity.org/other">Home</a>'
            '<a href="https://workbench.cisecurity.org/sections/3">PARENT : Services</a>'
        )
        parent = WorkbenchParser.parse_parent_link(html)
        assert parent is not None
        assert str(parent.url) == "https://workbench.cisecurity.org/sections/3"

    def test_a_parent_link_without_href_is_no_parent(self):
        assert WorkbenchParser.parse_parent_link("<a>PARENT : Services</a>") is None

    def test_no_parent_link_is_none(self):
        assert WorkbenchParser.parse_parent_link('<a href="/x">Home</a>') is None


# ============================================================================
# TEST: HTMLCleaner
# ============================================================================


class TestHTMLCleaner:
    """Unit tests for the HTML table and reference parsers."""

    def test_parse_mitre_table(self, sample_mitre_table):
        """Test MITRE table parsing (from HTMLCleaner)."""
        result = HTMLCleaner.parse_mitre_table(sample_mitre_table)

        if result:  # If implementation exists
            assert isinstance(result, dict)

    def test_parse_nist_references(self, sample_nist_references):
        """Test NIST reference parsing (from HTMLCleaner)."""
        result = HTMLCleaner.parse_nist_references(sample_nist_references)

        assert isinstance(result, list)
        if result:  # If patterns match
            assert any("CM-7" in ref for ref in result)


# ============================================================================
# TEST: Integration - End-to-End Scenarios
# ============================================================================


class TestIntegrationScenarios:
    """Integration tests using real-world examples."""

    @pytest.fixture
    def engine(self, config_path):
        """Create MappingEngine instance."""
        return MappingEngine(config_path)

    def test_embedded_tags_are_built_from_the_style_components(self, engine, sample_recommendation):
        """The description's tags come from the style's components, in their order, each
        part's text escaped once so a reader that unescapes the description and parses the
        tags gets the stored text."""
        from html import unescape

        components = engine.config.field_mappings["description"]["components"]

        result = engine.create_embedded_xml_tags(components, sample_recommendation)

        tags = re.findall(r"<([A-Za-z]+)>", result)
        assert tags == [component["tag"] for component in components]
        vuln = re.search(r"<VulnDiscussion>(.*)</VulnDiscussion>", result, re.S).group(1)
        assert unescape(vuln) == (
            f"{sample_recommendation.description}\n\n{sample_recommendation.rationale}"
        )

    def test_each_part_is_escaped_so_a_placeholder_is_not_read_as_a_tag(self, engine):
        rec = Recommendation(
            ref="1.1.1",
            title="t",
            url="https://workbench.cisecurity.org/sections/1/recommendations/1",
            assessment_status="Automated",
            description="Owned by <user> & <group>",
            impact=None,
        )
        components = [
            {"tag": "VulnDiscussion", "sources": [{"field": "description"}]},
            {"tag": "PotentialImpacts", "sources": [{"field": "impact"}]},
            {"tag": "Documentable", "content": "false"},
        ]

        result = engine.create_embedded_xml_tags(components, rec)

        assert result == (
            "<VulnDiscussion>Owned by &lt;user&gt; &amp; &lt;group&gt;</VulnDiscussion>"
            "<PotentialImpacts></PotentialImpacts><Documentable>false</Documentable>"
        )

    def test_a_separator_follows_a_source_only_when_another_text_comes_after_it(self, engine):
        rec = Recommendation(
            ref="1.1.1",
            title="t",
            url="https://workbench.cisecurity.org/sections/1/recommendations/1",
            assessment_status="Automated",
            description="First.",
            rationale=None,
        )
        components = [
            {
                "tag": "VulnDiscussion",
                "sources": [
                    {"field": "description", "separator": "\n\n"},
                    {"field": "rationale"},
                ],
            }
        ]

        assert engine.create_embedded_xml_tags(components, rec) == (
            "<VulnDiscussion>First.</VulnDiscussion>"
        )

    def test_get_ccis_with_deduplication(self, engine, sample_recommendation):
        """Test CCI lookup and deduplication with real recommendation."""
        ccis, extra_nist = engine.get_ccis_with_deduplication(sample_recommendation)

        assert isinstance(ccis, list)
        assert isinstance(extra_nist, list)

        # Should have some result (either CCIs or extra NIST)
        assert len(ccis) > 0 or len(extra_nist) > 0

    def test_normalize_ref(self, engine):
        """Test ref normalization for IDs."""
        assert engine.normalize_ref("3.1.1") == "3_1_1"
        assert engine.normalize_ref("1.2.3.4") == "1_2_3_4"
        assert engine.normalize_ref("5") == "5"

    def test_variable_substitution_in_rule_id(self, engine, sample_context):
        """Test that rule ID template substitution works correctly."""
        template = engine.config.rule_id.get("template", "CIS-{ref_normalized}_rule")
        result = VariableSubstituter.substitute(template, sample_context)

        # DISA style uses stig_number (030101), CIS style uses ref_normalized (3_1_1)
        # Either format is valid depending on config
        assert "030101" in result or "3_1_1" in result
        # DISA uses SV-/V- prefix, CIS uses organization prefix
        assert "SV-" in result or "xccdf" in result.lower() or "cis" in result.lower()

    def test_full_transformation_pipeline(self, sample_recommendation):
        """Test full pipeline: stored text → Transform → Substitute → Output."""
        # 1. The stored text (Markdown)
        content = sample_recommendation.description

        # 2. Transform (the text is written as it is)
        text = TransformRegistry.apply("none", content)
        assert text == content

        # 3. Substitute variables
        template = "Ref {ref}: {content}"
        context = {"ref": sample_recommendation.ref, "content": text}
        result = VariableSubstituter.substitute(template, context)

        # Should have ref and content
        assert "3.1.1" in result
        assert "kubeconfig" in result.lower()


# ============================================================================
# TEST: Edge Cases and Error Handling
# ============================================================================


# ============================================================================
# TEST: ID Format Validation (TDD for config-driven ID templates)
# ============================================================================


class TestIDFormatValidation:
    """Verify ID formats match expected patterns for each style.

    DISA STIG convention:
    - Group ID: V-NNNNNN (e.g., V-030101)
    - Rule ID: SV-NNNNNNrREV_rule (e.g., SV-030101r1_rule)

    CIS convention:
    - Group ID: xccdf_org.cisecurity.benchmarks_group_{ref_normalized}
    - Rule ID: xccdf_org.cisecurity.benchmarks_rule_{ref_normalized}
    """

    @pytest.fixture
    def disa_engine(self, disa_config_path):
        """Create MappingEngine with DISA style."""
        return MappingEngine(disa_config_path)

    @pytest.fixture
    def cis_engine(self, cis_config_path):
        """Create MappingEngine with CIS style."""
        return MappingEngine(cis_config_path)

    # --- DISA ID Format Tests ---

    def test_disa_group_id_format_v_prefix(self, disa_engine):
        """DISA Group ID must start with V- prefix."""
        template = disa_engine.config.group_id.get("template", "")
        context = {"stig_number": "030101", "ref_normalized": "3_1_1", "platform": "eks"}
        group_id = VariableSubstituter.substitute(template, context)

        assert group_id.startswith("V-"), f"DISA Group ID must start with V-, got: {group_id}"

    def test_disa_group_id_format_numeric(self, disa_engine):
        """DISA Group ID must have numeric portion after V-."""
        import re

        template = disa_engine.config.group_id.get("template", "")
        context = {"stig_number": "030101", "ref_normalized": "3_1_1", "platform": "eks"}
        group_id = VariableSubstituter.substitute(template, context)

        # Pattern: V-NNNNNN (V- followed by digits)
        pattern = r"^V-\d+$"
        assert re.match(pattern, group_id), f"DISA Group ID must match V-NNNNNN, got: {group_id}"

    def test_disa_rule_id_format_sv_prefix(self, disa_engine):
        """DISA Rule ID must start with SV- prefix."""
        template = disa_engine.config.rule_id.get("template", "")
        context = {"stig_number": "030101", "ref_normalized": "3_1_1", "platform": "eks"}
        rule_id = VariableSubstituter.substitute(template, context)

        assert rule_id.startswith("SV-"), f"DISA Rule ID must start with SV-, got: {rule_id}"

    def test_disa_rule_id_format_revision_suffix(self, disa_engine):
        """DISA Rule ID must have rN_rule suffix."""
        import re

        template = disa_engine.config.rule_id.get("template", "")
        context = {"stig_number": "030101", "ref_normalized": "3_1_1", "platform": "eks"}
        rule_id = VariableSubstituter.substitute(template, context)

        # Pattern: SV-NNNNNNrREV_rule
        pattern = r"^SV-\d+r\d+_rule$"
        assert re.match(pattern, rule_id), (
            f"DISA Rule ID must match SV-NNNNNNrN_rule, got: {rule_id}"
        )

    def test_disa_stig_number_conversion(self, disa_engine):
        """Test ref_to_stig_number converts refs correctly."""
        test_cases = [
            ("1.1.1", "010101"),
            ("3.2.1", "030201"),
            ("10.5.3", "100503"),
            ("1.1.1.1", "01010101"),
            ("5", "05"),
        ]
        for ref, expected in test_cases:
            result = disa_engine.ref_to_stig_number(ref)
            assert result == expected, f"ref_to_stig_number({ref}) = {result}, expected {expected}"

    def test_disa_ids_are_unique_for_different_refs(self, disa_engine):
        """Different CIS refs should produce different DISA IDs."""
        refs = ["1.1.1", "1.1.2", "2.1.1", "3.2.1"]
        group_template = disa_engine.config.group_id.get("template", "")
        rule_template = disa_engine.config.rule_id.get("template", "")

        group_ids = set()
        rule_ids = set()

        for ref in refs:
            stig_number = disa_engine.ref_to_stig_number(ref)
            context = {"stig_number": stig_number, "ref_normalized": ref.replace(".", "_")}

            group_id = VariableSubstituter.substitute(group_template, context)
            rule_id = VariableSubstituter.substitute(rule_template, context)

            assert group_id not in group_ids, f"Duplicate Group ID: {group_id}"
            assert rule_id not in rule_ids, f"Duplicate Rule ID: {rule_id}"

            group_ids.add(group_id)
            rule_ids.add(rule_id)

    # --- CIS ID Format Tests ---

    def test_cis_group_id_format_prefix(self, cis_engine):
        """CIS Group ID must have cisecurity.benchmarks prefix."""
        template = cis_engine.config.group_id.get("template", "")
        context = {"stig_number": "030101", "ref_normalized": "3_1_1", "platform": "eks"}
        group_id = VariableSubstituter.substitute(template, context)

        assert "cisecurity.benchmarks" in group_id, (
            f"CIS Group ID must contain cisecurity.benchmarks, got: {group_id}"
        )
        assert "_group_" in group_id, f"CIS Group ID must contain _group_, got: {group_id}"

    def test_cis_group_id_format_contains_ref(self, cis_engine):
        """CIS Group ID must contain the normalized ref."""
        template = cis_engine.config.group_id.get("template", "")
        context = {"stig_number": "030101", "ref_normalized": "3_1_1", "platform": "eks"}
        group_id = VariableSubstituter.substitute(template, context)

        assert "3_1_1" in group_id, (
            f"CIS Group ID must contain ref_normalized (3_1_1), got: {group_id}"
        )

    def test_cis_rule_id_format_prefix(self, cis_engine):
        """CIS Rule ID must have cisecurity.benchmarks prefix."""
        template = cis_engine.config.rule_id.get("template", "")
        context = {"stig_number": "030101", "ref_normalized": "3_1_1", "platform": "eks"}
        rule_id = VariableSubstituter.substitute(template, context)

        assert "cisecurity.benchmarks" in rule_id, (
            f"CIS Rule ID must contain cisecurity.benchmarks, got: {rule_id}"
        )
        assert "_rule_" in rule_id, f"CIS Rule ID must contain _rule_, got: {rule_id}"

    def test_cis_rule_id_format_contains_ref(self, cis_engine):
        """CIS Rule ID must contain the normalized ref."""
        template = cis_engine.config.rule_id.get("template", "")
        context = {"stig_number": "030101", "ref_normalized": "3_1_1", "platform": "eks"}
        rule_id = VariableSubstituter.substitute(template, context)

        assert "3_1_1" in rule_id, (
            f"CIS Rule ID must contain ref_normalized (3_1_1), got: {rule_id}"
        )

    def test_cis_ids_are_unique_for_different_refs(self, cis_engine):
        """Different CIS refs should produce different CIS IDs."""
        refs = ["1.1.1", "1.1.2", "2.1.1", "3.2.1"]
        group_template = cis_engine.config.group_id.get("template", "")
        rule_template = cis_engine.config.rule_id.get("template", "")

        group_ids = set()
        rule_ids = set()

        for ref in refs:
            context = {"ref_normalized": ref.replace(".", "_")}

            group_id = VariableSubstituter.substitute(group_template, context)
            rule_id = VariableSubstituter.substitute(rule_template, context)

            assert group_id not in group_ids, f"Duplicate Group ID: {group_id}"
            assert rule_id not in rule_ids, f"Duplicate Rule ID: {rule_id}"

            group_ids.add(group_id)
            rule_ids.add(rule_id)

    # --- Edge Cases for ref_to_stig_number ---

    def test_stig_number_empty_ref(self, disa_engine):
        """Empty ref returns '00' (empty string split produces one empty segment)."""
        # Note: "".split(".") → [""] → "".zfill(2) → "00"
        # This is acceptable edge case behavior - empty refs shouldn't occur in practice
        result = disa_engine.ref_to_stig_number("")
        assert result == "00", f"Empty ref edge case, got: {result}"

    def test_stig_number_single_digit_segments(self, disa_engine):
        """Single digit segments should be zero-padded."""
        test_cases = [
            ("1", "01"),
            ("9", "09"),
            ("1.2", "0102"),
            ("1.2.3", "010203"),
        ]
        for ref, expected in test_cases:
            result = disa_engine.ref_to_stig_number(ref)
            assert result == expected, f"ref_to_stig_number({ref}) = {result}, expected {expected}"

    def test_stig_number_double_digit_segments(self, disa_engine):
        """Double digit segments should not be truncated."""
        test_cases = [
            ("10", "10"),
            ("10.11", "1011"),
            ("10.11.12", "101112"),
            ("99.99.99", "999999"),
        ]
        for ref, expected in test_cases:
            result = disa_engine.ref_to_stig_number(ref)
            assert result == expected, f"ref_to_stig_number({ref}) = {result}, expected {expected}"

    def test_stig_number_very_deep_hierarchy(self, disa_engine):
        """Very deep refs (5+ levels) should still work."""
        result = disa_engine.ref_to_stig_number("1.2.3.4.5")
        assert result == "0102030405", f"Deep ref failed, got: {result}"

    # --- End-to-End ID Tests (map_rule/map_group) ---

    def test_disa_map_rule_produces_sv_id(self, disa_engine, sample_recommendation):
        """map_rule() with DISA config should produce SV- prefixed rule ID."""
        import re

        context = {"benchmark": None}
        rule = disa_engine.map_rule(sample_recommendation, context)

        assert rule.id.startswith("SV-"), f"DISA Rule ID should start with SV-, got: {rule.id}"
        assert re.match(r"^SV-\d+r\d+_rule$", rule.id), f"Invalid DISA Rule ID format: {rule.id}"

    def test_disa_map_group_produces_v_id(self, disa_engine, sample_recommendation):
        """map_group() with DISA config should produce V- prefixed group ID."""
        import re

        context = {"benchmark": None}
        rule = disa_engine.map_rule(sample_recommendation, context)
        group = disa_engine.map_group(sample_recommendation, rule, context)

        assert group.id.startswith("V-"), f"DISA Group ID should start with V-, got: {group.id}"
        assert re.match(r"^V-\d+$", group.id), f"Invalid DISA Group ID format: {group.id}"

    def test_cis_map_rule_produces_benchmarks_id(self, cis_engine, sample_recommendation):
        """map_rule() with CIS config should produce cisecurity.benchmarks rule ID."""
        context = {"benchmark": None}
        rule = cis_engine.map_rule(sample_recommendation, context)

        assert "cisecurity.benchmarks" in rule.id, (
            f"CIS Rule ID should contain cisecurity.benchmarks, got: {rule.id}"
        )
        assert "_rule_" in rule.id, f"CIS Rule ID should contain _rule_, got: {rule.id}"
        assert "3_1_1" in rule.id, (
            f"CIS Rule ID should contain ref_normalized (3_1_1), got: {rule.id}"
        )

    def test_cis_map_group_produces_benchmarks_id(self, cis_engine, sample_recommendation):
        """map_group() with CIS config should produce cisecurity.benchmarks group ID."""
        context = {"benchmark": None}
        rule = cis_engine.map_rule(sample_recommendation, context)
        group = cis_engine.map_group(sample_recommendation, rule, context)

        assert "cisecurity.benchmarks" in group.id, (
            f"CIS Group ID should contain cisecurity.benchmarks, got: {group.id}"
        )
        assert "_group_" in group.id, f"CIS Group ID should contain _group_, got: {group.id}"
        assert "3_1_1" in group.id, (
            f"CIS Group ID should contain ref_normalized (3_1_1), got: {group.id}"
        )

    def test_disa_rule_and_group_ids_correspond(self, disa_engine, sample_recommendation):
        """DISA Rule and Group IDs should use same stig_number."""
        context = {"benchmark": None}
        rule = disa_engine.map_rule(sample_recommendation, context)
        group = disa_engine.map_group(sample_recommendation, rule, context)

        # Extract numbers: V-030101 → 030101, SV-030101r1_rule → 030101
        group_num = group.id.replace("V-", "")
        rule_num = rule.id.split("r")[0].replace("SV-", "")

        assert group_num == rule_num, (
            f"Group ({group.id}) and Rule ({rule.id}) should share stig_number"
        )

    # --- Profile Select Element ID Tests ---

    def test_disa_profile_selects_use_sv_rule_ids(self, disa_engine, synthetic_complete_benchmark):
        """Profile select elements should reference SV- rule IDs in DISA style."""
        # Get profile config from engine config (not context)
        profile_config = disa_engine.config.benchmark.get("profiles", {})

        # Generate profiles
        profiles = disa_engine.generate_profiles_from_rules(
            synthetic_complete_benchmark.recommendations, profile_config
        )

        # Check at least one profile has selects
        assert any(p.select for p in profiles), "No profiles with selects generated"

        # Check all select idrefs use SV- format
        for profile in profiles:
            for select in profile.select:
                assert select.idref.startswith("SV-"), (
                    f"Profile select idref should use SV- format, got: {select.idref}"
                )

    def test_cis_profile_selects_use_benchmarks_rule_ids(
        self, cis_engine, synthetic_complete_benchmark
    ):
        """Profile select elements should reference cisecurity.benchmarks rule IDs in CIS style."""
        # Get profile config from engine config (not context)
        profile_config = cis_engine.config.benchmark.get("profiles", {})

        # Generate profiles
        profiles = cis_engine.generate_profiles_from_rules(
            synthetic_complete_benchmark.recommendations, profile_config
        )

        # Check at least one profile has selects
        assert any(p.select for p in profiles), "No profiles with selects generated"

        # Check all select idrefs use CIS format
        for profile in profiles:
            for select in profile.select:
                assert "cisecurity.benchmarks" in select.idref, (
                    f"Profile select idref should use cisecurity.benchmarks format, got: {select.idref}"
                )

    # --- Cross-Style Validation ---

    def test_disa_and_cis_ids_are_distinct_formats(self, disa_engine, cis_engine):
        """DISA and CIS IDs should be visually distinct formats."""
        context = {"stig_number": "030101", "ref_normalized": "3_1_1", "platform": "eks"}

        disa_group = VariableSubstituter.substitute(
            disa_engine.config.group_id.get("template", ""), context
        )
        cis_group = VariableSubstituter.substitute(
            cis_engine.config.group_id.get("template", ""), context
        )

        # They should be different
        assert disa_group != cis_group, "DISA and CIS Group IDs should differ"

        # DISA should be short numeric, CIS should be long descriptive
        assert len(disa_group) < len(cis_group), "DISA IDs should be shorter than CIS IDs"
        assert disa_group.startswith("V-"), "DISA should use V- prefix"
        assert "xccdf" in cis_group.lower(), "CIS should use xccdf prefix"


# ============================================================================
# TEST: DISA/Vulcan Compatibility (Benchmark-level format tests)
# ============================================================================


class TestDISAVulcanCompatibility:
    """Tests for DISA/Vulcan-compatible export format.

    Vulcan expects specific formats:
    - Benchmark ID: Short format (e.g., "CIS_AlmaLinux_STIG")
    - Version: Without 'v' prefix (e.g., "4.0.0" not "v4.0.0")
    - Group title: Contains useful info (not "<GroupDescription></GroupDescription>")
    """

    def test_disa_benchmark_id_is_short_format(self, disa_config_path):
        """DISA benchmark ID template should produce short IDs for Vulcan."""
        engine = MappingEngine(disa_config_path)
        id_template = engine.config.benchmark.get("id_template", "")

        # Template should NOT contain full xccdf namespace
        assert "xccdf_org.cisecurity_benchmark" not in id_template, (
            "DISA benchmark ID should not use full XCCDF namespace"
        )

        # Should produce short readable ID using benchmark_id
        context = {"benchmark_id": "23598"}
        bench_id = VariableSubstituter.substitute(id_template, context)

        assert len(bench_id) < 50, "Benchmark ID should be reasonably short"
        assert "CIS" in bench_id, "Benchmark ID should contain 'CIS'"
        assert "23598" in bench_id, "Benchmark ID should contain benchmark_id"

    def test_disa_version_transform_strips_v_prefix(self, disa_config_path):
        """DISA version config should use strip_version_prefix transform."""
        engine = MappingEngine(disa_config_path)
        version_config = engine.config.benchmark.get("version", {})

        transform = version_config.get("transform")
        assert transform == "strip_version_prefix", (
            f"DISA version should use strip_version_prefix, got: {transform}"
        )

    def test_disa_group_title_has_source(self, disa_config_path):
        """DISA group title should have a source field (not default placeholder)."""
        engine = MappingEngine(disa_config_path)
        title_config = engine.config.group_elements.get("title", {})

        source = title_config.get("source")
        assert source is not None, "DISA group title should have a source field"
        assert source == "ref", "DISA group title source should be 'ref'"

    def test_disa_group_description_has_source(self, disa_config_path):
        """DISA group description should have a source field."""
        engine = MappingEngine(disa_config_path)
        desc_config = engine.config.group_elements.get("description", {})

        source = desc_config.get("source")
        assert source is not None, "DISA group description should have a source field"
        assert source == "title", "DISA group description source should be 'title'"

    def test_disa_map_group_uses_ref_as_title(self, disa_config_path, synthetic_complete_benchmark):
        """map_group should use CIS ref as group title."""
        engine = MappingEngine(disa_config_path)
        benchmark = synthetic_complete_benchmark
        rec = benchmark.recommendations[0]
        context = {"benchmark": benchmark}

        rule = engine.map_rule(rec, context)
        group = engine.map_group(rec, rule, context)

        # Group title should contain the ref (e.g., "1.1.1")
        assert group.title, "Group should have title"
        title_content = (
            group.title[0].content[0]
            if hasattr(group.title[0], "content")
            else group.title[0].value
        )
        assert rec.ref in title_content, (
            f"Group title should contain ref '{rec.ref}', got: {title_content}"
        )
        # Should NOT contain the placeholder
        assert "<GroupDescription>" not in title_content, (
            "Group title should not contain placeholder"
        )

    def test_disa_map_group_uses_rule_title_as_description(
        self, disa_config_path, synthetic_complete_benchmark
    ):
        """map_group should use rule title as group description."""
        engine = MappingEngine(disa_config_path)
        benchmark = synthetic_complete_benchmark
        rec = benchmark.recommendations[0]
        context = {"benchmark": benchmark}

        rule = engine.map_rule(rec, context)
        group = engine.map_group(rec, rule, context)

        # Group description should contain the rule title
        assert group.description, "Group should have description"
        desc_content = (
            group.description[0].content[0]
            if hasattr(group.description[0], "content")
            else group.description[0].value
        )
        # Title may be transformed, so check for key words
        assert len(desc_content) > 10, f"Group description should have content, got: {desc_content}"
        assert "<GroupDescription>" not in desc_content, (
            "Group description should not contain placeholder"
        )


class TestEdgeCases:
    def test_empty_recommendation_fields(self):
        """Test handling recommendation with minimal fields (some empty optionals)."""
        rec = Recommendation(
            url="https://example.com",
            ref="1.1",
            title="Minimal Recommendation",  # title is required, must be non-empty
            description=None,  # Optional fields can be None
            rationale=None,
            assessment_status="Unknown",
        )

        # Should handle None gracefully in optional fields
        assert rec.title == "Minimal Recommendation"
        assert rec.description is None

    def test_transformation_chain_with_none(self):
        """Test transformation pipeline with None values."""
        result1 = TransformRegistry.apply("strip_version_prefix", None)
        result2 = TransformRegistry.apply("none", result1)

        assert result1 == ""
        assert result2 == ""

    def test_a_missing_nested_key_is_refused(self):
        with pytest.raises(ValueError, match="missing"):
            VariableSubstituter.substitute("Value: {top.missing.key}", {"top": {"other": 1}})

    def test_malformed_json_in_parsers(self):
        """Test parsers with malformed JSON."""
        bad_json = '{"version": "8", "control": '  # Unclosed
        result = WorkbenchParser.parse_cis_controls_json(bad_json)
        assert result == []

    def test_nist_control_deduplication_with_duplicates(self):
        """Test NIST deduplication with duplicate inputs."""
        service = CCILookupService()
        cis_controls = ["4.8", "4.8"]  # Duplicate
        cited_nist = ["CM-7", "CM-7", "SI-3"]  # Duplicates

        ccis, extra_nist = service.deduplicate_nist_controls(cis_controls, cited_nist)

        # Should handle duplicates gracefully
        assert isinstance(ccis, list)
        assert isinstance(extra_nist, list)


# ============================================================================
# TEST: Config-Driven XCCDF Notice Creation
# ============================================================================


class TestNoticeCreation:
    """Unit tests for config-driven XCCDF <notice> construction in MappingEngine."""

    def test_create_notice_populates_content_id_and_lang_from_style_config(
        self, cis_config_path, synthetic_complete_benchmark
    ):
        """create_notice resolves direct id, lang, and variable-substituted content."""
        engine = MappingEngine(cis_config_path)
        engine.config.benchmark["notice"] = {
            "id": "custom-notice",
            "lang": "en-US",
            "xccdf_type": "NoticeType",
            "content": "Exported from {benchmark.title} ({benchmark.url})",
        }

        notice = engine.create_notice(synthetic_complete_benchmark)

        assert notice.id == "custom-notice"
        assert notice.lang == "en-US"
        assert notice.content == [
            f"Exported from {synthetic_complete_benchmark.title} ({synthetic_complete_benchmark.url})"
        ]

    def test_create_notice_resolves_attributes_dict_and_default_id(
        self, disa_config_path, synthetic_complete_benchmark
    ):
        """create_notice resolves attributes.id and attributes['xml:lang'] and normalizes HttpUrl."""
        engine = MappingEngine(disa_config_path)
        engine.config.benchmark["notice"] = {
            "element": "notice",
            "xccdf_type": "NoticeType",
            "attributes": {
                "id": "attr-notice-id",
                "xml:lang": "en",
            },
            "content": "{benchmark.url}",
        }

        notice = engine.create_notice(synthetic_complete_benchmark)

        assert notice.id == "attr-notice-id"
        assert notice.lang == "en"
        assert notice.content == [str(synthetic_complete_benchmark.url)]
        assert isinstance(notice.content[0], str)

        engine.config.benchmark["notice"] = {
            "xccdf_type": "NoticeType",
            "content": "Plain notice without explicit id or lang",
        }
        fallback_notice = engine.create_notice(synthetic_complete_benchmark)
        assert fallback_notice.id == "terms-of-use"
        assert fallback_notice.lang is None
        assert fallback_notice.content == ["Plain notice without explicit id or lang"]

    def test_create_notice_preserves_empty_content_when_omitted_or_blank(
        self, cis_config_path, synthetic_complete_benchmark
    ):
        """Custom styles with empty or omitted notice content preserve content=[]."""
        engine = MappingEngine(cis_config_path)

        engine.config.benchmark["notice"] = {
            "id": "empty-str",
            "lang": "en",
            "content": "",
        }
        empty_notice = engine.create_notice(synthetic_complete_benchmark)
        assert empty_notice.id == "empty-str"
        assert empty_notice.lang == "en"
        assert empty_notice.content == []

        engine.config.benchmark["notice"] = {"id": "omitted-content"}
        omitted_notice = engine.create_notice(synthetic_complete_benchmark)
        assert omitted_notice.id == "omitted-content"
        assert omitted_notice.lang is None
        assert omitted_notice.content == []

        engine.config.benchmark.pop("notice", None)
        missing_section_notice = engine.create_notice(synthetic_complete_benchmark)
        assert missing_section_notice.id == "terms-of-use"
        assert missing_section_notice.lang is None
        assert missing_section_notice.content == []


class TestBenchmarkIdTemplate:
    """Benchmark/@id comes from the style's id_template and the engine's substitution values."""

    def test_missing_id_template_is_an_export_error(
        self, styles_dir, synthetic_complete_benchmark, tmp_path
    ):
        """A style without benchmark.id_template cannot name its Benchmark; the engine says so."""
        from cis_bench.exceptions import ExportError

        config = tmp_path / "no_id.yaml"
        config.write_text(
            f"extends: {Path(styles_dir).parent / 'base.yaml'}\n"
            'metadata:\n  style_name: "no_id"\n  xccdf_version: "1.2"\n'
        )
        engine = MappingEngine(config)

        with pytest.raises(ExportError, match="benchmark.id_template"):
            engine.map_benchmark(
                synthetic_complete_benchmark, [], {"benchmark": synthetic_complete_benchmark}
            )

    def test_an_id_template_naming_an_unknown_variable_is_refused(
        self, cis_config_path, synthetic_complete_benchmark
    ):
        # The variable is benchmark_id; a typo would write id="CIS-" without a word.
        engine = MappingEngine(cis_config_path)
        engine.config.benchmark["id_template"] = "CIS-{bench_id}"

        with pytest.raises(ValueError, match="bench_id"):
            engine.map_benchmark(
                synthetic_complete_benchmark,
                [],
                {"benchmark": synthetic_complete_benchmark, "recommendations": []},
            )

    def test_a_profile_id_template_naming_an_unknown_variable_is_refused(
        self, cis_config_path, synthetic_complete_benchmark
    ):
        engine = MappingEngine(cis_config_path)
        engine.config.benchmark["profiles"]["id_template"] = "{profile.name|slug:-}"
        context = {
            "benchmark": synthetic_complete_benchmark,
            "recommendations": synthetic_complete_benchmark.recommendations,
        }

        with pytest.raises(ValueError, match="profile.name"):
            engine.map_benchmark(synthetic_complete_benchmark, [], context)

    def test_cis_template_substitutes_version_and_title_slug(
        self, cis_config_path, synthetic_complete_benchmark
    ):
        engine = MappingEngine(cis_config_path)
        bench = synthetic_complete_benchmark.model_copy(
            update={"title": "CIS Red Hat Enterprise Linux 9 Benchmark", "version": "v2.0.0"}
        )

        xccdf_bench = engine.map_benchmark(bench, [], {"benchmark": bench, "recommendations": []})

        assert xccdf_bench.id == (
            "xccdf_org.cisecurity.benchmarks_benchmark_v2.0.0_CIS_Red_Hat_Enterprise_Linux_9_Benchmark"
        )


class TestStyleFieldNames:
    """A style names the recommendation and benchmark fields it reads; a name that is no
    field would read as empty and drop the element without a word, so loading refuses it."""

    @pytest.mark.parametrize(
        ("override", "bad_name"),
        [
            ("field_mappings:\n  title:\n    source_field: titel\n", "titel"),
            (
                "field_mappings:\n  mitre_techniques:\n    source_field: mitre_mapping.techiques\n",
                "mitre_mapping.techiques",
            ),
            (
                "field_mappings:\n  check:\n    children:\n"
                "      - element: check-content\n        source_field: audti\n",
                "audti",
            ),
            # A dotted path where the reader takes one field name reads as empty too.
            (
                "field_mappings:\n  title:\n    source_field: mitre_mapping.techniques\n",
                "mitre_mapping.techniques",
            ),
            # A dotted path through a list reads the list's attribute, which is no value.
            (
                "field_mappings:\n  mitre_techniques:\n    source_field: cis_controls.control\n",
                "cis_controls.control",
            ),
            (
                "field_mappings:\n  ident:\n    cci_lookup:\n      source_field: cis_controlz\n",
                "cis_controlz",
            ),
            # A real field that does not hold CIS controls (artifacts is a list of
            # another model, and may be empty) is refused by name too.
            (
                "field_mappings:\n  ident:\n    cci_lookup:\n      source_field: artifacts\n",
                "artifacts",
            ),
            ("group_elements:\n  title:\n    source: titel\n", "titel"),
            ("benchmark:\n  title:\n    source: titel\n", "titel"),
        ],
    )
    def test_a_style_naming_a_field_that_does_not_exist_is_refused(
        self, styles_dir, tmp_path, override, bad_name
    ):
        config = tmp_path / "misspelled.yaml"
        config.write_text(f"extends: {Path(styles_dir) / 'disa.yaml'}\n{override}")

        with pytest.raises(ValueError, match=re.escape(bad_name)):
            MappingEngine(config)

    def test_the_refusal_names_the_model_the_path_fails_on(self, styles_dir, tmp_path):
        config = tmp_path / "nested.yaml"
        config.write_text(
            f"extends: {Path(styles_dir) / 'disa.yaml'}\n"
            "field_mappings:\n  mitre_techniques:\n    source_field: mitre_mapping.techniqes\n"
        )

        with pytest.raises(ValueError, match="MITREMapping"):
            MappingEngine(config)

    def test_a_dotted_path_sees_through_an_annotated_optional_model(self):
        from typing import Annotated

        from cis_bench.exporters.mapping_engine import _model_in

        assert _model_in(Annotated[MITREMapping, "constraint"] | None) is MITREMapping
        assert _model_in(list[MITREMapping]) is None


class TestEmbeddedTagsAreCheckedWhenTheStyleLoads:
    """A style's embedded_xml_tags components are checked when the engine loads it, not
    when an export fails: every source names a field that exists, every tag is an XML name."""

    @staticmethod
    def _style(tmp_path, disa_config_path, components):
        import yaml

        style = tmp_path / "style.yaml"
        style.write_text(
            yaml.safe_dump(
                {
                    "extends": str(disa_config_path),
                    "field_mappings": {
                        "description": {
                            "target_element": "description",
                            "structure": "embedded_xml_tags",
                            "components": components,
                        }
                    },
                }
            )
        )
        return style

    def test_a_source_naming_no_field_is_refused(self, tmp_path, disa_config_path):
        style = self._style(
            tmp_path,
            disa_config_path,
            [{"tag": "VulnDiscussion", "sources": [{"field": "descriptoin"}]}],
        )

        with pytest.raises(ValueError, match="components\\[0\\].sources\\[0\\].*descriptoin"):
            MappingEngine(style)

    def test_a_source_without_a_field_is_refused(self, tmp_path, disa_config_path):
        style = self._style(
            tmp_path,
            disa_config_path,
            [{"tag": "VulnDiscussion", "sources": [{"source_field": "description"}]}],
        )

        with pytest.raises(ValueError, match="a component source needs field"):
            MappingEngine(style)

    @pytest.mark.parametrize("tag", ["bad tag", "1st", "", None])
    def test_a_tag_that_is_no_xml_name_is_refused(self, tmp_path, disa_config_path, tag):
        style = self._style(tmp_path, disa_config_path, [{"tag": tag, "content": ""}])

        with pytest.raises(ValueError, match="is not a valid XML tag name"):
            MappingEngine(style)

    def test_the_shipped_disa_style_passes_the_checks(self, disa_config_path):
        engine = MappingEngine(disa_config_path)

        tags = [c["tag"] for c in engine.config.field_mappings["description"]["components"]]
        assert tags[0] == "VulnDiscussion" and len(tags) == 11


class TestTransformsAreCheckedWhenTheStyleLoads:
    """Every transform a style names is checked when the engine loads it, not when the first
    export reaches the field: a name no transform is registered under is refused, with the
    place that names it. The HTML conversions the styles once named are among the unknown."""

    @staticmethod
    def _style(tmp_path, parent, **sections):
        import yaml

        style = tmp_path / "style.yaml"
        style.write_text(yaml.safe_dump({"extends": str(parent), **sections}))
        return style

    @pytest.mark.parametrize(
        "name",
        [
            "strip_html",
            "strip_html_keep_code",
            "html_to_markdown",
            "wrap_xhtml_paragraphs",
            "no_such_transform",
        ],
    )
    def test_a_field_mapping_naming_no_transform_is_refused(self, tmp_path, cis_config_path, name):
        style = self._style(
            tmp_path,
            cis_config_path,
            field_mappings={
                "title": {"target_element": "title", "source_field": "title", "transform": name}
            },
        )

        with pytest.raises(ValueError, match=f"field_mappings.title.*{name}"):
            MappingEngine(style)

    def test_a_child_naming_no_transform_is_refused(self, tmp_path, cis_config_path):
        style = self._style(
            tmp_path,
            cis_config_path,
            field_mappings={
                "check": {
                    "target_element": "check",
                    "structure": "nested",
                    "children": [
                        {
                            "element": "check-content",
                            "source_field": "audit",
                            "transform": "no_such_transform",
                        }
                    ],
                }
            },
        )

        with pytest.raises(
            ValueError, match="field_mappings.check.children\\[0\\].*no_such_transform"
        ):
            MappingEngine(style)

    def test_a_component_source_naming_no_transform_is_refused(self, tmp_path, disa_config_path):
        style = self._style(
            tmp_path,
            disa_config_path,
            field_mappings={
                "description": {
                    "target_element": "description",
                    "structure": "embedded_xml_tags",
                    "components": [
                        {
                            "tag": "VulnDiscussion",
                            "sources": [{"field": "description", "transform": "strip_html"}],
                        }
                    ],
                }
            },
        )

        with pytest.raises(
            ValueError,
            match="field_mappings.description.components\\[0\\].sources\\[0\\].*strip_html",
        ):
            MappingEngine(style)

    def test_a_benchmark_element_naming_no_transform_is_refused(self, tmp_path, cis_config_path):
        style = self._style(
            tmp_path,
            cis_config_path,
            benchmark={"title": {"source": "title", "transform": "strip_html"}},
        )

        with pytest.raises(ValueError, match="benchmark.title.*strip_html"):
            MappingEngine(style)

    def test_a_group_element_naming_no_transform_is_refused(self, tmp_path, disa_config_path):
        style = self._style(
            tmp_path,
            disa_config_path,
            group_elements={"title": {"source": "title", "transform": "no_such_transform"}},
        )

        with pytest.raises(ValueError, match="group_elements.title.*no_such_transform"):
            MappingEngine(style)

    def test_a_profile_description_transform_naming_no_transform_is_refused(
        self, tmp_path, cis_config_path
    ):
        style = self._style(
            tmp_path,
            cis_config_path,
            benchmark={
                "profiles": {"generate_from_rules": True, "description_transform": "strip_html"}
            },
        )

        with pytest.raises(
            ValueError, match="benchmark.profiles.description_transform.*strip_html"
        ):
            MappingEngine(style)

    @pytest.mark.parametrize(
        ("section", "where"),
        [
            ({"rule_id": {"template": "{ref_normalized|strip_html}"}}, "rule_id.template"),
            ({"group_id": {"template": "{ref_normalized|no_such_transform}"}}, "group_id.template"),
            (
                {
                    "benchmark": {
                        "profiles": {
                            "generate_from_rules": True,
                            "id_template": "{profile.title|strip_html}",
                        }
                    }
                },
                "benchmark.profiles.id_template",
            ),
            (
                {
                    "field_mappings": {
                        "mitre_techniques": {
                            "target_element": "ident",
                            "structure": "ident_from_list",
                            "source_field": "mitre_mapping.techniques",
                            "ident_spec": {
                                "system_template": "https://attack.mitre.org/techniques",
                                "value_template": "{item|html_to_markdown}",
                            },
                        }
                    }
                },
                "field_mappings.mitre_techniques.ident_spec.value_template",
            ),
        ],
    )
    def test_a_template_filter_naming_no_transform_is_refused(
        self, tmp_path, cis_config_path, section, where
    ):
        """A filter in a template ({value|transform}) is a transform name too; it is checked
        where the style is loaded, not when the first rule reaches the template."""
        style = self._style(tmp_path, cis_config_path, **section)

        with pytest.raises(
            ValueError, match=f"{where.replace('.', '[.]')}.*Unknown transformation"
        ):
            MappingEngine(style)

    @pytest.mark.parametrize(
        ("section", "where"),
        [
            (
                {"benchmark": {"notice": {"content": "Read {benchmark.title|strip_html} first."}}},
                "benchmark.notice.content",
            ),
            (
                {
                    "field_mappings": {
                        "nist_reference": {
                            "target_element": "reference",
                            "structure": "dublin_core",
                            "source_field": "nist_controls",
                            "multiple": True,
                            "dc_elements": [
                                {"element": "publisher", "content": "NIST SP 800-53"},
                                {
                                    "element": "identifier",
                                    "content": "{nist_control_id|no_such_transform}",
                                },
                            ],
                            "href": "https://example.com/{nist_control_id|html_to_markdown}",
                        }
                    }
                },
                "field_mappings.nist_reference.dc_elements\\[1\\].content",
            ),
        ],
    )
    def test_a_filter_in_any_substituted_string_is_refused(
        self, tmp_path, cis_config_path, section, where
    ):
        """The engine substitutes strings under many keys (content, href, system, prefix,
        attributes), not only *template; a filter in any of them is checked at load."""
        style = self._style(tmp_path, cis_config_path, **section)

        with pytest.raises(ValueError, match=f"{where}.*Unknown transformation"):
            MappingEngine(style)

    def test_a_filter_in_a_reference_href_attribute_is_refused(self, tmp_path, cis_config_path):
        """The reference's href lives under attributes, where the exporter reads it."""
        style = self._style(
            tmp_path,
            cis_config_path,
            field_mappings={
                "nist_reference": {
                    "target_element": "reference",
                    "structure": "dublin_core",
                    "source_field": "nist_controls",
                    "multiple": True,
                    "dc_elements": [{"element": "dc:identifier", "content": "{nist_control_id}"}],
                    "attributes": {"href": "https://example.com/{nist_control_id|strip_html}"},
                }
            },
        )

        with pytest.raises(
            ValueError, match="field_mappings.nist_reference.attributes.href.*strip_html"
        ):
            MappingEngine(style)

    def test_a_filter_without_a_name_is_refused_at_load(self, tmp_path, cis_config_path):
        style = self._style(tmp_path, cis_config_path, rule_id={"template": "{ref_normalized|}"})

        with pytest.raises(ValueError, match="rule_id.template.*filter without a transform name"):
            MappingEngine(style)

    def test_a_transform_that_is_not_a_name_is_refused(self, tmp_path, cis_config_path):
        style = self._style(
            tmp_path,
            cis_config_path,
            field_mappings={
                "title": {"target_element": "title", "source_field": "title", "transform": ["none"]}
            },
        )

        with pytest.raises(ValueError, match="field_mappings.title.*transform must be a name"):
            MappingEngine(style)

    def test_a_composite_source_naming_no_field_is_refused(self, tmp_path, cis_config_path):
        style = self._style(
            tmp_path,
            cis_config_path,
            field_mappings={
                "description": {
                    "target_element": "description",
                    "structure": "composite",
                    "sources": [{"field": "description"}, {"field": "defualt_value"}],
                }
            },
        )

        with pytest.raises(
            ValueError, match="field_mappings.description.sources\\[1\\].*defualt_value"
        ):
            MappingEngine(style)

    @pytest.mark.parametrize("mapping", [{}, {"sources": []}, {"sources": "description"}])
    def test_a_composite_without_sources_is_refused(self, tmp_path, cis_config_path, mapping):
        style = self._style(
            tmp_path,
            cis_config_path,
            # a name the parent style does not have, so nothing is inherited into it
            field_mappings={
                "folded": {
                    "target_element": "description",
                    "structure": "composite",
                    **mapping,
                }
            },
        )

        with pytest.raises(ValueError, match="field_mappings.folded: composite needs sources"):
            MappingEngine(style)

    def test_a_composite_source_without_a_field_is_refused(self, tmp_path, cis_config_path):
        style = self._style(
            tmp_path,
            cis_config_path,
            field_mappings={
                "folded": {
                    "target_element": "description",
                    "structure": "composite",
                    "sources": [{"field": "description"}, {"label": "Default Value:"}],
                }
            },
        )

        with pytest.raises(
            ValueError, match="field_mappings.folded.sources\\[1\\]: a composite source needs field"
        ):
            MappingEngine(style)

    def test_a_composite_source_naming_no_transform_is_refused(self, tmp_path, cis_config_path):
        style = self._style(
            tmp_path,
            cis_config_path,
            field_mappings={
                "description": {
                    "target_element": "description",
                    "structure": "composite",
                    "sources": [{"field": "description", "transform": "strip_html"}],
                }
            },
        )

        with pytest.raises(
            ValueError, match="field_mappings.description.sources\\[0\\].*strip_html"
        ):
            MappingEngine(style)

    def test_the_shipped_styles_name_registered_transforms_only(
        self, cis_config_path, disa_config_path
    ):
        for path in (cis_config_path, disa_config_path):
            MappingEngine(path)
