"""Shared TUI components for cis-bench interactive commands."""

import re

import html2text
from rich.markdown import Markdown
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    DataTable,
    Input,
    Label,
    Static,
)


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


def natural_sort_key(ref: str) -> tuple:
    """Generate a sort key for natural/version sorting of CIS refs.

    Converts "1.2.3" to (1, 2, 3) for proper numeric comparison.
    Handles mixed formats like "1.1.1.1" and non-numeric parts.

    Examples:
        "1.1" -> (1, 1)
        "1.2.3" -> (1, 2, 3)
        "1.10" -> (1, 10)  # Sorts after 1.9, not after 1.1
        "6.2.3.14" -> (6, 2, 3, 14)
    """
    parts = re.split(r"[.\-]", ref)
    result = []
    for part in parts:
        # Try to convert to int, fall back to string for non-numeric
        try:
            result.append((0, int(part)))  # (0, n) for numbers
        except ValueError:
            result.append((1, part))  # (1, s) for strings (sort after numbers)
    return tuple(result)


# Configure html2text for clean markdown output
_h2t = html2text.HTML2Text()
_h2t.ignore_links = False
_h2t.ignore_images = True
_h2t.body_width = 0  # Don't wrap


def html_to_markdown(html_content: str) -> str:
    """Convert HTML content to clean markdown.

    Args:
        html_content: HTML string to convert.

    Returns:
        Markdown formatted string.
    """
    if not html_content:
        return ""
    # Handle plain text (no HTML)
    if "<" not in html_content:
        return html_content
    return _h2t.handle(html_content).strip()


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


class DetailView(Static):
    """Base class for detailed content display with markdown rendering."""

    can_focus = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._content_text = ""

    def get_content_text(self) -> str:
        """Return the plain text content for saving."""
        return self._content_text

    def set_content(self, text: str) -> None:
        """Set content and render as markdown."""
        self._content_text = text
        try:
            md = Markdown(text)
            self.update(md)
        except Exception:
            self.update(text)

    def render_recommendation(self, rec: dict, show_as: str = "view") -> str:
        """Render a recommendation to markdown.

        Args:
            rec: Recommendation dict with title, description, etc.
            show_as: How to show it - "view", "added", "removed"

        Returns:
            Markdown formatted string.
        """
        lines = []
        ref = rec.get("ref", "")
        title = rec.get("title", "Untitled")

        if show_as == "added":
            lines.append(f"# ✚ ADDED: {ref}")
        elif show_as == "removed":
            lines.append(f"# ✖ REMOVED: {ref}")
        else:
            lines.append(f"# {ref}")

        lines.append(f"**{title}**\n")

        # Profiles and status
        profiles = rec.get("profiles", [])
        status = rec.get("assessment_status", "")
        if profiles or status:
            meta_parts = []
            if profiles:
                meta_parts.append(f"Profiles: {', '.join(profiles)}")
            if status:
                meta_parts.append(f"Status: {status}")
            lines.append(f"*{' | '.join(meta_parts)}*\n")

        # Main content sections
        if rec.get("description"):
            lines.append("## Description")
            lines.append(html_to_markdown(rec["description"]))
            lines.append("")

        if rec.get("rationale"):
            lines.append("## Rationale")
            lines.append(html_to_markdown(rec["rationale"]))
            lines.append("")

        if rec.get("audit"):
            lines.append("## Audit")
            lines.append(html_to_markdown(rec["audit"]))
            lines.append("")

        if rec.get("remediation"):
            lines.append("## Remediation")
            lines.append(html_to_markdown(rec["remediation"]))
            lines.append("")

        if rec.get("impact"):
            lines.append("## Impact")
            lines.append(html_to_markdown(rec["impact"]))
            lines.append("")

        if rec.get("default_value"):
            lines.append("## Default Value")
            lines.append(html_to_markdown(rec["default_value"]))
            lines.append("")

        if rec.get("references"):
            lines.append("## References")
            refs = rec["references"]
            # Handle both string (HTML) and list formats
            if isinstance(refs, str):
                lines.append(html_to_markdown(refs))
            else:
                for ref_item in refs:
                    lines.append(f"- {ref_item}")
            lines.append("")

        # Compliance mappings
        if rec.get("cis_controls"):
            lines.append("## CIS Controls")
            for ctrl in rec["cis_controls"]:
                if isinstance(ctrl, dict):
                    lines.append(f"- v{ctrl.get('version', '?')}: {ctrl.get('control', '')}")
                else:
                    lines.append(f"- {ctrl}")
            lines.append("")

        if rec.get("nist_controls"):
            lines.append("## NIST Controls")
            lines.append(", ".join(rec["nist_controls"]))
            lines.append("")

        return "\n".join(lines)


