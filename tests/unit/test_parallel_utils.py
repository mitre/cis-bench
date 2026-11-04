"""Tests for parallel execution utilities."""

import threading
import time
from unittest.mock import patch

import pytest

from cis_bench.utils.parallel import (
    ParallelResult,
    iter_batches,
    parallel_execute,
    parallel_execute_batched,
)


def _staggered(delay_per_unit: float):
    """Return a worker whose run time grows with its input, so completion order differs
    from input order whenever the input is not already ascending."""

    def work(x):
        time.sleep(x * delay_per_unit)
        return x * 10

    return work


class _ConcurrencyProbe:
    """Worker that records how many calls were running at once and how many have finished."""

    def __init__(self, hold_seconds: float):
        self.hold_seconds = hold_seconds
        self.active = 0
        self.peak = 0
        self.finished = 0
        self._lock = threading.Lock()

    def __call__(self, x):
        with self._lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        time.sleep(self.hold_seconds)
        with self._lock:
            self.active -= 1
            self.finished += 1
        return x


class TestParallelExecute:
    """Tests for parallel_execute function."""

    def test_parallel_execute_processes_all_items(self):
        """Should process all items and return results."""
        items = [1, 2, 3, 4, 5]
        result = parallel_execute(items, lambda x: x * 2, max_workers=3)

        assert len(result.results) == 5
        assert sorted(result.results) == [2, 4, 6, 8, 10]
        assert result.total == 5
        assert len(result.failed) == 0

    def test_parallel_execute_handles_failures(self):
        """Should continue on failures and track them."""

        def sometimes_fail(x):
            if x == 3:
                raise ValueError("Intentional failure")
            return x * 2

        items = [1, 2, 3, 4, 5]
        result = parallel_execute(items, sometimes_fail, max_workers=3)

        assert len(result.results) == 4
        assert sorted(result.results) == [2, 4, 8, 10]
        assert len(result.failed) == 1
        assert result.failed[0][0] == 3  # Failed item
        assert isinstance(result.failed[0][1], ValueError)  # Error

    def test_parallel_execute_fail_fast(self):
        """Should stop on first error when fail_fast=True."""
        call_count = 0

        def slow_func(x):
            nonlocal call_count
            call_count += 1
            time.sleep(0.1)
            if x == 2:
                raise ValueError("Stop!")
            return x

        items = [1, 2, 3, 4, 5]
        result = parallel_execute(items, slow_func, max_workers=1, fail_fast=True)

        # Should have stopped after item 2 failed
        assert len(result.failed) >= 1
        # Total completed should be less than all items (due to cancellation)
        assert call_count <= 5

    def test_parallel_execute_progress_callback(self):
        """Should call progress callback for each completion."""
        progress_calls = []

        def track_progress(completed, total, item):
            progress_calls.append((completed, total, item))

        items = [1, 2, 3]
        parallel_execute(items, lambda x: x, max_workers=1, progress_callback=track_progress)

        assert len(progress_calls) == 3
        # Check that completed count increases
        completed_counts = [c[0] for c in progress_calls]
        assert sorted(completed_counts) == [1, 2, 3]

    def test_parallel_execute_empty_items(self):
        """Should handle empty input."""
        result = parallel_execute([], lambda x: x)

        assert len(result.results) == 0
        assert result.total == 0
        assert len(result.failed) == 0

    def test_parallel_execute_single_item(self):
        """Should handle single item."""
        result = parallel_execute([42], lambda x: x * 2)

        assert result.results == [84]
        assert result.total == 1

    def test_parallel_execute_is_faster_than_sequential(self):
        """Parallel execution should be faster than sequential for I/O-bound tasks."""

        def slow_task(x):
            time.sleep(0.1)
            return x

        items = list(range(10))

        # Parallel (10 workers for 10 items = ~0.1s)
        start = time.time()
        parallel_execute(items, slow_task, max_workers=10)
        parallel_time = time.time() - start

        # Sequential would take 10 * 0.1 = 1.0s
        # Parallel should take ~0.1-0.2s
        assert parallel_time < 0.5  # Much faster than 1.0s

    def test_results_keep_input_order_when_completion_order_differs(self):
        items = [3, 1, 2]
        result = parallel_execute(items, _staggered(0.05), max_workers=3)

        assert result.results == [30, 10, 20]

    def test_failed_items_keep_input_order_when_completion_order_differs(self):
        def fail_slowly(x):
            time.sleep(x * 0.05)
            raise RuntimeError(f"boom {x}")

        items = [3, 1, 2]
        result = parallel_execute(items, fail_slowly, max_workers=3)

        assert result.results == []
        assert [item for item, _ in result.failed] == [3, 1, 2]
        assert [str(error) for _, error in result.failed] == ["boom 3", "boom 1", "boom 2"]

    def test_progress_callback_reports_each_item_once_in_completion_order(self):
        progress_calls = []

        def track_progress(completed, total, item):
            progress_calls.append((completed, total, item))

        parallel_execute(
            [3, 1, 2], _staggered(0.05), max_workers=3, progress_callback=track_progress
        )

        assert progress_calls == [(1, 3, 1), (2, 3, 2), (3, 3, 3)]

    def test_fail_fast_stops_the_run_at_the_first_failure(self):
        started = []

        def work(x):
            started.append(x)
            time.sleep(0.1)
            if x == 2:
                raise ValueError("stop")
            return x

        result = parallel_execute([1, 2, 3, 4, 5], work, max_workers=1, fail_fast=True)

        assert result.results == [1]
        assert [item for item, _ in result.failed] == [2]
        assert result.total == 5
        # Item 3 may already be running when item 2 fails; items 4 and 5 never start.
        assert started[:2] == [1, 2]
        assert len(started) <= 3

    @pytest.mark.parametrize("workers", [0, -1])
    def test_rejects_worker_count_below_one(self, workers):
        with pytest.raises(ValueError, match="max_workers"):
            parallel_execute([1, 2], lambda x: x, max_workers=workers)

    def test_default_worker_count_is_paced_not_unbounded(self):
        probe = _ConcurrencyProbe(hold_seconds=0.05)

        parallel_execute(list(range(12)), probe)

        assert 2 <= probe.peak <= 5


