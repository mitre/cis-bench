"""Validate command: check XCCDF files against the schemas shipped with cis-bench."""

import sys
from gettext import ngettext

import click
from rich.console import Console
from rich.markup import escape

from cis_bench.validators.xccdf_schema import NotXccdfError, validate_xccdf

console = Console()
error_console = Console(stderr=True)


@click.command(name="validate")
@click.argument("files", nargs=-1, required=True, type=click.Path(dir_okay=False))
def validate_cmd(files):
    """Check XCCDF files against the NIST XCCDF schema.

    Each FILE is validated against the schema for the XCCDF version its root element names
    (1.1 or 1.2), with the schemas shipped in cis-bench: no network, no xmllint. Schema
    validity says the document is well-formed XCCDF; it is not DISA or CIS convention
    compliance.

    \b
    Exit codes (as oscap xccdf validate):
      0  every file is valid
      2  a file is not valid; each error is listed with its line
      1  a file could not be validated (missing, not XML, not XCCDF)

    \b
    Examples:
        cis-bench export 23598 --format xccdf --style cis
        cis-bench validate benchmark_23598.xml
        cis-bench validate exports/*.xml
    """
    invalid = 0
    not_validated = 0
    for file in files:
        try:
            result = validate_xccdf(file)
        except NotXccdfError as error:
            not_validated += 1
            error_console.print(f"[red]✗[/red] {escape(str(error))}", soft_wrap=True)
            continue
        if result.is_valid:
            console.print(
                f"[green]✓[/green] {escape(file)}: valid XCCDF {result.version}", soft_wrap=True
            )
            continue
        invalid += 1
        count = len(result.errors)
        error_console.print(
            f"[red]✗[/red] {escape(file)}: invalid XCCDF {result.version} "
            + ngettext("({count} error)", "({count} errors)", count).format(count=count),
            soft_wrap=True,
        )
        for message in result.errors:
            error_console.print(f"    {escape(message)}")

    if not_validated:
        sys.exit(1)
    if invalid:
        sys.exit(2)
