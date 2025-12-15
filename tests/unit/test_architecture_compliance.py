"""Architecture compliance tests for loop-driven implementation.

These tests FAIL if the architecture is violated (hard-coding, shortcuts).

Per docs/IMPLEMENTATION_FAILURES.md - prevent Session 1 mistakes from recurring.
"""

import ast
from pathlib import Path

import pytest


class TestArchitectureCompliance:
    """Ensure implementation follows config-driven loop architecture."""

    def test_no_hard_coded_xccdf_imports_in_unified_exporter(self):
        """Unified XCCDF exporter must NOT directly import xccdf models.

        It must use engine.get_xccdf_class() for version-agnostic access.
        """
        exporter_file = (
            Path(__file__).parent.parent.parent
            / "src"
            / "cis_bench"
            / "exporters"
            / "xccdf_unified_exporter.py"
        )

        source = exporter_file.read_text()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and ("xccdf_1_2" in node.module or "xccdf_v1_1" in node.module):
                    pytest.fail(
                        f"{exporter_file.name} hard-codes XCCDF import: {node.module}\n"
                        f"  Use engine.get_xccdf_class() instead"
                    )

    def test_types_loaded_from_config(self, disa_config_path):
        """All XCCDF types must be specified in YAML config, not hard-coded."""
        from cis_bench.exporters.mapping_engine import ConfigLoader

        config = ConfigLoader.load(disa_config_path)

        # Check rule_elements section exists
        assert config.rule_elements, "Missing rule_elements in config"
        assert len(config.rule_elements) > 0, "rule_elements is empty"

        # Check all have xccdf_type specified
        for element_name, element_spec in config.rule_elements.items():
            assert "xccdf_type" in element_spec, (
                f"Element '{element_name}' missing xccdf_type specification"
            )

        # Check group_elements
        assert config.group_elements, "Missing group_elements in config"
        for element_name, element_spec in config.group_elements.items():
            assert "xccdf_type" in element_spec, (
                f"Group element '{element_name}' missing xccdf_type specification"
            )

    def test_loop_driven_construction(self, mapping_engine_file):
        """MappingEngine must construct elements by looping config, not listing fields."""
        source = mapping_engine_file.read_text()

        # Check for loop patterns in new methods
        assert "for field_name, field_mapping in self.config.field_mappings.items()" in source, (
            "map_rule() doesn't loop through config.field_mappings"
        )

        assert "for element_name, element_config in self.config.group_elements.items()" in source, (
            "map_group() doesn't loop through config.group_elements"
        )

        assert "for element_name, element_config in self.config.benchmark.items()" in source, (
            "map_benchmark() doesn't loop through config.benchmark"
        )

    def test_no_hard_coded_field_checks_in_new_methods(self, mapping_engine_file):
        """New methods must NOT check field names like 'if field_name == title'.

        They should use config attributes (structure, multiple, etc.) instead.
        """
        source = mapping_engine_file.read_text()

        # Extract just the new methods
        lines = source.split("\n")
        map_methods_source = []
        in_map_method = False

        for line in lines:
            if "def map_rule(" in line or "def map_group(" in line or "def map_benchmark(" in line:
                in_map_method = True
            elif in_map_method and line.strip().startswith("def ") and "map_" not in line:
                in_map_method = False

            if in_map_method:
                map_methods_source.append(line)

        map_source = "\n".join(map_methods_source)

        # Check for hard-coded field name checks
        forbidden_patterns = [
            "if field_name == 'title'",
            "if field_name == 'description'",
            "if target_element == 'title'",
            "if target_element == 'description'",
        ]

        for pattern in forbidden_patterns:
            assert pattern not in map_source, (
                f"Found hard-coded field check in new methods: {pattern}\n"
                f"Use config attributes (structure, multiple) instead!"
            )

    def test_config_driven_field_addition(self, disa_config_path, almalinux_complete_file):
        """Config changes control output - can modify existing element behavior.

        Tests that we can CHANGE which source field maps to an element
        without touching Python code.
        """
        import tempfile

        import yaml

        from cis_bench.exporters.mapping_engine import MappingEngine
        from cis_bench.models.benchmark import Benchmark

        # Load original config
        with open(disa_config_path) as f:
            config_data = yaml.safe_load(f)

        # MODIFY existing field: Change title source from 'title' to 'ref'
        # This tests we can change behavior via config without code changes
        original_source = config_data["field_mappings"]["title"]["source_field"]
        config_data["field_mappings"]["title"]["source_field"] = "ref"

        # Remove 'extends' to make config self-contained for temp file
        if "extends" in config_data:
            del config_data["extends"]

        # Write to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            temp_config = f.name

        try:
            # Create engine with modified config
            engine = MappingEngine(Path(temp_config))

            # Load test data
            benchmark = Benchmark.from_json_file(str(almalinux_complete_file))
            rec = benchmark.recommendations[0]
            context = {"platform": "test", "benchmark": benchmark}

            # Map rule
            rule = engine.map_rule(rec, context)

            # THE TEST: title should contain ref value, not title value
            assert rule.title, "Title element missing"
            title_text = (
                rule.title[0].content[0]
                if hasattr(rule.title[0], "content")
                else rule.title[0].value
            )

            assert rec.ref in title_text, (
                f"Config change didn't work! Expected ref '{rec.ref}' in title, got: {title_text}\n"
                f"Architecture test FAILED - not truly config-driven"
            )

            assert rec.title not in title_text, (
                "Config change ignored! Still using old source. Architecture test FAILED."
            )

        finally:
            Path(temp_config).unlink()

    def test_dry_helpers_exist(self, disa_config_path):
        """Verify DRY helper methods exist."""
        from cis_bench.exporters.mapping_engine import MappingEngine

        engine = MappingEngine(disa_config_path)

        # Check DRY helpers
        assert hasattr(engine, "_construct_typed_element"), (
            "Missing DRY helper: _construct_typed_element"
        )

        assert hasattr(engine, "_is_list_field"), "Missing DRY helper: _is_list_field"

        assert hasattr(engine, "_element_name_to_type_name"), (
            "Missing DRY helper: _element_name_to_type_name"
        )

        assert hasattr(engine, "_build_field_value"), "Missing DRY helper: _build_field_value"

    def test_new_methods_exist_and_work(self, disa_config_path, almalinux_complete_benchmark):
        """Verify new loop-driven methods exist and are functional."""
        from cis_bench.exporters.mapping_engine import MappingEngine

        engine = MappingEngine(disa_config_path)

        # Check methods exist
        assert hasattr(engine, "map_rule"), "Missing map_rule() method"
        assert hasattr(engine, "map_group"), "Missing map_group() method"
        assert hasattr(engine, "map_benchmark"), "Missing map_benchmark() method"

        # Check they work
        benchmark = almalinux_complete_benchmark
        rec = benchmark.recommendations[0]
        context = {"platform": "test", "benchmark": benchmark}

        # Test map_rule
        rule = engine.map_rule(rec, context)
        assert rule.id, "map_rule() didn't create rule with ID"

        # Test map_group
        group = engine.map_group(rec, rule, context)
        assert group.id, "map_group() didn't create group with ID"
        assert group.rule, "map_group() didn't include rule"

        # Test map_benchmark
        xccdf_bench = engine.map_benchmark(benchmark, [group], context)
        assert xccdf_bench.id, "map_benchmark() didn't create benchmark with ID"
