"""View detail view component."""

from cis_bench.cli.commands.tui.base import DetailView


class ViewDetailView(DetailView):
    """Shows detailed recommendation content."""

    def show_recommendation(self, rec: dict) -> None:
        """Display a recommendation's full details."""
        content = self.render_recommendation(rec)
        self.set_content(content)
