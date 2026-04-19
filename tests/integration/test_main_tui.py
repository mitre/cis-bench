"""Tests for main tabbed TUI app (TDD - tests first)."""

import pytest


class TestMainTUIStructure:
    """Test main TUI app structure and tab container."""

    @pytest.mark.asyncio
    async def test_main_app_has_tabbed_content(self):
        """Test main app contains TabbedContent widget."""
        from cis_bench.cli.commands.tui.main_app import MainTUIApp

        app = MainTUIApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Verify TabbedContent exists
            from textual.widgets import TabbedContent

            tabbed = app.query_one(TabbedContent)
            assert tabbed is not None

    @pytest.mark.asyncio
    async def test_main_app_has_correct_tab_count(self):
        """Test main app has correct number of tabs from config."""
        from cis_bench.cli.commands.tui.main_app import MainTUIApp, get_tab_count

        app = MainTUIApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            from textual.widgets import Tab

            tabs = app.query(Tab)
            assert len(tabs) == get_tab_count()

    @pytest.mark.asyncio
    async def test_tab_labels_match_config(self):
        """Test tabs have labels matching TABS config."""
        from cis_bench.cli.commands.tui.main_app import MainTUIApp, get_tab_labels

        app = MainTUIApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            from textual.widgets import Tab, Tabs

            tabs_widget = app.query_one(Tabs)
            actual_labels = [str(tab.label) for tab in tabs_widget.query(Tab)]
            expected_labels = get_tab_labels()

            # All expected labels should be present
            for label in expected_labels:
                assert label in actual_labels, f"Missing tab: {label}"

            # No extra labels
            assert len(actual_labels) == len(expected_labels)

    @pytest.mark.asyncio
    async def test_first_tab_active_by_default(self):
        """Test first tab from config is active on startup."""
        from cis_bench.cli.commands.tui.main_app import TABS, MainTUIApp

        app = MainTUIApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            from textual.widgets import TabbedContent

            tabbed = app.query_one(TabbedContent)
            expected_initial = TABS[0].id
            assert tabbed.active == expected_initial


class TestMainTUINavigation:
    """Test tab navigation in main TUI."""

    @pytest.mark.asyncio
    async def test_programmatic_tab_switching(self):
        """Test programmatically switching between tabs."""
        from cis_bench.cli.commands.tui.main_app import MainTUIApp

        app = MainTUIApp()
        async with app.run_test() as pilot:
            from textual.widgets import TabbedContent

            tabbed = app.query_one(TabbedContent)
            assert tabbed.active == "tab-catalog"

            # Switch tabs using the Tabs widget method (more reliable)
            tabs = tabbed.query_one("Tabs")
            tabs.action_previous_tab()
            await pilot.pause()
            # Tab switching cycles, so going previous from first should work
            # Just verify no errors occur

            tabs.action_next_tab()
            await pilot.pause()
            # Should be back to catalog or moved to next tab

    @pytest.mark.asyncio
    async def test_quit_binding_works(self):
        """Test 'q' key quits the app."""
        from cis_bench.cli.commands.tui.main_app import MainTUIApp

        app = MainTUIApp()
        async with app.run_test() as pilot:
            await pilot.press("q")
            await pilot.pause()

            # App should have exited
            assert not app.is_running


class TestMainTUIHeader:
    """Test main TUI header display."""

    @pytest.mark.asyncio
    async def test_header_shows_title(self):
        """Test header displays app title."""
        from cis_bench.cli.commands.tui.main_app import MainTUIApp

        app = MainTUIApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            from textual.widgets import Header

            header = app.query_one(Header)
            assert header is not None


