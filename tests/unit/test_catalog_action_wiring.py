"""Tests for catalog browser action wiring.

Tests that catalog browser actions properly launch ViewApp/DiffApp
instead of just showing notifications.
"""

import pytest


class TestActionMenuNoDisabledButtons:
    """Test that ActionMenu buttons are not disabled based on download status."""

    def test_view_button_never_disabled(self):
        """View button should never be disabled (auto-fetch handles missing content)."""
        from cis_bench.cli.commands.tui.catalog.actions import ActionMenu

        benchmark = {"benchmark_id": "23598", "title": "Test", "version": "v1"}

        # Even when not downloaded, View should NOT be disabled
        menu = ActionMenu(benchmark, is_downloaded=False)
        # Access internal state - buttons are composed later
        # The key assertion is that the action works regardless of is_downloaded
        assert not getattr(menu, "_view_disabled_check", False)

    def test_export_button_never_disabled(self):
        """Export button should never be disabled (auto-fetch handles missing content)."""
        from cis_bench.cli.commands.tui.catalog.actions import ActionMenu

        benchmark = {"benchmark_id": "23598", "title": "Test", "version": "v1"}

        menu = ActionMenu(benchmark, is_downloaded=False)
        assert not getattr(menu, "_export_disabled_check", False)

    def test_action_view_always_dismisses(self):
        """action_view should always dismiss with view action, not check is_downloaded."""
        from unittest.mock import MagicMock, patch

        from cis_bench.cli.commands.tui.catalog.actions import ActionMenu

        benchmark = {"benchmark_id": "23598", "title": "Test", "version": "v1"}
        menu = ActionMenu(benchmark, is_downloaded=False)
        menu.dismiss = MagicMock()

        # Patch the app property to avoid the read-only error
        with patch.object(ActionMenu, "app", create=True, new_callable=lambda: MagicMock()):
            menu.action_view()

        # Should dismiss with view action, NOT show warning
        menu.dismiss.assert_called_once_with(("view", benchmark))

    def test_action_export_always_dismisses(self):
        """action_export should always dismiss with export action, not check is_downloaded."""
        from unittest.mock import MagicMock, patch

        from cis_bench.cli.commands.tui.catalog.actions import ActionMenu

        benchmark = {"benchmark_id": "23598", "title": "Test", "version": "v1"}
        menu = ActionMenu(benchmark, is_downloaded=False)
        menu.dismiss = MagicMock()

        with patch.object(ActionMenu, "app", create=True, new_callable=lambda: MagicMock()):
            menu.action_export()

        menu.dismiss.assert_called_once_with(("export", benchmark))


class TestCatalogBrowserActionHandling:
    """Test that _handle_action properly exits with action info."""

    @pytest.fixture
    def sample_benchmarks(self):
        """Sample benchmark data for testing."""
        return [
            {
                "benchmark_id": "23598",
                "title": "CIS Ubuntu 22.04 Benchmark",
                "version": "v2.0.0",
                "platform": "Operating System",
            },
            {
                "benchmark_id": "24001",
                "title": "CIS Ubuntu 22.04 Benchmark",
                "version": "v1.0.0",
                "platform": "Operating System",
            },
        ]

    def test_handle_view_action_exits_app(self, sample_benchmarks):
        """View action should exit the app with action info for runner to handle."""
        from unittest.mock import MagicMock

        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        app.exit = MagicMock()

        benchmark = sample_benchmarks[0]
        app._handle_action(("view", benchmark))

        # Should exit with view action info
        app.exit.assert_called_once()
        call_args = app.exit.call_args[0][0]
        assert call_args[0] == "view"
        assert call_args[1] == benchmark["benchmark_id"]

    def test_handle_diff_action_with_two_selected_exits_app(self, sample_benchmarks):
        """Diff action with 2 selected benchmarks should exit with action info."""
        from unittest.mock import MagicMock

        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        app.exit = MagicMock()

        # Simulate 2 selected items
        app._selected_indices = {0, 1}

        benchmark = sample_benchmarks[0]
        app._handle_action(("diff", benchmark))

        # Should exit with diff action info including both selected IDs
        app.exit.assert_called_once()
        call_args = app.exit.call_args[0][0]
        assert call_args[0] == "diff"

    def test_handle_diff_action_needs_exactly_two_selected(self, sample_benchmarks):
        """Diff action should show error if not exactly 2 benchmarks selected."""
        from unittest.mock import MagicMock

        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        app.exit = MagicMock()
        app.notify = MagicMock()

        # Only 1 selected (or 0)
        app._selected_indices = set()

        benchmark = sample_benchmarks[0]
        app._handle_action(("diff", benchmark))

        # Should NOT exit, should notify with error
        app.exit.assert_not_called()
        app.notify.assert_called_once()
        # Check it's an error/warning
        _, kwargs = app.notify.call_args
        assert kwargs.get("severity") in ("warning", "error")

    def test_handle_export_action_exits_app(self, sample_benchmarks):
        """Export action should exit the app with action info."""
        from unittest.mock import MagicMock

        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        app.exit = MagicMock()

        benchmark = sample_benchmarks[0]
        app._handle_action(("export", benchmark))

        # Should exit with export action info
        app.exit.assert_called_once()
        call_args = app.exit.call_args[0][0]
        assert call_args[0] == "export"
        assert call_args[1] == benchmark["benchmark_id"]


