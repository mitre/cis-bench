#!/usr/bin/env python3
"""CIS Benchmark CLI - Main application."""

from pathlib import Path

import click
from rich.console import Console
from rich.markup import escape

from cis_bench import __version__
from cis_bench.cli.helpers.errors import report_configuration_error
from cis_bench.cli.lazy_group import LazyGroup
from cis_bench.config import HOME_VARIABLE, load_settings, resolve_folders
from cis_bench.exceptions import ConfigurationError
from cis_bench.utils.logging_config import LoggingConfig

console = Console()


# Subcommands are imported on first use (Click's documented lazy-loading pattern), so
# `cis-bench export` never loads the scraper or catalog stacks and startup stays fast.
LAZY_SUBCOMMANDS = {
    "auth": "cis_bench.cli.commands.auth.auth",
    "catalog": "cis_bench.cli.commands.catalog.catalog",
    "config": "cis_bench.cli.commands.config.config",
    "download": "cis_bench.cli.commands.download.download",
    "export": "cis_bench.cli.commands.export.export_cmd",
    "get": "cis_bench.cli.commands.get.get_cmd",
    "info": "cis_bench.cli.commands.info.info",
    "list": "cis_bench.cli.commands.list_cmd.list_benchmarks",
    "remove": "cis_bench.cli.commands.remove.remove_cmd",
    "search": "cis_bench.cli.commands.search.search_cmd",
}


def _asks_for_help(command: click.Command, ctx: click.Context, args: list[str]) -> bool:
    """Whether Click will show help for this command line, judged by Click's own parser.

    Each command's parser reads the arguments the way Click will, so a value such as the
    "--help" in ``--platform --help`` is the option's value, not a help request. Nothing
    is acted on: no callback runs and no context is entered.

    Command.make_parser is public, but the parser class it returns is marked for removal
    in Click 9.0; pyproject.toml caps click below 9 so that upgrade is a deliberate step.
    """
    if not args and isinstance(command, click.Group):
        return command.no_args_is_help  # a group named alone shows its help
    try:
        options, rest, _ = command.make_parser(ctx).parse_args(list(args))
    except click.UsageError:
        return False  # Click reports the usage error itself, not help
    if options.get("help"):
        return True
    if not isinstance(command, click.Group) or not rest:
        return False
    subcommand = command.get_command(ctx, rest[0])
    if subcommand is None:
        return False
    sub_ctx = click.Context(subcommand, info_name=rest[0], parent=ctx)
    return _asks_for_help(subcommand, sub_ctx, rest[1:])


class RootGroup(LazyGroup):
    """The cis-bench command: notes whether the command line asks for help.

    The root callback checks the settings before any command runs, but Click handles a
    subcommand's --help only after that callback; help must work even with a bad setting.
    """

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        ctx.meta["cis_bench.asks_for_help"] = _asks_for_help(self, ctx, args)
        return super().parse_args(ctx, args)


@click.group(cls=RootGroup, lazy_subcommands=LAZY_SUBCOMMANDS)
@click.version_option(version=__version__, prog_name="cis-bench")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose (DEBUG level) logging")
@click.option(
    "--debug", "-d", is_flag=True, help="Enable maximum debug logging (same as --verbose)"
)
@click.option("--quiet", "-q", is_flag=True, help="Quiet mode (warnings and errors only)")
@click.pass_context
def cli(ctx, verbose, debug, quiet):
    """CIS Benchmark CLI - Fetch and manage CIS benchmarks.

    Download CIS benchmarks from CIS WorkBench and export to multiple formats
    including JSON, YAML, CSV, Markdown, and NIST XCCDF 1.2.

    \b
    Quick Start:
        cis-bench auth login --browser chrome    # One-time login
        cis-bench catalog refresh                # Build catalog (under a minute)
        cis-bench get "ubuntu 22" --format xccdf # Get benchmark

    \b
    Common Workflows:
        # Search and download
        cis-bench search "oracle cloud" --platform-type cloud
        cis-bench download 23598

        # All-in-one command
        cis-bench get "aws eks" --format xccdf --style cis

        # Scripting with JSON output
        cis-bench search oracle --output-format json | jq

    \b
    Global Flags:
        --verbose, -v    Show DEBUG level logs
        --debug, -d      Same as --verbose
        --quiet, -q      Only warnings and errors
    """
    # --debug is same as --verbose
    verbose = verbose or debug

    # Configure logging based on flags
    LoggingConfig.setup_from_flags(quiet=quiet, verbose=verbose)

    # Store in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["quiet"] = quiet

    # Every setting is checked once, before any command touches a file or the network.
    if not ctx.meta.get("cis_bench.asks_for_help"):
        try:
            settings = load_settings()
        except ConfigurationError as error:
            report_configuration_error(console, error)
            ctx.exit(1)
        ctx.obj["settings"] = settings
        if settings.folders.legacy is not None:
            _report_legacy_folder(settings.folders.legacy)


def _report_legacy_folder(legacy: Path) -> None:
    """One stderr line: this run still uses an earlier version's folder, and how to move on.

    stderr keeps stdout machine-readable (``--output-format json``). Support for the old
    folder ends in the next major version.
    """
    current = resolve_folders(use_legacy=False)
    Console(stderr=True).print(
        f"Note: cis-bench now keeps its files in {escape(str(current.config))}, "
        f"{escape(str(current.data))} and {escape(str(current.state))}; this run uses "
        f"{escape(str(legacy))} from an earlier version. Run `cis-bench config migrate` to "
        f"move them, or set {HOME_VARIABLE}={escape(str(legacy))} to keep one folder. "
        f"Support for {escape(str(legacy))} ends in the next major version.",
        soft_wrap=True,
        highlight=False,
    )


if __name__ == "__main__":
    cli()
