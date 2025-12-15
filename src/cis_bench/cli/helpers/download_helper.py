"""Helper functions for download operations with progress bars."""

import logging
import re

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn

logger = logging.getLogger(__name__)


def download_with_progress(scraper, url, prefix=""):
    """Download benchmark with Rich progress bar.

    Args:
        scraper: WorkbenchScraper instance
        url: Benchmark URL to download
        prefix: Optional prefix for messages (e.g., "[1/3]")

    Returns:
        Benchmark object

    Example:
        scraper = WorkbenchScraper(session)
        benchmark = download_with_progress(scraper, url, prefix="[1/1]")
    """
    console = Console()

    progress_bar = None
    progress_task = None
    benchmark_title = None

    def progress_callback(msg):
        nonlocal progress_bar, progress_task, benchmark_title

        if "Benchmark title:" in msg:
            # Extract and show title
            benchmark_title = msg.split("Benchmark title:", 1)[1].strip()
            console.print(f"{prefix}{benchmark_title}", highlight=False)
        elif "Found" in msg and "recommendations" in msg:
            # Extract total and create progress bar
            match = re.search(r"Found (\d+) recommendations", msg)
            if match:
                total = int(match.group(1))
                progress_bar = Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                    TextColumn("({task.completed}/{task.total})"),
                    TimeRemainingColumn(),
                )
                progress_bar.start()
                progress_task = progress_bar.add_task(
                    f"{prefix} Downloading {total} recommendations", total=total
                )
        elif msg.startswith("["):
            # Update progress bar
            match = re.search(r"\[(\d+)/(\d+)\]", msg)
            if match and progress_bar and progress_task is not None:
                current = int(match.group(1))
                progress_bar.update(progress_task, completed=current)

    # Download with progress callback
    logger.debug(f"Starting download: {url}")
    benchmark = scraper.download_benchmark(url, progress_callback=progress_callback)

    # Stop progress bar if created
    if progress_bar:
        progress_bar.stop()

    logger.debug(f"Download complete: {benchmark.title}")
    return benchmark
