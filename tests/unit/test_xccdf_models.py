"""Namespaces in the generated XCCDF models and in xsdata's render of an export.

Both XCCDF schemas set elementFormDefault="qualified": every element they declare is in a
namespace, the XCCDF version's own or the one the schema gives it (Dublin Core, a CPE or
platform schema, a wildcard's). A model field that declares no namespace makes xsdata write
that element outside any namespace.
"""

import inspect
from collections.abc import Iterator
from dataclasses import is_dataclass
from pathlib import Path
from types import ModuleType

import pytest
from lxml import etree
from xsdata.formats.dataclass.context import XmlContext

from cis_bench.exporters import ExporterFactory
from cis_bench.models.benchmark import Benchmark
from cis_bench.models.xccdf import xccdf_1_2
from cis_bench.models.xccdf_v1_1 import xccdf_1_1_4
from cis_bench.utils.xml_utils import XCCDFSerializer

MODEL_MODULES = [
    pytest.param(xccdf_1_1_4, id="xccdf-1.1.4"),
    pytest.param(xccdf_1_2, id="xccdf-1.2"),
]


def model_classes(module: ModuleType) -> Iterator[type]:
    """Every dataclass a model module defines, nested classes included."""

    def nested(cls: type) -> Iterator[type]:
        yield cls
        for member in vars(cls).values():
            if inspect.isclass(member) and is_dataclass(member):
                yield from nested(member)

    for member in vars(module).values():
        if (
            inspect.isclass(member)
            and is_dataclass(member)
            and member.__module__ == module.__name__
        ):
            yield from nested(member)


def unqualified_elements(module: ModuleType) -> list[str]:
    """Element fields xsdata would write outside any namespace, as Class.field."""
    context = XmlContext()
    found = []
    for cls in model_classes(module):
        meta = context.build(cls)
        element_vars = [var for group in meta.elements.values() for var in group]
        element_vars += [choice for var in meta.choices for choice in var.elements.values()]
        found += [
            f"{cls.__qualname__}.{var.name}"
            for var in element_vars
            if not var.qname.startswith("{")
        ]
    return found


@pytest.mark.parametrize("module", MODEL_MODULES)
def test_every_xccdf_element_field_is_in_its_versions_namespace(module: ModuleType):
    assert unqualified_elements(module) == []


@pytest.mark.parametrize("style", ["disa", "cis"])
@pytest.mark.parametrize(
    "fixture",
    sorted(
        (Path(__file__).resolve().parents[1] / "fixtures" / "benchmarks").glob("synthetic_*.json")
    ),
    ids=lambda path: path.stem,
)
def test_the_raw_render_of_an_export_writes_no_element_outside_a_namespace(
    style: str, fixture: Path
):
    # The object the exporter builds and xsdata's render of it, before the exporter's
    # post-processing, which is what export() runs first.
    exporter = ExporterFactory.create("xccdf", style=style)
    xccdf_benchmark = exporter._create_benchmark(Benchmark.from_json_file(str(fixture)))
    root = etree.fromstring(XCCDFSerializer.serialize_to_string(xccdf_benchmark).encode())

    outside = sorted(
        {
            element.tag
            for element in root.iter()
            if isinstance(element.tag, str) and etree.QName(element).namespace is None
        }
    )
    assert outside == []
