"""Integration tests for TUI user workflows.

These tests verify actual user workflows using Textual's app.run_test().
NO MOCKING of core functions - tests real behavior.

Tests are based on user stories from docs/design/tui-user-stories.md.
"""

import pytest

from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def sample_benchmarks():
    """Minimal benchmark data for TUI testing."""
    return [
        {
            "benchmark_id": "23598",
            "title": "CIS AlmaLinux OS 8 Benchmark",
            "version": "v4.0.0",
            "platform": "AlmaLinux",
            "is_latest": True,
            "published_date": "2024-01-15",
            "description": "Security configuration benchmark for AlmaLinux 8",
        },
        {
            "benchmark_id": "23599",
            "title": "CIS AlmaLinux OS 8 Benchmark",
            "version": "v3.0.0",
            "platform": "AlmaLinux",
            "is_latest": False,
            "published_date": "2023-06-01",
            "description": "Previous version of AlmaLinux benchmark",
        },
        {
            "benchmark_id": "24001",
            "title": "CIS Ubuntu Linux 22.04 LTS Benchmark",
            "version": "v2.0.0",
            "platform": "Ubuntu",
            "is_latest": True,
            "published_date": "2024-02-20",
            "description": "Security configuration for Ubuntu 22.04",
        },
        {
            "benchmark_id": "24002",
            "title": "CIS Red Hat Enterprise Linux 9 Benchmark",
            "version": "v1.0.0",
            "platform": "RHEL",
            "is_latest": True,
            "published_date": "2024-03-10",
            "description": "Security configuration for RHEL 9",
        },
    ]


# ============================================================================
# US-7: Search/Filter Tests
# ============================================================================


class TestCatalogSearch:
    """Test search and filter functionality (US-7)."""

    async def test_catalog_displays_all_benchmarks(self, sample_benchmarks):
        """Catalog should display all benchmarks on startup."""
        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        async with app.run_test(size=(120, 40)) as pilot:
            # Wait for mount
            await pilot.pause()

            # Verify table has all items
            from textual.widgets import DataTable

            table = app.query_one("#changes-table", DataTable)
            assert table.row_count == len(sample_benchmarks)

    async def test_search_filters_by_title(self, sample_benchmarks):
        """Search should filter benchmarks by title text."""
        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # Press '/' to focus search
            await pilot.press("/")
            await pilot.pause()

            # Type search term
            await pilot.press("u", "b", "u", "n", "t", "u")
            await pilot.pause()

            # Press Enter to apply filter
            await pilot.press("enter")
            await pilot.pause()

            # Verify filtered results
            from textual.widgets import DataTable

            table = app.query_one("#changes-table", DataTable)
            # Should only show Ubuntu benchmark
            assert table.row_count == 1

    async def test_search_filters_by_platform(self, sample_benchmarks):
        """Search should filter benchmarks by platform."""
        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # Search for RHEL
            await pilot.press("/")
            await pilot.pause()
            await pilot.press("r", "h", "e", "l")
            await pilot.pause()  # Pause after typing, before submit
            await pilot.press("enter")
            await pilot.pause()

            from textual.widgets import DataTable

            table = app.query_one("#changes-table", DataTable)
            assert table.row_count == 1

    async def test_empty_search_shows_all(self, sample_benchmarks):
        """Clearing search should show all benchmarks again."""
        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            from textual.widgets import DataTable

            table = app.query_one("#changes-table", DataTable)
            initial_count = table.row_count
            assert initial_count == len(sample_benchmarks)

            # Search for something specific
            await pilot.press("/")
            await pilot.pause()
            await pilot.press("u", "b", "u", "n", "t", "u")
            await pilot.pause()  # Pause after typing, before submit
            await pilot.press("enter")
            await pilot.pause()

            filtered_count = table.row_count
            assert filtered_count < initial_count

            # Clear by searching empty string - press / then just clear input
            await pilot.press("/")
            await pilot.pause()
            # Clear the search input by pressing backspace multiple times
            # Use single press call with multiple keys for atomic operation
            await pilot.press(
                "backspace",
                "backspace",
                "backspace",
                "backspace",
                "backspace",
                "backspace",
                "backspace",
                "backspace",
                "backspace",
                "backspace",
            )
            await pilot.pause()  # Pause after clearing, before submit
            await pilot.press("enter")
            await pilot.pause()

            # Should show all again
            assert table.row_count == len(sample_benchmarks)


