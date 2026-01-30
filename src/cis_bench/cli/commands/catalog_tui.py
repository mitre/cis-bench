"""Interactive TUI for browsing the CIS benchmark catalog."""

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import DataTable, Footer, Header, Static

from cis_bench.cli.commands.tui_base import (
    COMMON_CSS,
    BaseBrowserApp,
    DetailView,
    SearchInput,
)


class CatalogDetailView(DetailView):
    """Shows detailed information for a selected benchmark."""

    def update_content(self, benchmark: dict) -> None:
        """Update the detail view with benchmark information.

        Args:
            benchmark: Dictionary with benchmark metadata.
        """
        if not benchmark:
            self.set_content("*Select a benchmark to see details*")
            return

        lines = []

        # Title and ID
        title = benchmark.get("title", "Unknown Benchmark")
        benchmark_id = benchmark.get("benchmark_id", "")
        lines.append(f"# {title}")
        lines.append("")

        # Metadata section
        lines.append("## Details")
        lines.append("")

        if benchmark.get("version"):
            lines.append(f"**Version:** {benchmark['version']}")
        if benchmark_id:
            lines.append(f"**ID:** {benchmark_id}")
        if benchmark.get("platform"):
            lines.append(f"**Platform:** {benchmark['platform']}")
        if benchmark.get("community"):
            lines.append(f"**Community:** {benchmark['community']}")
        if benchmark.get("status"):
            lines.append(f"**Status:** {benchmark['status']}")
        if benchmark.get("published_date"):
            lines.append(f"**Published:** {benchmark['published_date']}")
        if benchmark.get("is_latest"):
            lines.append("**Latest Version:** Yes")
        lines.append("")

        # Description
        if benchmark.get("description"):
            lines.append("## Description")
            lines.append("")
            lines.append(benchmark["description"])
            lines.append("")

        # URL
        if benchmark.get("url"):
            lines.append("## Links")
            lines.append("")
            lines.append(f"[CIS WorkBench]({benchmark['url']})")
            lines.append("")

        # Actions hint
        lines.append("---")
        lines.append("*Actions: d=Download, v=View (if downloaded), D=Diff*")

        self.set_content("\n".join(lines))


