"""Unit tests for output formatting helper."""

import json

import pytest
import yaml

from cis_bench.cli.helpers.output import output_csv, output_data, output_json, output_yaml

# ============================================================================
# Tests: JSON Output
# ============================================================================


class TestJSONOutput:
    """Test JSON output formatting."""

    def test_output_json_with_dict(self, capsys):
        """Output dictionary as JSON."""
        data = {"key": "value", "number": 42}

        with pytest.raises(SystemExit) as exc_info:
            output_json(data)

        assert exc_info.value.code == 0

        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result == data

    def test_output_json_with_list(self, capsys):
        """Output list as JSON."""
        data = [{"id": 1, "name": "test1"}, {"id": 2, "name": "test2"}]

        with pytest.raises(SystemExit):
            output_json(data)

        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result == data

    def test_output_json_handles_datetime(self, capsys):
        """Output JSON handles datetime objects."""
        from datetime import datetime

        data = {"timestamp": datetime(2025, 1, 1, 12, 0, 0)}

        with pytest.raises(SystemExit):
            output_json(data)

        captured = capsys.readouterr()
        # Should not crash, datetime converted to string
        assert "2025-01-01" in captured.out


# ============================================================================
# Tests: CSV Output
# ============================================================================


class TestCSVOutput:
    """Test CSV output formatting."""

    def test_output_csv_with_data(self, capsys):
        """Output list of dicts as CSV."""
        data = [
            {"id": "1", "name": "test1", "value": "100"},
            {"id": "2", "name": "test2", "value": "200"},
        ]

        with pytest.raises(SystemExit):
            output_csv(data)

        captured = capsys.readouterr()
        lines = [line.strip() for line in captured.out.strip().split("\n")]

        assert lines[0] == "id,name,value"
        assert lines[1] == "1,test1,100"
        assert lines[2] == "2,test2,200"

    def test_output_csv_with_custom_fields(self, capsys):
        """Output CSV with custom field order."""
        data = [{"id": "1", "name": "test", "extra": "ignore"}]

        with pytest.raises(SystemExit):
            output_csv(data, fields=["name", "id"])

        captured = capsys.readouterr()
        lines = [line.strip() for line in captured.out.strip().split("\n")]

        assert lines[0] == "name,id"
        assert lines[1] == "test,1"

    def test_output_csv_empty_data(self, capsys):
        """Output CSV with empty data exits cleanly."""
        with pytest.raises(SystemExit) as exc_info:
            output_csv([])

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert captured.out == ""


# ============================================================================
# Tests: YAML Output
# ============================================================================


class TestYAMLOutput:
    """Test YAML output formatting."""

    def test_output_yaml_with_dict(self, capsys):
        """Output dictionary as YAML."""
        data = {"key": "value", "number": 42, "list": [1, 2, 3]}

        with pytest.raises(SystemExit):
            output_yaml(data)

        captured = capsys.readouterr()
        result = yaml.safe_load(captured.out)
        assert result == data

    def test_output_yaml_with_list(self, capsys):
        """Output list as YAML."""
        data = [{"id": 1}, {"id": 2}]

        with pytest.raises(SystemExit):
            output_yaml(data)

        captured = capsys.readouterr()
        result = yaml.safe_load(captured.out)
        assert result == data


# ============================================================================
# Tests: Unified output_data Function
# ============================================================================


class TestOutputData:
    """Test unified output_data function."""

    def test_output_data_json_format(self, capsys):
        """output_data with json format."""
        data = [{"id": 1, "name": "test"}]

        with pytest.raises(SystemExit):
            output_data(data, format="json")

        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result == data

    def test_output_data_csv_format(self, capsys):
        """output_data with csv format."""
        data = [{"id": "1", "name": "test"}]

        with pytest.raises(SystemExit):
            output_data(data, format="csv")

        captured = capsys.readouterr()
        assert "id,name" in captured.out
        assert "1,test" in captured.out

    def test_output_data_yaml_format(self, capsys):
        """output_data with yaml format."""
        data = {"key": "value"}

        with pytest.raises(SystemExit):
            output_data(data, format="yaml")

        captured = capsys.readouterr()
        assert "key: value" in captured.out

    def test_output_data_table_format_with_formatter(self, capsys):
        """output_data with table format calls formatter function."""
        data = [{"id": 1}]

        formatter_called = []

        def mock_formatter(console, data):
            formatter_called.append(True)
            console.print("Table displayed")

        output_data(data, format="table", human_formatter_func=mock_formatter)

        captured = capsys.readouterr()
        assert formatter_called
        assert "Table displayed" in captured.out

    def test_output_data_csv_with_custom_fields(self, capsys):
        """output_data CSV with custom field order."""
        data = [{"id": "1", "name": "test", "extra": "skip"}]

        with pytest.raises(SystemExit):
            output_data(data, format="csv", csv_fields=["name", "id"])

        captured = capsys.readouterr()
        assert "name,id" in captured.out
        assert "test,1" in captured.out
