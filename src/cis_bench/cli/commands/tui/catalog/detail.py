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

        # Publication & Release Info
        if (
            benchmark.get("published_date")
            or benchmark.get("release_type")
            or benchmark.get("last_revision_date")
        ):
            lines.append("## Publication")
            lines.append("")
            if benchmark.get("published_date"):
                lines.append(f"**Published:** {benchmark['published_date']}  ")
            if benchmark.get("last_revision_date"):
                lines.append(f"**Last Revision:** {benchmark['last_revision_date']}  ")
            if benchmark.get("release_type"):
                lines.append(f"**Release Type:** {benchmark['release_type']}  ")
            if benchmark.get("milestone_name"):
                lines.append(f"**Milestone:** {benchmark['milestone_name']}  ")
            lines.append("")

        # Lineage
        if benchmark.get("parent_benchmark_url"):
            lines.append("## Lineage")
            lines.append("")
            parent_title = benchmark.get("parent_benchmark_title", "Parent Benchmark")
            lines.append(f"**Forked From:** {parent_title}  ")
            lines.append(f"*{benchmark['parent_benchmark_url']}*  ")
            lines.append("")

        # Assets (CPE-IDs)
        # Note: assets come from downloaded benchmarks, not catalog
        # Catalog might not have this data unless benchmark was downloaded

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

        # Contributors
        if benchmark.get("contributors"):
            lines.append("## Contributors")
            lines.append("")
            # Contributors stored as comma-separated string in catalog DB
            lines.append(benchmark["contributors"])
            lines.append("")

        # Intended Audience
        if benchmark.get("intended_audience"):
            lines.append("## Intended Audience")
            lines.append("")
            lines.append(benchmark["intended_audience"])
            lines.append("")

        # Acknowledgements
        if benchmark.get("acknowledgements"):
            lines.append("## Acknowledgements")
            lines.append("")
            lines.append(benchmark["acknowledgements"])
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
