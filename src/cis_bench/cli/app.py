#!/usr/bin/env python3
"""CIS Benchmark CLI - Main application."""

import click
from rich.console import Console

from cis_bench import __version__
from cis_bench.utils.logging_config import LoggingConfig

console = Console()


@click.group()
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
        cis-bench catalog refresh                # Build catalog (~2 min)
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


# Import and register commands
from cis_bench.cli.commands import auth, catalog, download, export, get, info, list_cmd, search

cli.add_command(auth.auth)
cli.add_command(download.download)
cli.add_command(export.export_cmd)
cli.add_command(get.get_cmd)
cli.add_command(list_cmd.list_benchmarks)
cli.add_command(info.info)
cli.add_command(search.search_cmd)
cli.add_command(catalog.catalog)


if __name__ == "__main__":
    cli()
