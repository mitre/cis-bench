"""Unit tests for output formatting helper."""

import json
from io import StringIO

import pytest
import yaml
from rich.console import Console

from cis_bench.cli.helpers.output import (
    benchmark_table,
    output_csv,
    output_data,
    output_json,
    output_yaml,
)

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


# ============================================================================
# Tests: Benchmark results table
# ============================================================================

LONG_TITLE = (
    "CIS Microsoft Windows Server 2022 Benchmark for Domain Controllers "
    "and Member Servers in Hybrid Azure Environments"
)


# The Title column width a run uses when CIS_BENCH_TABLE_TITLE_WIDTH is not set.
TITLE_WIDTH = 90


def _render(table, width):
    buffer = StringIO()
    Console(file=buffer, width=width).print(table)
    return buffer.getvalue()


class TestBenchmarkTable:
    """The search/get results table fits the terminal without cutting short columns."""

    def test_short_columns_stay_whole_and_the_title_wraps_at_80_columns(self):
        rows = [
            {
                "benchmark_id": "23598",
                "title": LONG_TITLE,
                "version": "v4.0.0",
                "status": "Published",
            }
        ]

        output = _render(benchmark_table(rows, title_width=TITLE_WIDTH), width=80)

        assert "23598" in output
        assert "v4.0.0" in output
        assert "Published" in output
        assert "…" not in output
        for word in LONG_TITLE.split():
            assert word in output

    @pytest.mark.parametrize(
        ("benchmark_id", "version", "status"),
        [
            ("2359823598", "v1", "P"),
            ("1", "v4.0.0-draft1", "P"),
            ("1", "v1", "Published Archive"),
        ],
        ids=["widest-id", "widest-version", "widest-status"],
    )
    def test_in_a_narrow_pane_only_the_title_gives_up_width(self, benchmark_id, version, status):
        rows = [
            {
                "benchmark_id": benchmark_id,
                "title": LONG_TITLE,
                "version": version,
                "status": status,
            }
        ]

        output = _render(benchmark_table(rows, title_width=TITLE_WIDTH), width=40)

        assert benchmark_id in output
        assert version in output
        assert status in output
        assert "…" not in output  # a word wider than the title column folds, it is not cut

    def test_title_width_is_the_widest_the_title_column_grows(self):
        rows = [{"benchmark_id": "1", "title": LONG_TITLE, "version": "v1", "status": "Published"}]

        output = _render(benchmark_table(rows, title_width=30), width=200)

        title_lines = [
            line for line in output.splitlines() if "Hybrid" in line or "Windows" in line
        ]
        assert title_lines
        assert all(len(line.split("│")[2].strip()) <= 30 for line in title_lines)

    def test_cells_from_the_catalog_are_shown_verbatim(self):
        rows = [
            {"benchmark_id": "1", "title": "CIS T [/t]", "version": "v1 [/v]", "status": "P [/s]"}
        ]

        output = _render(benchmark_table(rows, title_width=TITLE_WIDTH), width=120)

        assert "CIS T [/t]" in output
        assert "v1 [/v]" in output
        assert "P [/s]" in output


# ============================================================================
# Tests: Times in tables
# ============================================================================


class TestDisplayTime:
    """A table shows a time in the viewer's zone and names it; a time with no zone says so."""

    def test_an_aware_time_is_shown_in_the_local_zone_with_its_name(self, new_york_clock):
        from datetime import UTC, datetime

        from cis_bench.cli.helpers.output import display_time

        assert (
            display_time(datetime(2026, 11, 7, 2, 5, 58, tzinfo=UTC)) == "2026-11-06 21:05:58 EST"
        )

    def test_a_summer_time_gets_the_summer_name(self, new_york_clock):
        from datetime import UTC, datetime

        from cis_bench.cli.helpers.output import display_time

        assert display_time(datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)) == "2026-07-01 08:00:00 EDT"

    def test_a_time_without_a_zone_is_shown_as_it_is_and_marked(self, new_york_clock):
        from datetime import datetime

        from cis_bench.cli.helpers.output import display_time

        assert (
            display_time(datetime(2026, 11, 6, 20, 5, 58))
            == "2026-11-06 20:05:58 (zone not recorded)"
        )
