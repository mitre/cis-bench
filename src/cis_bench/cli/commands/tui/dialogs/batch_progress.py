"""Batch progress modal for tracking multi-item operations."""

import logging
from dataclasses import dataclass

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Container
from textual.screen import ModalScreen
from textual.widgets import Label, LoadingIndicator, ProgressBar, Static

logger = logging.getLogger(__name__)

# CSS for batch progress modal
BATCH_PROGRESS_CSS = """
BatchProgressModal {
    align: center middle;
}

#batch-progress-container {
    width: 50;
    height: auto;
    border: thick $primary;
    background: $surface;
    padding: 1 2;
}

#batch-title {
    text-style: bold;
    width: 100%;
    text-align: center;
    padding-bottom: 1;
}

#batch-spinner {
    width: 100%;
    height: 3;
    content-align: center middle;
}

#batch-status {
    width: 100%;
    text-align: center;
    padding: 1 0;
}

#batch-progress {
    width: 100%;
    margin: 1 0;
}

#batch-summary {
    width: 100%;
    text-align: center;
    padding: 1 0;
}

#batch-hint {
    text-style: italic;
    color: $text-muted;
    width: 100%;
    text-align: center;
    margin-top: 1;
}
"""


@dataclass
class BatchResult:
    """Result of a single item in batch operation."""

    item_id: str
    success: bool
    error: str | None = None


class BatchProgressModal(ModalScreen[list[BatchResult]]):
    """Modal for displaying progress of batch operations.

    Shows:
    - Animated spinner
    - Progress bar with current/total
    - Status message for current item
    - Running count of successes/failures
    - Cancel option

    Usage:
        modal = BatchProgressModal(title="Exporting...", total=10)
        self.push_screen(modal, on_batch_complete)

        # From worker thread:
        modal.update_progress(5, "Processing item 5...")
        modal.add_result(success=True, item_id="5")

        # When complete:
        modal.complete()
    """

    CSS = BATCH_PROGRESS_CSS

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, title: str = "Processing...", total: int = 0, **kwargs):
        """Initialize batch progress modal.

        Args:
            title: Title to display
            total: Total number of items to process
        """
        super().__init__(**kwargs)
        self._modal_title = title
        self.total = total
        self.current = 0
        self._status = "Starting..."
        self._cancelled = False
        self._results: list[BatchResult] = []
        self._mounted = False

    @property
    def modal_title(self) -> str:
        """Get modal title."""
        return self._modal_title

    @property
    def is_cancelled(self) -> bool:
        """Check if operation was cancelled."""
        return self._cancelled

    @property
    def success_count(self) -> int:
        """Count of successful items."""
        return sum(1 for r in self._results if r.success)

    @property
    def failure_count(self) -> int:
        """Count of failed items."""
        return sum(1 for r in self._results if not r.success)

    @property
    def results(self) -> list[BatchResult]:
        """Get all results."""
        return self._results.copy()

    def compose(self) -> ComposeResult:
        """Compose the modal UI."""
        yield Center(
            Container(
                Label(self._modal_title, id="batch-title"),
                LoadingIndicator(id="batch-spinner"),
                Static(self._status, id="batch-status"),
                ProgressBar(id="batch-progress", show_eta=False, show_percentage=True),
                Static("", id="batch-summary"),
                Label("Press Esc to cancel", id="batch-hint"),
                id="batch-progress-container",
            ),
        )

    def on_mount(self) -> None:
        """Initialize widgets on mount."""
        self._progress_bar = self.query_one("#batch-progress", ProgressBar)
        self._status_widget = self.query_one("#batch-status", Static)
        self._summary_widget = self.query_one("#batch-summary", Static)
        self._progress_bar.update(total=self.total, progress=0)
        self._mounted = True

    def update_progress(self, current: int, status: str = "") -> None:
        """Update progress display.

        Call from worker thread via call_from_thread().

        Args:
            current: Current item number (1-based)
            status: Status message to display
        """
        if self._cancelled:
            return

        self.current = current
        self._status = status

        if not self._mounted:
            return

        try:
            self._progress_bar.update(progress=current)
            self._progress_bar.refresh()

            if status:
                self._status_widget.update(f"[{current}/{self.total}] {status}")
            else:
                self._status_widget.update(f"[{current}/{self.total}]")
            self._status_widget.refresh()

            self._update_summary()
        except Exception as e:
            logger.debug(f"Could not update progress: {e}")

    def add_result(self, success: bool, item_id: str, error: str | None = None) -> None:
        """Add result for an item.

        Args:
            success: Whether item succeeded
            item_id: Identifier for the item
            error: Error message if failed
        """
        self._results.append(BatchResult(item_id=item_id, success=success, error=error))
        if self._mounted:
            self._update_summary()

    def _update_summary(self) -> None:
        """Update summary display."""
        if not self._mounted:
            return
        try:
            summary = f"✓ {self.success_count} succeeded"
            if self.failure_count > 0:
                summary += f"  ✗ {self.failure_count} failed"
            self._summary_widget.update(summary)
            self._summary_widget.refresh()
        except Exception as e:
            logger.debug(f"Could not update summary: {e}")

    def complete(self) -> None:
        """Mark operation as complete and dismiss.

        Call from worker thread via call_from_thread().
        """
        if not self._cancelled:
            self.dismiss(self._results)

    def action_cancel(self) -> None:
        """Cancel the operation."""
        self._cancelled = True
        self.dismiss(self._results)
