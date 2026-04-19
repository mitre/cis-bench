"""Unit tests for CatalogTabPane (sync tests, no app.run_test()).

Tests for:
- Bindings and key mappings
- Action methods existence
- Selection tracking
- Downloaded status tracking
- Phase 2b: View/Diff/Export actions
"""


class TestCatalogTabPaneBindings:
    """Test that catalog tab pane has expected key bindings (adapted from test_catalog_browser.py)."""

    def test_has_space_for_multiselect(self):
        """Catalog tab pane should have space binding for multi-select."""
        from cis_bench.cli.commands.tui.catalog.pane import CatalogTabPane

        binding_keys = [b.key for b in CatalogTabPane.BINDINGS]
        assert "space" in binding_keys

    def test_has_open_url_binding(self):
        """Catalog tab pane should have o binding for open URL in browser."""
        from cis_bench.cli.commands.tui.catalog.pane import CatalogTabPane

        binding_keys = [b.key for b in CatalogTabPane.BINDINGS]
        assert "o" in binding_keys

    def test_has_arrow_key_bindings(self):
        """Catalog tab pane should have arrow key bindings for navigation."""
        from cis_bench.cli.commands.tui.catalog.pane import CatalogTabPane

        binding_keys = [b.key for b in CatalogTabPane.BINDINGS]
        assert "down" in binding_keys
        assert "up" in binding_keys

    def test_has_vim_key_bindings(self):
        """Catalog tab pane should have j/k vim bindings."""
        from cis_bench.cli.commands.tui.catalog.pane import CatalogTabPane

        binding_keys = [b.key for b in CatalogTabPane.BINDINGS]
        assert "j" in binding_keys
        assert "k" in binding_keys

    def test_has_tab_for_focus_toggle(self):
        """Catalog tab pane should have tab binding for focus toggle."""
        from cis_bench.cli.commands.tui.catalog.pane import CatalogTabPane

        binding_keys = [b.key for b in CatalogTabPane.BINDINGS]
        assert "tab" in binding_keys


class TestCatalogTabPaneActions:
    """Test that catalog tab pane has expected action methods (adapted from test_catalog_browser.py)."""

    def test_has_toggle_select_action(self):
        """CatalogTabPane should have action_toggle_select method."""
        from cis_bench.cli.commands.tui.catalog.pane import CatalogTabPane

        assert hasattr(CatalogTabPane, "action_toggle_select")
        assert callable(CatalogTabPane.action_toggle_select)

    def test_has_open_in_browser_action(self):
        """CatalogTabPane should have action_open_in_browser method."""
        from cis_bench.cli.commands.tui.catalog.pane import CatalogTabPane

        assert hasattr(CatalogTabPane, "action_open_in_browser")
        assert callable(CatalogTabPane.action_open_in_browser)

    def test_has_toggle_focus_action(self):
        """CatalogTabPane should have action_toggle_focus method."""
        from cis_bench.cli.commands.tui.catalog.pane import CatalogTabPane

        assert hasattr(CatalogTabPane, "action_toggle_focus")
        assert callable(CatalogTabPane.action_toggle_focus)


class TestCatalogTabPaneSelection:
    """Test multi-select functionality in catalog tab pane (adapted from test_catalog_browser.py)."""

    def test_has_selected_indices_attribute(self):
        """CatalogTabPane should have _selected_indices set."""
        from cis_bench.cli.commands.tui.catalog.pane import CatalogTabPane

        pane = CatalogTabPane()
        assert hasattr(pane, "_selected_indices")
        assert isinstance(pane._selected_indices, set)

    def test_selected_indices_empty_initially(self):
        """_selected_indices should be empty initially."""
        from cis_bench.cli.commands.tui.catalog.pane import CatalogTabPane

        pane = CatalogTabPane()
        assert len(pane._selected_indices) == 0

    def test_has_get_selected_items_method(self):
        """CatalogTabPane should have get_selected_items method."""
        from cis_bench.cli.commands.tui.catalog.pane import CatalogTabPane

        assert hasattr(CatalogTabPane, "get_selected_items")
        assert callable(CatalogTabPane.get_selected_items)