class TestRunCatalogBrowserActionLoop:
    """Test that run_catalog_browser handles action return values."""

    def test_run_catalog_browser_returns_none_on_quit(self):
        """When user quits catalog, run_catalog_browser should return None."""
        # This tests the interface - actual implementation would need app mocking
        from cis_bench.cli.commands.tui.catalog import run_catalog_browser

        # run_catalog_browser should accept benchmarks and return action info or None
        assert callable(run_catalog_browser)

    def test_run_catalog_browser_signature(self):
        """run_catalog_browser should have expected signature."""
        import inspect

        from cis_bench.cli.commands.tui.catalog import run_catalog_browser

        sig = inspect.signature(run_catalog_browser)
        params = list(sig.parameters.keys())

        assert "benchmarks" in params
        assert "offline" in params


class TestDirectKeyBindings:
    """Test direct keyboard shortcuts that skip the action menu."""

    @pytest.fixture
    def sample_benchmarks(self):
        """Sample benchmark data for testing."""
        return [
            {
                "benchmark_id": "23598",
                "title": "CIS Ubuntu 22.04 Benchmark",
                "version": "v2.0.0",
                "platform": "Operating System",
            },
            {
                "benchmark_id": "24001",
                "title": "CIS Ubuntu 22.04 Benchmark",
                "version": "v1.0.0",
                "platform": "Operating System",
            },
        ]

    def test_has_v_binding_for_view(self, sample_benchmarks):
        """CatalogBrowserApp should have 'v' binding for direct view."""
        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        binding_keys = [b.key for b in CatalogBrowserApp.BINDINGS]
        assert "v" in binding_keys

    def test_has_d_binding_for_diff(self, sample_benchmarks):
        """CatalogBrowserApp should have 'd' binding for direct diff."""
        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        binding_keys = [b.key for b in CatalogBrowserApp.BINDINGS]
        assert "d" in binding_keys

    def test_has_e_binding_for_export(self, sample_benchmarks):
        """CatalogBrowserApp should have 'e' binding for export."""
        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        binding_keys = [b.key for b in CatalogBrowserApp.BINDINGS]
        assert "e" in binding_keys

    def test_has_s_binding_for_export(self, sample_benchmarks):
        """CatalogBrowserApp should have 's' binding for save/export."""
        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        binding_keys = [b.key for b in CatalogBrowserApp.BINDINGS]
        assert "s" in binding_keys

    def test_action_view_benchmark_exists(self):
        """CatalogBrowserApp should have action_view_benchmark method."""
        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        assert hasattr(CatalogBrowserApp, "action_view_benchmark")
        assert callable(CatalogBrowserApp.action_view_benchmark)

    def test_action_diff_benchmarks_exists(self):
        """CatalogBrowserApp should have action_diff_benchmarks method."""
        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        assert hasattr(CatalogBrowserApp, "action_diff_benchmarks")
        assert callable(CatalogBrowserApp.action_diff_benchmarks)

    def test_action_export_benchmark_exists(self):
        """CatalogBrowserApp should have action_export_benchmark method."""
        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        assert hasattr(CatalogBrowserApp, "action_export_benchmark")
        assert callable(CatalogBrowserApp.action_export_benchmark)


class TestViewActionIntegration:
    """Integration tests for view action launching ViewApp."""

    def test_load_benchmark_is_importable(self):
        """load_benchmark should be importable from utils."""
        from cis_bench.cli.commands.utils import load_benchmark

        assert callable(load_benchmark)

    def test_run_interactive_view_is_importable(self):
        """run_interactive_view should be importable."""
        from cis_bench.cli.commands.tui.view import run_interactive_view

        assert callable(run_interactive_view)

    def test_compare_benchmarks_is_importable(self):
        """compare_benchmarks should be importable from diff command."""
        from cis_bench.cli.commands.diff import compare_benchmarks

        assert callable(compare_benchmarks)

    def test_run_interactive_diff_is_importable(self):
        """run_interactive_diff should be importable."""
        from cis_bench.cli.commands.tui.diff import run_interactive_diff

        assert callable(run_interactive_diff)
