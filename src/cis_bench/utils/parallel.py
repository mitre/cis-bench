"""Run one function over many items on a bounded thread pool.

Used for I/O-bound work such as fetching many WorkBench pages. Results come back in
input order whatever order the workers finish in, and every failure is returned to the
caller instead of being raised or dropped.
"""

import logging
import math
import time
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Pacing shared with the catalog refresh: five concurrent requests, then a two second pause.
DEFAULT_MAX_WORKERS = 5
DEFAULT_BATCH_SIZE = 10
DEFAULT_BATCH_DELAY_SECONDS = 2.0

type ProgressCallback[T] = Callable[[int, int, T], None]


@dataclass
class ParallelResult[T, R]:
    """Outcome of a parallel run.

    ``results`` holds the return values of the calls that succeeded, in input order.
    ``failed`` holds ``(item, exception)`` pairs for the calls that raised, in input order.
    ``total`` is the number of items given; with ``fail_fast`` or ``stop_on`` it may exceed
    ``len(results) + len(failed)`` because the remaining items never ran.
    """

    results: list[R]
    failed: list[tuple[T, Exception]]
    total: int


def _require_at_least_one(name: str, value: int) -> None:
    if value < 1:
        raise ValueError(f"{name} must be at least 1, got {value}")


def parallel_execute[T, R](
    items: Iterable[T],
    func: Callable[[T], R],
    max_workers: int = DEFAULT_MAX_WORKERS,
    progress_callback: ProgressCallback[T] | None = None,
    fail_fast: bool = False,
) -> ParallelResult[T, R]:
    """Call ``func`` on every item using up to ``max_workers`` threads.

    ``progress_callback`` is called once per finished item, in completion order, with
    ``(completed, total, item)``. An exception raised by ``func`` is recorded in
    ``failed`` and the other items still run, unless ``fail_fast`` is set, in which case
    the items not yet started are cancelled.
    """
    _require_at_least_one("max_workers", max_workers)
    items_list = list(items)
    total = len(items_list)
    outcomes: dict[int, R] = {}
    failures: dict[int, Exception] = {}
    completed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {
            executor.submit(func, item): index for index, item in enumerate(items_list)
        }

        for future in as_completed(future_to_index):
            index = future_to_index[future]
            item = items_list[index]
            completed += 1
            try:
                outcomes[index] = future.result()
            except Exception as error:
                failures[index] = error
                logger.debug(f"Parallel task failed for {item}: {error}")

            if progress_callback:
                progress_callback(completed, total, item)

            if fail_fast and failures:
                for pending in future_to_index:
                    pending.cancel()
                break

    return ParallelResult(
        results=[outcomes[index] for index in sorted(outcomes)],
        failed=[(items_list[index], failures[index]) for index in sorted(failures)],
        total=total,
    )


def check_batch_delay(batch_delay: float, name: str = "batch_delay") -> None:
    """Raise ValueError unless batch_delay is a finite number of seconds, zero or more.

    NaN would silently skip every pause and infinity would sleep forever, so both are refused
    along with negative values. ``name`` is the caller's parameter name for the message.
    """
    if not math.isfinite(batch_delay) or batch_delay < 0:
        raise ValueError(f"{name} must be a finite number of seconds >= 0, got {batch_delay}")


def _check_batch_arguments(batch_size: int, max_workers: int, batch_delay: float) -> None:
    _require_at_least_one("batch_size", batch_size)
    _require_at_least_one("max_workers", max_workers)
    check_batch_delay(batch_delay)


def iter_batches[T, R](
    items: Iterable[T],
    func: Callable[[T], R],
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_workers: int = DEFAULT_MAX_WORKERS,
    batch_delay: float = DEFAULT_BATCH_DELAY_SECONDS,
    progress_callback: ProgressCallback[T] | None = None,
) -> Iterator[ParallelResult[T, R]]:
    """Run ``parallel_execute`` over consecutive slices of ``items``, yielding each slice's result.

    Each batch runs to completion before it is yielded, on the calling thread, so the caller can
    act on it (for example write it to a database that only one thread may use) before the next
    batch starts. The pause of ``batch_delay`` seconds comes before each later batch, so a caller
    that stops iterating starts no further batch and waits no pause. ``progress_callback`` counts
    across the whole run. Arguments are checked when this is called, not on first iteration.
    """
    _check_batch_arguments(batch_size, max_workers, batch_delay)
    return _run_batches(list(items), func, batch_size, max_workers, batch_delay, progress_callback)


def _run_batches[T, R](
    items_list: list[T],
    func: Callable[[T], R],
    batch_size: int,
    max_workers: int,
    batch_delay: float,
    progress_callback: ProgressCallback[T] | None,
) -> Iterator[ParallelResult[T, R]]:
    total = len(items_list)
    completed = 0

    def overall_progress(_batch_completed: int, _batch_total: int, item: T) -> None:
        nonlocal completed
        completed += 1
        if progress_callback:
            progress_callback(completed, total, item)

    for batch_start in range(0, total, batch_size):
        if batch_start > 0 and batch_delay > 0:
            time.sleep(batch_delay)
        yield parallel_execute(
            items_list[batch_start : batch_start + batch_size],
            func,
            max_workers=max_workers,
            progress_callback=overall_progress if progress_callback else None,
        )


def parallel_execute_batched[T, R](
    items: Iterable[T],
    func: Callable[[T], R],
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_workers: int = DEFAULT_MAX_WORKERS,
    batch_delay: float = DEFAULT_BATCH_DELAY_SECONDS,
    progress_callback: ProgressCallback[T] | None = None,
    stop_on: tuple[type[Exception], ...] = (),
) -> ParallelResult[T, R]:
    """Run every batch from ``iter_batches`` and combine the results.

    Items within a batch run concurrently; the run pauses ``batch_delay`` seconds between
    batches and never after the last one. The defaults match the catalog refresh pacing.
    ``progress_callback`` counts across the whole run, not per batch.

    When a batch records a failure that is an instance of one of the ``stop_on`` types, the
    rest of that batch still finishes but no further batch starts; the failure is returned
    in ``failed`` like any other, and the caller decides what it means. Use it for failures
    after which every remaining item would fail too, such as an expired login.
    """
    items_list = list(items)
    all_results: list[R] = []
    all_failed: list[tuple[T, Exception]] = []
    for batch in iter_batches(
        items_list, func, batch_size, max_workers, batch_delay, progress_callback
    ):
        all_results.extend(batch.results)
        all_failed.extend(batch.failed)
        if stop_on and any(isinstance(error, stop_on) for _, error in batch.failed):
            break

    return ParallelResult(results=all_results, failed=all_failed, total=len(items_list))
