"""Parallel execution utilities for batch operations.

Provides a centralized ThreadPoolExecutor pattern used for:
- Catalog scraping (multiple pages)
- Benchmark downloading (multiple recommendations)
- Any batch I/O-bound operations
"""

import logging
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")  # Input type
R = TypeVar("R")  # Result type


@dataclass
class ParallelResult:
    """Result of parallel execution."""

    results: list  # Successful results
    failed: list  # Failed items (item, error) tuples
    total: int  # Total items processed


def parallel_execute(
    items: Iterable[T],
    func: Callable[[T], R],
    max_workers: int = 10,
    progress_callback: Callable[[int, int, T], None] | None = None,
    fail_fast: bool = False,
) -> ParallelResult:
    """Execute a function on multiple items in parallel.

    Uses ThreadPoolExecutor for I/O-bound operations like HTTP requests.

    Args:
        items: Items to process
        func: Function to apply to each item. Should return result or raise.
        max_workers: Number of parallel threads (default: 10)
        progress_callback: Called with (completed, total, current_item) for each completion
        fail_fast: If True, stop on first error (default: False, continue on errors)

    Returns:
        ParallelResult with successful results and failed items

    Example:
        def fetch_page(url):
            return requests.get(url).text

        urls = ["http://example.com/1", "http://example.com/2"]
        result = parallel_execute(urls, fetch_page, max_workers=5)
        print(f"Got {len(result.results)} pages, {len(result.failed)} failed")
    """
    items_list = list(items)
    total = len(items_list)
    results = []
    failed = []
    completed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_item = {executor.submit(func, item): item for item in items_list}

        # Process as they complete
        for future in as_completed(future_to_item):
            item = future_to_item[future]
            completed += 1

            try:
                result = future.result()
                results.append(result)

                if progress_callback:
                    progress_callback(completed, total, item)

            except Exception as e:
                failed.append((item, e))
                logger.debug(f"Parallel task failed for {item}: {e}")

                if progress_callback:
                    progress_callback(completed, total, item)

                if fail_fast:
                    # Cancel remaining futures
                    for f in future_to_item:
                        f.cancel()
                    break

    return ParallelResult(results=results, failed=failed, total=total)


def parallel_execute_batched(
    items: Iterable[T],
    func: Callable[[T], R],
    batch_size: int = 10,
    max_workers: int = 5,
    batch_delay: float = 0.0,
    progress_callback: Callable[[int, int, T], None] | None = None,
) -> ParallelResult:
    """Execute function on items in batches with optional delay between batches.

    Useful when rate limiting is needed between groups of requests.

    Args:
        items: Items to process
        func: Function to apply to each item
        batch_size: Number of items per batch (default: 10)
        max_workers: Threads per batch (default: 5)
        batch_delay: Seconds to wait between batches (default: 0)
        progress_callback: Called with (completed, total, current_item) for each completion

    Returns:
        ParallelResult with all results combined

    Example:
        # Process 100 URLs in batches of 10, with 2s delay between batches
        result = parallel_execute_batched(
            urls, fetch_page,
            batch_size=10, max_workers=5, batch_delay=2.0
        )
    """
    import time

    items_list = list(items)
    total = len(items_list)
    all_results = []
    all_failed = []
    completed = 0

    for batch_start in range(0, total, batch_size):
        batch = items_list[batch_start : batch_start + batch_size]

        # Track progress across batches
        def batch_progress(batch_completed, batch_total, item):
            nonlocal completed
            completed += 1
            if progress_callback:
                progress_callback(completed, total, item)

        # Execute batch
        batch_result = parallel_execute(
            batch,
            func,
            max_workers=max_workers,
            progress_callback=batch_progress if progress_callback else None,
        )

        all_results.extend(batch_result.results)
        all_failed.extend(batch_result.failed)

        # Delay between batches (but not after the last batch)
        if batch_delay > 0 and batch_start + batch_size < total:
            time.sleep(batch_delay)

    return ParallelResult(results=all_results, failed=all_failed, total=total)
