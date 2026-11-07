"""Pushable screens for TUI navigation.

These screens can be pushed onto any App's screen stack for seamless navigation.
They inherit from BaseBrowserScreen which provides all common functionality.
"""

from rich.text import Text
from textual.binding import Binding
from textual.widgets import DataTable, Static

from cis_bench.cli.commands.tui.base import (
    BaseBrowserScreen,
    natural_sort_key,
)
from cis_bench.cli.commands.tui.diff.detail import DiffDetailView
from cis_bench.cli.commands.tui.view.detail import ViewDetailView
from cis_bench.cli.commands.tui.widgets import SaveDialog


class ViewScreen(BaseBrowserScreen):
    """Screen for viewing a single benchmark's recommendations.

    Push this screen onto an App to view benchmark details.
    Pop to return to the previous screen.
    """

    has_search_container = False  # ViewScreen doesn't need search

    def __init__(
        self,
        benchmark: dict,
        recommendations: list,
        offline: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.benchmark = benchmark
        self.recommendations = recommendations
        self.offline = offline

    def get_detail_view(self) -> Static:
        return ViewDetailView(id="detail-view")

    def _get_columns(self) -> list[str]:
        return ["Ref", "Title", "Profiles", "Status"]

    def _build_summary(self) -> Text:
        text = Text()
        if self.offline:
            text.append("[OFFLINE] ", style="bold yellow")
        text.append(f"{self.benchmark.get('title', 'Benchmark')}", style="bold")
        text.append(f" v{self.benchmark.get('version', '?')}  ", style="dim")
        text.append(f"{len(self.recommendations)} recommendations", style="cyan")
        text.append("  [Esc] Back", style="dim italic")
        return text

    def _populate_table(self) -> None:
        table = self.query_one("#changes-table", DataTable)
        sorted_recs = sorted(
            self.recommendations,
            key=lambda r: natural_sort_key(r.get("ref", "")),
            reverse=self._sort_reverse,
        )
        for rec in sorted_recs:
            self._items.append(rec)
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

    def _rebuild_table(self) -> None:
        table = self.query_one("#changes-table", DataTable)
        table.clear()
        self._items = []
        self._populate_table()
        if self._items:
            self._show_detail(0)

    def _show_detail(self, index: int) -> None:
        if index < 0 or index >= len(self._items):
            return
        rec = self._items[index]
        detail_view = self.query_one("#detail-view", ViewDetailView)
        detail_view.show_recommendation(rec)

    def action_save_report(self) -> None:
        title = self.benchmark.get("title", "benchmark")
        safe_title = "".join(c if c.isalnum() or c in "- " else "_" for c in title)
        safe_title = safe_title.replace(" ", "-").lower()[:40]
        version = self.benchmark.get("version", "v1")
        default_name = f"{safe_title}-{version}.md"
        self.app.push_screen(SaveDialog(default_name), self._do_save)

    def _do_save(self, filename: str | None) -> None:
        if not filename:
            return
        report_lines = [
            f"# {self.benchmark.get('title', 'Benchmark')}",
            "",
            f"**Version:** {self.benchmark.get('version', 'unknown')}",
            f"**Total Recommendations:** {len(self.recommendations)}",
            "",
            "---",
            "",
        ]
        detail_view = ViewDetailView()
        for rec in self._items:
            content = detail_view.render_recommendation(rec)
            report_lines.extend([content, "", "---", ""])
        try:
            with open(filename, "w") as f:
                f.write("\n".join(report_lines))
            self.notify(f"Saved to {filename}", title="Report Saved")
        except Exception as e:
            self.notify(f"Error saving: {e}", title="Save Failed", severity="error")


class DiffScreen(BaseBrowserScreen):
    """Screen for viewing benchmark diff comparison.

    Push this screen onto an App to view diff details.
    Pop to return to the previous screen.
    """

    has_search_container = False  # DiffScreen doesn't need search

    # Add filter bindings on top of base screen bindings
    BINDINGS = BaseBrowserScreen.BINDINGS + [
        Binding("1", "filter_added", "Added Only", show=False),
        Binding("2", "filter_removed", "Removed Only", show=False),
        Binding("3", "filter_modified", "Modified Only", show=False),
        Binding("4", "filter_renumbered", "Renumbered Only", show=False),
        Binding("0", "filter_all", "Show All", show=False),
    ]

    def __init__(
        self,
        comparison: dict,
        old_data: dict,
        new_data: dict,
        offline: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.comparison = comparison
        self.old_data = old_data
        self.new_data = new_data
        self.offline = offline
        self._all_items: list = []
        self._current_filter = "all"
        # Build recommendation lookup dicts
        self._old_recs = {r["ref"]: r for r in old_data.get("recommendations", [])}
        self._new_recs = {r["ref"]: r for r in new_data.get("recommendations", [])}

    def get_detail_view(self) -> Static:
        return DiffDetailView(id="detail-view")

    def _get_columns(self) -> list[str]:
        return ["Status", "Ref", "Title", "Details"]

    def _build_summary(self) -> Text:
        text = Text()
        if self.offline:
            text.append("[OFFLINE] ", style="bold yellow")
        text.append(f"{self.comparison.get('benchmark_title', 'Diff')}", style="bold")
        text.append(
            f"  {self.comparison.get('old_version')} → {self.comparison.get('new_version')}  ",
            style="dim",
        )
        summary = self.comparison.get("summary", {})
        text.append(f"+{summary.get('added', 0)} ", style="green")
        text.append(f"-{summary.get('removed', 0)} ", style="red")
        text.append(f"~{summary.get('modified', 0)}", style="yellow")
        text.append("  [Esc] Back", style="dim italic")
        return text

    def on_mount(self) -> None:
        # Build all items before standard mount (which calls _populate_table)
        self._build_all_items()
        super().on_mount()

    def _build_all_items(self) -> None:
        """Build the list of all change items."""
        changes = self.comparison.get("changes", {})
        self._all_items = []

        for item in changes.get("added", []):
            self._all_items.append(
                {
                    "type": "added",
                    "ref": item["ref"],
                    "title": item["title"],
                    "details": "New recommendation",
                }
            )

        for item in changes.get("removed", []):
            self._all_items.append(
                {
                    "type": "removed",
                    "ref": item["ref"],
                    "title": item["title"],
                    "details": "Removed",
                }
            )

        for item in changes.get("modified", []):
            fields_changed = item.get("fields_changed", [])
            fields = ", ".join(fields_changed[:3])
            if len(fields_changed) > 3:
                fields += f" +{len(fields_changed) - 3}"
            self._all_items.append(
                {
                    "type": "modified",
                    "ref": item["ref"],
                    "title": item["title"],
                    "details": fields,
                    "fields_changed": fields_changed,
                    "diff": item.get("diff", {}),
                }
            )

        for item in changes.get("renumbered", []):
            self._all_items.append(
                {
                    "type": "renumbered",
                    "old_ref": item["old_ref"],
                    "new_ref": item["new_ref"],
                    "ref": item["new_ref"],
                    "title": item["title"],
                    "details": f"{item['old_ref']} → {item['new_ref']}",
                    "similarity": item.get("similarity", "?"),
                }
            )

    def _populate_table(self) -> None:
        table = self.query_one("#changes-table", DataTable)
        table.clear()
        self._items = []

        # Filter items
        items_to_show = self._all_items
        if self._current_filter != "all":
            items_to_show = [i for i in self._all_items if i["type"] == self._current_filter]

        # Sort by ref
        sorted_items = sorted(
            items_to_show,
            key=lambda x: natural_sort_key(x.get("ref", "")),
            reverse=self._sort_reverse,
        )

        for item in sorted_items:
            self._items.append(item)
            item_type = item["type"]

            if item_type == "added":
                status = Text("✚ Added", style="green")
            elif item_type == "removed":
                status = Text("✖ Removed", style="red")
            elif item_type == "modified":
                status = Text("⟳ Modified", style="yellow")
            elif item_type == "renumbered":
                status = Text("↷ Renumbered", style="cyan")
            else:
                status = Text(item_type)

            table.add_row(
                status,
                item.get("ref", ""),
                self._truncate(item.get("title", ""), 40),
                item.get("details", ""),
            )

    def _rebuild_table(self) -> None:
        self._populate_table()
        if self._items:
            self._show_detail(0)

    def _show_detail(self, index: int) -> None:
        if index < 0 or index >= len(self._items):
            return
        item = self._items[index]
        detail_view = self.query_one("#detail-view", DiffDetailView)

        item_type = item["type"]
        ref = item.get("ref", "")

        if item_type == "added":
            new_rec = self._new_recs.get(ref, {})
            detail_view.update_content(item_type, item, None, new_rec)
        elif item_type == "removed":
            old_rec = self._old_recs.get(ref, {})
            detail_view.update_content(item_type, item, old_rec, None)
        elif item_type == "modified":
            old_rec = self._old_recs.get(ref, {})
            new_rec = self._new_recs.get(ref, {})
            detail_view.update_content(item_type, item, old_rec, new_rec)
        elif item_type == "renumbered":
            old_ref = item.get("old_ref", "")
            old_rec = self._old_recs.get(old_ref, {})
            new_rec = self._new_recs.get(ref, {})
            detail_view.update_content(item_type, item, old_rec, new_rec)

    # Filter actions
    def action_filter_added(self) -> None:
        self._current_filter = "added"
        self._populate_table()
        self.notify("Showing: Added only", severity="information")

    def action_filter_removed(self) -> None:
        self._current_filter = "removed"
        self._populate_table()
        self.notify("Showing: Removed only", severity="information")

    def action_filter_modified(self) -> None:
        self._current_filter = "modified"
        self._populate_table()
        self.notify("Showing: Modified only", severity="information")

    def action_filter_renumbered(self) -> None:
        self._current_filter = "renumbered"
        self._populate_table()
        self.notify("Showing: Renumbered only", severity="information")

    def action_filter_all(self) -> None:
        self._current_filter = "all"
        self._populate_table()
        self.notify("Showing: All changes", severity="information")

    def action_save_report(self) -> None:
        old_ver = self.comparison.get("old_version", "old")
        new_ver = self.comparison.get("new_version", "new")
        default_name = f"diff-{old_ver}-to-{new_ver}.md"
        self.app.push_screen(SaveDialog(default_name), self._do_save)

    def _do_save(self, filename: str | None) -> None:
        if not filename:
            return
        summary = self.comparison.get("summary", {})
        report_lines = [
            f"# Benchmark Diff: {self.comparison.get('benchmark_title', '')}",
            "",
            f"**{self.comparison.get('old_version')}** → **{self.comparison.get('new_version')}**",
            "",
            "## Summary",
            f"- Added: {summary.get('added', 0)}",
            f"- Removed: {summary.get('removed', 0)}",
            f"- Modified: {summary.get('modified', 0)}",
            f"- Renumbered: {summary.get('renumbered', 0)}",
            "",
            "---",
            "",
        ]
        for item in self._items:
            item_type = item["type"]
            ref = item.get("ref", "")
            title = item.get("title", "")
            report_lines.append(f"### [{item_type.upper()}] {ref}: {title}")
            report_lines.append("")
        try:
            with open(filename, "w") as f:
                f.write("\n".join(report_lines))
            self.notify(f"Saved to {filename}", title="Report Saved")
        except Exception as e:
            self.notify(f"Error saving: {e}", title="Save Failed", severity="error")
