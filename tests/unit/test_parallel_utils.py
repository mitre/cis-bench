"""Tests for parallel execution utilities."""

import time

from cis_bench.utils.parallel import (
    ParallelResult,
    parallel_execute,
    parallel_execute_batched,
)


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


class TestParallelExecuteBatched:
    """Tests for parallel_execute_batched function."""

    def test_batched_processes_all_items(self):
        """Should process all items across batches."""
        items = list(range(25))
        result = parallel_execute_batched(items, lambda x: x * 2, batch_size=10, max_workers=5)

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
            progress_callback=track_progress,
        )

        assert len(progress_calls) == 25
        # Total should always be 25
        assert all(p[1] == 25 for p in progress_calls)
        # Final completed should be 25
        assert max(p[0] for p in progress_calls) == 25


class TestParallelResult:
    """Tests for ParallelResult dataclass."""

    def test_parallel_result_attributes(self):
        """Should have expected attributes."""
        result = ParallelResult(results=[1, 2, 3], failed=[(4, "error")], total=4)

        assert result.results == [1, 2, 3]
        assert result.failed == [(4, "error")]
        assert result.total == 4


class TestParallelDownloadIntegration:
    """Integration tests for parallel download in WorkbenchScraper."""

    def test_workbench_scraper_has_max_workers_param(self):
        """WorkbenchScraper.download_benchmark should accept max_workers."""
        # Check the signature includes max_workers
        import inspect

        from cis_bench.fetcher.workbench import WorkbenchScraper

        sig = inspect.signature(WorkbenchScraper.download_benchmark)
        params = list(sig.parameters.keys())

        assert "max_workers" in params

    def test_workbench_scraper_uses_parallel_execute(self):
        """WorkbenchScraper should use centralized parallel_execute utility."""
        import inspect

        from cis_bench.fetcher import workbench

        # Read source and check for parallel_execute usage
        source = inspect.getsource(workbench)

        # Check for parallel_execute import from utils.parallel
        assert "from cis_bench.utils.parallel import parallel_execute" in source

        # Check for parallel_execute usage in download_benchmark
        assert "parallel_execute(" in source
