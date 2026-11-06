"""Click group that imports subcommands on first use.

Click documents this pattern for CLIs whose subcommands have slow imports: the
group stores ``{command name: "module.path.attribute"}`` and resolves a command
only when it is invoked, listed for ``--help``, or shell-completed. Running one
command therefore never imports another command's dependency stack.
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from typing import Any

import click


class LazyGroup(click.Group):
    """A ``click.Group`` whose subcommands are imported on demand."""

    def __init__(
        self,
        *args: Any,
        lazy_subcommands: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.lazy_subcommands: dict[str, str] = dict(lazy_subcommands or {})

    def list_commands(self, ctx: click.Context) -> list[str]:
        return super().list_commands(ctx) + sorted(self.lazy_subcommands)

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        if cmd_name in self.lazy_subcommands:
            return self._lazy_load(cmd_name)
        return super().get_command(ctx, cmd_name)

    def _lazy_load(self, cmd_name: str) -> click.Command:
        import_path = self.lazy_subcommands[cmd_name]
        module_name, attribute = import_path.rsplit(".", 1)
        command = getattr(importlib.import_module(module_name), attribute)
        if not isinstance(command, click.Command):
            raise TypeError(
                f"Lazy loading of {import_path} returned {type(command).__name__}, "
                "not a click.Command"
            )
        return command