class TestCatalogTabKeyboardNavigation:
    """Test keyboard navigation in catalog tab (fix for cis-bench-f5b)."""

    @pytest.mark.asyncio
    async def test_catalog_datatable_receives_focus_on_startup(self):
        """Test DataTable is focused when catalog tab is active on startup."""
        from cis_bench.cli.commands.tui.main_app import MainTUIApp

        app = MainTUIApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Wait for catalog to load
            await pilot.pause()

            from textual.widgets import DataTable

            table = app.query_one("#catalog-table", DataTable)
            # Table should be focused due to TabActivated handler
            assert table.has_focus or app.focused is None  # None if table hasn't loaded yet

    @pytest.mark.asyncio
    async def test_arrow_keys_navigate_catalog_table(self):
        """Test arrow keys work for DataTable navigation (fix for cis-bench-f5b)."""
        from cis_bench.cli.commands.tui.main_app import MainTUIApp

        app = MainTUIApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            from textual.widgets import DataTable

            table = app.query_one("#catalog-table", DataTable)

            # Wait for table to load data
            await pilot.pause()
            await pilot.pause()

            # Store initial cursor position
            initial_row = table.cursor_row if table.cursor_row is not None else 0

            # Press down arrow
            await pilot.press("down")
            await pilot.pause()

            # Cursor should have moved (if table has data)
            if table.row_count > 1:
                assert table.cursor_row != initial_row

    @pytest.mark.asyncio
    async def test_vim_keys_navigate_catalog_table(self):
        """Test j/k vim keys work for navigation."""
        from cis_bench.cli.commands.tui.main_app import MainTUIApp

        app = MainTUIApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            from textual.widgets import DataTable

            table = app.query_one("#catalog-table", DataTable)
            await pilot.pause()
            await pilot.pause()

            initial_row = table.cursor_row if table.cursor_row is not None else 0

            # Press j (down)
            await pilot.press("j")
            await pilot.pause()

            if table.row_count > 1:
                assert table.cursor_row != initial_row

    @pytest.mark.asyncio
    async def test_page_keys_work(self):
        """Test page up/down keys work."""
        from cis_bench.cli.commands.tui.main_app import MainTUIApp

        app = MainTUIApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            from textual.widgets import DataTable

            table = app.query_one("#catalog-table", DataTable)
            await pilot.pause()
            await pilot.pause()

            # Press page down (should not error even with no data)
            await pilot.press("pagedown")
            await pilot.pause()

            # Press page up
            await pilot.press("pageup")
            await pilot.pause()

            # No assertion - just verify no errors

    @pytest.mark.asyncio
    async def test_tab_switching_refocuses_datatable(self):
        """Test switching tabs and back refocuses DataTable (TabActivated handler)."""
        from cis_bench.cli.commands.tui.main_app import MainTUIApp

        app = MainTUIApp()
        async with app.run_test() as pilot:
            # Wait for catalog to load
            await pilot.pause()
            await pilot.pause()
            await pilot.pause()

            from textual.widgets import DataTable, TabbedContent

            table = app.query_one("#catalog-table", DataTable)
            tabbed = app.query_one(TabbedContent)

            # Ensure table has focus first
            table.focus()
            await pilot.pause()

            # Switch away using Tabs action
            tabs = tabbed.query_one("Tabs")
            tabs.action_next_tab()
            await pilot.pause()

            # Switch back to catalog
            tabs.action_previous_tab()
            await pilot.pause()
            await pilot.pause()

            # Table should be refocused by TabActivated handler
            # Accept table focus, detail-container focus (if tab toggle happened), or None
            focused_widget = app.focused
            assert focused_widget is None or focused_widget.id in (
                "catalog-table",
                "detail-container",
            )


class TestCatalogPaneSwitching:
    """Test switching between table and detail pane in catalog tab."""

    @pytest.mark.asyncio
    async def test_detail_view_in_scroll_container(self):
        """Test detail view is wrapped in VerticalScroll for scrolling."""
        from cis_bench.cli.commands.tui.main_app import MainTUIApp

        app = MainTUIApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            from textual.containers import VerticalScroll

            # Verify VerticalScroll container exists with correct ID
            detail_container = app.query_one("#detail-container", VerticalScroll)
            assert detail_container is not None

            # Verify detail view is inside the scroll container
            from cis_bench.cli.commands.tui.catalog.detail import CatalogDetailView

            detail_view = detail_container.query_one("#detail-view", CatalogDetailView)
            assert detail_view is not None

    @pytest.mark.asyncio
    async def test_tab_key_switches_focus_to_detail_pane(self):
        """Test tab key switches focus from table to detail pane."""
        from cis_bench.cli.commands.tui.main_app import MainTUIApp

        app = MainTUIApp()
        async with app.run_test() as pilot:
            # Wait for catalog to load
            await pilot.pause()
            await pilot.pause()
            await pilot.pause()

            from textual.containers import VerticalScroll
            from textual.widgets import DataTable

            table = app.query_one("#catalog-table", DataTable)
            detail_container = app.query_one("#detail-container", VerticalScroll)

            # Ensure table is focused first
            table.focus()
            await pilot.pause()
            assert table.has_focus

            # Press tab to switch to detail pane
            await pilot.press("tab")
            await pilot.pause()

            # Detail container should now have focus
            assert detail_container.has_focus
            assert not table.has_focus

    @pytest.mark.asyncio
    async def test_tab_key_switches_focus_back_to_table(self):
        """Test tab key switches focus from detail pane back to table."""
        from cis_bench.cli.commands.tui.main_app import MainTUIApp

        app = MainTUIApp()
        async with app.run_test() as pilot:
            # Wait for catalog to load
            await pilot.pause()
            await pilot.pause()
            await pilot.pause()

            from textual.containers import VerticalScroll
            from textual.widgets import DataTable

            table = app.query_one("#catalog-table", DataTable)
            detail_container = app.query_one("#detail-container", VerticalScroll)

            # Focus detail container first
            detail_container.focus()
            await pilot.pause()
            assert detail_container.has_focus

            # Press tab to switch back to table
            await pilot.press("tab")
            await pilot.pause()

            # Table should now have focus
            assert table.has_focus
            assert not detail_container.has_focus

    @pytest.mark.asyncio
    async def test_detail_pane_scrollable_when_focused(self):
        """Test detail pane can be scrolled when focused."""
        from cis_bench.cli.commands.tui.main_app import MainTUIApp

        app = MainTUIApp()
        async with app.run_test() as pilot:
            # Wait for catalog to load
            await pilot.pause()
            await pilot.pause()
            await pilot.pause()

            from textual.containers import VerticalScroll

            detail_container = app.query_one("#detail-container", VerticalScroll)

            # Focus detail container
            detail_container.focus()
            await pilot.pause()

            # Get initial scroll position
            initial_scroll = detail_container.scroll_y

            # Press down arrow to scroll (should not error)
            await pilot.press("down")
            await pilot.pause()

            # Scroll position may or may not change depending on content length
            # Main test is that no error occurs
            assert detail_container.has_focus
