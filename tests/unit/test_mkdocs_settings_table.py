"""The docs build renders the settings table from the Settings class, so the docs cannot drift."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

HOOK = Path(__file__).resolve().parents[2] / "scripts" / "mkdocs_settings_table.py"


@pytest.fixture(scope="module")
def hook():
    spec = importlib.util.spec_from_file_location("mkdocs_settings_table", HOOK)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class Demo(BaseSettings):
    """A small settings class with one field of each kind the table must render."""

    model_config = SettingsConfigDict(env_prefix="DEMO_")

    folders: str = Field(default="located", exclude=True)
    speed: float = Field(
        default=1.5, description="How fast", json_schema_extra={"accepted": "a number above 0"}
    )
    quiet: bool = Field(default=False, description="Say less")
    pages: int = Field(default=10, description="Pages per batch")
    tool: str = Field(
        default="hammer", description="Tool to use", json_schema_extra={"accepted": "hammer or saw"}
    )


EXPECTED = """| Setting | `config.toml` key | Type | Default | Accepted values | What it does |
|---|---|---|---|---|---|
| `DEMO_SPEED` | `speed` | number | `1.5` | a number above 0 | How fast |
| `DEMO_QUIET` | `quiet` | true/false | `false` | `true` or `false` | Say less |
| `DEMO_PAGES` | `pages` | integer | `10` | an integer | Pages per batch |
| `DEMO_TOOL` | `tool` | text | `"hammer"` | hammer or saw | Tool to use |"""


class TestRenderSettingsTable:
    def test_one_row_per_named_setting_in_declaration_order(self, hook):
        table = hook.render_settings_table(Demo, ["speed", "quiet", "pages", "tool"])
        assert table == EXPECTED

    def test_only_the_named_fields_are_rows(self, hook):
        table = hook.render_settings_table(Demo, ["quiet"])
        assert table.count("\n") == 2
        assert "DEMO_FOLDERS" not in table
        assert "DEMO_SPEED" not in table


class TestTheHookFillsTheConfigurationPage:
    @staticmethod
    def _page(src_uri):
        return SimpleNamespace(file=SimpleNamespace(src_uri=src_uri))

    def test_the_marker_on_the_configuration_page_becomes_the_table(self, hook):
        markdown = "## Settings\n\n<!-- settings-table -->\n\nMore text.\n"
        result = hook.on_page_markdown(
            markdown, page=self._page("user-guide/configuration.md"), config={}, files=None
        )
        assert "<!-- settings-table -->" not in result
        assert "| `CIS_BENCH_SEARCH_LIMIT` | `search_limit` | integer | `100` |" in result
        assert '| `CIS_BENCH_BROWSER` | `browser` | text | `"chrome"` |' in result
        assert "CIS_BENCH_FOLDERS" not in result
        assert result.endswith("\n\nMore text.\n")

    def test_a_configuration_page_without_the_marker_fails_the_build(self, hook):
        with pytest.raises(hook.PluginError, match="settings-table"):
            hook.on_page_markdown(
                "## Settings\n",
                page=self._page("user-guide/configuration.md"),
                config={},
                files=None,
            )

    def test_other_pages_are_left_alone(self, hook):
        markdown = "<!-- settings-table -->\n"
        assert (
            hook.on_page_markdown(markdown, page=self._page("index.md"), config={}, files=None)
            is markdown
        )
