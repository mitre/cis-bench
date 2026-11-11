"""The synthetic data folder: the synthetic benchmarks as a user's downloads, through the CLI.

scripts/synthetic_home.py builds a data folder (CIS_BENCH_HOME) holding every benchmark in
tests/fixtures/benchmarks/synthetic_*.json as a catalog row and a downloaded copy, each
stored as its file holds it. Every word of those benchmarks is our own; their shapes follow
real copies (a current Linux benchmark, its previous version stored the older way, a cloud
account's foundations, a Windows server), so the commands below take the paths real
downloads take.
"""

import json
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest
from click.testing import CliRunner

from cis_bench.cli.app import cli

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "synthetic_home.py"

SYNTHETIC = {
    "90001": ("CIS Synthetic Enterprise Platform Benchmark v1.0.0", "v1.0.0"),
    "90002": ("CIS Synthetic Linux Server Benchmark", "v2.0.0"),
    "90003": ("CIS Synthetic Linux Server Benchmark", "v1.0.0"),
    "90004": ("CIS Synthetic Cloud Foundations Benchmark", "v3.0.0"),
    "90005": ("CIS Synthetic Windows Server Benchmark", "v1.0.0"),
}


def _build(folder: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(folder)],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture(scope="module")
def synthetic_home(tmp_path_factory):
    folder = tmp_path_factory.mktemp("synthetic") / "home"
    built = _build(folder)
    assert built.returncode == 0, built.stdout + built.stderr
    return folder


@pytest.fixture
def run(synthetic_home, monkeypatch):
    """Run cis-bench with CIS_BENCH_HOME at the synthetic folder, nothing sent anywhere."""
    import requests

    def refuse(*args, **kwargs):
        raise AssertionError("an HTTP request was sent")

    monkeypatch.setattr(requests.Session, "send", refuse)
    monkeypatch.setenv("CIS_BENCH_HOME", str(synthetic_home))

    def invoke(*args):
        result = CliRunner().invoke(cli, list(args))
        assert result.exit_code == 0, result.output
        return result

    return invoke


def _json(result):
    return json.loads(result.stdout)


class TestTheFolder:
    def test_the_synthetic_folder_holds_every_synthetic_benchmark_as_downloaded(self, run):
        listed = _json(run("list", "--output-format", "json"))["downloaded"]

        assert {item["benchmark_id"]: (item["title"], item["version"]) for item in listed} == (
            SYNTHETIC
        )

    def test_each_has_a_catalog_row_and_no_session_is_saved(self, run, synthetic_home):
        status = _json(run("cache", "status", "--output-format", "json"))
        found = _json(run("search", "synthetic", "--status", "all", "--output-format", "json"))
        latest = _json(run("search", "synthetic linux", "--latest", "--output-format", "json"))

        assert status["catalog"]["benchmarks"] == len(SYNTHETIC)
        assert status["session"]["present"] is False
        assert not (synthetic_home / "session.cookies").exists()
        assert {row["benchmark_id"] for row in found} == set(SYNTHETIC)
        assert [row["benchmark_id"] for row in latest] == ["90002"]

    def test_a_copy_saved_the_older_way_is_stored_as_its_file_holds_it(self, synthetic_home):
        from cis_bench.catalog.database import CatalogDatabase

        with closing(CatalogDatabase(synthetic_home / "catalog.db")) as db:
            stored = db.get_downloaded("90003")["content_json"]

        written = (ROOT / "tests/fixtures/benchmarks/synthetic_linux_previous.json").read_text()
        assert json.loads(stored) == json.loads(written)
        assert "text_format" not in json.loads(stored)

    def test_the_script_refuses_a_folder_that_holds_anything(self, tmp_path):
        folder = tmp_path / "home"
        folder.mkdir()
        (folder / "notes.txt").write_text("keep me")

        built = _build(folder)

        assert built.returncode != 0
        assert str(folder) in built.stderr
        assert sorted(p.name for p in folder.iterdir()) == ["notes.txt"]
        assert (folder / "notes.txt").read_text() == "keep me"


class TestCommandsOnTheSyntheticData:
    @pytest.mark.parametrize("benchmark_id", sorted(SYNTHETIC))
    @pytest.mark.parametrize(
        "export_args",
        [
            ("--format", "yaml"),
            ("--format", "csv"),
            ("--format", "markdown"),
            ("--format", "xccdf", "--style", "cis"),
            ("--format", "xccdf", "--style", "disa"),
        ],
        ids=lambda args: " ".join(args[1::2]) if len(args) > 2 else args[1],
    )
    def test_every_synthetic_benchmark_exports_and_its_xccdf_validates(
        self, run, tmp_path, benchmark_id, export_args
    ):
        out = tmp_path / "out"

        run("export", benchmark_id, *export_args, "--output-dir", str(out))

        (written,) = list(out.iterdir())
        assert written.stat().st_size > 0
        if "xccdf" in export_args:
            run("validate", str(written))

    def test_diff_of_the_two_linux_versions_reports_each_kind_of_change(self, run):
        changes = _json(run("diff", "90003", "90002", "--format", "json"))["changes"]

        assert [c["ref"] for c in changes["added"]] == ["6.1.1"]
        assert [c["ref"] for c in changes["removed"]] == ["4.1.4"]
        assert [(c["old_ref"], c["new_ref"]) for c in changes["renumbered"]] == [("2.2.1", "2.1.1")]
        assert [c["ref"] for c in changes["reformatted"]] == ["4.1.3"]
        modified = {c["ref"]: c["fields_changed"] for c in changes["modified"]}
        assert "title" in modified["3.2.1.2"]
        assert "audit" in modified["4.1.2"]
