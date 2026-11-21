"""A benchmark's recommendations arranged into its section tree, as the CIS style writes it."""

import pytest

from cis_bench.exceptions import ExportError
from cis_bench.exporters.section_groups import section_tree
from cis_bench.models.benchmark import Benchmark, Recommendation, Section


def _section(section_id: int, number: str, parent_id: int | None, order: int) -> Section:
    return Section(
        id=section_id,
        number=number,
        title=f"Section {number}",
        parent_id=parent_id,
        order=order,
        description=f"About section {number}.",
    )


def _rec(ref: str, section_id: int | None) -> Recommendation:
    return Recommendation(
        ref=ref,
        title=f"Recommendation {ref}",
        url=f"https://workbench.cisecurity.org/sections/{section_id}/recommendations/{ref}",
        assessment_status="Automated",
        section_id=section_id,
    )


def _benchmark(sections: list[Section] | None, recommendations: list[Recommendation]) -> Benchmark:
    return Benchmark(
        title="CIS Synthetic Benchmark",
        benchmark_id="12345",
        url="https://workbench.cisecurity.org/benchmarks/12345",
        version="v1.0.0",
        scraper_version="v2_2026_01",
        sections=sections,
        section_descriptions_recorded=sections is not None,
        total_recommendations=len(recommendations),
        recommendations=recommendations,
    )


# Sections in the recorded (navtree) order: depth first, siblings by WorkBench's order
SECTIONS = [
    _section(10, "1", None, 1),
    _section(11, "1.1", 10, 1),
    _section(12, "1.2", 10, 2),
    _section(20, "2", None, 2),
    _section(30, "3", None, 3),  # no recommendations and no sub-sections
]
RECOMMENDATIONS = [
    _rec("1.1.1", 11),
    _rec("1.1.2", 11),
    _rec("1.2.1", 12),
    _rec("2.1", 20),
    _rec("2.2", 20),
]


def _shape(nodes) -> list:
    """(section number, recommendation refs, children) for each node, recursively."""
    return [
        (node.section.number, [r.ref for r in node.recommendations], _shape(node.children))
        for node in nodes
    ]


def test_recommendations_sit_under_their_section_and_sections_under_their_parent():
    tree = section_tree(_benchmark(SECTIONS, RECOMMENDATIONS))

    assert _shape(tree) == [
        ("1", [], [("1.1", ["1.1.1", "1.1.2"], []), ("1.2", ["1.2.1"], [])]),
        ("2", ["2.1", "2.2"], []),
        ("3", [], []),
    ]


def test_the_recorded_order_is_kept_not_the_numbers():
    """WorkBench's order wins: a section recorded first stays first whatever its number,
    and recommendations keep the order the copy records."""
    sections = [_section(20, "2", None, 1), _section(10, "1", None, 2)]
    recommendations = [_rec("1.2", 10), _rec("2.1", 20), _rec("1.1", 10)]

    tree = section_tree(_benchmark(sections, recommendations))

    assert _shape(tree) == [("2", ["2.1"], []), ("1", ["1.2", "1.1"], [])]


def test_each_node_carries_the_section_and_recommendation_objects_unchanged():
    benchmark = _benchmark(SECTIONS, RECOMMENDATIONS)

    first = section_tree(benchmark)[0]

    assert first.section is benchmark.sections[0]
    assert first.children[0].recommendations[0] is benchmark.recommendations[0]


def test_a_copy_without_sections_is_refused_naming_the_benchmark():
    with pytest.raises(ExportError, match="12345.*no sections"):
        section_tree(_benchmark(None, RECOMMENDATIONS))


@pytest.mark.parametrize("section_id", [99, None], ids=["unknown-section", "no-section"])
def test_a_recommendation_outside_the_recorded_sections_is_refused(section_id):
    recommendations = [*RECOMMENDATIONS, _rec("9.9", section_id)]

    with pytest.raises(ExportError, match=rf"12345.*9\.9.*{section_id}"):
        section_tree(_benchmark(SECTIONS, recommendations))


def test_sections_whose_parents_form_a_loop_are_refused_not_dropped():
    """Sections that never reach the top level (each the other's parent, or its own) would
    vanish from the tree with their recommendations; they are refused instead."""
    sections = [*SECTIONS, _section(50, "5", 51, 5), _section(51, "5.1", 50, 1)]
    recommendations = [*RECOMMENDATIONS, _rec("5.1.1", 51)]

    with pytest.raises(ExportError, match=r"12345.*5, 5\.1"):
        section_tree(_benchmark(sections, recommendations))


@pytest.mark.parametrize(
    "duplicate",
    [
        # Two top-level sections with one id would each take the other's recommendations
        _section(10, "9", None, 9),
        # A child reusing its own top-level ancestor's id would make the tree endless
        _section(10, "1.3", 10, 3),
    ],
    ids=["second-root", "child-of-itself"],
)
def test_a_section_id_recorded_twice_is_refused(duplicate):
    sections = [*SECTIONS, duplicate]

    with pytest.raises(ExportError, match=r"12345.*section id 10.*more than once"):
        section_tree(_benchmark(sections, RECOMMENDATIONS))


def test_a_section_whose_parent_is_not_recorded_is_refused():
    sections = [*SECTIONS, _section(40, "4.1", 41, 4)]

    with pytest.raises(ExportError, match=r"12345.*4\.1.*41"):
        section_tree(_benchmark(sections, RECOMMENDATIONS))
