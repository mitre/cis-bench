"""Shared utilities for CLI commands."""

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
from io import StringIO
from pathlib import Path

import click
from rich.console import Console

from cis_bench.catalog.database import CatalogDatabase
from cis_bench.config import Config

console = Console()
logger = logging.getLogger(__name__)


def get_pager() -> str | None:
    """Get the pager command to use.

    Checks PAGER environment variable first, then falls back to less -R or more.
    """
    pager = os.environ.get("PAGER")
    if pager:
        return pager
    if shutil.which("less"):
        return "less -R"
    if shutil.which("more"):
        return "more"
    return None


def output_with_pager(output_func, *args, **kwargs) -> None:
    """Run output function, piping through pager if stdout is TTY and output is long.

    Args:
        output_func: Function that outputs to console. Must accept _console kwarg.
        *args, **kwargs: Arguments to pass to output_func.
    """
    if not sys.stdout.isatty():
        output_func(*args, **kwargs)
        return

    pager = get_pager()
    if not pager:
        output_func(*args, **kwargs)
        return

    # Capture output
    string_io = StringIO()
    capture_console = Console(file=string_io, force_terminal=True, width=console.width)
    output_func(*args, _console=capture_console, **kwargs)
    output = string_io.getvalue()

    # Get terminal height
    terminal_height = shutil.get_terminal_size().lines
    output_lines = output.count("\n") + 1

    if output_lines <= terminal_height - 2:
        print(output, end="")
        return

    try:
        process = subprocess.Popen(  # noqa: S602
            pager,
            stdin=subprocess.PIPE,
            shell=True,
        )
        process.communicate(input=output.encode())
    except Exception:
        print(output, end="")


def auto_fetch_benchmark(benchmark_id: str) -> dict | None:
    """Attempt to fetch a benchmark from CIS WorkBench.

    Args:
        benchmark_id: The benchmark ID to fetch.

    Returns:
        Benchmark data dict if successful.

    Raises:
        click.ClickException: If authentication fails or other errors.
    """
    from cis_bench.fetcher.auth import AuthManager
    from cis_bench.fetcher.workbench import WorkbenchScraper

    console.print(f"[cyan]Fetching benchmark {benchmark_id} from CIS WorkBench...[/cyan]")

    try:
        session = AuthManager.get_or_create_session()
    except ValueError as e:
        raise click.ClickException(
            f"Benchmark '{benchmark_id}' not found locally.\n\n"
            "To fetch from CIS WorkBench, authenticate first:\n"
            "  cis-bench auth login --browser chrome\n\n"
            "Or provide a local file path."
        ) from e
    except Exception as e:
        raise click.ClickException(
            f"Authentication failed: {e}\n\n"
            "Your session may have expired. Try:\n"
            "  cis-bench auth login --browser chrome"
        ) from e

    scraper = WorkbenchScraper(session)
    url = f"https://workbench.cisecurity.org/benchmarks/{benchmark_id}"

    try:
        from cis_bench.cli.helpers.download_helper import download_with_progress

        benchmark = download_with_progress(scraper, url, prefix="")

        # Save to catalog database
        catalog_db_path = Config.get_catalog_db_path()
        if catalog_db_path.exists():
            try:
                content_json = benchmark.model_dump_json()
                content_hash = hashlib.sha256(content_json.encode()).hexdigest()
                recommendation_count = len(benchmark.recommendations)

                db = CatalogDatabase(catalog_db_path)
                db.save_downloaded(
                    benchmark_id=benchmark_id,
                    content_json=content_json,
                    content_hash=content_hash,
                    recommendation_count=recommendation_count,
                )
                console.print(f"[green]✓[/green] Cached benchmark {benchmark_id}")
            except Exception as e:
                logger.warning(f"Failed to cache benchmark: {e}")

        return json.loads(benchmark.model_dump_json())

    except Exception as e:
        logger.error(f"Failed to fetch benchmark {benchmark_id}: {e}")
        raise click.ClickException(f"Failed to fetch benchmark '{benchmark_id}': {e}") from e


def load_benchmark(identifier: str, offline: bool = False) -> dict:
    """Load benchmark from ID or file path.

    Args:
        identifier: Benchmark ID, URL, or file path.
        offline: If True, don't attempt to fetch from CIS WorkBench.

    Returns:
        Benchmark data as dict.

    Raises:
        FileNotFoundError: If benchmark not found locally and offline=True.
        click.ClickException: If auto-fetch fails.
    """
    # Try as file path first
    path = Path(identifier)
    if path.exists() and path.is_file():
        with open(path) as f:
            return json.load(f)

    # Try as benchmark ID from database
    db_path = Config.get_catalog_db_path()
    if db_path.exists():
        db = CatalogDatabase(db_path)
        downloaded = db.get_downloaded(identifier)
        if downloaded and downloaded.get("content_json"):
            return json.loads(downloaded["content_json"])

    # Try as file in benchmarks directory
    benchmarks_dir = Config.get_benchmarks_dir()
    json_file = benchmarks_dir / f"{identifier}.json"
    if json_file.exists():
        with open(json_file) as f:
            return json.load(f)

    # Not found locally - try auto-fetch if online mode
    if offline:
        raise FileNotFoundError(
            f"Benchmark '{identifier}' not found locally.\n\n"
            "In offline mode, benchmarks must be pre-downloaded.\n"
            "Remove --offline flag to auto-fetch from CIS WorkBench."
        )

    logger.info(f"Benchmark {identifier} not cached, attempting to fetch from WorkBench")
    return auto_fetch_benchmark(identifier)
