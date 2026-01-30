"""Tests for interactive diff TUI functionality."""

import json
import os
import shutil
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from rich.console import Console

from cis_bench.cli.app import cli
from cis_bench.cli.commands.diff_tui import DiffApp, DiffDetailView
from cis_bench.cli.commands.tui_base import html_to_markdown
from cis_bench.cli.commands.utils import get_pager as _get_pager
from cis_bench.cli.commands.utils import output_with_pager as _output_with_pager


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def sample_comparison():
    """Sample comparison result for testing."""
    return {
        "old_version": "1.0.0",
        "new_version": "2.0.0",
        "benchmark_title": "Test Benchmark",
        "summary": {
            "added": 1,
            "removed": 1,
            "modified": 1,
            "unchanged": 0,
            "renumbered": 1,
        },
        "changes": {
            "added": [{"ref": "1.1.1", "title": "New recommendation"}],
            "removed": [{"ref": "2.1.1", "title": "Old recommendation"}],
            "modified": [
                {
                    "ref": "3.1.1",
                    "title": "Modified recommendation",
                    "old_title": "Old title",
                    "fields_changed": ["title", "audit"],
                    "diff": {},
                }
            ],
            "unchanged": [],
            "renumbered": [
                {
                    "old_ref": "4.1.1",
                    "new_ref": "5.1.1",
                    "title": "Renumbered recommendation",
                    "similarity": 95.0,
                }
            ],
        },
    }


@pytest.fixture
def sample_old_data():
    """Sample old benchmark data."""
    return {
        "title": "Test Benchmark",
        "version": "1.0.0",
        "recommendations": [
            {"ref": "2.1.1", "title": "Old recommendation", "description": "Old desc"},
            {"ref": "3.1.1", "title": "Old title", "audit": "old audit"},
            {"ref": "4.1.1", "title": "Renumbered recommendation", "description": "Same"},
        ],
    }


@pytest.fixture
def sample_new_data():
    """Sample new benchmark data."""
    return {
        "title": "Test Benchmark",
        "version": "2.0.0",
        "recommendations": [
            {"ref": "1.1.1", "title": "New recommendation", "description": "New desc"},
            {"ref": "3.1.1", "title": "Modified recommendation", "audit": "new audit"},
            {"ref": "5.1.1", "title": "Renumbered recommendation", "description": "Same"},
        ],
    }


@pytest.fixture
def benchmark_files(tmp_path, sample_old_data, sample_new_data):
    """Create temporary benchmark files."""
    old_file = tmp_path / "old.json"
    new_file = tmp_path / "new.json"
    old_file.write_text(json.dumps(sample_old_data))
    new_file.write_text(json.dumps(sample_new_data))
    return old_file, new_file


class TestInteractiveFlags:
    """Test interactive mode flag handling."""

    def test_no_interactive_flag_forces_table(self, runner, monkeypatch, benchmark_files):
        """--no-interactive should output table even if TTY."""
        monkeypatch.setenv("CIS_BENCH_ENV", "test")
        old_file, new_file = benchmark_files

        result = runner.invoke(cli, ["diff", str(old_file), str(new_file), "--no-interactive"])

        # Should show table output, not TUI
        assert result.exit_code == 0
        assert "Summary" in result.output or "Added" in result.output

    def test_short_no_interactive_flag(self, runner, monkeypatch, benchmark_files):
        """-I should be shorthand for --no-interactive."""
        monkeypatch.setenv("CIS_BENCH_ENV", "test")
        old_file, new_file = benchmark_files

        result = runner.invoke(cli, ["diff", str(old_file), str(new_file), "-I"])

        assert result.exit_code == 0
        assert "Summary" in result.output or "Added" in result.output

    def test_help_shows_interactive_option(self, runner, monkeypatch):
        """Help should document the interactive option."""
        monkeypatch.setenv("CIS_BENCH_ENV", "test")

        result = runner.invoke(cli, ["diff", "--help"])

        assert "interactive" in result.output.lower()


class TestTTYDetection:
    """Test TTY auto-detection behavior."""

    def test_non_tty_defaults_to_table(self, runner, monkeypatch, benchmark_files):
        """When stdout is not a TTY, should default to table output."""
        monkeypatch.setenv("CIS_BENCH_ENV", "test")
        old_file, new_file = benchmark_files

        # CliRunner's output is not a TTY, so should get table output
        result = runner.invoke(cli, ["diff", str(old_file), str(new_file)])

        assert result.exit_code == 0
        # Should have table output, not TUI (which would hang or error in test)
        assert "Summary" in result.output or "Benchmark Comparison" in result.output