class TestParallelExecuteBatched:
    """Tests for parallel_execute_batched function."""

    def test_batched_processes_all_items(self):
        """Should process all items across batches."""
        items = list(range(25))
        result = parallel_execute_batched(
            items, lambda x: x * 2, batch_size=10, max_workers=5, batch_delay=0.0
        )

        assert len(result.results) == 25
        assert result.total == 25

    def test_batched_applies_delay_between_batches(self):
        """Should delay between batches."""
        items = list(range(20))

        start = time.time()
        parallel_execute_batched(items, lambda x: x, batch_size=10, max_workers=10, batch_delay=0.1)
        elapsed = time.time() - start

        # With 2 batches and 0.1s delay between, should take at least 0.1s
        assert elapsed >= 0.1

    def test_batched_progress_callback_counts_correctly(self):
        """Progress callback should count across all batches."""
        progress_calls = []

        def track_progress(completed, total, item):
            progress_calls.append((completed, total))

        items = list(range(25))
        parallel_execute_batched(
            items,
            lambda x: x,
            batch_size=10,
            max_workers=5,
            batch_delay=0.0,
            progress_callback=track_progress,
        )

        assert len(progress_calls) == 25
        # Total should always be 25
        assert all(p[1] == 25 for p in progress_calls)
        # Final completed should be 25
        assert max(p[0] for p in progress_calls) == 25

    def test_batched_sleeps_only_between_batches(self):
        with patch("cis_bench.utils.parallel.time.sleep") as sleep:
            parallel_execute_batched(
                list(range(12)), lambda x: x, batch_size=5, max_workers=5, batch_delay=0.5
            )

        # 12 items in batches of 5 -> 3 batches -> 2 gaps; never after the last batch
        assert sleep.call_args_list == [((0.5,),), ((0.5,),)]

    def test_batched_defaults_match_catalog_refresh_pacing(self):
        probe = _ConcurrencyProbe(hold_seconds=0.02)
        finished_at_each_pause = []

        # Replace only the module's own clock so the workers' sleeps stay real.
        with patch("cis_bench.utils.parallel.time") as clock:
            clock.sleep.side_effect = lambda _seconds: finished_at_each_pause.append(probe.finished)
            result = parallel_execute_batched(list(range(25)), probe)

        assert result.results == list(range(25))
        # Batches of ten: the pauses fall after the 10th and 20th item, never after the last.
        assert finished_at_each_pause == [10, 20]
        assert clock.sleep.call_args_list == [((2.0,),), ((2.0,),)]
        # Five workers per batch.
        assert 2 <= probe.peak <= 5

    def test_batched_results_keep_input_order_across_batches(self):
        items = [3, 1, 2, 6, 4, 5]
        result = parallel_execute_batched(
            items, _staggered(0.02), batch_size=3, max_workers=3, batch_delay=0.0
        )

        assert result.results == [30, 10, 20, 60, 40, 50]

    @pytest.mark.parametrize("workers", [0, -1])
    def test_batched_rejects_worker_count_below_one(self, workers):
        with pytest.raises(ValueError, match="max_workers"):
            parallel_execute_batched([1, 2], lambda x: x, max_workers=workers)

    @pytest.mark.parametrize("size", [0, -1])
    def test_batched_rejects_batch_size_below_one(self, size):
        with pytest.raises(ValueError, match="batch_size"):
            parallel_execute_batched([1, 2], lambda x: x, batch_size=size)

    def test_batched_rejects_negative_delay(self):
        with pytest.raises(ValueError, match="batch_delay"):
            parallel_execute_batched([1, 2], lambda x: x, batch_delay=-0.1)