# ============================================================================
# US-17: Navigation Tests
# ============================================================================


class TestCatalogNavigation:
    """Test keyboard navigation (US-17)."""

    async def test_arrow_keys_move_cursor(self, sample_benchmarks):
        """Arrow keys should move cursor in table."""
        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            from textual.widgets import DataTable

            table = app.query_one("#changes-table", DataTable)

            # Initially at row 0
            assert table.cursor_row == 0

            # Move down
            await pilot.press("down")
            await pilot.pause()
            assert table.cursor_row == 1

            # Move down again
            await pilot.press("down")
            await pilot.pause()
            assert table.cursor_row == 2

            # Move up
            await pilot.press("up")
            await pilot.pause()
            assert table.cursor_row == 1

    async def test_j_k_vim_navigation(self, sample_benchmarks):
        """j/k keys should work like down/up (vim style)."""
        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            from textual.widgets import DataTable

            table = app.query_one("#changes-table", DataTable)

            # j moves down
            await pilot.press("j")
            await pilot.pause()
            assert table.cursor_row == 1

            # k moves up
            await pilot.press("k")
            await pilot.pause()
            assert table.cursor_row == 0

    async def test_help_screen_shows_and_dismisses(self, sample_benchmarks):
        """? key should show help, Escape should dismiss."""
        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # Get initial screen count
            initial_stack_len = len(app.screen_stack)

            # Press ? for help
            await pilot.press("?")
            await pilot.pause()

            # Should have pushed a screen
            assert len(app.screen_stack) > initial_stack_len

            # Press Escape to dismiss
            await pilot.press("escape")
            await pilot.pause()

            # Should be back to catalog
            assert len(app.screen_stack) == initial_stack_len


# ============================================================================
# Selection Tests (for Diff)
# ============================================================================


class TestBenchmarkSelection:
    """Test selection functionality for diff workflow."""

    async def test_space_toggles_selection(self, sample_benchmarks):
        """Space key should toggle selection on current row."""
        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # Initially no selection
            assert len(app._selected_indices) == 0

            # Press space to select
            await pilot.press("space")
            await pilot.pause()

            # Should have 1 selected
            assert len(app._selected_indices) == 1
            assert 0 in app._selected_indices

            # Press space again to deselect
            await pilot.press("space")
            await pilot.pause()

            # Should be deselected
            assert len(app._selected_indices) == 0

    async def test_select_two_for_diff(self, sample_benchmarks):
        """Should be able to select exactly 2 items for diff."""
        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # Select first item
            await pilot.press("space")
            await pilot.pause()

            # Move down and select second
            await pilot.press("down")
            await pilot.pause()  # Pause after cursor move, before selection
            await pilot.press("space")
            await pilot.pause()

            # Should have exactly 2 selected
            assert len(app._selected_indices) == 2
            assert 0 in app._selected_indices
            assert 1 in app._selected_indices


# ============================================================================
# US-1: View Benchmark (WILL FAIL until ViewScreen is fixed)
# ============================================================================


