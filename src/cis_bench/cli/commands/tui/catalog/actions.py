"""Action menu and CSS for catalog browser."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label

# CSS specific to catalog browser (extends COMMON_CSS)
CATALOG_CSS = """
#main-container {
    height: 100%;
    width: 100%;
}

#list-container {
    width: 45%;
    height: 100%;
    border: solid $primary;
}

#detail-container {
    width: 55%;
    height: 100%;
    border: solid $secondary;
    padding: 1;
    overflow-y: auto;
}

#detail-container:focus-within {
    border: solid $accent;
}

#summary {
    height: 3;
    padding: 0 1;
    background: $surface;
    dock: top;
}

DataTable {
    height: 100%;
}

DataTable:focus {
    border: solid $accent;
}

#search-container {
    dock: bottom;
    height: 3;
    width: 100%;
    background: $surface;
    padding: 0 1;
    display: none;
}

#search-container.visible {
    display: block;
}

#search-input {
    width: 100%;
}

#search-count {
    dock: right;
    width: auto;
    padding: 0 1;
}

/* Action menu styles */
#action-menu {
    align: center middle;
    width: 40;
    height: auto;
    max-height: 20;
    border: solid $primary;
    background: $surface;
    padding: 1 2;
}

#action-title {
    text-style: bold;
    width: 100%;
    text-align: center;
    padding-bottom: 1;
}

#action-buttons {
    width: 100%;
    height: auto;
}

#action-buttons Button {
    width: 100%;
    margin: 0 0 1 0;
}

#action-hint {
    text-style: italic;
    color: $text-muted;
    width: 100%;
    text-align: center;
    margin-top: 1;
}
"""


class ActionMenu(ModalScreen):
    """Modal menu for benchmark actions."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("d", "download", "Download"),
        Binding("v", "view", "View"),
        Binding("D", "diff", "Diff"),
        Binding("e", "export", "Export"),
    ]

    def __init__(self, benchmark: dict, is_downloaded: bool = False, **kwargs):
        """Initialize the action menu.

        Args:
            benchmark: The benchmark to act on.
            is_downloaded: Whether the benchmark is already downloaded.
        """
        super().__init__(**kwargs)
        self.benchmark = benchmark
        self.is_downloaded = is_downloaded

    def compose(self) -> ComposeResult:
        title = self.benchmark.get("title", "Unknown")
        version = self.benchmark.get("version", "")
        display_title = f"{title[:30]}..." if len(title) > 30 else title
        if version:
            display_title = f"{display_title} {version}"

        yield Container(
            Label(display_title, id="action-title"),
            Vertical(
                Button("⬇ Download", id="btn-download", variant="primary"),
                Button(
                    "👁 View" if self.is_downloaded else "👁 View (not downloaded)",
                    id="btn-view",
                    disabled=not self.is_downloaded,
                ),
                Button("⟷ Diff versions...", id="btn-diff"),
                Button("📤 Export...", id="btn-export", disabled=not self.is_downloaded),
                id="action-buttons",
            ),
            Label("Press key or click • Esc to cancel", id="action-hint"),
            id="action-menu",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks."""
        button_id = event.button.id
        if button_id == "btn-download":
            self.dismiss(("download", self.benchmark))
        elif button_id == "btn-view":
            self.dismiss(("view", self.benchmark))
        elif button_id == "btn-diff":
            self.dismiss(("diff", self.benchmark))
        elif button_id == "btn-export":
            self.dismiss(("export", self.benchmark))

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_download(self) -> None:
        self.dismiss(("download", self.benchmark))

    def action_view(self) -> None:
        if self.is_downloaded:
            self.dismiss(("view", self.benchmark))
        else:
            self.app.notify("Download the benchmark first", severity="warning")

    def action_diff(self) -> None:
        self.dismiss(("diff", self.benchmark))

    def action_export(self) -> None:
        if self.is_downloaded:
            self.dismiss(("export", self.benchmark))
        else:
            self.app.notify("Download the benchmark first", severity="warning")
