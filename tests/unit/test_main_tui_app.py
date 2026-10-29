"""Unit tests for MainTUIApp (sync tests, no app.run_test()).

Tests for:
- TabConfig dataclass structure
- TABS configuration list
- Helper functions (get_tab_labels, get_tab_count)
- MainTUIApp bindings

Phase 1 unit tests - mirrors tests/integration/test_main_tui.py pattern.
"""


class TestTabConfig:
    """Test TabConfig dataclass structure."""

    def test_tab_config_has_required_fields(self):
        """TabConfig should have id, label, pane_class fields."""
        from cis_bench.cli.commands.tui.main_app import TabConfig

        # Create instance to verify fields work
        config = TabConfig(
            id="test-tab",
            label="Test",
            pane_class=None,
        )
        assert config.id == "test-tab"
        assert config.label == "Test"
        assert config.pane_class is None

    def test_tab_config_has_optional_placeholder_text(self):
        """TabConfig should have optional placeholder_text with default."""
        from cis_bench.cli.commands.tui.main_app import TabConfig

        # Without placeholder_text
        config1 = TabConfig(id="t1", label="T1", pane_class=None)
        assert config1.placeholder_text == ""

        # With placeholder_text
        config2 = TabConfig(id="t2", label="T2", pane_class=None, placeholder_text="Coming soon")
        assert config2.placeholder_text == "Coming soon"


class TestTabsConfig:
    """Test TABS configuration list."""

    def test_tabs_is_non_empty_list(self):
        """TABS should be a non-empty list."""
        from cis_bench.cli.commands.tui.main_app import TABS

        assert isinstance(TABS, list)
        assert len(TABS) > 0

    def test_tabs_contains_tab_configs(self):
        """TABS should contain TabConfig instances."""
        from cis_bench.cli.commands.tui.main_app import TABS, TabConfig

        for tab in TABS:
            assert isinstance(tab, TabConfig)

    def test_tabs_has_catalog_first(self):
        """First tab should be Catalog (primary use case)."""
        from cis_bench.cli.commands.tui.main_app import TABS

        assert TABS[0].id == "tab-catalog"
        assert TABS[0].label == "Catalog"

    def test_all_tab_ids_unique(self):
        """All tab IDs should be unique."""
        from cis_bench.cli.commands.tui.main_app import TABS

        ids = [tab.id for tab in TABS]
        assert len(ids) == len(set(ids)), "Duplicate tab IDs found"

    def test_all_tab_labels_unique(self):
        """All tab labels should be unique."""
        from cis_bench.cli.commands.tui.main_app import TABS

        labels = [tab.label for tab in TABS]
        assert len(labels) == len(set(labels)), "Duplicate tab labels found"

    def test_catalog_tab_has_pane_class(self):
        """Catalog tab should have a pane_class (not placeholder)."""
        from cis_bench.cli.commands.tui.main_app import TABS

        catalog_tab = next(t for t in TABS if t.id == "tab-catalog")
        assert catalog_tab.pane_class is not None


class TestTabHelperFunctions:
    """Test tab helper functions."""

    def test_get_tab_labels_returns_list(self):
        """get_tab_labels should return list of strings."""
        from cis_bench.cli.commands.tui.main_app import get_tab_labels

        labels = get_tab_labels()
        assert isinstance(labels, list)
        assert all(isinstance(label, str) for label in labels)

    def test_get_tab_labels_matches_tabs(self):
        """get_tab_labels should match TABS config."""
        from cis_bench.cli.commands.tui.main_app import TABS, get_tab_labels

        labels = get_tab_labels()
        expected = [tab.label for tab in TABS]
        assert labels == expected

    def test_get_tab_count_returns_int(self):
        """get_tab_count should return integer."""
        from cis_bench.cli.commands.tui.main_app import get_tab_count

        count = get_tab_count()
        assert isinstance(count, int)

    def test_get_tab_count_matches_tabs(self):
        """get_tab_count should match len(TABS)."""
        from cis_bench.cli.commands.tui.main_app import TABS, get_tab_count

        assert get_tab_count() == len(TABS)


class TestMainTUIAppBindings:
    """Test MainTUIApp keybindings."""

    def test_has_quit_binding(self):
        """MainTUIApp should have quit binding."""
        from cis_bench.cli.commands.tui.main_app import MainTUIApp

        # Bindings can be Binding objects or tuples (key, action, description)
        binding_keys = []
        for b in MainTUIApp.BINDINGS:
            if hasattr(b, "key"):
                binding_keys.append(b.key)
            elif isinstance(b, tuple):
                binding_keys.append(b[0])  # First element is key
        assert "q" in binding_keys or "escape" in binding_keys

    def test_has_quit_action(self):
        """MainTUIApp should have action_quit method."""
        from cis_bench.cli.commands.tui.main_app import MainTUIApp

        assert hasattr(MainTUIApp, "action_quit")
        assert callable(MainTUIApp.action_quit)


class TestMainTUIAppClass:
    """Test MainTUIApp class structure."""

    def test_main_tui_app_has_title(self):
        """MainTUIApp should have TITLE set."""
        from cis_bench.cli.commands.tui.main_app import MainTUIApp

        assert hasattr(MainTUIApp, "TITLE")
        assert MainTUIApp.TITLE is not None

    def test_main_tui_app_has_css(self):
        """MainTUIApp should have CSS defined."""
        from cis_bench.cli.commands.tui.main_app import MainTUIApp

        assert hasattr(MainTUIApp, "CSS")
        assert MainTUIApp.CSS is not None

    def test_main_tui_app_has_compose_method(self):
        """MainTUIApp should have compose method."""
        from cis_bench.cli.commands.tui.main_app import MainTUIApp

        assert hasattr(MainTUIApp, "compose")
        assert callable(MainTUIApp.compose)

    def test_main_tui_app_extends_app(self):
        """MainTUIApp should extend textual.App."""
        from textual.app import App

        from cis_bench.cli.commands.tui.main_app import MainTUIApp

        assert issubclass(MainTUIApp, App)
