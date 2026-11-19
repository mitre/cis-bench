"""The docs build publishes the style file JSON Schema from StyleConfig, so an editor can check
a style file against the same schema cis-bench loads it with."""

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator, ValidationError
from jsonschema.validators import validator_for
from mkdocs.config.defaults import MkDocsConfig
from mkdocs.structure.files import Files

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "scripts" / "mkdocs_style_schema.py"
CONFIGS = ROOT / "src" / "cis_bench" / "exporters" / "configs"
STYLES = [CONFIGS / "base.yaml", *sorted((CONFIGS / "styles").glob("*.yaml"))]
assert len(STYLES) == 3, "base.yaml, cis.yaml and disa.yaml"


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
    published = files.get_file_from_path("schemas/style.json")

    assert published is not None
    return json.loads(published.content_string)


def test_the_schema_declares_json_schema_draft_2020_12(schema):
    assert validator_for(schema, default=None) is Draft202012Validator


@pytest.mark.parametrize("path", STYLES, ids=lambda path: path.name)
def test_the_published_schema_accepts_every_shipped_style(schema, path):
    Draft202012Validator(schema).validate(yaml.safe_load(path.read_text()))


def test_a_style_with_an_unknown_section_is_refused(schema):
    with pytest.raises(ValidationError, match="'bogus' was unexpected"):
        Draft202012Validator(schema).validate({"metadata": {"style_name": "s"}, "bogus": {}})


def test_a_field_mapping_with_a_key_its_structure_does_not_take_is_refused(schema):
    style = {"field_mappings": {"title": {"structure": "composite", "source_field": "title"}}}

    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(style)


@pytest.mark.parametrize("weight", [10.0, 10, "10.0", "7.5"])
def test_a_weight_written_as_a_number_or_as_decimal_text_is_accepted(schema, weight):
    Draft202012Validator(schema).validate({"rule_defaults": {"weight": weight}})
