"""Tests for export-related TUI dialogs."""

from pathlib import Path


class TestExportConfigDialogExists:
    """Test ExportConfigDialog class structure."""

    def test_export_config_dialog_importable(self):
        """ExportConfigDialog should be importable."""
        from cis_bench.cli.commands.tui.dialogs import ExportConfigDialog

        assert ExportConfigDialog is not None

    def test_export_config_dialog_is_modal_screen(self):
        """ExportConfigDialog should be a ModalScreen."""
        from textual.screen import ModalScreen

        from cis_bench.cli.commands.tui.dialogs import ExportConfigDialog

        assert issubclass(ExportConfigDialog, ModalScreen)

    def test_export_config_dialog_accepts_context(self):
        """ExportConfigDialog should accept export context."""
        from cis_bench.cli.commands.tui.dialogs import ExportConfigDialog

        # Should accept context parameter
        dialog = ExportConfigDialog(context="single")
        assert dialog.context == "single"

        dialog = ExportConfigDialog(context="diff")
        assert dialog.context == "diff"

        dialog = ExportConfigDialog(context="batch")
        assert dialog.context == "batch"

    def test_export_config_dialog_has_escape_binding(self):
        """ExportConfigDialog should have escape to cancel."""
        from cis_bench.cli.commands.tui.dialogs import ExportConfigDialog

        binding_keys = [b.key for b in ExportConfigDialog.BINDINGS]
        assert "escape" in binding_keys


class TestExportConfigDialogFormats:
    """Test format selection in ExportConfigDialog."""

    def test_dialog_shows_formats_for_single_context(self):
        """Dialog should show appropriate formats for single benchmark."""
        from cis_bench.cli.commands.tui.dialogs import ExportConfigDialog

        dialog = ExportConfigDialog(context="single")
        formats = dialog.get_available_formats()

        assert "json" in formats
        assert "yaml" in formats
        assert "xccdf" in formats
        assert "csv" in formats
        assert "markdown" in formats

    def test_dialog_shows_formats_for_diff_context(self):
        """Dialog should show appropriate formats for diff."""
        from cis_bench.cli.commands.tui.dialogs import ExportConfigDialog

        dialog = ExportConfigDialog(context="diff")
        formats = dialog.get_available_formats()

        assert "json" in formats
        assert "markdown" in formats
        # XCCDF not available for diff
        assert "xccdf" not in formats

    def test_dialog_shows_formats_for_batch_context(self):
        """Dialog should show appropriate formats for batch."""
        from cis_bench.cli.commands.tui.dialogs import ExportConfigDialog

        dialog = ExportConfigDialog(context="batch")
        formats = dialog.get_available_formats()

        assert "json" in formats
        assert "yaml" in formats
        assert "xccdf" in formats


class TestExportConfigDialogResult:
    """Test ExportConfigDialog result handling."""

    def test_dialog_result_type_importable(self):
        """ExportDialogResult should be importable."""
        from cis_bench.cli.commands.tui.dialogs import ExportDialogResult

        assert ExportDialogResult is not None

    def test_dialog_result_has_format(self):
        """ExportDialogResult should have format field."""
        from cis_bench.cli.commands.tui.dialogs import ExportDialogResult

        result = ExportDialogResult(format="json")
        assert result.format == "json"

    def test_dialog_result_has_output_dir(self):
        """ExportDialogResult should have output_dir field."""
        from cis_bench.cli.commands.tui.dialogs import ExportDialogResult

        result = ExportDialogResult(format="json", output_dir=Path.cwd())
        assert result.output_dir == Path.cwd()

    def test_dialog_result_has_style(self):
        """ExportDialogResult should have optional style field."""
        from cis_bench.cli.commands.tui.dialogs import ExportDialogResult

        result = ExportDialogResult(format="xccdf", style="disa")
        assert result.style == "disa"

    def test_dialog_result_style_defaults_none(self):
        """ExportDialogResult style should default to None."""
        from cis_bench.cli.commands.tui.dialogs import ExportDialogResult

        result = ExportDialogResult(format="json")
        assert result.style is None


