"""The XCCDF status a benchmark's CIS WorkBench status maps to."""

import pytest

from cis_bench.catalog.models import BenchmarkStatus
from cis_bench.exceptions import ExportError
from cis_bench.exporters.benchmark_status import xccdf_status
from cis_bench.models.xccdf import xccdf_1_2
from cis_bench.models.xccdf_v1_1 import xccdf_1_1_4


@pytest.mark.parametrize(
    ("workbench_status", "expected"),
    [
        ("Published", "accepted"),
        ("Accepted", "accepted"),
        ("Final Update", "accepted"),
        ("Draft", "draft"),
        ("Archived", "deprecated"),
        ("Rejected", "deprecated"),
        ("Withdrawn", "deprecated"),
    ],
)
def test_each_workbench_status_maps_to_its_xccdf_status(
    synthetic_complete_benchmark, workbench_status, expected
):
    benchmark = synthetic_complete_benchmark.model_copy(
        update={"workbench_status": workbench_status}
    )

    assert xccdf_status(benchmark) == expected


def test_every_status_the_catalog_knows_maps_to_a_status_both_xccdf_versions_have(
    synthetic_complete_benchmark,
):
    for workbench_status in BenchmarkStatus:
        benchmark = synthetic_complete_benchmark.model_copy(
            update={"workbench_status": workbench_status.value}
        )
        mapped = xccdf_status(benchmark)
        xccdf_1_2.StatusType(mapped)
        xccdf_1_1_4.StatusType(mapped)


def test_an_unknown_workbench_status_is_refused(synthetic_complete_benchmark):
    benchmark = synthetic_complete_benchmark.model_copy(update={"workbench_status": "Retired"})

    with pytest.raises(ExportError, match="'Retired'"):
        xccdf_status(benchmark)


def test_a_benchmark_with_no_workbench_status_is_refused(synthetic_complete_benchmark):
    benchmark = synthetic_complete_benchmark.model_copy(update={"workbench_status": None})

    with pytest.raises(ExportError, match=f"{benchmark.benchmark_id}.*no WorkBench status"):
        xccdf_status(benchmark)