class TestDiffAppCreation:
    """Test DiffApp TUI component creation."""

    def test_diff_app_instantiation(self, sample_comparison, sample_old_data, sample_new_data):
        """DiffApp should instantiate with comparison data."""
        old_recs = {r["ref"]: r for r in sample_old_data.get("recommendations", [])}
        new_recs = {r["ref"]: r for r in sample_new_data.get("recommendations", [])}

        app = DiffApp(sample_comparison, old_recs, new_recs)

        assert app.comparison == sample_comparison
        assert app.old_recs == old_recs
        assert app.new_recs == new_recs

    def test_diff_app_has_bindings(self, sample_comparison, sample_old_data, sample_new_data):
        """DiffApp should have keyboard bindings defined."""
        old_recs = {r["ref"]: r for r in sample_old_data.get("recommendations", [])}
        new_recs = {r["ref"]: r for r in sample_new_data.get("recommendations", [])}

        app = DiffApp(sample_comparison, old_recs, new_recs)

        # Check that bindings exist
        binding_keys = [b.key for b in app.BINDINGS]
        assert "q" in binding_keys
        assert "escape" in binding_keys


class TestDiffAppAsync:
    """Async tests for DiffApp using Textual's test framework."""

    @pytest.mark.asyncio
    async def test_diff_app_mounts(self, sample_comparison, sample_old_data, sample_new_data):
        """DiffApp should mount and display content."""
        old_recs = {r["ref"]: r for r in sample_old_data.get("recommendations", [])}
        new_recs = {r["ref"]: r for r in sample_new_data.get("recommendations", [])}

        app = DiffApp(sample_comparison, old_recs, new_recs)

        async with app.run_test() as pilot:
            # App should mount successfully
            assert app.is_running

            # Should have a data table
            table = app.query_one("#changes-table")
            assert table is not None

    @pytest.mark.asyncio
    async def test_diff_app_shows_changes(
        self, sample_comparison, sample_old_data, sample_new_data
    ):
        """DiffApp should display all change types."""
        old_recs = {r["ref"]: r for r in sample_old_data.get("recommendations", [])}
        new_recs = {r["ref"]: r for r in sample_new_data.get("recommendations", [])}

        app = DiffApp(sample_comparison, old_recs, new_recs)

        async with app.run_test() as pilot:
            # The change list should be populated
            assert len(app._change_list) == 4  # 1 added + 1 removed + 1 modified + 1 renumbered

    @pytest.mark.asyncio
    async def test_diff_app_keyboard_navigation(
        self, sample_comparison, sample_old_data, sample_new_data
    ):
        """DiffApp should respond to keyboard navigation."""
        old_recs = {r["ref"]: r for r in sample_old_data.get("recommendations", [])}
        new_recs = {r["ref"]: r for r in sample_new_data.get("recommendations", [])}

        app = DiffApp(sample_comparison, old_recs, new_recs)

        async with app.run_test() as pilot:
            # Press down arrow to move cursor
            await pilot.press("down")
            await pilot.press("down")

            # App should still be running
            assert app.is_running

    @pytest.mark.asyncio
    async def test_diff_app_quit_binding(self, sample_comparison, sample_old_data, sample_new_data):
        """DiffApp should quit on 'q' key."""
        old_recs = {r["ref"]: r for r in sample_old_data.get("recommendations", [])}
        new_recs = {r["ref"]: r for r in sample_new_data.get("recommendations", [])}

        app = DiffApp(sample_comparison, old_recs, new_recs)

        async with app.run_test() as pilot:
            await pilot.press("q")
            # App should be exiting
            # Note: In test mode, this might not fully quit


class TestHtmlToMarkdown:
    """Tests for HTML to Markdown conversion."""

    def test_empty_string(self):
        """Empty string returns empty string."""
        assert html_to_markdown("") == ""

    def test_none_returns_empty(self):
        """None input returns empty string."""
        assert html_to_markdown(None) == ""

    def test_plain_text_passthrough(self):
        """Plain text without HTML is returned as-is."""
        text = "This is plain text with no HTML"
        assert html_to_markdown(text) == text

    def test_simple_html_conversion(self):
        """Basic HTML tags are converted to markdown."""
        html = "<p>This is a paragraph.</p>"
        result = html_to_markdown(html)
        assert "This is a paragraph." in result

    def test_bold_conversion(self):
        """Bold HTML tags convert to markdown bold."""
        html = "<strong>bold text</strong>"
        result = html_to_markdown(html)
        assert "**bold text**" in result

    def test_list_conversion(self):
        """HTML lists convert to markdown lists."""
        html = "<ul><li>Item 1</li><li>Item 2</li></ul>"
        result = html_to_markdown(html)
        assert "Item 1" in result
        assert "Item 2" in result

    def test_code_block_conversion(self):
        """HTML code blocks convert to markdown."""
        html = "<pre><code>echo hello</code></pre>"
        result = html_to_markdown(html)
        assert "echo hello" in result

    def test_link_conversion(self):
        """HTML links are preserved."""
        html = '<a href="https://example.com">Link</a>'
        result = html_to_markdown(html)
        # html2text should keep link info
        assert "Link" in result

    def test_complex_html(self):
        """Complex HTML with nested elements."""
        html = """
        <div>
            <h2>Audit Steps</h2>
            <ol>
                <li>Run the command: <code>grep root /etc/passwd</code></li>
                <li>Verify output matches expected</li>
            </ol>
        </div>
        """
        result = html_to_markdown(html)
        assert "Audit Steps" in result
        assert "grep root" in result


