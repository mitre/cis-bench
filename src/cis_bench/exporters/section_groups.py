"""A benchmark's recommendations arranged into its section tree.

The CIS style writes one XCCDF Group per WorkBench section, nested as the sections are, each
holding its own recommendations' Rules. This module gives the engine that tree as plain data:
every section under its parent and every recommendation under its section, both in the order
the copy records (WorkBench's order). A section with nothing in it is kept, as CIS writes such
Groups. Anything the tree cannot place is refused rather than dropped or guessed.
"""

from collections import defaultdict
from typing import NamedTuple

from cis_bench.exceptions import ExportError
from cis_bench.models.benchmark import Benchmark, Recommendation, Section


class SectionNode(NamedTuple):
    """One section with its own recommendations and its sub-sections, in recorded order."""

    section: Section
    recommendations: tuple[Recommendation, ...]
    children: tuple["SectionNode", ...]


def section_tree(benchmark: Benchmark) -> tuple[SectionNode, ...]:
    """The benchmark's top-level sections, each with its recommendations and sub-sections.

    Raises:
        ExportError: The copy records no sections (saved before sections were recorded), a
            section id is recorded twice, a recommendation's section or a section's parent
            is not one of them, or sections' parents form a loop; the message names the
            benchmark and the id.
    """
    if benchmark.sections is None:
        raise ExportError(
            f"Benchmark {benchmark.benchmark_id} has no sections: the copy was saved before "
            "sections were recorded"
        )
    known: set[int] = set()
    for section in benchmark.sections:
        if section.id in known:
            # Each copy of the id would take the same recommendations and sub-sections, or,
            # reused below itself, make the tree endless
            raise ExportError(
                f"Benchmark {benchmark.benchmark_id}: section id {section.id} (section "
                f"{section.number}) is recorded more than once"
            )
        known.add(section.id)

    children: defaultdict[int | None, list[Section]] = defaultdict(list)
    for section in benchmark.sections:
        if section.parent_id is not None and section.parent_id not in known:
            raise ExportError(
                f"Benchmark {benchmark.benchmark_id}: section {section.number} (id "
                f"{section.id}) has parent id {section.parent_id}, which is not one of its "
                "sections"
            )
        children[section.parent_id].append(section)

    recommendations: defaultdict[int, list[Recommendation]] = defaultdict(list)
    for recommendation in benchmark.recommendations:
        if recommendation.section_id not in known:
            raise ExportError(
                f"Benchmark {benchmark.benchmark_id}: recommendation {recommendation.ref} has "
                f"section id {recommendation.section_id}, which is not one of its sections"
            )
        recommendations[recommendation.section_id].append(recommendation)

    placed: set[int] = set()

    def nodes(parent_id: int | None) -> tuple[SectionNode, ...]:
        placed.update(section.id for section in children[parent_id])
        return tuple(
            SectionNode(
                section=section,
                recommendations=tuple(recommendations[section.id]),
                children=nodes(section.id),
            )
            for section in children[parent_id]
        )

    tree = nodes(None)
    if len(placed) < len(known):
        # Parents that loop never reach the top level; their sections would be dropped
        looped = ", ".join(s.number for s in benchmark.sections if s.id not in placed)
        raise ExportError(
            f"Benchmark {benchmark.benchmark_id}: sections {looped} never reach a top-level "
            "section (their parents form a loop)"
        )
    return tree
