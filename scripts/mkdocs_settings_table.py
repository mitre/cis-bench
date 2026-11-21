"""mkdocs hook: render the settings table in docs/user-guide/configuration.md from the Settings class.

Wired in mkdocs.yml under ``hooks:``. At build time the ``<!-- settings-table -->`` marker on the
configuration page becomes one row per setting: variable, config.toml key, type, default,
accepted values and description, all read from ``cis_bench.config.Settings``. The page has no
hand-written copy, so the docs cannot drift from the code; a configuration page without the
marker fails the build.
"""

from __future__ import annotations

from collections.abc import Iterable

from mkdocs.exceptions import PluginError
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings

MARKER = "<!-- settings-table -->"
CONFIGURATION_PAGE = "user-guide/configuration.md"

_TYPE_NAMES = {float: "number", int: "integer", bool: "true/false", str: "text"}
_HEADER = (
    "| Setting | `config.toml` key | Type | Default | Accepted values | What it does |\n"
    "|---|---|---|---|---|---|"
)


def _type_name(field: FieldInfo) -> str:
    annotation = field.annotation
    if annotation in _TYPE_NAMES:
        return _TYPE_NAMES[annotation]
    raise PluginError(f"settings-table: no name for the type {annotation!r}")


def _default(field: FieldInfo) -> str:
    value = field.default
    if isinstance(value, bool):
        return f"`{str(value).lower()}`"  # the TOML spelling
    if isinstance(value, str):
        return f'`"{value}"`'
    return f"`{value!r}`"


def _accepted(field: FieldInfo) -> str:
    extra = field.json_schema_extra
    if isinstance(extra, dict) and extra.get("accepted"):
        return str(extra["accepted"])
    if field.annotation is bool:
        return "`true` or `false`"
    if field.annotation is int:
        return "an integer"
    if field.annotation is float:
        return "a number"
    return ""


def render_settings_table(model: type[BaseSettings], names: Iterable[str]) -> str:
    """The Markdown table for the named fields of model, in the order given."""
    prefix = str(model.model_config.get("env_prefix", ""))
    rows = []
    for name in names:
        field = model.model_fields[name]
        rows.append(
            f"| `{prefix}{name.upper()}` | `{name}` | {_type_name(field)} | {_default(field)} "
            f"| {_accepted(field)} | {field.description or ''} |"
        )
    return "\n".join([_HEADER, *rows])


def on_page_markdown(markdown: str, page, config, files) -> str:
    """mkdocs event: fill the marker on the configuration page; leave every other page alone."""
    if page.file.src_uri != CONFIGURATION_PAGE:
        return markdown
    if MARKER not in markdown:
        raise PluginError(f"{CONFIGURATION_PAGE} has no {MARKER} marker for the settings table")

    from cis_bench.config import Settings, setting_names

    return markdown.replace(MARKER, render_settings_table(Settings, setting_names()))
