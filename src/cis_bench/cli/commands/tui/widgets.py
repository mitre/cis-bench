"""Shared widget components for TUI applications."""

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static


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


class HelpScreen(ModalScreen):
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
        self.app.pop_screen()


class SaveDialog(ModalScreen):
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


class JumpDialog(ModalScreen):
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
