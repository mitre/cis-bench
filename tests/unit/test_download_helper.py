"""Tests for download helper with progress bar."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from cis_bench.models.benchmark import Benchmark, Recommendation


@pytest.fixture
def sample_benchmark():
    """Create a sample benchmark for testing."""
    return Benchmark(
        title="CIS Test Benchmark",
        benchmark_id="12345",
        url="https://workbench.cisecurity.org/benchmarks/12345",
        version="v1.0.0",
        downloaded_at=datetime(2025, 1, 1),
        scraper_version="1.0.0",
        total_recommendations=3,
        recommendations=[
            Recommendation(
                ref="1.1",
                title="Test Rec 1",
                url="https://example.com/1",
                assessment_status="Automated",
                profiles=["Level 1"],
            ),
            Recommendation(
                ref="1.2",
                title="Test Rec 2",
                url="https://example.com/2",
                assessment_status="Automated",
                profiles=["Level 1"],
            ),
            Recommendation(
                ref="1.3",
                title="Test Rec 3",
                url="https://example.com/3",
                assessment_status="Manual",
                profiles=["Level 2"],
            ),
        ],
    )


class TestDownloadWithProgress:
    """Tests for download_with_progress function."""

    def test_download_with_progress_returns_benchmark(self, sample_benchmark):
        """download_with_progress should return benchmark from scraper."""
        from cis_bench.cli.helpers.download_helper import download_with_progress

        mock_scraper = MagicMock()
        mock_scraper.download_benchmark.return_value = sample_benchmark

        result = download_with_progress(mock_scraper, "https://example.com/benchmarks/12345")

        assert result == sample_benchmark
        mock_scraper.download_benchmark.assert_called_once()

    def test_download_with_progress_passes_callback(self, sample_benchmark):
        """download_with_progress should pass progress_callback to scraper."""
        from cis_bench.cli.helpers.download_helper import download_with_progress

        mock_scraper = MagicMock()
        mock_scraper.download_benchmark.return_value = sample_benchmark

        download_with_progress(mock_scraper, "https://example.com/benchmarks/12345")

        # Verify callback was passed
        call_kwargs = mock_scraper.download_benchmark.call_args.kwargs
        assert "progress_callback" in call_kwargs
        assert callable(call_kwargs["progress_callback"])

    def test_download_with_progress_prefix(self, sample_benchmark):
        """download_with_progress should use prefix in output."""
        from cis_bench.cli.helpers.download_helper import download_with_progress

        mock_scraper = MagicMock()
        mock_scraper.download_benchmark.return_value = sample_benchmark

        # Call with prefix
        result = download_with_progress(
            mock_scraper, "https://example.com/benchmarks/12345", prefix="[1/3] "
        )

        assert result == sample_benchmark

    @patch("cis_bench.cli.helpers.download_helper.Console")
    def test_callback_handles_benchmark_title(self, mock_console_class, sample_benchmark):
        """Progress callback should print benchmark title."""
        from cis_bench.cli.helpers.download_helper import download_with_progress

        mock_console = MagicMock()
        mock_console_class.return_value = mock_console

        mock_scraper = MagicMock()

        # Capture the callback
        def capture_callback(url, progress_callback=None):
            if progress_callback:
                progress_callback("Benchmark title: CIS Test Benchmark")
            return sample_benchmark

        mock_scraper.download_benchmark.side_effect = capture_callback

        download_with_progress(mock_scraper, "https://example.com/benchmarks/12345")

        # Verify console.print was called with title
        mock_console.print.assert_called()
        call_args = str(mock_console.print.call_args)
        assert "CIS Test Benchmark" in call_args

    @patch("cis_bench.cli.helpers.download_helper.Progress")
    @patch("cis_bench.cli.helpers.download_helper.Console")
    def test_callback_creates_progress_bar_on_found(
        self, mock_console_class, mock_progress_class, sample_benchmark
    ):
        """Progress callback should create progress bar when 'Found X recommendations'."""
        from cis_bench.cli.helpers.download_helper import download_with_progress

        mock_console = MagicMock()
        mock_console_class.return_value = mock_console

        mock_progress = MagicMock()
        mock_progress_class.return_value = mock_progress

        mock_scraper = MagicMock()

        # Capture the callback and simulate finding recommendations
        def capture_callback(url, progress_callback=None):
            if progress_callback:
                progress_callback("Found 50 recommendations to download")
            return sample_benchmark

        mock_scraper.download_benchmark.side_effect = capture_callback

        download_with_progress(mock_scraper, "https://example.com/benchmarks/12345")

        # Verify progress bar was created and started
        mock_progress.start.assert_called_once()
        mock_progress.add_task.assert_called_once()
        mock_progress.stop.assert_called_once()

    @patch("cis_bench.cli.helpers.download_helper.Progress")
    @patch("cis_bench.cli.helpers.download_helper.Console")
    def test_callback_updates_progress_on_index(
        self, mock_console_class, mock_progress_class, sample_benchmark
    ):
        """Progress callback should update progress bar on '[X/Y]' messages."""
        from cis_bench.cli.helpers.download_helper import download_with_progress

        mock_console = MagicMock()
        mock_console_class.return_value = mock_console

        mock_progress = MagicMock()
        mock_progress.add_task.return_value = 0  # task_id
        mock_progress_class.return_value = mock_progress

        mock_scraper = MagicMock()

        # Capture the callback and simulate progress updates
        def capture_callback(url, progress_callback=None):
            if progress_callback:
                progress_callback("Found 3 recommendations to download")
                progress_callback("[1/3] Downloading recommendation 1")
                progress_callback("[2/3] Downloading recommendation 2")
                progress_callback("[3/3] Downloading recommendation 3")
            return sample_benchmark

        mock_scraper.download_benchmark.side_effect = capture_callback

        download_with_progress(mock_scraper, "https://example.com/benchmarks/12345")

        # Verify progress was updated 3 times
        assert mock_progress.update.call_count == 3

    @patch("cis_bench.cli.helpers.download_helper.Console")
    def test_callback_ignores_unknown_messages(self, mock_console_class, sample_benchmark):
        """Progress callback should ignore unknown message formats."""
        from cis_bench.cli.helpers.download_helper import download_with_progress

        mock_console = MagicMock()
        mock_console_class.return_value = mock_console

        mock_scraper = MagicMock()

        # Capture the callback and send unknown messages
        def capture_callback(url, progress_callback=None):
            if progress_callback:
                progress_callback("Some random debug message")
                progress_callback("Another unrelated message")
            return sample_benchmark

        mock_scraper.download_benchmark.side_effect = capture_callback

        # Should not raise
        result = download_with_progress(mock_scraper, "https://example.com/benchmarks/12345")
        assert result == sample_benchmark

    @patch("cis_bench.cli.helpers.download_helper.Console")
    def test_no_progress_bar_created_without_found_message(
        self, mock_console_class, sample_benchmark
    ):
        """Progress bar should not be created if 'Found' message never received."""
        from cis_bench.cli.helpers.download_helper import download_with_progress

        mock_console = MagicMock()
        mock_console_class.return_value = mock_console

        mock_scraper = MagicMock()
        mock_scraper.download_benchmark.return_value = sample_benchmark

        # No callback invocation - just return benchmark
        result = download_with_progress(mock_scraper, "https://example.com/benchmarks/12345")

        assert result == sample_benchmark

    @patch("cis_bench.cli.helpers.download_helper.Progress")
    @patch("cis_bench.cli.helpers.download_helper.Console")
    def test_progress_bar_stopped_after_download(
        self, mock_console_class, mock_progress_class, sample_benchmark
    ):
        """Progress bar should be stopped after download completes."""
        from cis_bench.cli.helpers.download_helper import download_with_progress

        mock_console = MagicMock()
        mock_console_class.return_value = mock_console

        mock_progress = MagicMock()
        mock_progress_class.return_value = mock_progress

        mock_scraper = MagicMock()

        def capture_callback(url, progress_callback=None):
            if progress_callback:
                progress_callback("Found 10 recommendations to download")
            return sample_benchmark

        mock_scraper.download_benchmark.side_effect = capture_callback

        download_with_progress(mock_scraper, "https://example.com/benchmarks/12345")

        # Verify stop was called
        mock_progress.stop.assert_called_once()

    @patch("cis_bench.cli.helpers.download_helper.Console")
    def test_callback_extracts_title_correctly(self, mock_console_class, sample_benchmark):
        """Progress callback should correctly extract title after colon."""
        from cis_bench.cli.helpers.download_helper import download_with_progress

        mock_console = MagicMock()
        mock_console_class.return_value = mock_console

        mock_scraper = MagicMock()

        def capture_callback(url, progress_callback=None):
            if progress_callback:
                # Title with extra spaces
                progress_callback("Benchmark title:   CIS Ubuntu 22.04 Benchmark   ")
            return sample_benchmark

        mock_scraper.download_benchmark.side_effect = capture_callback

        download_with_progress(mock_scraper, "https://example.com/benchmarks/12345")

        # Verify the title was printed (stripped)
        call_args = str(mock_console.print.call_args)
        assert "CIS Ubuntu 22.04 Benchmark" in call_args
