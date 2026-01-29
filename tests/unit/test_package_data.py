"""Tests for package data inclusion.

These tests verify that non-Python files (YAML configs, etc.) are properly
included in the package distribution and accessible at runtime.

Issue #6: Users installing from PyPI get "cis is not one of ." error because
YAML config files are not included in the package.
"""

from pathlib import Path

import pytest


class TestPackageDataInclusion:
    """Verify package data files are accessible at runtime."""

    def test_styles_directory_exists(self):
        """The configs/styles directory must exist in the installed package."""
        from cis_bench.exporters import xccdf_unified_exporter

        # Get the package directory
        exporter_file = Path(xccdf_unified_exporter.__file__)
        styles_dir = exporter_file.parent / "configs" / "styles"

        assert styles_dir.exists(), (
            f"Styles directory not found at {styles_dir}\n"
            "This indicates YAML configs are not included in the package distribution.\n"
            "Fix: Add package-data configuration to pyproject.toml"
        )

    def test_disa_yaml_exists(self):
        """DISA style config must be accessible."""
        from cis_bench.exporters import xccdf_unified_exporter

        exporter_file = Path(xccdf_unified_exporter.__file__)
        disa_yaml = exporter_file.parent / "configs" / "styles" / "disa.yaml"

        assert disa_yaml.exists(), (
            f"disa.yaml not found at {disa_yaml}\n"
            "YAML config files must be included in package distribution."
        )

    def test_cis_yaml_exists(self):
        """CIS style config must be accessible."""
        from cis_bench.exporters import xccdf_unified_exporter

        exporter_file = Path(xccdf_unified_exporter.__file__)
        cis_yaml = exporter_file.parent / "configs" / "styles" / "cis.yaml"

        assert cis_yaml.exists(), (
            f"cis.yaml not found at {cis_yaml}\n"
            "YAML config files must be included in package distribution."
        )

    def test_get_available_styles_returns_expected_styles(self):
        """XCCDFExporter._get_available_styles() must return at least disa and cis."""
        from cis_bench.exporters.xccdf_unified_exporter import XCCDFExporter

        styles = XCCDFExporter._get_available_styles()

        assert len(styles) >= 2, (
            f"Expected at least 2 styles, got {len(styles)}: {styles}\n"
            "This indicates YAML configs are not included in the package distribution."
        )

        assert "disa" in styles, f"'disa' style not found. Available: {styles}"
        assert "cis" in styles, f"'cis' style not found. Available: {styles}"

    def test_style_choice_validation_works(self):
        """DynamicStyleChoice must accept 'disa' and 'cis' as valid choices."""
        from cis_bench.cli.commands.export import DynamicStyleChoice

        choice = DynamicStyleChoice()

        # These should not raise
        assert "disa" in choice.choices, f"'disa' not in choices: {choice.choices}"
        assert "cis" in choice.choices, f"'cis' not in choices: {choice.choices}"

    def test_xccdf_exporter_can_be_instantiated_with_disa(self):
        """XCCDFExporter must be instantiable with style='disa'."""
        from cis_bench.exporters.xccdf_unified_exporter import XCCDFExporter

        # This should not raise ValueError about unknown style
        try:
            exporter = XCCDFExporter(style="disa")
            assert exporter.style == "disa"
        except ValueError as e:
            pytest.fail(f"Failed to instantiate XCCDFExporter with style='disa': {e}")

    def test_xccdf_exporter_can_be_instantiated_with_cis(self):
        """XCCDFExporter must be instantiable with style='cis'."""
        from cis_bench.exporters.xccdf_unified_exporter import XCCDFExporter

        # This should not raise ValueError about unknown style
        try:
            exporter = XCCDFExporter(style="cis")
            assert exporter.style == "cis"
        except ValueError as e:
            pytest.fail(f"Failed to instantiate XCCDFExporter with style='cis': {e}")

    def test_base_yaml_exists(self):
        """Base config (base.yaml) must be accessible."""
        from cis_bench.exporters import xccdf_unified_exporter

        exporter_file = Path(xccdf_unified_exporter.__file__)
        base_yaml = exporter_file.parent / "configs" / "base.yaml"

        assert base_yaml.exists(), (
            f"base.yaml not found at {base_yaml}\n"
            "Base config must be included in package distribution."
        )

    def test_configs_directory_structure(self):
        """Verify the complete configs directory structure exists."""
        from cis_bench.exporters import xccdf_unified_exporter

        exporter_file = Path(xccdf_unified_exporter.__file__)
        configs_dir = exporter_file.parent / "configs"

        # Check main configs directory
        assert configs_dir.exists(), f"configs/ directory not found at {configs_dir}"

        # Check styles subdirectory
        styles_dir = configs_dir / "styles"
        assert styles_dir.exists(), f"configs/styles/ directory not found at {styles_dir}"

        # Count YAML files
        yaml_files = list(configs_dir.glob("**/*.yaml"))
        assert len(yaml_files) >= 3, (
            f"Expected at least 3 YAML files (base.yaml, disa.yaml, cis.yaml), "
            f"found {len(yaml_files)}: {[f.name for f in yaml_files]}"
        )
