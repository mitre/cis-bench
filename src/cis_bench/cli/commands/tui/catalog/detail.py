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

        # Metadata section
        lines.append("## Details")
        lines.append("")

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
            lines.append("**Latest Version:** ★ Yes")
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
        lines.append("*Press Enter for actions menu*")

        self.set_content("\n".join(lines))
