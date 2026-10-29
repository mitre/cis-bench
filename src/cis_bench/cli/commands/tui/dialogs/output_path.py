"""Output path configuration dialog."""

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Container, Horizontal, Vertical
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

# CSS for output path dialog
OUTPUT_PATH_CSS = """
OutputPathDialog {
    align: center middle;
}

#path-dialog-container {
    width: 70;
    height: auto;
    border: thick $primary;
    background: $surface;
    padding: 1 2;
}

#path-dialog-title {
    text-style: bold;
    width: 100%;
    text-align: center;
    padding-bottom: 1;
}

#path-section {
    width: 100%;
    height: auto;
    padding: 1 0;
}

#path-label {
    padding-bottom: 1;
}

#path-input {
    width: 100%;
}

#pattern-section {
    width: 100%;
    height: auto;
    padding: 1 0;
}

#pattern-label {
    padding-bottom: 1;
}

#pattern-input {
    width: 100%;
}

#pattern-hint {
    text-style: italic;
    color: $text-muted;
    padding-top: 1;
}

#button-row {
    width: 100%;
    height: auto;
    align: center middle;
    padding-top: 1;
}

#button-row Button {
    margin: 0 1;
}
"""


class OutputPathDialog(ModalScreen[tuple[Path, str | None] | None]):
    """Modal dialog for configuring output path and filename pattern.

    Allows user to configure:
    - Output directory
    - Filename pattern with placeholders

    Returns:
        Tuple of (output_dir, filename_pattern) or None if cancelled.

    Usage:
        def on_path_selected(result: tuple[Path, str | None] | None) -> None:
            if result:
                output_dir, pattern = result
                # Proceed with export
            else:
                # User cancelled
                pass

        self.push_screen(OutputPathDialog(default_dir=Path.cwd()), on_path_selected)
    """

    CSS = OUTPUT_PATH_CSS

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "Confirm"),
    ]

    def __init__(
        self,
        default_dir: Path | None = None,
        default_pattern: str | None = None,
        show_pattern: bool = True,
        **kwargs,
    ):
        """Initialize output path dialog.

        Args:
            default_dir: Default output directory
            default_pattern: Default filename pattern
            show_pattern: Whether to show pattern input
        """
        super().__init__(**kwargs)
        self.default_dir = default_dir or Path.cwd()
        self.default_pattern = default_pattern or "{id}_{title}"
        self.show_pattern = show_pattern

    def compose(self) -> ComposeResult:
        """Compose the dialog UI."""
        with Center():
            with Container(id="path-dialog-container"):
                yield Label("Output Location", id="path-dialog-title")

                # Directory input
                with Vertical(id="path-section"):
                    yield Label("Directory:", id="path-label")
                    yield Input(
                        value=str(self.default_dir),
                        placeholder="Enter output directory...",
                        id="path-input",
                    )

                # Filename pattern input
                if self.show_pattern:
                    with Vertical(id="pattern-section"):
                        yield Label("Filename Pattern:", id="pattern-label")
                        yield Input(
                            value=self.default_pattern,
                            placeholder="{id}_{title}",
                            id="pattern-input",
                        )
                        yield Static(
                            "Placeholders: {id}, {title}, {version}",
                            id="pattern-hint",
                        )

                # Buttons
                with Horizontal(id="button-row"):
                    yield Button("Cancel", variant="default", id="cancel-btn")
                    yield Button("OK", variant="primary", id="ok-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "cancel-btn":
            self.dismiss(None)
        elif event.button.id == "ok-btn":
            self._confirm()

    def action_cancel(self) -> None:
        """Cancel and close dialog."""
        self.dismiss(None)

    def action_confirm(self) -> None:
        """Confirm selection and close dialog."""
        self._confirm()

    def _confirm(self) -> None:
        """Build result and dismiss."""
        path_input = self.query_one("#path-input", Input)
        output_dir = Path(path_input.value)

        pattern = None
        if self.show_pattern:
            try:
                pattern_input = self.query_one("#pattern-input", Input)
                pattern = pattern_input.value or None
            except NoMatches:
                pass  # Pattern input not in DOM, use default None

        self.dismiss((output_dir, pattern))