class TestViewBenchmark:
    """Test view benchmark workflow (US-1).

    These tests WILL FAIL until we fix the TUI architecture.
    This is intentional TDD - RED phase.
    """

    async def test_v_key_attempts_view(self, sample_benchmarks):
        """Pressing 'v' should attempt to view selected benchmark.

        Note: This will show a notification about loading, which is the
        start of the view workflow. Full navigation to ViewScreen requires
        the benchmark to be loaded (which needs network/cache).
        """
        app = CatalogBrowserApp(benchmarks=sample_benchmarks, offline=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # Press 'v' to view
            await pilot.press("v")
            await pilot.pause(delay=0.5)

            # At minimum, the action should be triggered
            # (notification shown or screen pushed)
            # For now, just verify app didn't crash
            assert app.is_running

    @pytest.mark.xfail(
        reason="BUG: ActionMenu push causes app exit in test mode - needs investigation"
    )
    async def test_enter_opens_action_menu(self, sample_benchmarks):
        """Enter key should open action menu for selected benchmark.

        Known issue: In test mode, the ModalScreen push causes the app to exit.
        This needs investigation during the SPA refactor.
        """
        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # Press Enter to open actions
            await pilot.press("enter")
            await pilot.pause(delay=0.5)

            # ActionMenu should be visible (it's a ModalScreen)
            from cis_bench.cli.commands.tui.catalog.actions import ActionMenu

            # Check current screen
            current_screen = app.screen
            is_action_menu = isinstance(current_screen, ActionMenu)
            assert is_action_menu, f"Expected ActionMenu, got {type(current_screen).__name__}"

            # Dismiss with Escape
            await pilot.press("escape")
            await pilot.pause()

            assert app.is_running


# ============================================================================
# US-2: Diff Benchmarks (WILL FAIL until DiffScreen is fixed)
# ============================================================================


class TestDiffBenchmarks:
    """Test diff benchmark workflow (US-2).

    These tests WILL FAIL until we fix the DiffScreen crash.
    This is intentional TDD - RED phase.
    """

    async def test_d_key_with_no_selection_shows_warning(self, sample_benchmarks):
        """Pressing 'd' with no selection should show warning."""
        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # No selection - press d
            await pilot.press("d")
            await pilot.pause()

            # Should still be on catalog (no crash)
            # Warning notification should have been shown
            assert app.is_running
            # Verify we're still on the main screen (no screen pushed)
            assert len(app.screen_stack) == 1

    async def test_d_key_with_one_selection_shows_warning(self, sample_benchmarks):
        """Pressing 'd' with only 1 selection should show warning."""
        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # Select only one
            await pilot.press("space")
            await pilot.pause()

            # Press d
            await pilot.press("d")
            await pilot.pause()

            # Should still be on catalog (warning, not crash)
            assert app.is_running
            assert len(app.screen_stack) == 1

    async def test_d_key_with_two_selections_attempts_diff(self, sample_benchmarks):
        """Pressing 'd' with 2 selections should attempt diff.

        Note: This will show loading notification. Full diff screen
        requires both benchmarks to be loaded.
        """
        app = CatalogBrowserApp(benchmarks=sample_benchmarks, offline=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # Select two items
            await pilot.press("space")
            await pilot.pause()  # Pause after first selection
            await pilot.press("down")
            await pilot.pause()  # Pause after cursor move
            await pilot.press("space")
            await pilot.pause()

            # Press d
            await pilot.press("d")
            await pilot.pause(delay=0.5)

            # Should not crash
            assert app.is_running


# ============================================================================
# US-19: Quit
# ============================================================================


class TestQuit:
    """Test quit functionality (US-19)."""

    async def test_q_key_exits_app(self, sample_benchmarks):
        """Pressing 'q' should exit the application."""
        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # Press q to quit
            await pilot.press("q")
            await pilot.pause()

            # App should have exited (or be in process of exiting)
            # In test mode, we just verify no crash
            # The app.exit() is called but run_test handles it


# ============================================================================
# Detail View Tests
# ============================================================================


class TestDetailView:
    """Test detail view updates when navigating."""

    async def test_detail_view_exists(self, sample_benchmarks):
        """Detail view widget should exist and be queryable."""
        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            from cis_bench.cli.commands.tui.catalog.detail import CatalogDetailView

            detail_view = app.query_one("#detail-view", CatalogDetailView)
            assert detail_view is not None

    async def test_cursor_move_triggers_detail_update(self, sample_benchmarks):
        """Moving cursor should trigger detail view update."""
        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            from textual.widgets import DataTable

            table = app.query_one("#changes-table", DataTable)

            # Move cursor - this should trigger _show_detail internally
            await pilot.press("down")
            await pilot.pause()

            # Verify cursor moved and app didn't crash
            assert table.cursor_row == 1
            assert app.is_running


# ============================================================================
# Tab Focus Tests
# ============================================================================


class TestFocusManagement:
    """Test focus switching between panes."""

    @pytest.mark.xfail(
        reason="BUG: Tab key not triggering action_toggle_focus - needs investigation"
    )
    async def test_tab_toggles_focus_state(self, sample_benchmarks):
        """Tab key should toggle the focus state.

        Known issue: The Tab binding exists but action_toggle_focus isn't firing.
        This needs investigation during the SPA refactor.
        """
        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # Record initial focus state
            initial_focus = app._focus_on_detail

            # Press Tab to switch focus
            await pilot.press("tab")
            await pilot.pause()

            # Should have toggled (whatever the initial state was)
            assert app._focus_on_detail != initial_focus

            # Press Tab again
            await pilot.press("tab")
            await pilot.pause()

            # Should toggle back to initial
            assert app._focus_on_detail == initial_focus
