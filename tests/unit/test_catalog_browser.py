"""Tests for catalog browser TUI functionality."""

import pytest


class TestCatalogCSSExtension:
    """Test that CATALOG_CSS properly extends COMMON_CSS."""

    def test_catalog_css_contains_common_css(self):
        """CATALOG_CSS should include all of COMMON_CSS."""
        from cis_bench.cli.commands.tui import COMMON_CSS
        from cis_bench.cli.commands.tui.catalog.actions import CATALOG_CSS

        # Key elements from COMMON_CSS should be in CATALOG_CSS
        assert "#main-container" in CATALOG_CSS
        assert "#detail-container" in CATALOG_CSS
        assert "#search-container" in CATALOG_CSS
        # COMMON_CSS has dialogs that catalog should inherit
        assert "#save-dialog" in CATALOG_CSS or COMMON_CSS in CATALOG_CSS
        assert "#help-dialog" in CATALOG_CSS or COMMON_CSS in CATALOG_CSS

    def test_catalog_css_has_overrides(self):
        """CATALOG_CSS should have catalog-specific overrides."""
        from cis_bench.cli.commands.tui.catalog.actions import CATALOG_CSS

        # Catalog uses wider list for more columns (65/35 split)
        assert "65%" in CATALOG_CSS  # list-container
        assert "35%" in CATALOG_CSS  # detail-container

    def test_catalog_css_has_action_menu(self):
        """CATALOG_CSS should include action menu styles."""
        from cis_bench.cli.commands.tui.catalog.actions import CATALOG_CSS

        assert "#action-menu" in CATALOG_CSS
        assert "#action-buttons" in CATALOG_CSS


class TestCatalogBrowserAppExists:
    """Test that CatalogBrowserApp class exists and has expected structure."""

    def test_catalog_browser_app_importable(self):
        """CatalogBrowserApp should be importable."""
        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        assert CatalogBrowserApp is not None

    def test_catalog_browser_app_extends_base_browser(self):
        """CatalogBrowserApp should extend BaseBrowserApp."""
        from cis_bench.cli.commands.tui import BaseBrowserApp
        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        assert issubclass(CatalogBrowserApp, BaseBrowserApp)

    def test_catalog_detail_view_exists(self):
        """CatalogDetailView should be importable."""
        from cis_bench.cli.commands.tui.catalog import CatalogDetailView

        assert CatalogDetailView is not None

    def test_catalog_detail_view_extends_detail_view(self):
        """CatalogDetailView should extend DetailView."""
        from cis_bench.cli.commands.tui import DetailView
        from cis_bench.cli.commands.tui.catalog import CatalogDetailView

        assert issubclass(CatalogDetailView, DetailView)


class TestCatalogBrowserBindings:
    """Test that catalog browser has expected key bindings."""

    def test_bindings_include_common_bindings(self):
        """CatalogBrowserApp BINDINGS should include all COMMON_BINDINGS."""
        from cis_bench.cli.commands.tui import COMMON_BINDINGS
        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        app_keys = [b.key for b in CatalogBrowserApp.BINDINGS]
        common_keys = [b.key for b in COMMON_BINDINGS]

        # All common keys should be in app bindings
        for key in common_keys:
            assert key in app_keys, f"Missing common binding: {key}"

    def test_has_search_binding(self):
        """Catalog browser should have search binding (/)."""
        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        binding_keys = [b.key for b in CatalogBrowserApp.BINDINGS]
        assert "slash" in binding_keys

    def test_has_space_for_multiselect(self):
        """Catalog browser should have space binding for multi-select."""
        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        binding_keys = [b.key for b in CatalogBrowserApp.BINDINGS]
        assert "space" in binding_keys

    def test_has_jump_binding(self):
        """Catalog browser should have g binding for jump."""
        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        binding_keys = [b.key for b in CatalogBrowserApp.BINDINGS]
        assert "g" in binding_keys

    def test_has_help_binding(self):
        """Catalog browser should have ? binding for help."""
        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        binding_keys = [b.key for b in CatalogBrowserApp.BINDINGS]
        assert "question_mark" in binding_keys

    def test_has_quit_binding(self):
        """Catalog browser should have q binding for quit."""
        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        binding_keys = [b.key for b in CatalogBrowserApp.BINDINGS]
        assert "q" in binding_keys

    def test_has_open_url_binding(self):
        """Catalog browser should have o binding for open URL in browser."""
        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        binding_keys = [b.key for b in CatalogBrowserApp.BINDINGS]
        assert "o" in binding_keys


