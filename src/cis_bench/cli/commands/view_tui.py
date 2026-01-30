"""Interactive TUI for browsing a single benchmark."""

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import DataTable, Footer, Header, Static

from cis_bench.cli.commands.tui_base import (
    COMMON_BINDINGS,
    COMMON_CSS,
    BaseBrowserApp,
    DetailView,
    SaveDialog,
    natural_sort_key,
)


class ViewDetailView(DetailView):
    """Shows detailed recommendation content."""

    def show_recommendation(self, rec: dict) -> None:
        """Display a recommendation's full details."""
        content = self.render_recommendation(rec)
        self.set_content(content)


class ViewApp(BaseBrowserApp):
    """Interactive TUI for browsing benchmark recommendations."""

    CSS = COMMON_CSS
    BINDINGS = COMMON_BINDINGS

    def __init__(self, benchmark: dict, recommendations: list, offline: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.benchmark = benchmark
        self.recommendations = recommendations
        self.offline = offline
        self._rec_list = []
        self._sort_reverse = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self._build_summary(), id="summary")
        yield Horizontal(
            Container(
                DataTable(id="changes-table"),
                id="list-container",
            ),
            VerticalScroll(
                ViewDetailView(id="detail-view"),
                id="detail-container",
            ),
            id="main-container",
        )
        yield Footer()

    def _build_summary(self) -> Text:
        """Build summary text."""
        text = Text()
        if self.offline:
            text.append("[OFFLINE] ", style="bold yellow")
        text.append(f"{self.benchmark.get('title', 'Benchmark')}", style="bold")
        text.append(f" v{self.benchmark.get('version', '?')}  ", style="dim")
        text.append(f"{len(self.recommendations)} recommendations", style="cyan")
        return text

    def on_mount(self) -> None:
        """Set up the table when app mounts."""
        table = self.query_one("#changes-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True

        table.add_columns("Ref", "Title", "Profiles", "Status")

        # Add recommendations sorted by ref (natural/version sort)
        sorted_recs = sorted(self.recommendations, key=lambda r: natural_sort_key(r.get("ref", "")))
        for rec in sorted_recs:
            self._rec_list.append(rec)

            profiles = ", ".join(rec.get("profiles", []))[:20]
            if len(", ".join(rec.get("profiles", []))) > 20:
                profiles = profiles[:17] + "..."

            status = rec.get("assessment_status", "")
            if status.lower() == "automated":
                status_display = Text("Auto", style="green")
            elif status.lower() == "manual":
                status_display = Text("Manual", style="yellow")
            else:
                status_display = Text(status[:8] if status else "", style="dim")

            table.add_row(
                rec.get("ref", ""),
                self._truncate(rec.get("title", ""), 45),
                profiles,
                status_display,
            )

        # Show first item details if available
        if self._rec_list:
            self._show_detail(0)

        # Focus the table initially
        table.focus()

    @on(DataTable.RowHighlighted)
    def on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Update detail view when row selection changes."""
        if event.cursor_row is not None and event.cursor_row < len(self._rec_list):
            self._show_detail(event.cursor_row)

    def _show_detail(self, index: int) -> None:
        """Show detail for the selected recommendation."""
        if index < 0 or index >= len(self._rec_list):
            return

        rec = self._rec_list[index]
        detail_view = self.query_one("#detail-view", ViewDetailView)
        detail_view.show_recommendation(rec)

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
        self._rec_list = []

        sorted_recs = sorted(
            self.recommendations,
            key=lambda r: natural_sort_key(r.get("ref", "")),
            reverse=self._sort_reverse,
        )

        for rec in sorted_recs:
            self._rec_list.append(rec)

            profiles = ", ".join(rec.get("profiles", []))[:20]
            if len(", ".join(rec.get("profiles", []))) > 20:
                profiles = profiles[:17] + "..."

            status = rec.get("assessment_status", "")
            if status.lower() == "automated":
                status_display = Text("Auto", style="green")
            elif status.lower() == "manual":
                status_display = Text("Manual", style="yellow")
            else:
                status_display = Text(status[:8] if status else "", style="dim")

            table.add_row(
                rec.get("ref", ""),
                self._truncate(rec.get("title", ""), 45),
                profiles,
                status_display,
            )

        if self._rec_list:
            self._show_detail(0)

    def action_save_report(self) -> None:
        """Open save dialog."""
        title = self.benchmark.get("title", "benchmark")
        safe_title = "".join(c if c.isalnum() or c in "- " else "_" for c in title)
        safe_title = safe_title.replace(" ", "-").lower()[:40]
        version = self.benchmark.get("version", "v1")
        default_name = f"{safe_title}-{version}.md"

        self.push_screen(SaveDialog(default_name), self._do_save)

    def _do_save(self, filename: str | None) -> None:
        """Save the report to file."""
        if not filename:
            return

        # Generate full report
        report_lines = [
            f"# {self.benchmark.get('title', 'Benchmark')}",
            "",
            f"**Version:** {self.benchmark.get('version', 'unknown')}",
            f"**Total Recommendations:** {len(self.recommendations)}",
            "",
            "---",
            "",
        ]

        # Add each recommendation
        detail_view = ViewDetailView()
        for rec in self._rec_list:
            content = detail_view.render_recommendation(rec)
            report_lines.append(content)
            report_lines.append("")
            report_lines.append("---")
            report_lines.append("")

        # Write to file
        try:
            with open(filename, "w") as f:
                f.write("\n".join(report_lines))
            self.notify(f"Saved to {filename}", title="Report Saved")
        except Exception as e:
            self.notify(f"Error saving: {e}", title="Save Failed", severity="error")


def run_interactive_view(benchmark: dict, recommendations: list, offline: bool = False) -> None:
    """Run the interactive view TUI.

    Args:
        benchmark: The benchmark data dict
        recommendations: List of recommendations to display (may be filtered)
        offline: Whether running in offline mode (shows indicator)
    """
    app = ViewApp(benchmark, recommendations, offline=offline)
    app.title = "CIS Benchmark Viewer"
    app.run()
