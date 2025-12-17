"""Architecture compliance tests - enforce design principles.

These tests ensure we don't regress to hard-coded, organization-specific patterns.
"""

import ast
import re
from pathlib import Path

import pytest


class TestConfigDrivenPrinciple:
    """Ensure code follows config-driven architecture."""

    def test_no_organization_specific_method_names(self):
        """Method names MUST NOT contain organization names (cis, mitre, pci, disa, iso)."""
        mapping_engine = Path("src/cis_bench/exporters/mapping_engine.py")
        content = mapping_engine.read_text()

        # Parse AST to get method names
        tree = ast.parse(content)

        org_patterns = ["cis", "mitre", "pci", "disa", "iso", "hipaa", "nist"]
        violations = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                method_name = node.name.lower()

                # Skip private helpers and approved generic methods
                if method_name.startswith("_"):
                    continue

                # Check for org names
                for org in org_patterns:
                    if org in method_name:
                        # Exceptions: get_ccis (uses CCI service), normalize (generic)
                        if method_name in ["get_ccis_with_deduplication", "normalize_ref"]:
                            continue

                        violations.append(f"Method '{node.name}' contains '{org}'")

        assert not violations, (
            f"Found {len(violations)} organization-specific method names:\n"
            + "\n".join(violations)
            + "\n\nUse generic names: generate_idents_from_config, generate_metadata_from_config"
        )

    def test_no_hard_coded_uris_in_structure_logic(self):
        """Structure generation MUST NOT contain hard-coded URIs."""
        mapping_engine = Path("src/cis_bench/exporters/mapping_engine.py")
        content = mapping_engine.read_text()

        # Find hard-coded URIs in code (not in comments/strings)
        uri_patterns = [
            r"http://cisecurity\.org",
            r"https://attack\.mitre\.org",
            r"urn:cisecurity",
        ]

        lines = content.split("\n")
        violations = []
        in_docstring = False

        for i, line in enumerate(lines, 1):
            # Track docstrings
            if '"""' in line or "'''" in line:
                in_docstring = not in_docstring
                continue

            # Skip if in docstring
            if in_docstring:
                continue

            # Skip comments
            if line.strip().startswith("#"):
                continue

            for pattern in uri_patterns:
                if re.search(pattern, line):
                    # Should only appear in templates or variable substitution
                    if "VariableSubstituter" in line or "{" in line or "template" in line.lower():
                        continue  # OK - in template

                    # Check if it's in a comment on the line
                    if "#" in line:
                        code_part = line.split("#")[0]
                        if pattern not in code_part:
                            continue  # In comment only

                    violations.append(f"Line {i}: {line.strip()[:80]}")

        assert not violations, (
            f"Found {len(violations)} hard-coded URIs in structure logic:\n"
            + "\n".join(violations[:10])
            + "\n\nURIs should be in YAML config templates, not Python code."
        )

    def test_all_handlers_are_generic(self):
        """All structure handlers should work for ANY organization."""
        mapping_engine = Path("src/cis_bench/exporters/mapping_engine.py")
        content = mapping_engine.read_text()

        # Find all "if structure ==" handlers
        handler_pattern = r'if structure == "(.*?)":'
        handlers = re.findall(handler_pattern, content)

        # Approved generic handlers
        approved = {
            "ident_from_list",  # Generic
            "metadata_from_config",  # Generic
            "embedded_xml_tags",  # Specialized (DISA VulnDiscussion)
            "nested",  # Specialized (simple nesting)
            "dublin_core",  # Standard (W3C)
        }

        violations = [h for h in handlers if h not in approved]

        assert not violations, (
            f"Found {len(violations)} non-approved handlers: {violations}\n"
            "Only approved: " + ", ".join(approved) + "\n"
            "Remove organization-specific handlers!"
        )


class TestExtensibility:
    """Test that adding new frameworks requires only YAML."""

    def test_mock_pci_dss_via_config_only(self):
        """Test that mock PCI-DSS can be added via YAML config only (no code changes)."""
        # Create mock PCI-DSS config
        mock_config = Path("tests/fixtures/configs/mock_pci_dss.yaml")

        if not mock_config.exists():
            pytest.skip("Mock PCI-DSS config not yet created")

        # If config exists, verify it uses only generic handlers
        content = mock_config.read_text()

        # Should only use approved generic patterns
        assert "ident_from_list" in content or "metadata_from_config" in content
        assert "pci_specific_handler" not in content  # No custom handlers!

    def test_adding_framework_documented_as_yaml_only(self):
        """Documentation should state adding frameworks requires only YAML."""
        docs_dir = Path("docs")

        # Check for framework extension guide
        extension_guides = list(docs_dir.glob("**/adding-*.md"))

        # Should have at least one example guide
        assert len(extension_guides) > 0, (
            "Should have framework extension guides (e.g., adding-pci-dss.md)"
        )

        # Check content mentions "no code changes"
        for guide in extension_guides:
            content = guide.read_text().lower()
            assert "yaml" in content or "config" in content, (
                f"{guide.name} should mention YAML configuration"
            )


class TestNoRegressionToOldPatterns:
    """Ensure we don't bring back deleted patterns."""

    def test_old_methods_deleted(self):
        """Verify old organization-specific methods are deleted."""
        mapping_engine = Path("src/cis_bench/exporters/mapping_engine.py")
        content = mapping_engine.read_text()

        # Old methods that should NOT exist
        old_methods = [
            "build_cis_controls",  # Replaced by metadata_from_config
            "generate_cis_idents",  # Replaced by ident_from_list
            "generate_mitre_idents",  # Never created (used ident_from_list)
        ]

        for method in old_methods:
            assert f"def {method}" not in content, (
                f"Old method '{method}' found! Should be deleted."
            )

    def test_old_handlers_deleted(self):
        """Verify old structure handlers are deleted."""
        mapping_engine = Path("src/cis_bench/exporters/mapping_engine.py")
        content = mapping_engine.read_text()

        # Old handlers that should NOT exist
        old_handlers = [
            'structure == "official_cis_controls"',
            'structure == "enhanced_namespace"',
            'structure == "custom_namespace"',
            'structure == "cis_controls_ident"',  # Replaced by ident_from_list
        ]

        for handler in old_handlers:
            assert handler not in content, f"Old handler '{handler}' found! Should be deleted."

    def test_no_style_specific_injection_methods(self):
        """Exporter should not have organization-specific injection methods."""
        exporter = Path("src/cis_bench/exporters/xccdf_unified_exporter.py")
        content = exporter.read_text()

        # Old injection methods (should be deleted or made generic)
        old_injection = [
            "_inject_cis_controls_metadata",  # Deleted
            "_inject_enhanced_metadata",  # Deleted
        ]

        for method in old_injection:
            assert f"def {method}" not in content, (
                f"Old injection method '{method}' found! Should be deleted."
            )

        # Should have generic injection
        assert "_inject_metadata_from_config" in content, (
            "Should have generic _inject_metadata_from_config"
        )
