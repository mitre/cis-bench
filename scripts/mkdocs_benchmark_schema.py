"""mkdocs hook: publish the benchmark JSON Schema, generated from the Benchmark model.

Wired in mkdocs.yml under ``hooks:``. At build time it adds ``schemas/benchmark.json`` to the
site: ``Benchmark.model_json_schema()`` with a ``$schema`` keyword naming the draft pydantic
generates for (JSON Schema Draft 2020-12). The file is added in ``on_files`` as a generated
file, so pages can link it and ``mkdocs build --strict`` checks those links. Nothing is
committed: the model is the one source, so the published schema cannot drift from what
cis-bench reads.
"""

from __future__ import annotations

import json
from typing import Any

from mkdocs.config.defaults import MkDocsConfig
from mkdocs.structure.files import File, Files
from pydantic.json_schema import GenerateJsonSchema, JsonSchemaMode

from cis_bench.models.benchmark import Benchmark

PATH = "schemas/benchmark.json"


class _WithDialect(GenerateJsonSchema):
    """pydantic's generator, adding the ``$schema`` keyword it leaves out (as its docs show)."""

    def generate(self, schema: Any, mode: JsonSchemaMode = "validation") -> dict[str, Any]:
        json_schema = super().generate(schema, mode=mode)
        json_schema["$schema"] = self.schema_dialect
        return json_schema


def benchmark_schema() -> dict[str, Any]:
    """The JSON Schema of a benchmark file cis-bench reads."""
    return Benchmark.model_json_schema(schema_generator=_WithDialect)


def on_files(files: Files, *, config: MkDocsConfig) -> Files:
    files.append(
        File.generated(config, PATH, content=json.dumps(benchmark_schema(), indent=2) + "\n")
    )
    return files