# Common CSS for TUI apps
COMMON_CSS = """
#main-container {
    height: 100%;
    width: 100%;
}

#list-container {
    width: 40%;
    height: 100%;
    border: solid $primary;
}

#detail-container {
    width: 60%;
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

#save-dialog {
    align: center middle;
    width: 60;
    height: 12;
    border: solid $primary;
    background: $surface;
    padding: 1 2;
}

#save-title {
    text-style: bold;
    width: 100%;
    text-align: center;
    padding-bottom: 1;
}

#filename-input {
    width: 100%;
    margin: 1 0;
}

#save-hint {
    text-style: italic;
    color: $text-muted;
    width: 100%;
    text-align: center;
}

#help-dialog {
    align: center middle;
    width: 50;
    height: 20;
    border: solid $primary;
    background: $surface;
    padding: 1 2;
}

#help-title {
    text-style: bold;
    width: 100%;
    text-align: center;
    padding-bottom: 1;
}

#help-scroll {
    height: 100%;
    width: 100%;
}

#help-content {
    width: 100%;
}

#help-hint {
    text-style: italic;
    color: $text-muted;
    width: 100%;
    text-align: center;
    dock: bottom;
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

#jump-dialog {
    align: center middle;
    width: 50;
    height: 10;
    border: solid $primary;
    background: $surface;
    padding: 1 2;
}

#jump-title {
    text-style: bold;
    width: 100%;
    text-align: center;
    padding-bottom: 1;
}

#jump-input {
    width: 100%;
    margin: 1 0;
}

#jump-hint {
    text-style: italic;
    color: $text-muted;
    width: 100%;
    text-align: center;
}
"""

# Common key bindings
COMMON_BINDINGS = [
    Binding("q", "quit", "Quit"),
    Binding("escape", "quit", "Quit"),
    Binding("question_mark", "show_help", "Help", show=True),
    Binding("slash", "start_search", "Search", show=True),
    Binding("g", "jump_to_ref", "Go to Ref", show=True),
    Binding("c", "copy_to_clipboard", "Copy", show=True),
    Binding("tab", "toggle_focus", "Switch Pane", show=True),
    Binding("j", "cursor_down", "Down", show=False),
    Binding("k", "cursor_up", "Up", show=False),
    Binding("down", "cursor_down", "Down", show=False),
    Binding("up", "cursor_up", "Up", show=False),
    Binding("pagedown", "page_down", "Page Down", show=False),
    Binding("pageup", "page_up", "Page Up", show=False),
    Binding("s", "save_report", "Save Report", show=True),
    Binding("f", "toggle_fullscreen", "Fullscreen", show=True),
    Binding("r", "reverse_sort", "Reverse", show=True),
]