class _StopRun(Exception):
    """A failure after which no further batch should start."""


class TestParallelExecuteBatchedStopOn:
    """parallel_execute_batched(stop_on=...) ends the run after a batch with a fatal failure."""

    def test_a_stop_on_failure_starts_no_further_batch(self):
        started = []
        lock = threading.Lock()

        def work(x):
            with lock:
                started.append(x)
            if x == 3:
                raise _StopRun("session expired")
            return x

        with patch("cis_bench.utils.parallel.time") as clock:
            result = parallel_execute_batched(
                list(range(25)), work, batch_size=10, max_workers=5, stop_on=(_StopRun,)
            )

        assert sorted(started) == list(range(10))  # only the first batch ran
        assert result.results == [0, 1, 2, 4, 5, 6, 7, 8, 9]
        assert [item for item, _ in result.failed] == [3]
        assert isinstance(result.failed[0][1], _StopRun)
        assert result.total == 25
        clock.sleep.assert_not_called()  # no pause before a batch that will never run

    def test_an_ordinary_failure_does_not_stop_the_run(self):
        def work(x):
            if x == 3:
                raise ValueError("one bad item")
            return x

        with patch("cis_bench.utils.parallel.time"):
            result = parallel_execute_batched(
                list(range(25)), work, batch_size=10, max_workers=5, stop_on=(_StopRun,)
            )

        assert len(result.results) == 24
        assert [item for item, _ in result.failed] == [3]

    def test_a_subclass_of_a_stop_on_type_also_stops_the_run(self):
        class _SessionExpired(_StopRun):
            pass

        def work(x):
            if x == 0:
                raise _SessionExpired("login page")
            return x

        with patch("cis_bench.utils.parallel.time"):
            result = parallel_execute_batched(
                list(range(25)), work, batch_size=10, max_workers=5, stop_on=(_StopRun,)
            )

        assert len(result.results) + len(result.failed) == 10