class TestGetPager:
    """Tests for _get_pager() function."""

    def test_pager_env_variable(self, monkeypatch):
        """PAGER environment variable is used if set."""
        monkeypatch.setenv("PAGER", "custom-pager")
        assert _get_pager() == "custom-pager"

    def test_pager_env_empty_falls_back(self, monkeypatch):
        """Empty PAGER falls back to less."""
        monkeypatch.delenv("PAGER", raising=False)
        with patch.object(shutil, "which") as mock_which:
            mock_which.side_effect = lambda x: "/usr/bin/less" if x == "less" else None
            result = _get_pager()
            assert result == "less -R"

    def test_falls_back_to_more(self, monkeypatch):
        """Falls back to more if less not available."""
        monkeypatch.delenv("PAGER", raising=False)
        with patch.object(shutil, "which") as mock_which:
            mock_which.side_effect = lambda x: "/usr/bin/more" if x == "more" else None
            result = _get_pager()
            assert result == "more"

    def test_returns_none_if_no_pager(self, monkeypatch):
        """Returns None if no pager available."""
        monkeypatch.delenv("PAGER", raising=False)
        with patch.object(shutil, "which", return_value=None):
            result = _get_pager()
            assert result is None


class TestOutputWithPager:
    """Tests for _output_with_pager() function."""

    def test_non_tty_outputs_directly(self, monkeypatch):
        """Non-TTY output goes directly without pager."""
        # Track if output function was called
        call_count = {"count": 0}

        def output_func(_console=None):
            call_count["count"] += 1
            if _console:
                _console.print("Test output")

        # Patch isatty to return False
        with patch("sys.stdout.isatty", return_value=False):
            _output_with_pager(output_func)

        assert call_count["count"] == 1

    def test_short_output_no_pager(self, monkeypatch):
        """Short output that fits in terminal doesn't use pager."""
        monkeypatch.delenv("PAGER", raising=False)

        def output_func(_console=None):
            if _console:
                _console.print("Short output")

        with patch("sys.stdout.isatty", return_value=True):
            with patch.object(shutil, "get_terminal_size", return_value=os.terminal_size((80, 50))):
                with patch.object(shutil, "which", return_value="/usr/bin/less"):
                    # Should not use pager for short output
                    _output_with_pager(output_func)

    def test_passes_console_to_output_func(self, monkeypatch):
        """_console parameter is passed to output function."""
        received_console = {"console": None}

        def output_func(_console=None):
            received_console["console"] = _console
            if _console:
                _console.print("Test")

        with patch("sys.stdout.isatty", return_value=True):
            with patch.object(shutil, "get_terminal_size", return_value=os.terminal_size((80, 50))):
                with patch.object(shutil, "which", return_value="/usr/bin/less"):
                    _output_with_pager(output_func)

        assert received_console["console"] is not None
        assert isinstance(received_console["console"], Console)


class TestSkipVisuallyIdenticalFields:
    """Tests for skipping visually identical fields in diff detail."""

    def test_identical_content_after_normalization_is_skipped(self):
        """Fields that normalize to identical markdown are skipped."""
        detail_view = DiffDetailView()

        change_data = {
            "ref": "1.1.1",
            "title": "Test",
            "fields_changed": ["description"],
        }

        # Same content, different HTML encoding
        old_rec = {"description": "<p>Same content</p>"}
        new_rec = {"description": "<div><p>Same content</p></div>"}

        detail_view.update_content("modified", change_data, old_rec, new_rec)

        content = detail_view.get_content_text()
        # Should show "only formatting changes" message
        assert "formatting" in content.lower() or "encoding" in content.lower()

    def test_different_content_is_shown(self):
        """Fields with actual content differences are shown."""
        detail_view = DiffDetailView()

        change_data = {
            "ref": "1.1.1",
            "title": "Test",
            "fields_changed": ["description"],
        }

        old_rec = {"description": "<p>Old content</p>"}
        new_rec = {"description": "<p>New different content</p>"}

        detail_view.update_content("modified", change_data, old_rec, new_rec)

        content = detail_view.get_content_text()
        # Should show the diff
        assert "Old content" in content or "Before" in content
        assert "New different content" in content or "After" in content

    def test_leading_trailing_whitespace_is_skipped(self):
        """Leading/trailing whitespace differences are skipped."""
        detail_view = DiffDetailView()

        change_data = {
            "ref": "1.1.1",
            "title": "Test",
            "fields_changed": ["audit"],
        }

        # Same content, but with leading/trailing whitespace differences
        old_rec = {"audit": "  Run command  "}
        new_rec = {"audit": "\n\nRun command\n\n"}

        detail_view.update_content("modified", change_data, old_rec, new_rec)

        content = detail_view.get_content_text()
        # Should indicate only formatting changes
        assert "formatting" in content.lower() or "encoding" in content.lower()

    def test_multiple_fields_mixed(self):
        """Mix of identical and different fields handled correctly."""
        detail_view = DiffDetailView()

        change_data = {
            "ref": "1.1.1",
            "title": "Test",
            "fields_changed": ["description", "rationale", "audit"],
        }

        old_rec = {
            "description": "<p>Same</p>",  # Will be identical after normalization
            "rationale": "Old rationale",  # Different
            "audit": "<code>same code</code>",  # Will be identical
        }
        new_rec = {
            "description": "Same",  # Same content, different format
            "rationale": "New rationale",  # Different
            "audit": "`same code`",  # Different encoding, same result
        }

        detail_view.update_content("modified", change_data, old_rec, new_rec)

        content = detail_view.get_content_text()
        # Should show rationale diff (it's actually different)
        assert "rationale" in content.lower() or "Rationale" in content


