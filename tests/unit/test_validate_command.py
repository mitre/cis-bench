"""cis-bench validate: schema-validates XCCDF files with the shipped schemas; exit 0 when every
file is valid, 2 when any is invalid, 1 when any cannot be validated at all."""

import pytest
from click.testing import CliRunner

from cis_bench.cli.app import cli

XCCDF_1_2 = "http://checklists.nist.gov/xccdf/1.2"


def _benchmark(*children: str) -> str:
    body = "\n".join(children)
    return (
        f'<Benchmark xmlns="{XCCDF_1_2}" id="xccdf_org.example_benchmark_t">\n'
        f"<status>draft</status>\n{body}\n<version>1</version>\n</Benchmark>\n"
    )


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def valid_file(tmp_path):
    path = tmp_path / "valid.xml"
    path.write_text(_benchmark())
    return path


@pytest.fixture
def invalid_file(tmp_path):
    path = tmp_path / "broken.xml"
    path.write_text(_benchmark("<bogus/>"))
    return path


class TestValidateCommand:
    def test_a_valid_file_exits_0_and_names_the_version(self, runner, valid_file):
        result = runner.invoke(cli, ["validate", str(valid_file)])

        assert result.exit_code == 0, result.output
        assert "valid.xml" in result.output
        assert "valid XCCDF 1.2" in result.output

    def test_an_invalid_file_exits_2_and_lists_each_error_with_its_line(self, runner, invalid_file):
        result = runner.invoke(cli, ["validate", str(invalid_file)])

        assert result.exit_code == 2, result.output
        assert "broken.xml" in result.output
        assert "invalid" in result.output
        assert "line 3:" in result.output
        assert "bogus" in result.output

    def test_several_files_are_all_reported_and_one_invalid_file_fails_the_run(
        self, runner, valid_file, invalid_file
    ):
        result = runner.invoke(cli, ["validate", str(valid_file), str(invalid_file)])

        assert result.exit_code == 2, result.output
        assert "valid.xml" in result.output
        assert "broken.xml" in result.output

    def test_a_file_that_could_not_be_validated_outranks_an_invalid_one(
        self, runner, invalid_file, tmp_path
    ):
        """Exit 1 (could not run) wins over exit 2 (ran, invalid), as oscap ranks them."""
        result = runner.invoke(cli, ["validate", str(invalid_file), str(tmp_path / "nope.xml")])

        assert result.exit_code == 1, result.output
        assert "broken.xml" in result.output
        assert "nope.xml" in result.output

    def test_a_missing_file_exits_1_and_names_it(self, runner, tmp_path):
        result = runner.invoke(cli, ["validate", str(tmp_path / "nope.xml")])

        assert result.exit_code == 1, result.output
        assert "nope.xml" in result.output
        assert "Traceback" not in result.output

    def test_a_file_that_is_not_xccdf_exits_1(self, runner, tmp_path):
        page = tmp_path / "page.xml"
        page.write_text('<html xmlns="http://www.w3.org/1999/xhtml"/>\n')

        result = runner.invoke(cli, ["validate", str(page)])

        assert result.exit_code == 1, result.output
        assert "not an XCCDF document" in result.output

    def test_validate_is_listed_in_the_root_help(self, runner):
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "validate" in result.output
