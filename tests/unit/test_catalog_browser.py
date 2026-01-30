"""Tests for catalog browser TUI functionality."""

import pytest


class TestCatalogBrowserAppExists:
    """Test that CatalogBrowserApp class exists and has expected structure."""

    def test_catalog_browser_app_importable(self):
        """CatalogBrowserApp should be importable."""
        from cis_bench.cli.commands.catalog_tui import CatalogBrowserApp

        assert CatalogBrowserApp is not None

    def test_catalog_browser_app_extends_base_browser(self):
        """CatalogBrowserApp should extend BaseBrowserApp."""
        from cis_bench.cli.commands.catalog_tui import CatalogBrowserApp
        from cis_bench.cli.commands.tui_base import BaseBrowserApp

        assert issubclass(CatalogBrowserApp, BaseBrowserApp)

    def test_catalog_detail_view_exists(self):
        """CatalogDetailView should be importable."""
        from cis_bench.cli.commands.catalog_tui import CatalogDetailView

        assert CatalogDetailView is not None

    def test_catalog_detail_view_extends_detail_view(self):
        """CatalogDetailView should extend DetailView."""
        from cis_bench.cli.commands.catalog_tui import CatalogDetailView
        from cis_bench.cli.commands.tui_base import DetailView

        assert issubclass(CatalogDetailView, DetailView)


class TestCatalogBrowserBindings:
    """Test that catalog browser has expected key bindings."""

    def test_has_search_binding(self):
        """Catalog browser should have search binding (/)."""
        from cis_bench.cli.commands.catalog_tui import CatalogBrowserApp

        binding_keys = [b.key for b in CatalogBrowserApp.BINDINGS]
        assert "slash" in binding_keys

    def test_has_space_for_multiselect(self):
        """Catalog browser should have space binding for multi-select."""
        from cis_bench.cli.commands.catalog_tui import CatalogBrowserApp

        binding_keys = [b.key for b in CatalogBrowserApp.BINDINGS]
        assert "space" in binding_keys

    def test_has_jump_binding(self):
        """Catalog browser should have g binding for jump."""
        from cis_bench.cli.commands.catalog_tui import CatalogBrowserApp

        binding_keys = [b.key for b in CatalogBrowserApp.BINDINGS]
        assert "g" in binding_keys

    def test_has_help_binding(self):
        """Catalog browser should have ? binding for help."""
        from cis_bench.cli.commands.catalog_tui import CatalogBrowserApp

        binding_keys = [b.key for b in CatalogBrowserApp.BINDINGS]
        assert "question_mark" in binding_keys

    def test_has_quit_binding(self):
        """Catalog browser should have q binding for quit."""
        from cis_bench.cli.commands.catalog_tui import CatalogBrowserApp

        binding_keys = [b.key for b in CatalogBrowserApp.BINDINGS]
        assert "q" in binding_keys


class TestCatalogBrowserActions:
    """Test that catalog browser has expected action methods."""

    def test_has_toggle_select_action(self):
        """CatalogBrowserApp should have action_toggle_select method."""
        from cis_bench.cli.commands.catalog_tui import CatalogBrowserApp

        assert hasattr(CatalogBrowserApp, "action_toggle_select")
        assert callable(CatalogBrowserApp.action_toggle_select)

    def test_has_apply_search_filter(self):
        """CatalogBrowserApp should have _apply_search_filter method."""
        from cis_bench.cli.commands.catalog_tui import CatalogBrowserApp

        assert hasattr(CatalogBrowserApp, "_apply_search_filter")
        assert callable(CatalogBrowserApp._apply_search_filter)


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
        """CatalogBrowserApp should accept benchmarks in constructor."""
        from cis_bench.cli.commands.catalog_tui import CatalogBrowserApp

        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        assert hasattr(app, "_benchmarks")
        assert app._benchmarks == sample_benchmarks

    def test_initializes_empty_selection(self, sample_benchmarks):
        """CatalogBrowserApp should initialize with empty selection set."""
        from cis_bench.cli.commands.catalog_tui import CatalogBrowserApp

        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        assert hasattr(app, "_selected_indices")
        assert isinstance(app._selected_indices, set)
        assert len(app._selected_indices) == 0

    def test_stores_all_benchmarks(self, sample_benchmarks):
        """CatalogBrowserApp should store all benchmarks for filtering."""
        from cis_bench.cli.commands.catalog_tui import CatalogBrowserApp

        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        assert hasattr(app, "_all_benchmarks")
        assert app._all_benchmarks == sample_benchmarks


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
        from cis_bench.cli.commands.catalog_tui import CatalogDetailView

        view = CatalogDetailView()
        # Should not raise
        view.update_content(sample_benchmark)

    def test_update_content_sets_text(self, sample_benchmark):
        """CatalogDetailView.update_content should set content text."""
        from cis_bench.cli.commands.catalog_tui import CatalogDetailView

        view = CatalogDetailView()
        view.update_content(sample_benchmark)
        content = view.get_content_text()
        assert sample_benchmark["title"] in content

    def test_content_includes_version(self, sample_benchmark):
        """Detail content should include benchmark version."""
        from cis_bench.cli.commands.catalog_tui import CatalogDetailView

        view = CatalogDetailView()
        view.update_content(sample_benchmark)
        content = view.get_content_text()
        assert sample_benchmark["version"] in content

    def test_content_includes_platform(self, sample_benchmark):
        """Detail content should include platform."""
        from cis_bench.cli.commands.catalog_tui import CatalogDetailView

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
        from cis_bench.cli.commands.catalog_tui import CatalogBrowserApp

        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        result = app.get_selected_items()
        assert isinstance(result, list)

    def test_get_selected_items_empty_initially(self, sample_benchmarks):
        """get_selected_items should return empty list initially."""
        from cis_bench.cli.commands.catalog_tui import CatalogBrowserApp

        app = CatalogBrowserApp(benchmarks=sample_benchmarks)
        result = app.get_selected_items()
        assert len(result) == 0


class TestRunCatalogBrowserFunction:
    """Test the run_catalog_browser entry point function."""

    def test_run_catalog_browser_exists(self):
        """run_catalog_browser function should exist."""
        from cis_bench.cli.commands.catalog_tui import run_catalog_browser

        assert callable(run_catalog_browser)
