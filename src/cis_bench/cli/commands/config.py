"""The config command group: where cis-bench keeps its files."""

import logging
import shutil
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.markup import escape

from cis_bench.cli.helpers.services import settings_from
from cis_bench.config import (
    BENCHMARKS_FOLDER_NAME,
    CATALOG_DB_FILE_NAME,
    CONFIG_FILE_NAME,
    SESSION_FILE_NAME,
    Folders,
    resolve_folders,
)

console = Console()
logger = logging.getLogger(__name__)


@click.group()
def config():
    """Settings and the folders cis-bench keeps its files in."""


def _moves(legacy: Path, targets: Folders) -> list[tuple[Path, Path]]:
    """Each file of an earlier version's folder that exists, and where this version keeps it.

    catalog.db goes last: once it is in the new data folder the old folder is no longer in
    use, so a run that failed before that point can simply be run again.
    """
    planned = [
        (legacy / CONFIG_FILE_NAME, targets.config / CONFIG_FILE_NAME),
        (legacy / BENCHMARKS_FOLDER_NAME, targets.data / BENCHMARKS_FOLDER_NAME),
        (legacy / SESSION_FILE_NAME, targets.state / SESSION_FILE_NAME),
        (legacy / CATALOG_DB_FILE_NAME, targets.data / CATALOG_DB_FILE_NAME),
    ]
    return [(source, target) for source, target in planned if source.exists()]


@config.command()
def migrate():
    """Move an earlier version's ~/.cis-bench files into the folders this version uses.

    config.toml goes to the config folder, catalog.db and benchmarks/ to the data folder and
    session.cookies to the state folder (XDG base directories, or CIS_BENCH_HOME). Nothing is
    overwritten: an existing destination stops the run before anything moves. Other files in
    the old folder are left where they are; the folder is removed once it is empty.
    """
    legacy = settings_from().folders.legacy
    if legacy is None:
        console.print("Nothing to migrate: this run is not using an earlier version's folder.")
        return

    targets = resolve_folders(use_legacy=False)
    moves = _moves(legacy, targets)
    blocked = [target for _, target in moves if target.exists()]
    if blocked:
        console.print("[red]✗ Not migrating: these already exist and would be overwritten:[/red]")
        for target in blocked:
            console.print(f"  {escape(str(target))}", soft_wrap=True)
        console.print("Move or remove them, then run `cis-bench config migrate` again.")
        sys.exit(1)

    for source, target in moves:
        try:
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.move(source, target)
        except OSError as error:
            # What was moved is listed above; catalog.db moves last, so the old folder is
            # still the one in use and the next run picks up from here.
            console.print(
                f"[red]✗ Could not move {escape(source.name)}: {escape(str(error))}[/red]",
                soft_wrap=True,
            )
            console.print("Fix that, then run `cis-bench config migrate` again to move the rest.")
            sys.exit(1)
        logger.debug(f"Moved {source} to {target}")
        console.print(
            f"[green]✓[/green] {escape(source.name)} -> {escape(str(target))}", soft_wrap=True
        )

    left = sorted(legacy.iterdir())
    if left:
        console.print(f"Left in place in {escape(str(legacy))} (not files this version uses):")
        for path in left:
            console.print(f"  {escape(path.name)}")
    else:
        legacy.rmdir()
        console.print(f"[green]✓[/green] Removed the empty {escape(str(legacy))}", soft_wrap=True)

    console.print(
        f"\ncis-bench now uses {escape(str(targets.config))} for config.toml, "
        f"{escape(str(targets.data))} for catalog.db and benchmarks/, and "
        f"{escape(str(targets.state))} for session.cookies.",
        soft_wrap=True,
    )
