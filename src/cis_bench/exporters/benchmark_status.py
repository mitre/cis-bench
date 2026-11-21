"""The XCCDF status a benchmark's CIS WorkBench status maps to.

XCCDF gives a Benchmark one of five statuses (accepted, deprecated, draft, incomplete,
interim); CIS WorkBench gives each benchmark one of its own. The status written is the one
the benchmark's WorkBench status maps to; a benchmark with no WorkBench status, or one this
table does not name, is refused rather than written with a status nothing gave.
"""

from types import MappingProxyType
from typing import Final

from cis_bench.exceptions import ExportError
from cis_bench.models.benchmark import Benchmark

XCCDF_STATUS_OF_WORKBENCH_STATUS: Final = MappingProxyType(
    {
        "Published": "accepted",
        "Accepted": "accepted",
        "Final Update": "accepted",
        "Draft": "draft",
        "Archived": "deprecated",
        "Rejected": "deprecated",
        "Withdrawn": "deprecated",
    }
)


def xccdf_status(benchmark: Benchmark) -> str:
    """The XCCDF status (its value, e.g. "accepted") for the benchmark's WorkBench status.

    Raises:
        ExportError: The benchmark has no WorkBench status, or one the table does not name.
    """
    if benchmark.workbench_status is None:
        raise ExportError(
            f"Benchmark {benchmark.benchmark_id} has no WorkBench status, so its XCCDF status "
            "is not known: the copy records none and the catalog does not list the benchmark"
        )
    try:
        return XCCDF_STATUS_OF_WORKBENCH_STATUS[benchmark.workbench_status]
    except KeyError:
        raise ExportError(
            f"Benchmark {benchmark.benchmark_id} has the WorkBench status "
            f"{benchmark.workbench_status!r}, which maps to no XCCDF status"
        ) from None