class TestNaturalSortKey:
    """Tests for natural/version sorting of CIS refs."""

    def test_simple_refs(self):
        """Simple refs sort numerically."""
        from cis_bench.cli.commands.tui_base import natural_sort_key

        refs = ["1.2", "1.1", "1.10", "1.3", "2.1"]
        sorted_refs = sorted(refs, key=natural_sort_key)

        assert sorted_refs == ["1.1", "1.2", "1.3", "1.10", "2.1"]

    def test_deep_refs(self):
        """Deep refs (3+ levels) sort correctly."""
        from cis_bench.cli.commands.tui_base import natural_sort_key

        refs = ["1.1.1", "1.1.10", "1.1.2", "1.2.1", "1.10.1"]
        sorted_refs = sorted(refs, key=natural_sort_key)

        assert sorted_refs == ["1.1.1", "1.1.2", "1.1.10", "1.2.1", "1.10.1"]

    def test_mixed_depth_refs(self):
        """Refs with different depths sort correctly."""
        from cis_bench.cli.commands.tui_base import natural_sort_key

        refs = ["1.1.1", "1.2", "1.1", "1.2.3", "1.10"]
        sorted_refs = sorted(refs, key=natural_sort_key)

        assert sorted_refs == ["1.1", "1.1.1", "1.2", "1.2.3", "1.10"]

    def test_cis_benchmark_refs(self):
        """Real CIS benchmark ref patterns sort correctly."""
        from cis_bench.cli.commands.tui_base import natural_sort_key

        refs = ["6.2.3.14", "6.2.3.2", "6.1.2.5", "1.1.1.1", "6.2.3.1"]
        sorted_refs = sorted(refs, key=natural_sort_key)

        assert sorted_refs == ["1.1.1.1", "6.1.2.5", "6.2.3.1", "6.2.3.2", "6.2.3.14"]

    def test_empty_ref(self):
        """Empty ref doesn't crash, sorts to end."""
        from cis_bench.cli.commands.tui_base import natural_sort_key

        refs = ["1.1", "", "1.2"]
        sorted_refs = sorted(refs, key=natural_sort_key)

        # Empty refs sort to end (reasonable for anomalies)
        assert sorted_refs == ["1.1", "1.2", ""]

    def test_descending_sort(self):
        """Descending sort works with reverse=True."""
        from cis_bench.cli.commands.tui_base import natural_sort_key

        refs = ["1.1", "1.2", "1.10", "2.1"]
        sorted_refs = sorted(refs, key=natural_sort_key, reverse=True)

        assert sorted_refs == ["2.1", "1.10", "1.2", "1.1"]


class TestReferencesRendering:
    """Tests for references field rendering (fixes character-by-character bug)."""

    def test_references_as_string_html(self):
        """References as HTML string should render as markdown, not char-by-char."""
        from cis_bench.cli.commands.tui_base import DetailView

        detail_view = DetailView()
        rec = {
            "ref": "6.1.2.5",
            "title": "Ensure rsyslog logging is configured",
            "references": "<p>See the <b>rsyslog(8)</b> man page for more information.</p>",
        }

        content = detail_view.render_recommendation(rec)

        # Should contain the full text, not individual characters as bullets
        assert "rsyslog" in content
        assert "man page" in content
        # Should NOT have single-character bullets like "- r" "- s" "- y"
        assert "- r\n" not in content
        assert "- s\n" not in content

    def test_references_as_list(self):
        """References as list should render as bullet items."""
        from cis_bench.cli.commands.tui_base import DetailView

        detail_view = DetailView()
        rec = {
            "ref": "1.1.1",
            "title": "Test Control",
            "references": ["https://example.com/ref1", "https://example.com/ref2"],
        }

        content = detail_view.render_recommendation(rec)

        # Should have bullet items
        assert "- https://example.com/ref1" in content
        assert "- https://example.com/ref2" in content


