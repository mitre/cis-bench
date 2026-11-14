"""Rule metadata built from a style's metadata_from_config mapping.

The metadata is XCCDF model content: an xsdata AnyElement tree in the namespace the style
declares for the mapping's prefix, held by a MetadataType on Rule.metadata. XCCDF allows only
elements from another namespace inside metadata, so a mapping that could give anything else
is refused when the style loads.
"""

import pytest
from lxml import etree
from xsdata.formats.dataclass.models.generics import AnyElement

from cis_bench.exporters.mapping_engine import MappingEngine
from cis_bench.exporters.xccdf_unified_exporter import XCCDFExporter
from cis_bench.models.benchmark import Benchmark, CISControl, Recommendation

CONTROLS = "http://cisecurity.org/controls"


def control(version: int, number: str, title: str, ig1: bool = False) -> CISControl:
    return CISControl(version=version, control=number, title=title, ig1=ig1, ig2=True, ig3=True)


def recommendation(*controls: CISControl) -> Recommendation:
    return Recommendation(
        ref="6.1.1",
        title="Synthetic recommendation",
        url="https://example.org/6.1.1",
        assessment_status="Automated",
        cis_controls=list(controls),
    )


def shape(element: AnyElement) -> tuple:
    """An AnyElement tree as (qname, attributes, text, children)."""
    return (
        element.qname,
        dict(element.attributes),
        element.text,
        [shape(child) for child in element.children],
    )


@pytest.fixture
def engine(cis_config_path) -> MappingEngine:
    return MappingEngine(cis_config_path)


@pytest.fixture
def controls_mapping(engine) -> dict:
    """The CIS style's own CIS Controls metadata mapping."""
    return engine.config.field_mappings["cis_controls_metadata"]


class TestBuiltContent:
    def test_controls_are_grouped_by_version_with_each_safeguard_under_its_framework(
        self, engine, controls_mapping
    ):
        rec = recommendation(
            control(8, "3.14", "Log Sensitive Data Access"),
            control(7, "14.9", "Enforce Detail Logging", ig1=True),
        )

        root = engine.generate_metadata_from_config(rec, controls_mapping)

        def safeguard(version: str, number: str, title: str, ig1: str) -> tuple:
            return (
                f"{{{CONTROLS}}}safeguard",
                {"title": title, "urn": f"urn:cisecurity.org:controls:{version}:{number}"},
                None,
                [
                    (
                        f"{{{CONTROLS}}}implementation_groups",
                        {"ig1": ig1, "ig2": "true", "ig3": "true"},
                        None,
                        [],
                    ),
                    (f"{{{CONTROLS}}}asset_type", {}, "Unknown", []),
                    (f"{{{CONTROLS}}}security_function", {}, "Protect", []),
                ],
            )

        assert shape(root) == (
            f"{{{CONTROLS}}}cis_controls",
            {},
            None,
            [
                (
                    f"{{{CONTROLS}}}framework",
                    {"urn": "urn:cisecurity.org:controls:7"},
                    None,
                    [safeguard("7", "14.9", "Enforce Detail Logging", "true")],
                ),
                (
                    f"{{{CONTROLS}}}framework",
                    {"urn": "urn:cisecurity.org:controls:8"},
                    None,
                    [safeguard("8", "3.14", "Log Sensitive Data Access", "false")],
                ),
            ],
        )

    def test_items_of_one_group_keep_the_order_of_the_source(self, engine, controls_mapping):
        rec = recommendation(
            control(8, "4.8", "Second listed first"),
            control(8, "4.1", "First by number, listed second"),
        )

        root = engine.generate_metadata_from_config(rec, controls_mapping)

        (framework,) = root.children
        assert [child.attributes["title"] for child in framework.children] == [
            "Second listed first",
            "First by number, listed second",
        ]

    def test_a_boolean_attribute_of_an_item_element_is_written_lowercase(
        self, engine, controls_mapping
    ):
        mapping = {
            **controls_mapping,
            "metadata_spec": {
                **controls_mapping["metadata_spec"],
                "group_element": {
                    "element": "framework",
                    "item_element": {"element": "safeguard", "attributes": {"ig1": "{item.ig1}"}},
                },
            },
        }

        root = engine.generate_metadata_from_config(
            recommendation(control(8, "4.8", "t", ig1=True)), mapping
        )

        assert root.children[0].children[0].attributes == {"ig1": "true"}

    def test_no_data_gives_an_empty_root_when_the_mapping_allows_it(self, engine, controls_mapping):
        assert controls_mapping["metadata_spec"]["allow_empty"] is True

        root = engine.generate_metadata_from_config(recommendation(), controls_mapping)

        assert shape(root) == (f"{{{CONTROLS}}}cis_controls", {}, None, [])

    def test_no_data_gives_nothing_when_the_mapping_does_not_allow_an_empty_root(
        self, engine, controls_mapping
    ):
        mapping = {
            **controls_mapping,
            "metadata_spec": {**controls_mapping["metadata_spec"], "allow_empty": False},
        }

        assert engine.generate_metadata_from_config(recommendation(), mapping) is None

    @pytest.mark.parametrize(("allow_empty", "expected"), [(False, None), (True, "empty root")])
    def test_items_that_fall_in_no_group_are_handled_like_no_data(
        self, engine, controls_mapping, allow_empty, expected
    ):
        # Grouping by a field that is false for every item gives no group.
        mapping = {
            **controls_mapping,
            "metadata_spec": {
                **controls_mapping["metadata_spec"],
                "group_by": "item.ig1",
                "allow_empty": allow_empty,
            },
        }

        root = engine.generate_metadata_from_config(
            recommendation(control(8, "4.8", "t", ig1=False)), mapping
        )

        assert (root and "empty root") == expected
        assert root is None or shape(root) == (f"{{{CONTROLS}}}cis_controls", {}, None, [])

    def test_an_attribute_value_xsdata_would_rewrite_as_a_type_name_stops_the_export(
        self, engine, controls_mapping
    ):
        # xsdata writes a value that names an XML Schema type as a prefixed QName.
        rec = recommendation(control(8, "4.8", "{http://www.w3.org/2001/XMLSchema}string"))

        with pytest.raises(ValueError, match="title"):
            engine.generate_metadata_from_config(rec, controls_mapping)


