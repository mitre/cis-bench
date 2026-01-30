"""Diff browser TUI application."""

from rich.text import Text
from textual.binding import Binding
from textual.widgets import DataTable, Static

from cis_bench.cli.commands.tui.base import (
    COMMON_BINDINGS,
    COMMON_CSS,
    BaseBrowserApp,
    natural_sort_key,
)
from cis_bench.cli.commands.tui.diff.detail import DiffDetailView
from cis_bench.cli.commands.tui.widgets import SaveDialog


class DiffApp(BaseBrowserApp):
    """Interactive TUI for exploring benchmark differences."""

    CSS = COMMON_CSS

    # Extend COMMON_BINDINGS with diff-specific bindings
    BINDINGS = COMMON_BINDINGS + [
        # Selection
        Binding("space", "toggle_select", "Select", show=True),
        # Filter by change type
        Binding("1", "filter_added", "Added Only", show=False),
        Binding("2", "filter_removed", "Removed Only", show=False),
        Binding("3", "filter_modified", "Modified Only", show=False),
        Binding("4", "filter_renumbered", "Renumbered Only", show=False),
        Binding("0", "filter_all", "Show All", show=False),
    ]

    def __init__(
        self, comparison: dict, old_recs: dict, new_recs: dict, offline: bool = False, **kwargs
    ):
        super().__init__(**kwargs)
        self.comparison = comparison
        self.old_recs = old_recs
        self.new_recs = new_recs
        self.offline = offline
        # Standardized naming: _items for visible, _all_items for unfiltered
        self._items = []
        self._all_items = []  # Store all changes for search filtering
        self._sort_reverse = False
        self._selected_indices: set[int] = set()  # Track selected row indices

    def get_detail_view(self) -> Static:
        """Return the diff detail view widget."""
        return DiffDetailView(id="detail-view")

    def _get_columns(self) -> list[str]:
        """Return column headers for diff table."""
        return ["Status", "Ref", "Title", "Details"]

    def _build_summary(self) -> Text:
        """Build summary text."""
        s = self.comparison["summary"]
        text = Text()
        if self.offline:
            text.append("[OFFLINE] ", style="bold yellow")
        text.append(f"{self.comparison['benchmark_title']}: ", style="bold")
        text.append(
            f"{self.comparison['old_version']} → {self.comparison['new_version']}  ",
            style="dim",
        )
        text.append(f"+{s['added']} ", style="green")
        text.append(f"✖{s['removed']} ", style="red")
        text.append(f"⟳{s['modified']} ", style="yellow")
        text.append(f"↷{s['renumbered']}", style="cyan")
        return text

    def _populate_table(self) -> None:
        """Populate the table with change data."""
        table = self.query_one("#changes-table", DataTable)
        changes = self.comparison["changes"]

        # Sort each category by ref (natural/version sort)
        added = sorted(changes["added"], key=lambda x: natural_sort_key(x.get("ref", "")))
        removed = sorted(changes["removed"], key=lambda x: natural_sort_key(x.get("ref", "")))
        modified = sorted(changes["modified"], key=lambda x: natural_sort_key(x.get("ref", "")))
        renumbered = sorted(
            changes["renumbered"], key=lambda x: natural_sort_key(x.get("new_ref", ""))
        )

        # Build full change list for filtering
        self._all_items = []
        for item in added:
            self._all_items.append(("added", item))
        for item in removed:
            self._all_items.append(("removed", item))
        for item in modified:
            self._all_items.append(("modified", item))
        for item in renumbered:
            self._all_items.append(("renumbered", item))

        # Add rows and track change data
        for item in added:
            self._items.append(("added", item))
            table.add_row(
                Text("✚ Added", style="green"),
                item["ref"],
                self._truncate(item["title"], 45),
                "New",
            )

        for item in removed:
            self._items.append(("removed", item))
            table.add_row(
                Text("✖ Removed", style="red"),
                item["ref"],
                self._truncate(item["title"], 45),
                "Removed",
            )

        for item in modified:
            self._items.append(("modified", item))
            fields = item["fields_changed"]
            if len(fields) <= 2:
                details = ", ".join(fields)
            else:
                details = ", ".join(fields[:2]) + f" +{len(fields) - 2}"
            table.add_row(
                Text("⟳ Modified", style="yellow"),
                item["ref"],
                self._truncate(item["title"], 45),
                details,
            )

        for item in renumbered:
            self._items.append(("renumbered", item))
            table.add_row(
                Text("↷ Renum", style="cyan"),
                f"{item['old_ref']}→{item['new_ref']}",
                self._truncate(item["title"], 45),
                f"{item['similarity']}%",
            )

    def _show_detail(self, index: int) -> None:
        """Show detail for the selected change."""
        if index < 0 or index >= len(self._items):
            return

        change_type, change_data = self._items[index]
        detail_view = self.query_one("#detail-view", DiffDetailView)

        # Get old/new recommendation data
        if change_type == "added":
            old_rec = None
            new_rec = self.new_recs.get(change_data["ref"])
        elif change_type == "removed":
            old_rec = self.old_recs.get(change_data["ref"])
            new_rec = None
        elif change_type == "modified":
            old_rec = self.old_recs.get(change_data["ref"])
            new_rec = self.new_recs.get(change_data["ref"])
        elif change_type == "renumbered":
            old_rec = self.old_recs.get(change_data["old_ref"])
            new_rec = self.new_recs.get(change_data["new_ref"])
        else:
            old_rec = None
            new_rec = None

        detail_view.update_content(change_type, change_data, old_rec, new_rec)

    def action_reverse_sort(self) -> None:
        """Toggle sort order (asc/desc)."""
        self._sort_reverse = not self._sort_reverse
        self._rebuild_table()
        direction = "descending" if self._sort_reverse else "ascending"
        self.notify(f"Sort: {direction}", title="Sort Order")

    def action_toggle_select(self) -> None:
        """Toggle selection on the current row."""
        table = self.query_one("#changes-table", DataTable)
        current_row = table.cursor_row

        if current_row in self._selected_indices:
            self._selected_indices.remove(current_row)
        else:
            self._selected_indices.add(current_row)

        # Update visual indicator (for now just notify)
        count = len(self._selected_indices)
        if count > 0:
            self.notify(f"Selected: {count} items", severity="information")

    def get_selected_items(self) -> list[tuple[str, dict]]:
        """Get the selected items from the change list.

        Returns:
            List of (change_type, item_data) tuples for selected items.
        """
        return [
            self._items[idx] for idx in sorted(self._selected_indices) if idx < len(self._items)
        ]

    def action_filter_added(self) -> None:
        """Filter to show only added items."""
        self._filter_by_type("added")
        self.notify("Showing: Added only", severity="information")

    def action_filter_removed(self) -> None:
        """Filter to show only removed items."""
        self._filter_by_type("removed")
        self.notify("Showing: Removed only", severity="information")

    def action_filter_modified(self) -> None:
        """Filter to show only modified items."""
        self._filter_by_type("modified")
        self.notify("Showing: Modified only", severity="information")

    def action_filter_renumbered(self) -> None:
        """Filter to show only renumbered items."""
        self._filter_by_type("renumbered")
        self.notify("Showing: Renumbered only", severity="information")

    def action_filter_all(self) -> None:
        """Reset filter to show all items."""
        self._filter_by_type(None)
        self.notify("Showing: All changes", severity="information")

    def _filter_by_type(self, change_type: str | None) -> None:
        """Filter the table to show only items of a specific type.

        Args:
            change_type: Type to filter by (added/removed/modified/renumbered) or None for all.
        """
        table = self.query_one("#changes-table", DataTable)
        table.clear()
        self._items = []

        # Filter from _all_changes
        if change_type is None:
            # Show all
            filtered = self._all_items
        else:
            filtered = [(t, item) for t, item in self._all_items if t == change_type]

        # Re-sort the filtered list
        filtered = sorted(
            filtered,
            key=lambda x: natural_sort_key(x[1].get("ref", "") or x[1].get("new_ref", "")),
            reverse=self._sort_reverse,
        )

        # Add to table
        for change_type_item, item in filtered:
            self._items.append((change_type_item, item))
            if change_type_item == "added":
                table.add_row(
                    Text("✚ Added", style="green"),
                    item["ref"],
                    self._truncate(item["title"], 45),
                    "New",
                )
            elif change_type_item == "removed":
                table.add_row(
                    Text("✖ Removed", style="red"),
                    item["ref"],
                    self._truncate(item["title"], 45),
                    "Removed",
                )
            elif change_type_item == "modified":
                fields = ", ".join(item.get("fields_changed", [])[:3])
                table.add_row(
                    Text("⟳ Modified", style="yellow"),
                    item["ref"],
                    self._truncate(item["title"], 45),
                    fields,
                )
            elif change_type_item == "renumbered":
                table.add_row(
                    Text("↷ Renumbered", style="cyan"),
                    f"{item['old_ref']}→{item['new_ref']}",
                    self._truncate(item["title"], 45),
                    f"{item['similarity']}%",
                )

    def _rebuild_table(self) -> None:
        """Rebuild the table with current sort order."""
        table = self.query_one("#changes-table", DataTable)
        table.clear()
        self._items = []

        changes = self.comparison["changes"]

        # Sort each category by ref
        added = sorted(
            changes["added"],
            key=lambda x: natural_sort_key(x.get("ref", "")),
            reverse=self._sort_reverse,
        )
        removed = sorted(
            changes["removed"],
            key=lambda x: natural_sort_key(x.get("ref", "")),
            reverse=self._sort_reverse,
        )
        modified = sorted(
            changes["modified"],
            key=lambda x: natural_sort_key(x.get("ref", "")),
            reverse=self._sort_reverse,
        )
        renumbered = sorted(
            changes["renumbered"],
            key=lambda x: natural_sort_key(x.get("new_ref", "")),
            reverse=self._sort_reverse,
        )

        for item in added:
            self._items.append(("added", item))
            table.add_row(
                Text("✚ Added", style="green"),
                item["ref"],
                self._truncate(item["title"], 45),
                "New",
            )

        for item in removed:
            self._items.append(("removed", item))
            table.add_row(
                Text("✖ Removed", style="red"),
                item["ref"],
                self._truncate(item["title"], 45),
                "Removed",
            )

        for item in modified:
            self._items.append(("modified", item))
            fields = item["fields_changed"]
            if len(fields) <= 2:
                details = ", ".join(fields)
            else:
                details = ", ".join(fields[:2]) + f" +{len(fields) - 2}"
            table.add_row(
                Text("⟳ Modified", style="yellow"),
                item["ref"],
                self._truncate(item["title"], 45),
                details,
            )

        for item in renumbered:
            self._items.append(("renumbered", item))
            table.add_row(
                Text("↷ Renum", style="cyan"),
                f"{item['old_ref']}→{item['new_ref']}",
                self._truncate(item["title"], 45),
                f"{item['similarity']}%",
            )

        if self._items:
            self._show_detail(0)

    def _apply_search_filter(self, query: str) -> None:
        """Filter the table based on search query."""
        query = query.lower().strip()
        table = self.query_one("#changes-table", DataTable)
        table.clear()
        self._items = []

        for change_type, item in self._all_items:
            # Check if query matches ref or title
            ref = item.get("ref", "") or item.get("new_ref", "") or item.get("old_ref", "")
            title = item.get("title", "")

            if query and query not in ref.lower() and query not in title.lower():
                continue

            self._items.append((change_type, item))

            if change_type == "added":
                table.add_row(
                    Text("✚ Added", style="green"),
                    item["ref"],
                    self._truncate(item["title"], 45),
                    "New",
                )
            elif change_type == "removed":
                table.add_row(
                    Text("✖ Removed", style="red"),
                    item["ref"],
                    self._truncate(item["title"], 45),
                    "Removed",
                )
            elif change_type == "modified":
                fields = item["fields_changed"]
                if len(fields) <= 2:
                    details = ", ".join(fields)
                else:
                    details = ", ".join(fields[:2]) + f" +{len(fields) - 2}"
                table.add_row(
                    Text("⟳ Modified", style="yellow"),
                    item["ref"],
                    self._truncate(item["title"], 45),
                    details,
                )
            elif change_type == "renumbered":
                table.add_row(
                    Text("↷ Renum", style="cyan"),
                    f"{item['old_ref']}→{item['new_ref']}",
                    self._truncate(item["title"], 45),
                    f"{item['similarity']}%",
                )

        # Update search count
        search_count = self.query_one("#search-count", Static)
        if query:
            search_count.update(f"{len(self._items)}/{len(self._all_items)}")
        else:
            search_count.update("")

        if self._items:
            self._show_detail(0)

    def action_save_report(self) -> None:
        """Open save dialog."""
        # Generate default filename
        title = self.comparison.get("benchmark_title", "benchmark")
        safe_title = "".join(c if c.isalnum() or c in "- " else "_" for c in title)
        safe_title = safe_title.replace(" ", "-").lower()[:30]
        old_v = self.comparison.get("old_version", "v1")
        new_v = self.comparison.get("new_version", "v2")
        default_name = f"diff-{safe_title}-{old_v}-to-{new_v}.md"

        self.push_screen(SaveDialog(default_name), self._do_save)

    def _do_save(self, filename: str | None) -> None:
        """Save the report to file."""
        if not filename:
            return

        # Generate full report
        report_lines = [
            "# Benchmark Diff Report",
            "",
            f"**{self.comparison['benchmark_title']}**",
            f"Version: {self.comparison['old_version']} → {self.comparison['new_version']}",
            "",
            "## Summary",
            "",
            f"- **Added:** {self.comparison['summary']['added']}",
            f"- **Removed:** {self.comparison['summary']['removed']}",
            f"- **Modified:** {self.comparison['summary']['modified']}",
            f"- **Renumbered:** {self.comparison['summary']['renumbered']}",
            f"- **Unchanged:** {self.comparison['summary']['unchanged']}",
            "",
            "---",
            "",
        ]

        # Add each change
        for change_type, change_data in self._items:
            if change_type == "added":
                old_rec = None
                new_rec = self.new_recs.get(change_data["ref"])
            elif change_type == "removed":
                old_rec = self.old_recs.get(change_data["ref"])
                new_rec = None
            elif change_type == "modified":
                old_rec = self.old_recs.get(change_data["ref"])
                new_rec = self.new_recs.get(change_data["ref"])
            elif change_type == "renumbered":
                old_rec = self.old_recs.get(change_data["old_ref"])
                new_rec = self.new_recs.get(change_data["new_ref"])
            else:
                continue

            # Create a temporary detail view to get content
            temp_view = DiffDetailView()
            temp_view.update_content(change_type, change_data, old_rec, new_rec)
            report_lines.append(temp_view.get_content_text())
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


def run_interactive_diff(
    comparison: dict, old_data: dict, new_data: dict, offline: bool = False
) -> None:
    """Run the interactive diff TUI.

    Args:
        comparison: The comparison result from compare_benchmarks()
        old_data: The old benchmark data dict
        new_data: The new benchmark data dict
        offline: Whether running in offline mode (shows indicator)
    """
    # Build recommendation lookup dicts
    old_recs = {r["ref"]: r for r in old_data.get("recommendations", [])}
    new_recs = {r["ref"]: r for r in new_data.get("recommendations", [])}

    app = DiffApp(comparison, old_recs, new_recs, offline=offline)
    app.title = "CIS Benchmark Diff"
    app.run()
