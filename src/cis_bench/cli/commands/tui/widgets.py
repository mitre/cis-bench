"""Shared widget components for TUI applications."""

import logging

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Label, LoadingIndicator, ProgressBar, Static

logger = logging.getLogger(__name__)


class SearchInput(Input):
    """Search input widget that filters results in real-time."""

    BINDINGS = [
        Binding("escape", "cancel_search", "Cancel"),
        Binding("enter", "submit_search", "Search"),
    ]

    def __init__(self, **kwargs):
        super().__init__(placeholder="Search...", id="search-input", **kwargs)

    def action_cancel_search(self) -> None:
        """Cancel search and hide input."""
        self.app.action_cancel_search()

    def action_submit_search(self) -> None:
        """Submit search (keep filter active)."""
        self.app.action_submit_search()


class HelpScreen(ModalScreen[None]):
    """Modal screen showing keyboard shortcuts."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("question_mark", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
    ]

    def __init__(self, bindings: list, **kwargs):
        """Initialize help screen with bindings to display.

        Args:
            bindings: List of Binding objects to show in help.
        """
        super().__init__(**kwargs)
        self.bindings_list = bindings

    def compose(self) -> ComposeResult:
        yield Container(
            Label("Keyboard Shortcuts", id="help-title"),
            VerticalScroll(
                Static(self.get_help_content(), id="help-content"),
                id="help-scroll",
            ),
            Label("Press ? or Esc to close", id="help-hint"),
            id="help-dialog",
        )

    def get_help_content(self) -> str:
        """Generate formatted help content from bindings.

        Returns:
            Formatted string with all keybindings.
        """
        lines = []
        for binding in self.bindings_list:
            # Skip hidden bindings that duplicate others
            key_display = binding.key.replace("_", " ").title()
            if binding.key == "question_mark":
                key_display = "?"
            lines.append(f"  {key_display:<15} {binding.description}")
        return "\n".join(lines)

    def action_dismiss(self) -> None:
        """Close the help screen."""
        self.dismiss(None)


class SaveDialog(ModalScreen[str | None]):
    """Modal dialog for saving a report."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, default_filename: str = "report.md", **kwargs):
        super().__init__(**kwargs)
        self.default_filename = default_filename

    def compose(self) -> ComposeResult:
        yield Container(
            Label("Save Report", id="save-title"),
            Label("Filename:", id="filename-label"),
            Input(value=self.default_filename, id="filename-input"),
            Label("Press Enter to save, Escape to cancel", id="save-hint"),
            id="save-dialog",
        )

    def on_mount(self) -> None:
        self.query_one("#filename-input", Input).focus()

    @on(Input.Submitted)
    def on_submit(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)


class JumpDialog(ModalScreen[str | None]):
    """Modal dialog for jumping to a specific ref."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        yield Container(
            Label("Jump to Ref", id="jump-title"),
            Label("Enter ref (e.g., 1.2.3):", id="ref-label"),
            Input(placeholder="1.2.3", id="jump-input"),
            Label("Press Enter to jump, Escape to cancel", id="jump-hint"),
            id="jump-dialog",
        )

    def on_mount(self) -> None:
        self.query_one("#jump-input", Input).focus()

    @on(Input.Submitted)
    def on_submit(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)


# CSS for LoadingModal
LOADING_MODAL_CSS = """
#loading-container {
    align: center middle;
    width: 50;
    height: 12;
    border: solid $primary;
    background: $surface;
    padding: 1 2;
}

#loading-title {
    text-style: bold;
    width: 100%;
    text-align: center;
    padding-bottom: 1;
}

#loading-spinner {
    width: 100%;
    height: 3;
    content-align: center middle;
}

#loading-status {
    width: 100%;
    text-align: center;
    padding: 1 0;
}

#loading-progress {
    width: 100%;
    margin: 1 0;
}

#loading-hint {
    text-style: italic;
    color: $text-muted;
    width: 100%;
    text-align: center;
    margin-top: 1;
}
"""


class LoadingModal(ModalScreen[bool]):
    """Modal screen showing loading progress with spinner and progress bar.

    Use this when loading data asynchronously to provide visual feedback.

    Returns:
        True if loading completed, False if cancelled by user.

    Usage:
        def on_load_complete(result: bool) -> None:
            if result:
                # Proceed with loaded data
                pass
            else:
                # User cancelled
                pass

        self.push_screen(LoadingModal("Loading benchmark..."), on_load_complete)

        # From worker thread, update progress:
        self.call_from_thread(modal.update_progress, 50, "Downloading...")
    """

    CSS = LOADING_MODAL_CSS

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, title: str = "Loading...", **kwargs):
        """Initialize loading modal.

        Args:
            title: Title to show in the modal.
        """
        super().__init__(**kwargs)
        self._title = title
        self._status = ""
        self._progress = 0
        self._cancelled = False

    def compose(self) -> ComposeResult:
        yield Center(
            Container(
                Label(self._title, id="loading-title"),
                LoadingIndicator(id="loading-spinner"),
                Static("Starting...", id="loading-status"),
                ProgressBar(id="loading-progress", show_eta=False, show_percentage=True),
                Label("Press Esc to cancel", id="loading-hint"),
                id="loading-container",
            ),
        )

    def on_mount(self) -> None:
        """Start the progress bar and cache widget references for thread-safe access."""
        # Cache widget references to avoid repeated queries from threads
        self._progress_bar = self.query_one("#loading-progress", ProgressBar)
        self._status_widget = self.query_one("#loading-status", Static)
        self._progress_bar.update(total=100, progress=0)
        self._mounted = True

    def update_progress(self, progress: int, status: str = "") -> None:
        """Update the progress bar and status message.

        Call this from a worker thread via call_from_thread().

        Args:
            progress: Progress percentage (0-100).
            status: Status message to display.
        """
        if self._cancelled:
            return

        self._progress = progress
        self._status = status

        # Check if mounted and widgets are cached
        if not getattr(self, "_mounted", False):
            logger.debug("LoadingModal not mounted yet, skipping progress update")
            return

        try:
            # Use cached widget references instead of querying each time
            self._progress_bar.update(progress=progress)
            self._progress_bar.refresh()  # Force visual refresh

            if status:
                self._status_widget.update(status)
            else:
                self._status_widget.update(f"{progress}%")
            self._status_widget.refresh()  # Force visual refresh
        except Exception as e:
            # Widget might not be mounted yet
            logger.debug(f"Could not update loading progress (widget not ready): {e}")

    def complete(self, success: bool = True) -> None:
        """Mark loading as complete and dismiss the modal.

        Call this from a worker thread via call_from_thread().

        Args:
            success: Whether loading succeeded.
        """
        if not self._cancelled:
            self.dismiss(success)

    def action_cancel(self) -> None:
        """Cancel the loading operation."""
        self._cancelled = True
        self.dismiss(False)

    @property
    def is_cancelled(self) -> bool:
        """Check if the user cancelled the operation."""
        return self._cancelled