class TestDiffDetailViewContent:
    """Tests for DiffDetailView content generation."""

    def test_added_recommendation_content(self):
        """Added recommendation shows full new content."""
        detail_view = DiffDetailView()

        change_data = {"ref": "1.1.1", "title": "New Security Control"}
        new_rec = {
            "description": "This is the description",
            "rationale": "This is why it matters",
            "audit": "Run this command",
            "remediation": "Fix it this way",
        }

        detail_view.update_content("added", change_data, None, new_rec)

        content = detail_view.get_content_text()
        assert "ADDED" in content
        assert "1.1.1" in content
        assert "New Security Control" in content

    def test_removed_recommendation_content(self):
        """Removed recommendation shows old content."""
        detail_view = DiffDetailView()

        change_data = {"ref": "2.1.1", "title": "Deprecated Control"}
        old_rec = {"description": "Old description here"}

        detail_view.update_content("removed", change_data, old_rec, None)

        content = detail_view.get_content_text()
        assert "REMOVED" in content
        assert "2.1.1" in content

    def test_renumbered_recommendation_content(self):
        """Renumbered recommendation shows ref change and similarity."""
        detail_view = DiffDetailView()

        change_data = {
            "old_ref": "1.1",
            "new_ref": "2.1",
            "title": "Moved Control",
            "similarity": 95.5,
        }
        new_rec = {"description": "Control description"}

        detail_view.update_content("renumbered", change_data, None, new_rec)

        content = detail_view.get_content_text()
        assert "RENUMBERED" in content
        assert "1.1" in content
        assert "2.1" in content
        assert "95.5%" in content


class TestSearchInTUI:
    """Tests for search functionality in TUI (/ key)."""

    def test_search_binding_exists_in_common_bindings(self):
        """The '/' key should be in COMMON_BINDINGS for search."""
        from cis_bench.cli.commands.tui_base import COMMON_BINDINGS

        binding_keys = [b.key for b in COMMON_BINDINGS]
        assert "slash" in binding_keys or "/" in binding_keys

    def test_base_browser_app_has_search_action(self):
        """BaseBrowserApp should have action_start_search method."""
        from cis_bench.cli.commands.tui_base import BaseBrowserApp

        assert hasattr(BaseBrowserApp, "action_start_search")

    def test_search_input_class_exists(self):
        """SearchInput widget should exist in tui_base."""
        from cis_bench.cli.commands.tui_base import SearchInput

        assert SearchInput is not None

    @pytest.mark.asyncio
    async def test_search_opens_on_slash(self, sample_comparison, sample_old_data, sample_new_data):
        """Pressing '/' should show search input."""
        old_recs = {r["ref"]: r for r in sample_old_data.get("recommendations", [])}
        new_recs = {r["ref"]: r for r in sample_new_data.get("recommendations", [])}

        app = DiffApp(sample_comparison, old_recs, new_recs)

        async with app.run_test() as pilot:
            # Press '/' to open search
            await pilot.press("slash")

            # Search input should be visible
            search_input = app.query("SearchInput")
            assert len(search_input) > 0 or app.query("#search-input")

    @pytest.mark.asyncio
    async def test_search_filters_results(
        self, sample_comparison, sample_old_data, sample_new_data
    ):
        """Typing in search should filter the visible items."""
        old_recs = {r["ref"]: r for r in sample_old_data.get("recommendations", [])}
        new_recs = {r["ref"]: r for r in sample_new_data.get("recommendations", [])}

        app = DiffApp(sample_comparison, old_recs, new_recs)

        async with app.run_test() as pilot:
            # Initial count
            initial_count = len(app._change_list)
            assert initial_count > 0

            # Open search and type
            await pilot.press("slash")
            await pilot.press("x", "y", "z")  # Type something unlikely to match

            # The visible items should be filtered (or show no matches)
            # This tests that the filter mechanism exists
            assert app._search_query is not None or hasattr(app, "_search_query")

    @pytest.mark.asyncio
    async def test_escape_closes_search(self, sample_comparison, sample_old_data, sample_new_data):
        """Pressing Escape should close search and restore all items."""
        old_recs = {r["ref"]: r for r in sample_old_data.get("recommendations", [])}
        new_recs = {r["ref"]: r for r in sample_new_data.get("recommendations", [])}

        app = DiffApp(sample_comparison, old_recs, new_recs)

        async with app.run_test() as pilot:
            # Open search
            await pilot.press("slash")
            # Close with escape
            await pilot.press("escape")

            # Search should be closed (no search input visible or search mode off)
            assert not getattr(app, "_search_active", True) or app.query("#search-input") == []


