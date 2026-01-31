"""Catalog detail view component."""

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

        lines = []

        # Title and ID
        title = benchmark.get("title", "Unknown Benchmark")
        benchmark_id = benchmark.get("benchmark_id", "")
        version = benchmark.get("version", "")
        lines.append(f"# {title}")
        if version:
            lines.append(f"**Version {version}**")
        lines.append("")

        # Metadata section - vertical list with line breaks
        lines.append("## Details")
        lines.append("")

        # Each field on its own line (two trailing spaces = markdown line break)
        if benchmark_id:
            lines.append(f"**ID:** {benchmark_id}  ")
        if benchmark.get("status"):
            lines.append(f"**Status:** {benchmark['status']}  ")
        if benchmark.get("is_latest"):
            lines.append("★ **Latest Version**  ")
        lines.append("")

        # Dates
        if benchmark.get("published_date") or benchmark.get("last_revision_date"):
            lines.append("## Dates")
            lines.append("")
            if benchmark.get("published_date"):
                lines.append(f"**Published:** {benchmark['published_date']}  ")
            if benchmark.get("last_revision_date"):
                lines.append(f"**Last Revision:** {benchmark['last_revision_date']}  ")
            lines.append("")

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
            lines.append("## Classification")
            lines.append("")
            if benchmark.get("collections"):
                lines.append(f"**Collections:** {benchmark['collections']}  ")
            if benchmark.get("platform"):
                lines.append(f"**Platform:** {benchmark['platform']}  ")
            if benchmark.get("platform_type"):
                lines.append(f"**Type:** {benchmark['platform_type']}  ")
            if benchmark.get("community"):
                lines.append(f"**Community:** {benchmark['community']}  ")
            if benchmark.get("owner"):
                lines.append(f"**Owner:** {benchmark['owner']}  ")
            lines.append("")

        # Description
        if benchmark.get("description"):
            lines.append("## Description")
            lines.append("")
            lines.append(benchmark["description"])
            lines.append("")

        # URL with keybinding hint
        if benchmark.get("url"):
            lines.append("## WorkBench URL")
            lines.append("")
            lines.append(f"{benchmark['url']}  ")
            lines.append("*Press 'o' to open in browser*")
            lines.append("")

        # Actions hint
        lines.append("---")
        lines.append("*Press Enter for actions menu*")

        self.set_content("\n".join(lines))
