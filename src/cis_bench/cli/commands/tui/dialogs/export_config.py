"""Export configuration dialog for selecting format and options."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, RadioButton, RadioSet

from cis_bench.services.export_service import FORMATS_BY_CONTEXT

# CSS for export config dialog
EXPORT_CONFIG_CSS = """
ExportConfigDialog {
    align: center middle;
}

#export-dialog-container {
    width: 60;
    height: auto;
    max-height: 80%;
    border: thick $primary;
    background: $surface;
    padding: 1 2;
}

#export-dialog-title {
    text-style: bold;
    width: 100%;
    text-align: center;
    padding-bottom: 1;
}

#format-section {
    width: 100%;
    height: auto;
    padding: 1 0;
}

#format-label {
    padding-bottom: 1;
}

#format-options {
    width: 100%;
    height: auto;
}

#style-section {
    width: 100%;
    height: auto;
    padding: 1 0;
}

#style-label {
    padding-bottom: 1;
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


@dataclass
class ExportDialogResult:
    """Result from export configuration dialog.

    Attributes:
        format: Selected export format
        output_dir: Output directory path
        style: XCCDF style (disa/cis) if applicable
        filename_pattern: Optional filename pattern
    """

    format: str
    output_dir: Path | None = None
    style: str | None = None
    filename_pattern: str | None = None


class ExportConfigDialog(ModalScreen[ExportDialogResult | None]):
    """Modal dialog for configuring export options.

    Allows user to select:
    - Export format (JSON, YAML, CSV, Markdown, XCCDF)
    - XCCDF style (DISA or CIS) when XCCDF is selected
    - Output directory (future: integrate OutputPathDialog)

    Usage:
        def on_export_config(result: ExportDialogResult | None) -> None:
            if result:
                # User confirmed - proceed with export
                export_service.export_single(benchmark, result)
            else:
                # User cancelled
                pass

        self.push_screen(ExportConfigDialog(context="single"), on_export_config)
    """

    CSS = EXPORT_CONFIG_CSS

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "Confirm"),
    ]

    def __init__(
        self,
        context: Literal["single", "diff", "batch"] = "single",
        default_format: str | None = None,
        **kwargs,
    ):
        """Initialize export config dialog.

        Args:
            context: Export context - determines available formats
            default_format: Pre-selected format (optional)
        """
        super().__init__(**kwargs)
        self.context = context
        self.default_format = default_format or "json"
        self._selected_format = self.default_format
        self._selected_style: str | None = None

    def get_available_formats(self) -> list[str]:
        """Get available formats for current context."""
        return FORMATS_BY_CONTEXT.get(self.context, FORMATS_BY_CONTEXT["single"])

    def compose(self) -> ComposeResult:
        """Compose the dialog UI."""
        formats = self.get_available_formats()

        with Center():
            with Container(id="export-dialog-container"):
                yield Label("Export Options", id="export-dialog-title")

                # Format selection
                with Vertical(id="format-section"):
                    yield Label("Format:", id="format-label")
                    with RadioSet(id="format-options"):
                        for fmt in formats:
                            label = self._format_label(fmt)
                            is_default = fmt == self.default_format
                            yield RadioButton(label, value=is_default, id=f"format-{fmt}")

                # XCCDF style selection (only shown for xccdf format)
                with Vertical(id="style-section"):
                    yield Label("XCCDF Style:", id="style-label")
                    with RadioSet(id="style-options"):
                        yield RadioButton("DISA (STIG-compatible)", value=True, id="style-disa")
                        yield RadioButton("CIS (native)", id="style-cis")

                # Buttons
                with Horizontal(id="button-row"):
                    yield Button("Cancel", variant="default", id="cancel-btn")
                    yield Button("Export", variant="primary", id="export-btn")

    def on_mount(self) -> None:
        """Handle mount - show/hide style section based on format."""
        self._update_style_visibility()

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        """Handle format/style selection changes."""
        if event.radio_set.id == "format-options":
            # Extract format from button id
            if event.pressed and event.pressed.id:
                self._selected_format = event.pressed.id.replace("format-", "")
                self._update_style_visibility()
        elif event.radio_set.id == "style-options":
            if event.pressed and event.pressed.id:
                self._selected_style = event.pressed.id.replace("style-", "")

    def _update_style_visibility(self) -> None:
        """Show/hide style section based on selected format."""
        style_section = self.query_one("#style-section", Vertical)
        if self._selected_format == "xccdf":
            style_section.display = True
            # Default to DISA if not set
            if not self._selected_style:
                self._selected_style = "disa"
        else:
            style_section.display = False
            self._selected_style = None

    def _format_label(self, fmt: str) -> str:
        """Get human-readable label for format."""
        labels = {
            "json": "JSON",
            "yaml": "YAML",
            "csv": "CSV",
            "markdown": "Markdown",
            "xccdf": "XCCDF (XML)",
        }
        return labels.get(fmt, fmt.upper())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "cancel-btn":
            self.dismiss(None)
        elif event.button.id == "export-btn":
            self._confirm_export()

    def action_cancel(self) -> None:
        """Cancel and close dialog."""
        self.dismiss(None)

    def action_confirm(self) -> None:
        """Confirm selection and close dialog."""
        self._confirm_export()

    def _confirm_export(self) -> None:
        """Build result and dismiss."""
        result = ExportDialogResult(
            format=self._selected_format,
            style=self._selected_style if self._selected_format == "xccdf" else None,
            output_dir=Path.cwd(),  # Default for now, will integrate OutputPathDialog
        )
        self.dismiss(result)
