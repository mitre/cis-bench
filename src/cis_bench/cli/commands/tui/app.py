"""Unified CIS Bench TUI application.

This module provides a single App class that handles all TUI modes:
- catalog: Browse the CIS benchmark catalog
- view: View a single benchmark's recommendations
- diff: Compare two benchmark versions

SPA Architecture:
- CISBenchApp is the shell that manages screens
- Screens are pushed/popped for navigation
- All screens share common bindings and styling
"""

import logging

from textual.app import App
from textual.binding import Binding

from cis_bench.cli.commands.tui.base import COMMON_CSS

logger = logging.getLogger(__name__)


class CISBenchApp(App):
    """Unified TUI application for CIS Bench.

    This is the single app class that hosts all screens. It can be started
    in different modes based on the CLI command used.

    Modes:
        catalog: Shows the benchmark catalog browser
        view: Shows a single benchmark's recommendations
        diff: Shows comparison between two benchmarks

    Usage:
        # Start in catalog mode
        app = CISBenchApp.catalog(benchmarks=data, offline=False)
        app.run()

        # Start in view mode
        app = CISBenchApp.view(benchmark=data, recommendations=recs)
        app.run()

        # Start in diff mode
        app = CISBenchApp.diff(comparison=cmp, old_data=old, new_data=new)
        app.run()
    """

    CSS = COMMON_CSS

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=False, priority=True),
    ]

    def __init__(
        self,
        mode: str = "catalog",
        initial_screen=None,
        **kwargs,
    ):
        """Initialize the app.

        Args:
            mode: The mode to start in ('catalog', 'view', 'diff').
            initial_screen: The screen instance to push on mount.
            **kwargs: Additional arguments passed to App.
        """
        super().__init__(**kwargs)
        self.mode = mode
        self._initial_screen = initial_screen

    def on_mount(self) -> None:
        """Push the initial screen when the app mounts."""
        if self._initial_screen is not None:
            self.push_screen(self._initial_screen)

    @classmethod
    def catalog(cls, benchmarks: list[dict], offline: bool = False):
        """Create app in catalog mode.

        Note: For catalog mode, we use CatalogBrowserApp directly since it's
        already a full-featured App. This will be unified in task 247.6.

        Args:
            benchmarks: List of benchmark dictionaries from catalog.
            offline: Whether running in offline mode.

        Returns:
            Configured CatalogBrowserApp instance (not CISBenchApp).
        """
        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        app = CatalogBrowserApp(benchmarks=benchmarks, offline=offline)
        app.title = "CIS Benchmark Catalog"
        return app

    @classmethod
    def view(
        cls,
        benchmark: dict,
        recommendations: list,
        offline: bool = False,
    ) -> "CISBenchApp":
        """Create app in view mode.

        Args:
            benchmark: The benchmark data dictionary.
            recommendations: List of recommendations to display.
            offline: Whether running in offline mode.

        Returns:
            Configured CISBenchApp instance.
        """
        from cis_bench.cli.commands.tui.screens import ViewScreen

        screen = ViewScreen(
            benchmark=benchmark,
            recommendations=recommendations,
            offline=offline,
        )
        app = cls(mode="view", initial_screen=screen)
        app.title = "CIS Benchmark Viewer"
        return app

    @classmethod
    def diff(
        cls,
        comparison: dict,
        old_data: dict,
        new_data: dict,
        offline: bool = False,
    ) -> "CISBenchApp":
        """Create app in diff mode.

        Args:
            comparison: The comparison result from compare_benchmarks().
            old_data: The old benchmark data dictionary.
            new_data: The new benchmark data dictionary.
            offline: Whether running in offline mode.

        Returns:
            Configured CISBenchApp instance.
        """
        from cis_bench.cli.commands.tui.screens import DiffScreen

        screen = DiffScreen(
            comparison=comparison,
            old_data=old_data,
            new_data=new_data,
            offline=offline,
        )
        app = cls(mode="diff", initial_screen=screen)
        app.title = "CIS Benchmark Diff"
        return app


# Convenience functions for backward compatibility with existing CLI commands


def run_cis_bench_catalog(benchmarks: list[dict], offline: bool = False) -> None:
    """Run the catalog browser TUI.

    Args:
        benchmarks: List of benchmark dictionaries from catalog.
        offline: Whether running in offline mode.
    """
    app = CISBenchApp.catalog(benchmarks=benchmarks, offline=offline)
    app.run()


def run_cis_bench_view(
    benchmark: dict,
    recommendations: list,
    offline: bool = False,
) -> None:
    """Run the benchmark viewer TUI.

    Args:
        benchmark: The benchmark data dictionary.
        recommendations: List of recommendations to display.
        offline: Whether running in offline mode.
    """
    app = CISBenchApp.view(
        benchmark=benchmark,
        recommendations=recommendations,
        offline=offline,
    )
    app.run()


def run_cis_bench_diff(
    comparison: dict,
    old_data: dict,
    new_data: dict,
    offline: bool = False,
) -> None:
    """Run the benchmark diff TUI.

    Args:
        comparison: The comparison result from compare_benchmarks().
        old_data: The old benchmark data dictionary.
        new_data: The new benchmark data dictionary.
        offline: Whether running in offline mode.
    """
    app = CISBenchApp.diff(
        comparison=comparison,
        old_data=old_data,
        new_data=new_data,
        offline=offline,
    )
    app.run()