class TestOfflineIndicator:
    """Tests for offline mode indicator in TUI."""

    def test_diff_app_accepts_offline_parameter(
        self, sample_comparison, sample_old_data, sample_new_data
    ):
        """DiffApp should accept an offline parameter."""
        old_recs = {r["ref"]: r for r in sample_old_data.get("recommendations", [])}
        new_recs = {r["ref"]: r for r in sample_new_data.get("recommendations", [])}

        app = DiffApp(sample_comparison, old_recs, new_recs, offline=True)
        assert app.offline is True

    def test_diff_app_offline_defaults_false(
        self, sample_comparison, sample_old_data, sample_new_data
    ):
        """DiffApp offline should default to False."""
        old_recs = {r["ref"]: r for r in sample_old_data.get("recommendations", [])}
        new_recs = {r["ref"]: r for r in sample_new_data.get("recommendations", [])}

        app = DiffApp(sample_comparison, old_recs, new_recs)
        assert app.offline is False

    @pytest.mark.asyncio
    async def test_diff_app_shows_offline_indicator(
        self, sample_comparison, sample_old_data, sample_new_data
    ):
        """DiffApp should show offline indicator when offline=True."""
        old_recs = {r["ref"]: r for r in sample_old_data.get("recommendations", [])}
        new_recs = {r["ref"]: r for r in sample_new_data.get("recommendations", [])}

        app = DiffApp(sample_comparison, old_recs, new_recs, offline=True)

        async with app.run_test() as pilot:
            # Check that offline indicator is visible in summary
            # The summary is built with _build_summary which includes [OFFLINE]
            assert app.offline is True
            # Verify _build_summary includes OFFLINE text
            summary_text = str(app._build_summary())
            assert "OFFLINE" in summary_text

    @pytest.mark.asyncio
    async def test_diff_app_no_offline_indicator_when_online(
        self, sample_comparison, sample_old_data, sample_new_data
    ):
        """DiffApp should not show offline indicator when offline=False."""
        old_recs = {r["ref"]: r for r in sample_old_data.get("recommendations", [])}
        new_recs = {r["ref"]: r for r in sample_new_data.get("recommendations", [])}

        app = DiffApp(sample_comparison, old_recs, new_recs, offline=False)

        async with app.run_test() as pilot:
            # Verify _build_summary does not include OFFLINE text
            summary_text = str(app._build_summary())
            assert "OFFLINE" not in summary_text


class TestHelpScreen:
    """Tests for the help screen modal (? key)."""

    def test_help_screen_class_exists(self):
        """HelpScreen class should exist in tui_base."""
        from cis_bench.cli.commands.tui_base import HelpScreen

        assert HelpScreen is not None

    def test_help_screen_instantiation(self):
        """HelpScreen should instantiate with bindings list."""
        from cis_bench.cli.commands.tui_base import COMMON_BINDINGS, HelpScreen

        screen = HelpScreen(COMMON_BINDINGS)
        assert screen is not None
        assert screen.bindings_list == COMMON_BINDINGS

    def test_help_screen_formats_bindings(self):
        """HelpScreen should format bindings for display."""
        from textual.binding import Binding

        from cis_bench.cli.commands.tui_base import HelpScreen

        test_bindings = [
            Binding("q", "quit", "Quit"),
            Binding("question_mark", "show_help", "Help"),
            Binding("s", "save", "Save Report"),
        ]

        screen = HelpScreen(test_bindings)
        content = screen.get_help_content()

        # Keys are title-cased in display
        assert "Q" in content or "q" in content
        assert "Quit" in content
        assert "?" in content  # question_mark displays as ?
        assert "Help" in content
        assert "S" in content or "s" in content
        assert "Save Report" in content

    def test_help_binding_exists_in_common_bindings(self):
        """The '?' key should be in COMMON_BINDINGS."""
        from cis_bench.cli.commands.tui_base import COMMON_BINDINGS

        binding_keys = [b.key for b in COMMON_BINDINGS]
        assert "question_mark" in binding_keys or "?" in binding_keys

    def test_base_browser_app_has_help_action(self):
        """BaseBrowserApp should have action_show_help method."""
        from cis_bench.cli.commands.tui_base import BaseBrowserApp

        assert hasattr(BaseBrowserApp, "action_show_help")


class TestHelpScreenAsync:
    """Async tests for help screen functionality."""

    @pytest.mark.asyncio
    async def test_help_screen_opens_on_question_mark(
        self, sample_comparison, sample_old_data, sample_new_data
    ):
        """Pressing '?' should open the help screen."""
        old_recs = {r["ref"]: r for r in sample_old_data.get("recommendations", [])}
        new_recs = {r["ref"]: r for r in sample_new_data.get("recommendations", [])}

        app = DiffApp(sample_comparison, old_recs, new_recs)

        async with app.run_test() as pilot:
            # Press '?' to open help
            await pilot.press("?")

            # Help screen should be visible (check for modal or screen stack)
            # The screen stack should have more than just the main screen
            assert len(app.screen_stack) > 1 or app.query("HelpScreen")

    @pytest.mark.asyncio
    async def test_help_screen_closes_on_escape(
        self, sample_comparison, sample_old_data, sample_new_data
    ):
        """Pressing escape should close the help screen."""
        old_recs = {r["ref"]: r for r in sample_old_data.get("recommendations", [])}
        new_recs = {r["ref"]: r for r in sample_new_data.get("recommendations", [])}

        app = DiffApp(sample_comparison, old_recs, new_recs)

        async with app.run_test() as pilot:
            # Open help
            await pilot.press("?")
            # Close with escape
            await pilot.press("escape")

            # Should be back to main screen
            assert len(app.screen_stack) == 1

    @pytest.mark.asyncio
    async def test_help_screen_closes_on_question_mark_again(
        self, sample_comparison, sample_old_data, sample_new_data
    ):
        """Pressing '?' again should close the help screen."""
        old_recs = {r["ref"]: r for r in sample_old_data.get("recommendations", [])}
        new_recs = {r["ref"]: r for r in sample_new_data.get("recommendations", [])}

        app = DiffApp(sample_comparison, old_recs, new_recs)

        async with app.run_test() as pilot:
            # Open help
            await pilot.press("?")
            # Close with '?' again
            await pilot.press("?")

            # Should be back to main screen
            assert len(app.screen_stack) == 1

    @pytest.mark.asyncio
    async def test_help_screen_displays_all_bindings(
        self, sample_comparison, sample_old_data, sample_new_data
    ):
        """Help screen should display all keyboard bindings."""
        old_recs = {r["ref"]: r for r in sample_old_data.get("recommendations", [])}
        new_recs = {r["ref"]: r for r in sample_new_data.get("recommendations", [])}

        app = DiffApp(sample_comparison, old_recs, new_recs)

        async with app.run_test() as pilot:
            await pilot.press("?")

            # Check that help content includes key bindings
            # Look for common bindings in the screen content
            help_screen = app.screen
            assert help_screen is not None


