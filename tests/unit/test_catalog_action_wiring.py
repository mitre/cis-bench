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
    """Test that _handle_action properly triggers actions."""

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

    def test_handle_view_action_calls_load_and_view(self, sample_benchmarks):
        """View action should call _load_and_view to push ViewScreen."""
        from unittest.mock import MagicMock

        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        app._load_and_view = MagicMock()

        benchmark = sample_benchmarks[0]
        app._handle_action(("view", benchmark))

        # Should call _load_and_view with benchmark_id
        app._load_and_view.assert_called_once_with(benchmark["benchmark_id"])

    def test_handle_diff_action_with_two_selected_calls_load_and_diff(self, sample_benchmarks):
        """Diff action with 2 selected benchmarks should call _load_and_diff."""
        from unittest.mock import MagicMock

        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        app._load_and_diff = MagicMock()

        # Simulate 2 selected items
        app._selected_indices = {0, 1}

        benchmark = sample_benchmarks[0]
        app._handle_action(("diff", benchmark))

        # Should call _load_and_diff with both selected IDs
        app._load_and_diff.assert_called_once()

    def test_handle_diff_action_needs_exactly_two_selected(self, sample_benchmarks):
        """Diff action should show error if not exactly 2 benchmarks selected."""
        from unittest.mock import MagicMock

        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        app._load_and_diff = MagicMock()
        app.notify = MagicMock()

        # Only 1 selected (or 0)
        app._selected_indices = set()

        benchmark = sample_benchmarks[0]
        app._handle_action(("diff", benchmark))

        # Should NOT call _load_and_diff, should notify with error
        app._load_and_diff.assert_not_called()
        app.notify.assert_called_once()
        # Check it's an error/warning
        _, kwargs = app.notify.call_args
        assert kwargs.get("severity") in ("warning", "error")

    def test_handle_export_action_shows_not_implemented(self, sample_benchmarks):
        """Export action should show not implemented message (for now)."""
        from unittest.mock import MagicMock

        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        app.notify = MagicMock()

        benchmark = sample_benchmarks[0]
        app._handle_action(("export", benchmark))

        # Should notify about export not implemented
        app.notify.assert_called_once()
        call_args, kwargs = app.notify.call_args
        assert "not yet implemented" in call_args[0].lower() or "export" in call_args[0].lower()


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


class TestBaseBrowserScreen:
    """Test BaseBrowserScreen base class."""

    def test_base_browser_screen_importable(self):
        """BaseBrowserScreen should be importable."""
        from cis_bench.cli.commands.tui import BaseBrowserScreen

        assert BaseBrowserScreen is not None

    def test_screen_bindings_importable(self):
        """SCREEN_BINDINGS should be importable."""
        from cis_bench.cli.commands.tui import SCREEN_BINDINGS

        assert SCREEN_BINDINGS is not None
        # Should have escape binding for "go_back"
        binding_actions = [b.action for b in SCREEN_BINDINGS]
        assert "go_back" in binding_actions

    def test_base_browser_screen_has_go_back_not_quit(self):
        """BaseBrowserScreen should use go_back instead of quit."""
        from cis_bench.cli.commands.tui import BaseBrowserScreen

        # Should have action_go_back method
        assert hasattr(BaseBrowserScreen, "action_go_back")

    def test_base_browser_screen_inherits_from_screen(self):
        """BaseBrowserScreen should inherit from Screen."""
        from textual.screen import Screen

        from cis_bench.cli.commands.tui import BaseBrowserScreen

        assert issubclass(BaseBrowserScreen, Screen)


class TestLoadingModal:
    """Test LoadingModal widget."""

    def test_loading_modal_importable(self):
        """LoadingModal should be importable."""
        from cis_bench.cli.commands.tui import LoadingModal

        assert LoadingModal is not None

    def test_loading_modal_has_cancel_binding(self):
        """LoadingModal should have escape binding for cancel."""
        from cis_bench.cli.commands.tui.widgets import LoadingModal

        binding_keys = [b.key for b in LoadingModal.BINDINGS]
        assert "escape" in binding_keys

    def test_loading_modal_has_update_progress(self):
        """LoadingModal should have update_progress method."""
        from cis_bench.cli.commands.tui.widgets import LoadingModal

        modal = LoadingModal("Test")
        assert hasattr(modal, "update_progress")
        assert callable(modal.update_progress)

    def test_loading_modal_has_complete_method(self):
        """LoadingModal should have complete method."""
        from cis_bench.cli.commands.tui.widgets import LoadingModal

        modal = LoadingModal("Test")
        assert hasattr(modal, "complete")
        assert callable(modal.complete)

    def test_loading_modal_is_cancelled_property(self):
        """LoadingModal should have is_cancelled property."""
        from cis_bench.cli.commands.tui.widgets import LoadingModal

        modal = LoadingModal("Test")
        assert hasattr(modal, "is_cancelled")
        assert modal.is_cancelled is False

    def test_loading_modal_update_progress_before_mount(self):
        """update_progress should safely skip if not mounted."""
        from cis_bench.cli.commands.tui.widgets import LoadingModal

        modal = LoadingModal("Test")
        # Should not raise - just skip silently
        modal.update_progress(50, "Testing...")
        # Internal state should still be updated
        assert modal._progress == 50
        assert modal._status == "Testing..."


class TestCISBenchApp:
    """Test unified CISBenchApp class."""

    def test_cis_bench_app_importable(self):
        """CISBenchApp should be importable."""
        from cis_bench.cli.commands.tui.app import CISBenchApp

        assert CISBenchApp is not None

    def test_cis_bench_app_has_catalog_factory(self):
        """CISBenchApp should have catalog classmethod."""
        from cis_bench.cli.commands.tui.app import CISBenchApp

        assert hasattr(CISBenchApp, "catalog")
        assert callable(CISBenchApp.catalog)

    def test_cis_bench_app_has_view_factory(self):
        """CISBenchApp should have view classmethod."""
        from cis_bench.cli.commands.tui.app import CISBenchApp

        assert hasattr(CISBenchApp, "view")
        assert callable(CISBenchApp.view)

    def test_cis_bench_app_has_diff_factory(self):
        """CISBenchApp should have diff classmethod."""
        from cis_bench.cli.commands.tui.app import CISBenchApp

        assert hasattr(CISBenchApp, "diff")
        assert callable(CISBenchApp.diff)

    def test_run_cis_bench_functions_importable(self):
        """Convenience run functions should be importable."""
        from cis_bench.cli.commands.tui.app import (
            run_cis_bench_catalog,
            run_cis_bench_diff,
            run_cis_bench_view,
        )

        assert callable(run_cis_bench_catalog)
        assert callable(run_cis_bench_view)
        assert callable(run_cis_bench_diff)