class CatalogBrowserApp(BaseBrowserApp):
    """Interactive TUI for browsing the CIS benchmark catalog."""

    CSS = COMMON_CSS

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("escape", "quit", "Quit"),
        Binding("question_mark", "show_help", "Help", show=True),
        Binding("slash", "start_search", "Search", show=True),
        Binding("g", "jump_to_ref", "Go to ID", show=True),
        Binding("c", "copy_to_clipboard", "Copy", show=True),
        Binding("tab", "toggle_focus", "Switch Pane", show=True),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("pagedown", "page_down", "Page Down", show=False),
        Binding("pageup", "page_up", "Page Up", show=False),
        Binding("f", "toggle_fullscreen", "Fullscreen", show=True),
        Binding("r", "reverse_sort", "Reverse", show=True),
        # Selection
        Binding("space", "toggle_select", "Select", show=True),
        # Future actions (ep9.7-9)
        # Binding("d", "download", "Download", show=True),
        # Binding("v", "view", "View", show=True),
        # Binding("D", "diff", "Diff", show=True),
    ]

    def __init__(self, benchmarks: list[dict], offline: bool = False, **kwargs):
        """Initialize the catalog browser.

        Args:
            benchmarks: List of benchmark dictionaries from catalog search.
            offline: Whether running in offline mode.
        """
        super().__init__(**kwargs)
        self._benchmarks = benchmarks
        self._all_benchmarks = benchmarks.copy()
        self.offline = offline
        self._sort_reverse = False
        self._selected_indices: set[int] = set()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self._build_summary(), id="summary")
        yield Horizontal(
            Container(
                DataTable(id="changes-table"),
                id="list-container",
            ),
            VerticalScroll(
                CatalogDetailView(id="detail-view"),
                id="detail-container",
            ),
            id="main-container",
        )
        yield Container(
            SearchInput(),
            Static("", id="search-count"),
            id="search-container",
        )
        yield Footer()

    def _build_summary(self) -> Text:
        """Build summary text showing catalog stats."""
        text = Text()
        if self.offline:
            text.append("[OFFLINE] ", style="bold yellow")
        text.append("CIS Benchmark Catalog  ", style="bold")
        text.append(f"{len(self._benchmarks)} benchmarks", style="dim")
        return text

    def on_mount(self) -> None:
        """Set up the table when app mounts."""
        table = self.query_one("#changes-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True

        table.add_columns("ID", "Title", "Version", "Platform", "Published")

        self._populate_table()

        # Show first item details if available
        if self._benchmarks:
            self._show_detail(0)

        # Focus the table initially
        table.focus()

    def _populate_table(self) -> None:
        """Populate the table with benchmark data."""
        table = self.query_one("#changes-table", DataTable)

        for benchmark in self._benchmarks:
            # Mark latest versions
            title = benchmark.get("title", "Unknown")
            if benchmark.get("is_latest"):
                title = f"★ {title}"

            table.add_row(
                benchmark.get("benchmark_id", ""),
                self._truncate(title, 50),
                benchmark.get("version", ""),
                benchmark.get("platform", "")[:20] if benchmark.get("platform") else "",
                benchmark.get("published_date", "")[:10] if benchmark.get("published_date") else "",
            )

    @on(DataTable.RowHighlighted)
    def on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Update detail view when row selection changes."""
        if event.cursor_row is not None and event.cursor_row < len(self._benchmarks):
            self._show_detail(event.cursor_row)

    def _show_detail(self, index: int) -> None:
        """Show detail for the selected benchmark."""
        if index < 0 or index >= len(self._benchmarks):
            return

        benchmark = self._benchmarks[index]
        detail_view = self.query_one("#detail-view", CatalogDetailView)
        detail_view.update_content(benchmark)

    def action_toggle_select(self) -> None:
        """Toggle selection on the current row."""
        table = self.query_one("#changes-table", DataTable)
        current_row = table.cursor_row

        if current_row in self._selected_indices:
            self._selected_indices.remove(current_row)
        else:
            self._selected_indices.add(current_row)

        count = len(self._selected_indices)
        if count > 0:
            self.notify(f"Selected: {count} benchmarks", severity="information")

    def get_selected_items(self) -> list[dict]:
        """Get the selected benchmarks.

        Returns:
            List of benchmark dictionaries for selected items.
        """
        return [
            self._benchmarks[idx]
            for idx in sorted(self._selected_indices)
            if idx < len(self._benchmarks)
        ]

    def action_reverse_sort(self) -> None:
        """Toggle sort order (asc/desc)."""
        self._sort_reverse = not self._sort_reverse
        self._rebuild_table()
        direction = "descending" if self._sort_reverse else "ascending"
        self.notify(f"Sort: {direction}", title="Sort Order")

    def _rebuild_table(self) -> None:
        """Rebuild the table with current sort order."""
        table = self.query_one("#changes-table", DataTable)
        table.clear()

        # Sort by published date
        self._benchmarks = sorted(
            self._benchmarks,
            key=lambda x: x.get("published_date", "") or "",
            reverse=not self._sort_reverse,  # Default is newest first
        )

        self._populate_table()

        if self._benchmarks:
            self._show_detail(0)

    def _apply_search_filter(self, query: str) -> None:
        """Filter the table based on search query."""
        query = query.lower().strip()
        table = self.query_one("#changes-table", DataTable)
        table.clear()
        self._benchmarks = []

        for benchmark in self._all_benchmarks:
            # Check if query matches ID, title, platform, or description
            # Handle None values safely with `or ""`
            benchmark_id = str(benchmark.get("benchmark_id", ""))
            title = (benchmark.get("title") or "").lower()
            platform = (benchmark.get("platform") or "").lower()
            description = (benchmark.get("description") or "").lower()

            if query and not any(
                [
                    query in benchmark_id.lower(),
                    query in title,
                    query in platform,
                    query in description,
                ]
            ):
                continue

            self._benchmarks.append(benchmark)

        self._populate_table()

        # Update search count
        search_count = self.query_one("#search-count", Static)
        if query:
            search_count.update(f"{len(self._benchmarks)}/{len(self._all_benchmarks)}")
        else:
            search_count.update("")

        if self._benchmarks:
            self._show_detail(0)


def run_catalog_browser(benchmarks: list[dict], offline: bool = False) -> None:
    """Run the catalog browser TUI.

    Args:
        benchmarks: List of benchmark dictionaries from catalog search.
        offline: Whether running in offline mode (shows indicator).
    """
    app = CatalogBrowserApp(benchmarks=benchmarks, offline=offline)
    app.title = "CIS Benchmark Catalog"
    app.run()
