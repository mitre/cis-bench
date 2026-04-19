"""Catalog detail view component."""

from rich.console import Group
from rich.markdown import Markdown
from rich.text import Text

from cis_bench.cli.commands.tui.base import DetailView


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

        # Build rich content with styled elements
        parts = []

        # Title (large, bold)
        title = benchmark.get("title", "Unknown Benchmark")
        title_text = Text(title, style="bold cyan")
        parts.append(title_text)
        parts.append(Text(""))

        # Version badge
        version = benchmark.get("version", "")
        if version:
            version_text = Text()
            version_text.append("Version ", style="dim")
            version_text.append(version, style="bold green")
            parts.append(version_text)
            parts.append(Text(""))

        # Status line with colored indicator
        benchmark_id = benchmark.get("benchmark_id", "")
        if benchmark_id:
            id_text = Text()
            id_text.append("ID: ", style="bold")
            id_text.append(benchmark_id, style="cyan")
            parts.append(id_text)

        if benchmark.get("status"):
            status = benchmark["status"]
            status_text = Text()
            status_text.append("Status: ", style="bold")
            if status == "Published":
                status_text.append("● ", style="green")
                status_text.append(status, style="green")
            else:
                status_text.append("● ", style="yellow")
                status_text.append(status, style="yellow")
            parts.append(status_text)

        if benchmark.get("is_latest"):
            latest_text = Text()
            latest_text.append("★ ", style="yellow bold")
            latest_text.append("Latest Version", style="yellow bold")
            parts.append(latest_text)

        parts.append(Text(""))

        # Build markdown for the rest (sections with headers)
        md_lines = []

        # Publication & Release Info
        if (
            benchmark.get("published_date")
            or benchmark.get("release_type")
            or benchmark.get("last_revision_date")
        ):
            md_lines.append("## Publication")
            md_lines.append("")
            if benchmark.get("published_date"):
                md_lines.append(f"**Published:** {benchmark['published_date']}  ")
            if benchmark.get("last_revision_date"):
                md_lines.append(f"**Last Revision:** {benchmark['last_revision_date']}  ")
            if benchmark.get("release_type"):
                md_lines.append(f"**Release Type:** {benchmark['release_type']}  ")
            if benchmark.get("milestone_name"):
                md_lines.append(f"**Milestone:** {benchmark['milestone_name']}  ")
            md_lines.append("")

        # Lineage
        if benchmark.get("parent_benchmark_url"):
            md_lines.append("## Lineage")
            md_lines.append("")
            parent_title = benchmark.get("parent_benchmark_title", "Parent Benchmark")
            md_lines.append(f"**Forked From:** {parent_title}  ")
            md_lines.append(f"*{benchmark['parent_benchmark_url']}*  ")
            md_lines.append("")

        # Classification
        has_classification = any(
            [
                benchmark.get("platform"),
                benchmark.get("platform_type"),
                benchmark.get("community"),
                benchmark.get("owner"),
                benchmark.get("collections"),
            ]
        )
        if has_classification:
            md_lines.append("## Classification")
            md_lines.append("")
            if benchmark.get("collections"):
                md_lines.append(f"**Collections:** {benchmark['collections']}  ")
            if benchmark.get("platform"):
                md_lines.append(f"**Platform:** {benchmark['platform']}  ")
            if benchmark.get("platform_type"):
                md_lines.append(f"**Type:** {benchmark['platform_type']}  ")
            if benchmark.get("community"):
                md_lines.append(f"**Community:** {benchmark['community']}  ")
            if benchmark.get("owner"):
                md_lines.append(f"**Owner:** {benchmark['owner']}  ")
            md_lines.append("")

        # Description
        if benchmark.get("description"):
            md_lines.append("## Description")
            md_lines.append("")
            md_lines.append(benchmark["description"])
            md_lines.append("")

        # Contributors
        if benchmark.get("contributors"):
            md_lines.append("## Contributors")
            md_lines.append("")
            md_lines.append(benchmark["contributors"])
            md_lines.append("")

        # Intended Audience
        if benchmark.get("intended_audience"):
            md_lines.append("## Intended Audience")
            md_lines.append("")
            md_lines.append(benchmark["intended_audience"])
            md_lines.append("")

        # Acknowledgements
        if benchmark.get("acknowledgements"):
            md_lines.append("## Acknowledgements")
            md_lines.append("")
            md_lines.append(benchmark["acknowledgements"])
            md_lines.append("")

        # URL with keybinding hint
        if benchmark.get("url"):
            md_lines.append("## WorkBench URL")
            md_lines.append("")
            md_lines.append(f"`{benchmark['url']}`  ")
            md_lines.append("*Press 'o' to open in browser*")
            md_lines.append("")

        # Actions hint
        md_lines.append("---")
        md_lines.append("*Press 'v' to view, 'd' to diff, 'e' to export*")

        # Combine styled header with markdown body
        if md_lines:
            parts.append(Markdown("\n".join(md_lines)))

        # Store plain text for copy function
        self._content_text = f"{title}\nVersion {version}\nID: {benchmark_id}\n" + "\n".join(
            md_lines
        )

        # Render combined content
        self.update(Group(*parts))
