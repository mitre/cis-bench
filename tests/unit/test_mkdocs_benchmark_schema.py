"""The docs build publishes the benchmark JSON Schema from the Benchmark model, so the
published schema cannot drift from what cis-bench reads and writes."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError
from jsonschema.validators import validator_for
from mkdocs.config.defaults import MkDocsConfig
from mkdocs.structure.files import Files

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "scripts" / "mkdocs_benchmark_schema.py"
BENCHMARKS = sorted((ROOT / "tests" / "fixtures" / "benchmarks").glob("*.json"))
assert BENCHMARKS, "no synthetic benchmarks to validate"


@pytest.fixture
def schema(tmp_path):
    """The schema as the docs build publishes it: the file the hook adds to the site when
    MkDocs loads it from ``hooks:`` and fires the files event."""
    docs = tmp_path / "docs"
    docs.mkdir()
    config = MkDocsConfig()
    config.load_dict(
        {
            "site_name": "test",
            "docs_dir": str(docs),
            "site_dir": str(tmp_path / "site"),
            "hooks": [str(HOOK)],
        }
    )
    errors, _ = config.validate()
    assert not errors

    files = config.plugins.on_files(Files([]), config=config)
    published = files.get_file_from_path("schemas/benchmark.json")

    assert published is not None
    return json.loads(published.content_string)


def _copy(name: str) -> dict:
    return json.loads((ROOT / "tests" / "fixtures" / "benchmarks" / name).read_text())


def test_the_schema_declares_json_schema_draft_2020_12(schema):
    assert validator_for(schema, default=None) is Draft202012Validator


@pytest.mark.parametrize("path", BENCHMARKS, ids=lambda path: path.name)
def test_the_published_schema_accepts_every_synthetic_benchmark(schema, path):
    # Older copies omit text_format and artifact_title_format; cis-bench reads them, so
    # the schema must accept them.
    Draft202012Validator(schema).validate(json.loads(path.read_text()))


def test_a_benchmark_without_a_title_is_refused(schema):
    copy = _copy("synthetic_linux_current.json")
    del copy["title"]

    with pytest.raises(ValidationError, match="'title' is a required property"):
        Draft202012Validator(schema).validate(copy)


def test_a_text_format_other_than_html_or_markdown_is_refused(schema):
    copy = {**_copy("synthetic_linux_current.json"), "text_format": "rtf"}

    with pytest.raises(ValidationError, match="'rtf'"):
        Draft202012Validator(schema).validate(copy)