class TestCatalogTabPaneDownloadedStatus:
    """Test downloaded/cached status in catalog tab pane (adapted from test_catalog_browser.py)."""

    def test_has_downloaded_ids_attribute(self):
        """CatalogTabPane should have _downloaded_ids set."""
        from cis_bench.cli.commands.tui.catalog.pane import CatalogTabPane

        pane = CatalogTabPane()
        assert hasattr(pane, "_downloaded_ids")
        assert isinstance(pane._downloaded_ids, set)

    def test_has_load_downloaded_ids_method(self):
        """CatalogTabPane should have _load_downloaded_ids method."""
        from cis_bench.cli.commands.tui.catalog.pane import CatalogTabPane

        assert hasattr(CatalogTabPane, "_load_downloaded_ids")
        assert callable(CatalogTabPane._load_downloaded_ids)

    def test_downloaded_ids_check_works(self):
        """Should be able to check if benchmark is downloaded."""
        from cis_bench.cli.commands.tui.catalog.pane import CatalogTabPane

        pane = CatalogTabPane()

        # Initially empty
        assert "23598" not in pane._downloaded_ids

        # Manually add for testing
        pane._downloaded_ids.add("23598")
        assert "23598" in pane._downloaded_ids
        assert "12345" not in pane._downloaded_ids


class TestCatalogTabPaneViewAction:
    """Test view action in catalog tab pane (Phase 2b)."""

    def test_has_v_binding_for_view(self):
        """CatalogTabPane should have 'v' binding for direct view."""
        from cis_bench.cli.commands.tui.catalog.pane import CatalogTabPane

        binding_keys = [b.key for b in CatalogTabPane.BINDINGS]
        assert "v" in binding_keys

    def test_has_action_view_benchmark_method(self):
        """CatalogTabPane should have action_view_benchmark method."""
        from cis_bench.cli.commands.tui.catalog.pane import CatalogTabPane

        assert hasattr(CatalogTabPane, "action_view_benchmark")
        assert callable(CatalogTabPane.action_view_benchmark)


class TestCatalogTabPaneDiffAction:
    """Test diff action in catalog tab pane (Phase 2b)."""

    def test_has_d_binding_for_diff(self):
        """CatalogTabPane should have 'd' binding for direct diff."""
        from cis_bench.cli.commands.tui.catalog.pane import CatalogTabPane

        binding_keys = [b.key for b in CatalogTabPane.BINDINGS]
        assert "d" in binding_keys

    def test_has_action_diff_benchmarks_method(self):
        """CatalogTabPane should have action_diff_benchmarks method."""
        from cis_bench.cli.commands.tui.catalog.pane import CatalogTabPane

        assert hasattr(CatalogTabPane, "action_diff_benchmarks")
        assert callable(CatalogTabPane.action_diff_benchmarks)

    def test_has_get_ordered_diff_ids_method(self):
        """CatalogTabPane should have _get_ordered_diff_ids method."""
        from cis_bench.cli.commands.tui.catalog.pane import CatalogTabPane

        assert hasattr(CatalogTabPane, "_get_ordered_diff_ids")
        assert callable(CatalogTabPane._get_ordered_diff_ids)


class TestCatalogTabPaneExportAction:
    """Test export action in catalog tab pane (Phase 2b)."""

    def test_has_e_binding_for_export(self):
        """CatalogTabPane should have 'e' binding for export."""
        from cis_bench.cli.commands.tui.catalog.pane import CatalogTabPane

        binding_keys = [b.key for b in CatalogTabPane.BINDINGS]
        assert "e" in binding_keys

    def test_has_action_export_benchmark_method(self):
        """CatalogTabPane should have action_export_benchmark method."""
        from cis_bench.cli.commands.tui.catalog.pane import CatalogTabPane

        assert hasattr(CatalogTabPane, "action_export_benchmark")
        assert callable(CatalogTabPane.action_export_benchmark)


class TestCatalogTabPaneActionMenu:
    """Test action menu in catalog tab pane (Phase 2b)."""

    def test_has_enter_binding_for_actions(self):
        """CatalogTabPane should have 'enter' binding for actions menu."""
        from cis_bench.cli.commands.tui.catalog.pane import CatalogTabPane

        binding_keys = [b.key for b in CatalogTabPane.BINDINGS]
        assert "enter" in binding_keys

    def test_has_action_open_actions_method(self):
        """CatalogTabPane should have action_open_actions method."""
        from cis_bench.cli.commands.tui.catalog.pane import CatalogTabPane

        assert hasattr(CatalogTabPane, "action_open_actions")
        assert callable(CatalogTabPane.action_open_actions)
