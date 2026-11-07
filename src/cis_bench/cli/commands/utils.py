"""Shared helpers for the terminal-UI commands (browse, view, tui)."""

import json
import logging
import re
import shutil
import sys
from collections.abc import Callable
from io import StringIO
from pathlib import Path
from typing import Any

import click
from rich.console import Console

from cis_bench.catalog.database import CatalogDatabase
from cis_bench.catalog.downloader import CatalogDownloader
from cis_bench.cli.helpers.services import auth_manager, workbench_scraper
from cis_bench.config import Settings
from cis_bench.exceptions import AuthenticationError, CISBenchError, NoSavedSessionError
from cis_bench.utils.workbench_urls import is_benchmark_id

console = Console()
logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int, str], None]


def output_with_pager(output_func: Callable[..., None], *args: Any, **kwargs: Any) -> None:
    """Print output_func's output, through the system pager when it is longer than the terminal.

    output_func takes the console to print to as ``_console``. Off a terminal it prints
    straight to stdout. In a terminal, output that fits is printed as it is; longer output
    goes through Rich's pager, which is pydoc's: it honours ``MANPAGER`` and ``PAGER`` and
    falls back to ``less``.
    """
    if not sys.stdout.isatty():
        output_func(*args, _console=console, **kwargs)
        return

    rendered = StringIO()
    output_func(
        *args,
        _console=Console(file=rendered, force_terminal=True, width=console.width),
        **kwargs,
    )
    text = rendered.getvalue()
    if text.count("\n") + 1 <= shutil.get_terminal_size().lines - 2:
        print(text, end="")
        return

    with console.pager():
        output_func(*args, _console=console, **kwargs)


def _scraper_progress(progress_callback: ProgressCallback) -> Callable[[str], None]:
    """Turn the scraper's progress messages into (current, total, message) steps."""

    def on_message(message: str) -> None:
        if "Benchmark title:" in message:
            title = message.split("Benchmark title:", 1)[1].strip()
            progress_callback(0, 0, f"Loading: {title[:40]}...")
        elif match := re.search(r"Found (\d+) recommendations", message):
            total = int(match.group(1))
            progress_callback(0, total, f"Downloading {total} recommendations...")
        elif match := re.match(r"\[(\d+)/(\d+)\]", message):
            current, total = int(match.group(1)), int(match.group(2))
            progress_callback(current, total, f"[{current}/{total}] Processing...")

    return on_message


def auto_fetch_benchmark(
    benchmark_id: str,
    settings: Settings,
    progress_callback: ProgressCallback | None = None,
    silent: bool = False,
) -> dict:
    """Download a catalog benchmark into the cache, as ``download`` does, and return it.

    Args:
        benchmark_id: A catalog ID.
        settings: The run's settings.
        progress_callback: Receives (current, total, message) steps while it downloads.
        silent: No console output (the TUI shows its own progress).

    Raises:
        click.ClickException: Not logged in, the session was rejected, the ID is not in the
            catalog, or WorkBench could not be read.
    """
    if not silent:
        console.print(f"[cyan]Fetching benchmark {benchmark_id} from CIS WorkBench...[/cyan]")

    try:
        session = auth_manager(settings).get_or_create_session()
    except NoSavedSessionError as error:
        raise click.ClickException(
            f"Benchmark {benchmark_id} is not downloaded, and downloading it needs a login:\n"
            "  cis-bench auth login --browser chrome"
        ) from error
    except AuthenticationError as error:
        raise click.ClickException(
            f"WorkBench did not accept the saved session ({error}). Log in again:\n"
            "  cis-bench auth login --browser chrome"
        ) from error

    db = CatalogDatabase(settings.catalog_db_path)
    downloader = CatalogDownloader(db, workbench_scraper(settings, session))
    try:
        downloader.download_by_id(
            benchmark_id,
            progress_callback=_scraper_progress(progress_callback) if progress_callback else None,
        )
    except (ValueError, CISBenchError) as error:
        raise click.ClickException(
            f"Could not download benchmark {benchmark_id}: {error}"
        ) from error

    downloaded = db.get_downloaded(benchmark_id)
    if downloaded is None:
        raise click.ClickException(f"Benchmark {benchmark_id} was downloaded but is not cached")
    if not silent:
        console.print(f"[green]✓[/green] Downloaded and cached benchmark {benchmark_id}")
    data: dict = json.loads(downloaded["content_json"])
    return data


def load_benchmark(
    identifier: str,
    settings: Settings,
    *,
    offline: bool = False,
    progress_callback: ProgressCallback | None = None,
    silent: bool = False,
) -> dict:
    """A benchmark as a dict, by catalog ID or file path, the way the CLI resolves them.

    Digits are a catalog ID: the cached copy is used, and one that is not cached is
    downloaded into the cache first (unless offline). Anything else is a benchmark JSON file.

    Raises:
        FileNotFoundError: The file does not exist, or the ID is not cached and offline is set.
        click.ClickException: Downloading the benchmark failed.
    """
    if not is_benchmark_id(identifier):
        path = Path(identifier)
        if not path.is_file():
            raise FileNotFoundError(f"No benchmark file {identifier}")
        data: dict = json.loads(path.read_text())
        return data

    benchmark_id = identifier.strip()
    if settings.catalog_db_path.exists():
        downloaded = CatalogDatabase(settings.catalog_db_path).get_downloaded(benchmark_id)
        if downloaded is not None:
            cached: dict = json.loads(downloaded["content_json"])
            return cached

    if offline:
        raise FileNotFoundError(
            f"Benchmark {benchmark_id} is not downloaded, and offline mode does not download it"
        )

    logger.debug(f"Benchmark {benchmark_id} is not cached; downloading it")
    return auto_fetch_benchmark(
        benchmark_id, settings, progress_callback=progress_callback, silent=silent
    )