class BaseBrowserApp(App):
    """Base class for TUI apps that browse a list with detail view."""

    CSS = COMMON_CSS
    BINDINGS = COMMON_BINDINGS

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._item_list = []
        self._focus_on_detail = False
        self._fullscreen_detail = False
        self._search_active = False
        self._search_query = ""

    def action_start_search(self) -> None:
        """Open the search input."""
        self._search_active = True
        search_container = self.query_one("#search-container")
        search_container.add_class("visible")
        search_input = self.query_one("#search-input", SearchInput)
        search_input.value = ""
        search_input.focus()

    def action_cancel_search(self) -> None:
        """Cancel search and restore all items."""
        self._search_active = False
        self._search_query = ""
        search_container = self.query_one("#search-container")
        search_container.remove_class("visible")
        self._apply_search_filter("")
        self.query_one("#changes-table", DataTable).focus()

    def action_submit_search(self) -> None:
        """Submit search and keep filter active."""
        search_container = self.query_one("#search-container")
        search_container.remove_class("visible")
        self.query_one("#changes-table", DataTable).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes for real-time filtering."""
        if event.input.id == "search-input":
            self._search_query = event.value
            self._apply_search_filter(event.value)

    def _apply_search_filter(self, query: str) -> None:
        """Apply search filter to the table. Override in subclass."""
        pass  # Subclasses implement this

    def action_show_help(self) -> None:
        """Show the help screen with keyboard shortcuts."""
        self.push_screen(HelpScreen(self.BINDINGS))

    def action_toggle_focus(self) -> None:
        """Toggle focus between list and detail panes."""
        self._focus_on_detail = not self._focus_on_detail
        if self._focus_on_detail:
            self.query_one("#detail-container", VerticalScroll).focus()
        else:
            self.query_one("#changes-table", DataTable).focus()

    def action_cursor_down(self) -> None:
        """Move cursor down in list, or scroll detail."""
        if self._focus_on_detail:
            detail = self.query_one("#detail-container", VerticalScroll)
            detail.scroll_down()
        else:
            table = self.query_one("#changes-table", DataTable)
            table.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up in list, or scroll detail."""
        if self._focus_on_detail:
            detail = self.query_one("#detail-container", VerticalScroll)
            detail.scroll_up()
        else:
            table = self.query_one("#changes-table", DataTable)
            table.action_cursor_up()

    def action_page_down(self) -> None:
        """Page down in detail view."""
        if self._focus_on_detail:
            detail = self.query_one("#detail-container", VerticalScroll)
            detail.scroll_page_down()

    def action_page_up(self) -> None:
        """Page up in detail view."""
        if self._focus_on_detail:
            detail = self.query_one("#detail-container", VerticalScroll)
            detail.scroll_page_up()

    def action_toggle_fullscreen(self) -> None:
        """Toggle fullscreen detail view."""
        self._fullscreen_detail = not self._fullscreen_detail
        list_container = self.query_one("#list-container")
        detail_container = self.query_one("#detail-container")

        if self._fullscreen_detail:
            list_container.styles.display = "none"
            detail_container.styles.width = "100%"
        else:
            list_container.styles.display = "block"
            detail_container.styles.width = "60%"

    def action_jump_to_ref(self) -> None:
        """Open the jump to ref dialog."""

        def handle_jump(ref: str | None) -> None:
            """Handle the ref from the dialog."""
            if ref:
                self._jump_to_ref(ref)
            self.query_one("#changes-table", DataTable).focus()

        self.push_screen(JumpDialog(), handle_jump)

    def action_copy_to_clipboard(self) -> None:
        """Copy current detail view content to clipboard."""
        try:
            import pyperclip

            # Get the detail view content
            detail = self.query_one("#detail-view")
            if hasattr(detail, "get_content_text"):
                content = detail.get_content_text()
                if content:
                    pyperclip.copy(content)
                    self.notify("Copied to clipboard", severity="information")
                else:
                    self.notify("No content to copy", severity="warning")
            else:
                self.notify("Cannot copy from this view", severity="warning")
        except ImportError:
            self.notify("Clipboard not available (install pyperclip)", severity="error")
        except Exception as e:
            self.notify(f"Copy failed: {e}", severity="error")

    def _jump_to_ref(self, target_ref: str) -> None:
        """Jump to a specific ref in the table.

        Args:
            target_ref: The ref to jump to (e.g., "1.2.3").
        """
        table = self.query_one("#changes-table", DataTable)
        target_ref = target_ref.strip()

        # Search through table rows for matching ref
        for row_idx, row_key in enumerate(table.rows):
            # Get the first column value (ref) from the row
            row_data = table.get_row(row_key)
            if row_data:
                # First column is typically the ref or status+ref
                ref_cell = str(row_data[0]) if row_data else ""
                # Also check second column in case first is status indicator
                ref_cell2 = str(row_data[1]) if len(row_data) > 1 else ""

                if target_ref in ref_cell or target_ref in ref_cell2:
                    # Found the ref, move cursor to this row
                    table.move_cursor(row=row_idx)
                    return

        # If not found, notify user (could use a notification widget)
        self.notify(f"Ref '{target_ref}' not found", severity="warning")

    def _truncate(self, text: str, length: int) -> str:
        """Truncate text with ellipsis."""
        if len(text) <= length:
            return text
        return text[: length - 3] + "..."