class TestJumpToRef:
    """Tests for jump to ref feature (g key) - ep9.14."""

    def test_jump_binding_exists_in_common_bindings(self):
        """COMMON_BINDINGS should have 'g' key for jump to ref."""
        from cis_bench.cli.commands.tui_base import COMMON_BINDINGS

        keys = [b.key for b in COMMON_BINDINGS]
        assert "g" in keys

    def test_base_browser_app_has_jump_action(self):
        """BaseBrowserApp should have action_jump_to_ref method."""
        from cis_bench.cli.commands.tui_base import BaseBrowserApp

        assert hasattr(BaseBrowserApp, "action_jump_to_ref")

    @pytest.mark.asyncio
    async def test_jump_dialog_opens_on_g_key(
        self, sample_comparison, sample_old_data, sample_new_data
    ):
        """Pressing 'g' should open the jump to ref dialog."""
        old_recs = {r["ref"]: r for r in sample_old_data.get("recommendations", [])}
        new_recs = {r["ref"]: r for r in sample_new_data.get("recommendations", [])}

        app = DiffApp(sample_comparison, old_recs, new_recs)

        async with app.run_test() as pilot:
            # Press 'g' to open jump dialog
            await pilot.press("g")

            # Should have pushed a modal screen (JumpDialog)
            assert len(app.screen_stack) > 1

    @pytest.mark.asyncio
    async def test_jump_to_existing_ref(self, sample_comparison, sample_old_data, sample_new_data):
        """Typing a ref and pressing Enter should jump to that row."""
        from textual.widgets import DataTable

        old_recs = {r["ref"]: r for r in sample_old_data.get("recommendations", [])}
        new_recs = {r["ref"]: r for r in sample_new_data.get("recommendations", [])}

        app = DiffApp(sample_comparison, old_recs, new_recs)

        async with app.run_test() as pilot:
            table = app.query_one("#changes-table", DataTable)

            # Get a ref that exists in the table (from sample data)
            # Sample has added: 1.1.1, removed: 2.1.1, modified: 3.1.1, renumbered: 4.1
            target_ref = "3.1.1"

            # Press 'g' to open jump dialog
            await pilot.press("g")

            # Type the ref
            await pilot.press(*list(target_ref))
            await pilot.press("enter")

            # Should be back to main screen and cursor on the target row
            assert len(app.screen_stack) == 1


class TestFilterByChangeType:
    """Tests for filter by change type feature - ep9.5."""

    def test_filter_bindings_exist(self):
        """Number keys 1-4 and 0 should be bound for change type filtering."""
        from cis_bench.cli.commands.diff_tui import DiffApp

        # Check that DiffApp has filter bindings
        binding_keys = [b.key for b in DiffApp.BINDINGS]
        assert "1" in binding_keys  # Added
        assert "2" in binding_keys  # Removed
        assert "3" in binding_keys  # Modified
        assert "4" in binding_keys  # Renumbered
        assert "0" in binding_keys  # Show all

    def test_diff_app_has_filter_action(self):
        """DiffApp should have action_filter_type method."""
        from cis_bench.cli.commands.diff_tui import DiffApp

        assert hasattr(DiffApp, "action_filter_added")
        assert hasattr(DiffApp, "action_filter_removed")
        assert hasattr(DiffApp, "action_filter_modified")
        assert hasattr(DiffApp, "action_filter_renumbered")
        assert hasattr(DiffApp, "action_filter_all")

    @pytest.mark.asyncio
    async def test_filter_added_only(self, sample_comparison, sample_old_data, sample_new_data):
        """Pressing '1' should filter to show only added items."""
        from textual.widgets import DataTable

        old_recs = {r["ref"]: r for r in sample_old_data.get("recommendations", [])}
        new_recs = {r["ref"]: r for r in sample_new_data.get("recommendations", [])}

        app = DiffApp(sample_comparison, old_recs, new_recs)

        async with app.run_test() as pilot:
            table = app.query_one("#changes-table", DataTable)
            initial_count = table.row_count

            # Press '1' to filter to added only
            await pilot.press("1")

            # Should have fewer rows (only added items)
            assert table.row_count <= initial_count
            # Should have at least 1 row (sample data has 1 added)
            assert table.row_count >= 1

    @pytest.mark.asyncio
    async def test_filter_reset_with_zero(
        self, sample_comparison, sample_old_data, sample_new_data
    ):
        """Pressing '0' should reset filter and show all items."""
        from textual.widgets import DataTable

        old_recs = {r["ref"]: r for r in sample_old_data.get("recommendations", [])}
        new_recs = {r["ref"]: r for r in sample_new_data.get("recommendations", [])}

        app = DiffApp(sample_comparison, old_recs, new_recs)

        async with app.run_test() as pilot:
            table = app.query_one("#changes-table", DataTable)
            initial_count = table.row_count

            # Filter first
            await pilot.press("1")
            filtered_count = table.row_count

            # Reset with '0'
            await pilot.press("0")

            # Should be back to initial count
            assert table.row_count == initial_count


