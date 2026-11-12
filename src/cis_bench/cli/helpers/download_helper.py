"""Download a benchmark with a Rich progress bar."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from gettext import ngettext
from typing import TYPE_CHECKING

from rich.console import Console
from rich.markup import escape
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn

if TYPE_CHECKING:
    from cis_bench.fetcher.workbench import WorkbenchScraper
    from cis_bench.models.benchmark import Benchmark

logger = logging.getLogger(__name__)


@contextmanager
def scraper_progress(
    prefix: str = "", console: Console | None = None
) -> Iterator[Callable[[str], None]]:
    """A callback for the scraper's progress messages that draws them as a progress bar.

    Prints the benchmark's title, then a bar over its recommendations. The bar is stopped
    when the block ends, whether the download finished or raised.
    """
    console = console or Console()
    progress_bar: Progress | None = None
    progress_task = None

    def on_message(msg: str) -> None:
        nonlocal progress_bar, progress_task

        if "Benchmark title:" in msg:
            title = msg.split("Benchmark title:", 1)[1].strip()
            console.print(f"{prefix} {escape(title)}", highlight=False)
        elif match := re.search(r"Found (\d+) recommendations?\b", msg):
            total = int(match.group(1))
            progress_bar = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TextColumn("({task.completed}/{task.total})"),
                TimeRemainingColumn(),
                console=console,
            )
            progress_bar.start()
            downloading = ngettext(
                "Downloading {count} recommendation", "Downloading {count} recommendations", total
            ).format(count=total)
            progress_task = progress_bar.add_task(f"{prefix} {downloading}", total=total)
        elif match := re.match(r"\[(\d+)/(\d+)\]", msg):
            if progress_bar and progress_task is not None:
                progress_bar.update(progress_task, completed=int(match.group(1)))

    try:
        yield on_message
    finally:
        if progress_bar:
            progress_bar.stop()


def download_with_progress(
    scraper: WorkbenchScraper, url: str, prefix: str = "", console: Console | None = None
) -> Benchmark:
    """Download a benchmark from WorkBench with a progress bar on the given console.

    The caller caches it with CatalogDownloader.cache.
    """
    logger.debug(f"Starting download: {url}")
    with scraper_progress(prefix, console) as on_message:
        benchmark = scraper.download_benchmark(url, progress_callback=on_message)
    logger.debug(f"Download complete: {benchmark.title}")
    return benchmark