class TestCatalogBrowserActions:
    """Test that catalog browser has expected action methods."""

    def test_has_toggle_select_action(self):
        """CatalogBrowserApp should have action_toggle_select method."""
        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        assert hasattr(CatalogBrowserApp, "action_toggle_select")
        assert callable(CatalogBrowserApp.action_toggle_select)

    def test_has_apply_search_filter(self):
        """CatalogBrowserApp should have _apply_search_filter method."""
        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        assert hasattr(CatalogBrowserApp, "_apply_search_filter")
        assert callable(CatalogBrowserApp._apply_search_filter)

    def test_has_open_in_browser_action(self):
        """CatalogBrowserApp should have action_open_in_browser method."""
        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        assert hasattr(CatalogBrowserApp, "action_open_in_browser")
        assert callable(CatalogBrowserApp.action_open_in_browser)


class TestCatalogBrowserInitialization:
    """Test CatalogBrowserApp initialization."""

    @pytest.fixture
    def sample_benchmarks(self):
        """Sample benchmark data for testing."""
        return [
            {
                "benchmark_id": "23598",
                "title": "CIS Ubuntu Linux 22.04 LTS Benchmark",
                "version": "v2.0.0",
                "platform": "Operating System",
                "published_date": "2024-01-15",
                "is_latest": True,
                "status": "Published",
                "description": "Security configuration benchmark for Ubuntu 22.04",
            },
            {
                "benchmark_id": "23456",
                "title": "CIS Amazon Linux 2023 Benchmark",
                "version": "v1.0.0",
                "platform": "Operating System",
                "published_date": "2024-02-20",
                "is_latest": True,
                "status": "Published",
                "description": "Security configuration benchmark for Amazon Linux 2023",
            },
        ]

    def test_accepts_benchmarks_parameter(self, sample_benchmarks):
        """CatalogBrowserApp should accept benchmarks in constructor (sorted)."""
        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        # Standardized naming: _items for current visible items
        assert hasattr(app, "_items")
        # Items are sorted by title, check all items present
        assert len(app._items) == len(sample_benchmarks)
        original_ids = {b["benchmark_id"] for b in sample_benchmarks}
        sorted_ids = {b["benchmark_id"] for b in app._items}
        assert sorted_ids == original_ids

    def test_initializes_empty_selection(self, sample_benchmarks):
        """CatalogBrowserApp should initialize with empty selection set."""
        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        assert hasattr(app, "_selected_indices")
        assert isinstance(app._selected_indices, set)
        assert len(app._selected_indices) == 0

    def test_stores_all_benchmarks(self, sample_benchmarks):
        """CatalogBrowserApp should store all items for filtering (sorted)."""
        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        # Standardized naming: _all_items for unfiltered source
        assert hasattr(app, "_all_items")
        # Items are sorted by title, then by benchmark_id descending within groups
        # Check all items present (order may differ due to sorting)
        assert len(app._all_items) == len(sample_benchmarks)
        original_ids = {b["benchmark_id"] for b in sample_benchmarks}
        sorted_ids = {b["benchmark_id"] for b in app._all_items}
        assert sorted_ids == original_ids


class TestCatalogDetailViewContent:
    """Test CatalogDetailView content rendering."""

    @pytest.fixture
    def sample_benchmark(self):
        """Sample benchmark for detail view testing."""
        return {
            "benchmark_id": "23598",
            "title": "CIS Ubuntu Linux 22.04 LTS Benchmark",
            "version": "v2.0.0",
            "platform": "Operating System",
            "community": "CIS Ubuntu Linux",
            "published_date": "2024-01-15",
            "is_latest": True,
            "status": "Published",
            "description": "Security configuration benchmark for Ubuntu 22.04 LTS",
            "url": "https://workbench.cisecurity.org/benchmarks/23598",
        }

    def test_update_content_accepts_benchmark(self, sample_benchmark):
        """CatalogDetailView should have update_content method accepting benchmark dict."""
        from cis_bench.cli.commands.tui.catalog import CatalogDetailView

        view = CatalogDetailView()
        # Should not raise
        view.update_content(sample_benchmark)

    def test_update_content_sets_text(self, sample_benchmark):
        """CatalogDetailView.update_content should set content text."""
        from cis_bench.cli.commands.tui.catalog import CatalogDetailView

        view = CatalogDetailView()
        view.update_content(sample_benchmark)
        content = view.get_content_text()
        assert sample_benchmark["title"] in content

    def test_content_includes_version(self, sample_benchmark):
        """Detail content should include benchmark version."""
        from cis_bench.cli.commands.tui.catalog import CatalogDetailView

        view = CatalogDetailView()
        view.update_content(sample_benchmark)
        content = view.get_content_text()
        assert sample_benchmark["version"] in content

    def test_content_includes_platform(self, sample_benchmark):
        """Detail content should include platform."""
        from cis_bench.cli.commands.tui.catalog import CatalogDetailView

        view = CatalogDetailView()
        view.update_content(sample_benchmark)
        content = view.get_content_text()
        assert sample_benchmark["platform"] in content