class TestMetadataOnTheRule:
    def test_the_rule_holds_the_metadata_as_model_content(self, engine):
        rule = engine.map_rule(
            recommendation(control(8, "4.8", "t")),
            {"benchmark": None, "recommendations": []},
        )

        (metadata,) = rule.metadata
        (root,) = metadata.other_element
        assert isinstance(metadata, engine.get_xccdf_class("MetadataType"))
        assert root.qname == f"{{{CONTROLS}}}cis_controls"

    def test_each_metadata_mapping_gives_its_own_metadata_element_in_mapping_order(
        self, tmp_path, cis_config_path
    ):
        style = tmp_path / "style.yaml"
        style.write_text(
            f"extends: {cis_config_path}\nmetadata:\n  style_name: child\n"
            "field_mappings:\n  second_metadata:\n    target_element: metadata\n"
            "    structure: metadata_from_config\n    source_field: cis_controls\n"
            "    metadata_spec:\n      root_element: second\n"
            "      namespace_prefix: controls\n      group_by: item.version\n"
            "      group_element:\n        element: framework\n"
            "        item_element:\n          element: safeguard\n"
        )
        engine = MappingEngine(style)

        rule = engine.map_rule(
            recommendation(control(8, "4.8", "t")),
            {"benchmark": None, "recommendations": []},
        )

        assert [metadata.other_element[0].qname for metadata in rule.metadata] == [
            f"{{{CONTROLS}}}cis_controls",
            f"{{{CONTROLS}}}second",
        ]


class TestRefusedWhenTheStyleLoads:
    """A mapping that could write something XCCDF does not allow in metadata, or that sets a
    key nothing reads, is refused before any benchmark is exported."""

    @staticmethod
    def _style(tmp_path, parent, body: str):
        style = tmp_path / "style.yaml"
        style.write_text(f"extends: {parent}\nmetadata:\n  style_name: child\n{body}")
        return style

    def _with_metadata_spec(self, tmp_path, cis_config_path, spec_lines: str):
        return self._style(
            tmp_path,
            cis_config_path,
            "field_mappings:\n  cis_controls_metadata:\n    metadata_spec:\n" + spec_lines,
        )

    @pytest.mark.parametrize(
        ("spec_lines", "message"),
        [
            pytest.param('      namespace_prefix: ""\n', "namespace_prefix", id="no prefix"),
            pytest.param('      namespace_prefix: "nope"\n', "'nope'", id="undeclared prefix"),
            pytest.param(
                '      namespace_prefix: "default"\n',
                "another namespace",
                id="the XCCDF namespace itself",
            ),
            pytest.param(
                '      namespace: "http://cisecurity.org/controls"\n',
                "benchmark.namespaces",
                id="removed namespace key",
            ),
            pytest.param("      group_by: null\n", "group_by", id="no grouping"),
            pytest.param('      root_element: "not a name"\n', "not a name", id="bad element name"),
            pytest.param(
                '      group_element:\n        attributes:\n          "xsi:type": "x"\n',
                "xsi:type",
                id="attribute name with a prefix",
            ),
            pytest.param(
                '      group_element:\n        attributes:\n          xmlns: "urn:x"\n',
                "xmlns",
                id="a namespace declaration as an attribute",
            ),
            pytest.param('      root_element: "xmlns"\n', "xmlns", id="xmlns as an element"),
            pytest.param(
                '      group_by: "item.versoin"\n', "versoin", id="grouping by no field of the item"
            ),
        ],
    )
    def test_a_metadata_spec_that_cannot_be_written_is_refused(
        self, tmp_path, cis_config_path, spec_lines, message
    ):
        style = self._with_metadata_spec(tmp_path, cis_config_path, spec_lines)

        with pytest.raises(ValueError, match=message):
            MappingEngine(style)

    def test_metadata_aimed_at_an_element_that_holds_no_foreign_content_is_refused(
        self, tmp_path, cis_config_path
    ):
        # A Rule's title holds text; only metadata holds elements of another namespace.
        style = self._style(
            tmp_path,
            cis_config_path,
            "field_mappings:\n  cis_controls_metadata:\n    target_element: title\n",
        )

        with pytest.raises(ValueError, match="title"):
            MappingEngine(style)

    def test_the_removed_requires_post_processing_key_is_refused(self, tmp_path, cis_config_path):
        style = self._style(
            tmp_path,
            cis_config_path,
            "field_mappings:\n  cis_controls_metadata:\n    requires_post_processing: true\n",
        )

        with pytest.raises(ValueError, match="requires_post_processing"):
            MappingEngine(style)

    def test_metadata_is_refused_for_a_version_whose_rules_have_no_metadata_element(
        self, tmp_path, disa_config_path
    ):
        # XCCDF 1.1.4 has a metadata type (on Benchmark) but no metadata element in Rule.
        # The style is refused as it loads, whether or not a benchmark has controls.
        style = self._style(
            tmp_path,
            disa_config_path,
            "benchmark:\n  namespaces:\n    controls: http://cisecurity.org/controls\n"
            "field_mappings:\n  controls_metadata:\n    target_element: metadata\n"
            "    structure: metadata_from_config\n    source_field: cis_controls\n"
            "    metadata_spec:\n      root_element: cis_controls\n"
            "      namespace_prefix: controls\n      group_by: item.version\n"
            "      group_element:\n        element: framework\n"
            "        item_element:\n          element: safeguard\n",
        )

        with pytest.raises(ValueError, match=r"1\.1\.4.*metadata"):
            MappingEngine(style)