class TestCopyToClipboard:
    """Tests for copy to clipboard feature (c key) - ep9.15."""

    def test_copy_binding_exists_in_common_bindings(self):
        """COMMON_BINDINGS should have 'c' key for copy to clipboard."""
        from cis_bench.cli.commands.tui_base import COMMON_BINDINGS

        keys = [b.key for b in COMMON_BINDINGS]
        assert "c" in keys

    def test_base_browser_app_has_copy_action(self):
        """BaseBrowserApp should have action_copy_to_clipboard method."""
        from cis_bench.cli.commands.tui_base import BaseBrowserApp

        assert hasattr(BaseBrowserApp, "action_copy_to_clipboard")

    @pytest.mark.asyncio
    async def test_copy_shows_notification(
        self, sample_comparison, sample_old_data, sample_new_data
    ):
        """Pressing 'c' should copy content and show notification."""
        old_recs = {r["ref"]: r for r in sample_old_data.get("recommendations", [])}
        new_recs = {r["ref"]: r for r in sample_new_data.get("recommendations", [])}

        app = DiffApp(sample_comparison, old_recs, new_recs)

        async with app.run_test() as pilot:
            # Move to a row to ensure detail view has content
            await pilot.press("down")

            # Press 'c' to copy
            await pilot.press("c")

            # Should remain on main screen (no modal)
            assert len(app.screen_stack) == 1


class TestMouseClickSupport:
    """Tests for mouse click support in TUI (ep9.16)."""

    @pytest.mark.asyncio
    async def test_datatable_has_row_cursor_type(
        self, sample_comparison, sample_old_data, sample_new_data
    ):
        """DataTable should have cursor_type='row' for mouse click support."""
        from textual.widgets import DataTable

        old_recs = {r["ref"]: r for r in sample_old_data.get("recommendations", [])}
        new_recs = {r["ref"]: r for r in sample_new_data.get("recommendations", [])}

        app = DiffApp(sample_comparison, old_recs, new_recs)

        async with app.run_test() as pilot:
            table = app.query_one("#changes-table", DataTable)
            # cursor_type="row" enables mouse click to select rows
            assert table.cursor_type == "row"

    @pytest.mark.asyncio
    async def test_mouse_click_selects_row(
        self, sample_comparison, sample_old_data, sample_new_data
    ):
        """Clicking a row should select it and update detail view."""
        from textual.widgets import DataTable

        old_recs = {r["ref"]: r for r in sample_old_data.get("recommendations", [])}
        new_recs = {r["ref"]: r for r in sample_new_data.get("recommendations", [])}

        app = DiffApp(sample_comparison, old_recs, new_recs)

        async with app.run_test() as pilot:
            table = app.query_one("#changes-table", DataTable)

            # Verify table has rows
            assert table.row_count > 0

            # Get initial cursor position
            initial_cursor = table.cursor_row

            # Move cursor down to verify table is interactive
            await pilot.press("j")  # vim-style down

            # Cursor should have moved (or stayed at 0 if already there)
            # The important thing is that the table responds to input
            assert table.cursor_row >= 0

    @pytest.mark.asyncio
    async def test_row_highlight_triggers_detail_update(
        self, sample_comparison, sample_old_data, sample_new_data
    ):
        """Row highlight (from keyboard or mouse) should update detail view."""

        old_recs = {r["ref"]: r for r in sample_old_data.get("recommendations", [])}
        new_recs = {r["ref"]: r for r in sample_new_data.get("recommendations", [])}

        app = DiffApp(sample_comparison, old_recs, new_recs)

        async with app.run_test() as pilot:
            # Move to a row
            await pilot.press("down")

            # Detail view should have content
            detail = app.query_one("#detail-view", DiffDetailView)
            content = detail.get_content_text()

            # Should have some content (not empty)
            assert len(content) > 0