class TestCatalogBrowserMultiSelect:
    """Test multi-select functionality in catalog browser."""

    @pytest.fixture
    def sample_benchmarks(self):
        """Sample benchmark data for testing."""
        return [
            {"benchmark_id": "1", "title": "Benchmark 1", "version": "v1", "platform": "OS"},
            {"benchmark_id": "2", "title": "Benchmark 2", "version": "v1", "platform": "OS"},
            {"benchmark_id": "3", "title": "Benchmark 3", "version": "v1", "platform": "OS"},
        ]

    def test_get_selected_items_returns_list(self, sample_benchmarks):
        """get_selected_items should return a list."""
        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        result = app.get_selected_items()
        assert isinstance(result, list)

    def test_get_selected_items_empty_initially(self, sample_benchmarks):
        """get_selected_items should return empty list initially."""
        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        result = app.get_selected_items()
        assert len(result) == 0


class TestRunCatalogBrowserFunction:
    """Test the run_catalog_browser entry point function."""

    def test_run_catalog_browser_exists(self):
        """run_catalog_browser function should exist."""
        from cis_bench.cli.commands.tui.catalog import run_catalog_browser

        assert callable(run_catalog_browser)


class TestCatalogBrowserCachedStatus:
    """Test cached/downloaded status indicator in catalog browser."""

    @pytest.fixture
    def sample_benchmarks(self):
        """Sample benchmark data for testing."""
        return [
            {
                "benchmark_id": "23598",
                "title": "CIS Ubuntu Linux 22.04 LTS Benchmark",
                "version": "v2.0.0",
                "platform": "Operating System",
                "is_latest": True,
            },
            {
                "benchmark_id": "12345",
                "title": "CIS RHEL 9 Benchmark",
                "version": "v1.0.0",
                "platform": "Operating System",
                "is_latest": False,
            },
        ]

    def test_downloaded_ids_initialized_as_set(self, sample_benchmarks):
        """CatalogBrowserApp should initialize _downloaded_ids as set."""
        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        assert hasattr(app, "_downloaded_ids")
        assert isinstance(app._downloaded_ids, set)

    def test_has_load_downloaded_ids_method(self, sample_benchmarks):
        """CatalogBrowserApp should have _load_downloaded_ids method."""
        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        assert hasattr(app, "_load_downloaded_ids")
        assert callable(app._load_downloaded_ids)

    def test_columns_include_cached_status(self, sample_benchmarks):
        """_get_columns should include a cached status column."""
        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        columns = app._get_columns()

        # Should have 8 columns: checkbox, cached, ID, Title, Version, Latest, Published, Platform
        assert len(columns) == 8
        # Second column (after checkbox) should be for cached status
        assert columns[1] == "⬇"  # Download/cached column header
        # Verify key columns exist
        assert "Version" in columns
        assert "Latest" in columns
        assert "Published" in columns

    def test_is_downloaded_check_works(self, sample_benchmarks):
        """Should be able to check if benchmark is downloaded."""
        from cis_bench.cli.commands.tui.catalog import CatalogBrowserApp

        app = CatalogBrowserApp(benchmarks=sample_benchmarks)

        # Initially empty
        assert "23598" not in app._downloaded_ids

        # Manually add for testing
        app._downloaded_ids.add("23598")
        assert "23598" in app._downloaded_ids
        assert "12345" not in app._downloaded_ids