def benchmark(*recommendations: Recommendation) -> Benchmark:
    return Benchmark(
        title="Synthetic benchmark",
        benchmark_id="12345",
        url="https://example.org/benchmarks/12345",
        version="v1.0.0",
        scraper_version="v2_2026_01",
        total_recommendations=len(recommendations),
        recommendations=list(recommendations),
    )


class TestTheExportedMetadata:
    """The metadata as the CIS export writes it and a reader parses it back."""

    @staticmethod
    def _safeguards(path) -> list[dict[str, str]]:
        root = etree.parse(str(path)).getroot()
        return [dict(e.attrib) for e in root.iter(f"{{{CONTROLS}}}safeguard")]

    def test_attribute_text_is_written_as_given(self, tmp_path):
        titles = [
            "Use <tags> & \"quotes\" and 'apostrophes'",
            "Überwachung der Protokolle – café, 日本語",
            "Long title " + "x" * 5000,
        ]
        output = tmp_path / "cis.xml"
        rec = recommendation(*(control(8, f"4.{i}", title) for i, title in enumerate(titles)))

        XCCDFExporter(style="cis").export(benchmark(rec), str(output))

        assert [s["title"] for s in self._safeguards(output)] == titles

    def test_long_element_text_is_written_as_given(self, tmp_path, cis_config_path):
        style = tmp_path / "style.yaml"
        style.write_text(
            f"extends: {cis_config_path}\nmetadata:\n  style_name: child\n"
            "field_mappings:\n  cis_controls_metadata:\n    metadata_spec:\n"
            "      group_element:\n        item_element:\n          children:\n"
            '            - element: note\n              content: "{item.title}"\n'
        )
        title = "Long <text> & more " + "y" * 5000
        exporter = XCCDFExporter(style="cis")
        exporter.engine = MappingEngine(style)
        exporter.config = exporter.engine.config
        output = tmp_path / "cis.xml"

        exporter.export(benchmark(recommendation(control(8, "4.8", title))), str(output))

        root = etree.parse(str(output)).getroot()
        assert [e.text for e in root.iter(f"{{{CONTROLS}}}note")] == [title]

    def test_two_exports_from_one_exporter_are_identical(self, tmp_path):
        exporter = XCCDFExporter(style="cis")
        bench = benchmark(recommendation(control(8, "4.8", "t"), control(7, "9.2", "u")))
        first, second = tmp_path / "first.xml", tmp_path / "second.xml"

        exporter.export(bench, str(first))
        exporter.export(bench, str(second))

        assert first.read_bytes() == second.read_bytes()

    def test_a_rule_without_data_gets_no_metadata_element_when_empty_is_not_allowed(
        self, tmp_path, cis_config_path
    ):
        style = tmp_path / "style.yaml"
        style.write_text(
            f"extends: {cis_config_path}\nmetadata:\n  style_name: child\n"
            "field_mappings:\n  cis_controls_metadata:\n    metadata_spec:\n"
            "      allow_empty: false\n"
        )

        rule = MappingEngine(style).map_rule(
            recommendation(), {"benchmark": None, "recommendations": []}
        )

        assert rule.metadata == []

    def test_a_value_xsdata_would_rewrite_stops_the_export_before_the_file_is_written(
        self, tmp_path
    ):
        output = tmp_path / "cis.xml"
        rec = recommendation(control(8, "4.8", "{http://www.w3.org/2001/XMLSchema}string"))

        with pytest.raises(ValueError, match="title"):
            XCCDFExporter(style="cis").export(benchmark(rec), str(output))

        assert not output.exists()
