"""Base TUI components for cis-bench interactive commands."""

import re
from abc import abstractmethod

import html2text
from rich.markdown import Markdown
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Input, Static

from cis_bench.cli.commands.tui.widgets import HelpScreen, JumpDialog, SearchInput

# Configure html2text for clean markdown output
_h2t = html2text.HTML2Text()
_h2t.ignore_links = False
_h2t.ignore_images = True
_h2t.body_width = 0  # Don't wrap


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

    # Override in subclass to disable search container (e.g., ViewApp)
    has_search_container = True
    # Override in subclass to enable selection tracking (e.g., DiffApp, CatalogApp)
    supports_selection = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._items = []  # Standardized: current visible items
        self._sort_reverse = False  # Standardized: sort order state
        self._selected_indices: set[int] = set()  # Track selected row indices
        self._focus_on_detail = False
        self._fullscreen_detail = False
        self._search_active = False
        self._search_query = ""

    @abstractmethod
    def get_detail_view(self) -> Static:
        """Return the detail view widget for this app.

        Subclasses must implement this to return their specific detail view.

        Returns:
            A Static widget (or subclass) to display item details.
        """
        pass

    @abstractmethod
    def _build_summary(self):
        """Build the summary text for the header.

        Subclasses must implement this to return their specific summary.

        Returns:
            A Text object or string for the summary display.
        """
        pass

    @abstractmethod
    def _show_detail(self, index: int) -> None:
        """Show detail for the selected item.

        Subclasses must implement this to update their detail view.

        Args:
            index: Index of the item in self._items to display.
        """
        pass

    @abstractmethod
    def _get_columns(self) -> list[str]:
        """Return column headers for the data table.

        Returns:
            List of column header strings.
        """
        pass

    @abstractmethod
    def _populate_table(self) -> None:
        """Populate the table with data.

        Subclasses must implement this to add rows to the table.
        Should update self._items as rows are added.
        """
        pass

    @abstractmethod
    def _rebuild_table(self) -> None:
        """Rebuild the table with current sort order.

        Subclasses must implement this to handle their specific
        sorting logic and table rebuilding.
        """
        pass

    def action_reverse_sort(self) -> None:
        """Toggle sort order (asc/desc)."""
        self._sort_reverse = not self._sort_reverse
        self._rebuild_table()
        direction = "descending" if self._sort_reverse else "ascending"
        self.notify(f"Sort: {direction}", title="Sort Order")

    def action_toggle_select(self) -> None:
        """Toggle selection on the current row.

        Only active if supports_selection is True.
        """
        if not self.supports_selection:
            return

        table = self.query_one("#changes-table", DataTable)
        current_row = table.cursor_row

        if current_row in self._selected_indices:
            self._selected_indices.remove(current_row)
        else:
            self._selected_indices.add(current_row)

        # Call hook for subclass-specific behavior
        self._on_selection_changed()

    def _on_selection_changed(self) -> None:
        """Hook called after selection changes.

        Override in subclass to provide custom behavior (e.g., update UI).
        Default: notify user with selection count.
        """
        count = len(self._selected_indices)
        if count > 0:
            self.notify(f"Selected: {count} items", severity="information")

    def get_selected_items(self) -> list:
        """Get the selected items.

        Returns:
            List of items from self._items at selected indices.
        """
        return [
            self._items[idx] for idx in sorted(self._selected_indices) if idx < len(self._items)
        ]

    def on_mount(self) -> None:
        """Set up the table when app mounts."""
        table = self.query_one("#changes-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True

        # Add columns from subclass
        table.add_columns(*self._get_columns())

        # Populate table (subclass implements)
        self._populate_table()

        # Show first item details if available
        if self._items:
            self._show_detail(0)

        # Focus the table initially
        table.focus()

    @on(DataTable.RowHighlighted)
    def on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Update detail view when row selection changes."""
        if event.cursor_row is not None and event.cursor_row < len(self._items):
            self._show_detail(event.cursor_row)

    def compose(self) -> ComposeResult:
        """Compose the standard browser layout.

        Structure:
        - Header
        - Summary line
        - Main container (list + detail)
        - Optional search container
        - Footer
        """
        yield Header()
        yield Static(self._build_summary(), id="summary")
        yield Horizontal(
            Container(
                DataTable(id="changes-table"),
                id="list-container",
            ),
            VerticalScroll(
                self.get_detail_view(),
                id="detail-container",
            ),
            id="main-container",
        )
        if self.has_search_container:
            yield Container(
                SearchInput(),
                Static("", id="search-count"),
                id="search-container",
            )
        yield Footer()

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


# Screen-based bindings (Escape goes back instead of quit)
SCREEN_BINDINGS = [
    Binding("escape", "go_back", "Back", show=True),
    Binding("q", "go_back", "Back"),
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


class BaseBrowserScreen(Screen):
    """Base class for TUI screens that browse a list with detail view.

    This is the Screen-based equivalent of BaseBrowserApp for use in
    the SPA architecture where screens are pushed/popped from a single app.

    Key differences from BaseBrowserApp:
    - Inherits from Screen, not App
    - Escape/q goes back (pops screen) instead of quitting
    - Uses self.app to access parent app methods
    """

    CSS = COMMON_CSS
    BINDINGS = SCREEN_BINDINGS

    # Override in subclass to disable search container
    has_search_container = True
    # Override in subclass to enable selection tracking
    supports_selection = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._items = []  # Current visible items
        self._sort_reverse = False  # Sort order state
        self._selected_indices: set[int] = set()  # Track selected row indices
        self._focus_on_detail = False
        self._fullscreen_detail = False
        self._search_active = False
        self._search_query = ""

    @abstractmethod
    def get_detail_view(self) -> Static:
        """Return the detail view widget for this screen."""
        pass

    @abstractmethod
    def _build_summary(self):
        """Build the summary text for the header."""
        pass

    @abstractmethod
    def _show_detail(self, index: int) -> None:
        """Show detail for the selected item."""
        pass

    @abstractmethod
    def _get_columns(self) -> list[str]:
        """Return column headers for the data table."""
        pass

    @abstractmethod
    def _populate_table(self) -> None:
        """Populate the table with data."""
        pass

    @abstractmethod
    def _rebuild_table(self) -> None:
        """Rebuild the table with current sort order."""
        pass

    def action_go_back(self) -> None:
        """Go back to previous screen or exit if root."""
        if len(self.app.screen_stack) > 1:
            self.app.pop_screen()
        else:
            self.app.exit()

    def action_reverse_sort(self) -> None:
        """Toggle sort order (asc/desc)."""
        self._sort_reverse = not self._sort_reverse
        self._rebuild_table()
        direction = "descending" if self._sort_reverse else "ascending"
        self.notify(f"Sort: {direction}", title="Sort Order")

    def action_toggle_select(self) -> None:
        """Toggle selection on the current row."""
        if not self.supports_selection:
            return

        table = self.query_one("#changes-table", DataTable)
        current_row = table.cursor_row

        if current_row in self._selected_indices:
            self._selected_indices.remove(current_row)
        else:
            self._selected_indices.add(current_row)

        self._on_selection_changed()

    def _on_selection_changed(self) -> None:
        """Hook called after selection changes."""
        count = len(self._selected_indices)
        if count > 0:
            self.notify(f"Selected: {count} items", severity="information")

    def get_selected_items(self) -> list:
        """Get the selected items."""
        return [
            self._items[idx] for idx in sorted(self._selected_indices) if idx < len(self._items)
        ]

    def on_mount(self) -> None:
        """Set up the table when screen mounts."""
        table = self.query_one("#changes-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True

        # Add columns from subclass
        table.add_columns(*self._get_columns())

        # Populate table (subclass implements)
        self._populate_table()

        # Show first item details if available
        if self._items:
            self._show_detail(0)

        # Focus the table initially
        table.focus()

    @on(DataTable.RowHighlighted)
    def on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Update detail view when row selection changes."""
        if event.cursor_row is not None and event.cursor_row < len(self._items):
            self._show_detail(event.cursor_row)

    def compose(self) -> ComposeResult:
        """Compose the standard browser layout."""
        yield Header()
        yield Static(self._build_summary(), id="summary")
        yield Horizontal(
            Container(
                DataTable(id="changes-table"),
                id="list-container",
            ),
            VerticalScroll(
                self.get_detail_view(),
                id="detail-container",
            ),
            id="main-container",
        )
        if self.has_search_container:
            yield Container(
                SearchInput(),
                Static("", id="search-count"),
                id="search-container",
            )
        yield Footer()

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
        pass

    def action_show_help(self) -> None:
        """Show the help screen with keyboard shortcuts."""
        self.app.push_screen(HelpScreen(self.BINDINGS))

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
            if ref:
                self._jump_to_ref(ref)
            self.query_one("#changes-table", DataTable).focus()

        self.app.push_screen(JumpDialog(), handle_jump)

    def action_copy_to_clipboard(self) -> None:
        """Copy current detail view content to clipboard."""
        try:
            import pyperclip

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
        """Jump to a specific ref in the table."""
        table = self.query_one("#changes-table", DataTable)
        target_ref = target_ref.strip()

        for row_idx, row_key in enumerate(table.rows):
            row_data = table.get_row(row_key)
            if row_data:
                ref_cell = str(row_data[0]) if row_data else ""
                ref_cell2 = str(row_data[1]) if len(row_data) > 1 else ""

                if target_ref in ref_cell or target_ref in ref_cell2:
                    table.move_cursor(row=row_idx)
                    return

        self.notify(f"Ref '{target_ref}' not found", severity="warning")

    def _truncate(self, text: str, length: int) -> str:
        """Truncate text with ellipsis."""
        if len(text) <= length:
            return text
        return text[: length - 3] + "..."