class TestBatchProgressModalExists:
    """Test BatchProgressModal class structure."""

    def test_batch_progress_modal_importable(self):
        """BatchProgressModal should be importable."""
        from cis_bench.cli.commands.tui.dialogs import BatchProgressModal

        assert BatchProgressModal is not None

    def test_batch_progress_modal_is_modal_screen(self):
        """BatchProgressModal should be a ModalScreen."""
        from textual.screen import ModalScreen

        from cis_bench.cli.commands.tui.dialogs import BatchProgressModal

        assert issubclass(BatchProgressModal, ModalScreen)

    def test_batch_progress_modal_accepts_title(self):
        """BatchProgressModal should accept title parameter."""
        from cis_bench.cli.commands.tui.dialogs import BatchProgressModal

        modal = BatchProgressModal(title="Exporting...", total=10)
        assert modal.modal_title == "Exporting..."

    def test_batch_progress_modal_accepts_total(self):
        """BatchProgressModal should accept total items count."""
        from cis_bench.cli.commands.tui.dialogs import BatchProgressModal

        modal = BatchProgressModal(title="Exporting...", total=10)
        assert modal.total == 10

    def test_batch_progress_modal_has_escape_binding(self):
        """BatchProgressModal should have escape to cancel."""
        from cis_bench.cli.commands.tui.dialogs import BatchProgressModal

        binding_keys = [b.key for b in BatchProgressModal.BINDINGS]
        assert "escape" in binding_keys


class TestBatchProgressModalProgress:
    """Test progress tracking in BatchProgressModal."""

    def test_modal_has_update_progress_method(self):
        """BatchProgressModal should have update_progress method."""
        from cis_bench.cli.commands.tui.dialogs import BatchProgressModal

        modal = BatchProgressModal(title="Test", total=10)
        assert hasattr(modal, "update_progress")
        assert callable(modal.update_progress)

    def test_modal_tracks_current_item(self):
        """BatchProgressModal should track current item number."""
        from cis_bench.cli.commands.tui.dialogs import BatchProgressModal

        modal = BatchProgressModal(title="Test", total=10)
        modal.update_progress(5, "Processing item 5")
        assert modal.current == 5

    def test_modal_has_is_cancelled_property(self):
        """BatchProgressModal should have is_cancelled property."""
        from cis_bench.cli.commands.tui.dialogs import BatchProgressModal

        modal = BatchProgressModal(title="Test", total=10)
        assert hasattr(modal, "is_cancelled")
        assert modal.is_cancelled is False

    def test_modal_has_add_result_method(self):
        """BatchProgressModal should have add_result for tracking outcomes."""
        from cis_bench.cli.commands.tui.dialogs import BatchProgressModal

        modal = BatchProgressModal(title="Test", total=10)
        assert hasattr(modal, "add_result")
        assert callable(modal.add_result)

    def test_modal_tracks_success_count(self):
        """BatchProgressModal should track successful items."""
        from cis_bench.cli.commands.tui.dialogs import BatchProgressModal

        modal = BatchProgressModal(title="Test", total=3)
        modal.add_result(success=True, item_id="1")
        modal.add_result(success=True, item_id="2")
        modal.add_result(success=False, item_id="3", error="Failed")

        assert modal.success_count == 2
        assert modal.failure_count == 1


class TestOutputPathDialogExists:
    """Test OutputPathDialog class structure."""

    def test_output_path_dialog_importable(self):
        """OutputPathDialog should be importable."""
        from cis_bench.cli.commands.tui.dialogs import OutputPathDialog

        assert OutputPathDialog is not None

    def test_output_path_dialog_is_modal_screen(self):
        """OutputPathDialog should be a ModalScreen."""
        from textual.screen import ModalScreen

        from cis_bench.cli.commands.tui.dialogs import OutputPathDialog

        assert issubclass(OutputPathDialog, ModalScreen)

    def test_output_path_dialog_accepts_default_dir(self):
        """OutputPathDialog should accept default directory."""
        from cis_bench.cli.commands.tui.dialogs import OutputPathDialog

        dialog = OutputPathDialog(default_dir=Path.cwd())
        assert dialog.default_dir == Path.cwd()

    def test_output_path_dialog_has_escape_binding(self):
        """OutputPathDialog should have escape to cancel."""
        from cis_bench.cli.commands.tui.dialogs import OutputPathDialog

        binding_keys = [b.key for b in OutputPathDialog.BINDINGS]
        assert "escape" in binding_keys


class TestDialogsInit:
    """Test dialogs package initialization."""

    def test_dialogs_package_importable(self):
        """Dialogs package should be importable."""
        from cis_bench.cli.commands.tui import dialogs

        assert dialogs is not None

    def test_all_dialogs_exported(self):
        """All dialog classes should be exported from package."""
        from cis_bench.cli.commands.tui.dialogs import (
            BatchProgressModal,
            ExportConfigDialog,
            ExportDialogResult,
            OutputPathDialog,
        )

        assert ExportConfigDialog is not None
        assert ExportDialogResult is not None
        assert BatchProgressModal is not None
        assert OutputPathDialog is not None