class TestIterBatches:
    """iter_batches yields each batch's result on the calling thread before starting the next."""

    def test_yields_one_result_per_batch_in_order(self):
        with patch("cis_bench.utils.parallel.time"):
            batches = list(iter_batches(list(range(12)), lambda x: x * 10, batch_size=5))

        assert [b.results for b in batches] == [
            [0, 10, 20, 30, 40],
            [50, 60, 70, 80, 90],
            [100, 110],
        ]
        assert [b.total for b in batches] == [5, 5, 2]
        assert all(b.failed == [] for b in batches)

    def test_a_failure_is_reported_in_its_own_batch(self):
        def work(x):
            if x == 6:
                raise ValueError("bad item")
            return x

        with patch("cis_bench.utils.parallel.time"):
            batches = list(iter_batches(list(range(12)), work, batch_size=5))

        assert [[item for item, _ in b.failed] for b in batches] == [[], [6], []]

    def test_pauses_before_each_later_batch_only(self):
        with patch("cis_bench.utils.parallel.time") as clock:
            batches = iter_batches(list(range(12)), lambda x: x, batch_size=5, batch_delay=0.5)
            next(batches)
            clock.sleep.assert_not_called()  # no pause before the first batch
            next(batches)
            assert clock.sleep.call_args_list == [((0.5,),)]
            next(batches)
            assert clock.sleep.call_args_list == [((0.5,),), ((0.5,),)]
            assert next(batches, None) is None
        assert clock.sleep.call_count == 2  # never after the last batch

    def test_a_consumer_that_stops_starts_no_further_batch_and_waits_no_pause(self):
        started = []
        lock = threading.Lock()

        def work(x):
            with lock:
                started.append(x)
            return x

        with patch("cis_bench.utils.parallel.time") as clock:
            for _batch in iter_batches(list(range(25)), work, batch_size=10):
                break

        assert sorted(started) == list(range(10))
        clock.sleep.assert_not_called()

    def test_progress_counts_across_batches(self):
        calls = []
        with patch("cis_bench.utils.parallel.time"):
            for _batch in iter_batches(
                list(range(12)),
                lambda x: x,
                batch_size=5,
                progress_callback=lambda done, total, item: calls.append((done, total)),
            ):
                pass

        assert [done for done, _ in calls] == list(range(1, 13))
        assert {total for _, total in calls} == {12}

    @pytest.mark.parametrize(
        "kwargs",
        [{"batch_size": 0}, {"max_workers": 0}, {"batch_delay": -1.0}],
        ids=["batch_size", "max_workers", "batch_delay"],
    )
    def test_invalid_arguments_raise_when_called_not_when_iterated(self, kwargs):
        with pytest.raises(ValueError):
            iter_batches([1, 2], lambda x: x, **kwargs)


class TestBatchDelayValidation:
    """A batch pause must be a finite, non-negative number of seconds."""

    @pytest.mark.parametrize("delay", [float("nan"), float("inf"), float("-inf"), -0.5])
    def test_iter_batches_rejects_a_non_finite_or_negative_delay(self, delay):
        with pytest.raises(ValueError, match="batch_delay"):
            iter_batches([1, 2], lambda x: x, batch_delay=delay)

    @pytest.mark.parametrize("delay", [float("nan"), float("inf")])
    def test_parallel_execute_batched_rejects_a_non_finite_delay(self, delay):
        with pytest.raises(ValueError, match="batch_delay"):
            parallel_execute_batched([1, 2], lambda x: x, batch_delay=delay)


class TestParallelResult:
    """Tests for ParallelResult dataclass."""

    def test_parallel_result_attributes(self):
        """Should have expected attributes."""
        result = ParallelResult(results=[1, 2, 3], failed=[(4, "error")], total=4)

        assert result.results == [1, 2, 3]
        assert result.failed == [(4, "error")]
        assert result.total == 4
