"""The synthetic data folder: the synthetic benchmarks as a user's downloads, through the CLI.

scripts/synthetic_home.py builds a data folder (CIS_BENCH_HOME) holding every benchmark in
tests/fixtures/benchmarks/synthetic_*.json as a catalog row and a downloaded copy, each
stored as its file holds it. Every word of those benchmarks is our own; their shapes follow
real copies (a current Linux benchmark, its previous version stored the older way, a cloud
account's foundations, a Windows server), so the commands below take the paths real
downloads take.
"""

import json
import os
import re
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


def _build(folder: Path | str, home: Path | None = None) -> subprocess.CompletedProcess:
    """Run the script; ``home`` stands in for the home folder and the XDG folders under it,
    so a script that resolved the wrong folder could never reach the developer's own."""
    env = None
    if home is not None:
        env = {
            **os.environ,
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_DATA_HOME": str(home / ".local/share"),
            "XDG_STATE_HOME": str(home / ".local/state"),
        }
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(folder)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _populated(folder: Path) -> Path:
    folder.mkdir(parents=True)
    (folder / "notes.txt").write_text("keep me")
    return folder


def _untouched(folder: Path) -> bool:
    return [p.name for p in folder.iterdir()] == ["notes.txt"] and (
        folder / "notes.txt"
    ).read_text() == "keep me"


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


FIXTURES = ROOT / "tests" / "fixtures" / "benchmarks"


def _benchmark(benchmark_id):
    from cis_bench.models.benchmark import Benchmark

    (path,) = [
        path
        for path in FIXTURES.glob("synthetic_*.json")
        if json.loads(path.read_text())["benchmark_id"] == benchmark_id
    ]
    return Benchmark.from_json_file(str(path))


def _recommendations(benchmark_id):
    """(ref, title) of each of the benchmark's recommendations, in order."""
    return [(r.ref, r.title) for r in _benchmark(benchmark_id).recommendations]


def _exported_recommendations(path: Path, export_format: str):
    """(ref, title) of each recommendation an export holds, read back in its own format."""
    import csv
    import re

    import yaml
    from lxml import etree

    text = path.read_text(encoding="utf-8")
    if export_format == "yaml":
        # Read as a node tree: building objects from it is not needed to see the fields.
        root = yaml.compose(text)
        fields = {key.value: value for key, value in root.value}
        return [
            (entry["ref"].value, entry["title"].value)
            for entry in (
                {key.value: value for key, value in item.value}
                for item in fields["recommendations"].value
            )
        ]
    if export_format == "csv":
        return [(row["ref"], row["title"]) for row in csv.DictReader(text.splitlines())]
    if export_format == "markdown":
        return re.findall(r"^## (\S+) - (.+?)(?: \{#\w+\})?$", text, re.MULTILINE)
    rules = [e for e in etree.parse(str(path)).iter() if etree.QName(e).localname == "Rule"]
    return [
        tuple(
            next(c.text for c in rule if etree.QName(c).localname == name)
            for name in ("version", "title")
        )
        for rule in rules
    ]


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
        # Earlier versions stored WorkBench's \r\n line breaks in every text field.
        assert not [
            (r["ref"], name)
            for r in json.loads(stored)["recommendations"]
            for name, value in r.items()
            if isinstance(value, str) and "\n" in value.replace("\r\n", "")
        ]

    def test_each_catalog_row_carries_what_its_listing_and_page_would_say(self, run):
        current = _json(run("catalog", "info", "90004", "--output-format", "json"))
        older = _json(run("catalog", "info", "90003", "--output-format", "json"))
        status = _json(run("cache", "status", "--output-format", "json"))

        assert (current["platform"], current["platform_type"]) == ("synthetic-cloud", "cloud")
        assert current["published_date"] == "2026-04-15"
        assert current["description"] == _benchmark("90004").description
        # A copy saved before the page was read carries no page facts.
        assert (older["published_date"], older["description"]) == (None, None)
        assert status["catalog"]["last_full_refresh"] is not None

    def test_the_script_refuses_a_folder_that_holds_anything(self, tmp_path):
        folder = _populated(tmp_path / "home")

        built = _build(folder, home=tmp_path)

        assert built.returncode != 0
        assert str(folder) in built.stderr
        assert _untouched(folder)

    @pytest.mark.parametrize(
        "spelling",
        ["{folder} ", " {folder}", "~/home"],
        ids=["trailing space", "leading space", "home folder"],
    )
    def test_the_script_refuses_the_folder_cis_bench_would_use_however_it_is_spelled(
        self, tmp_path, spelling
    ):
        # CIS_BENCH_HOME drops surrounding spaces and reads ~ as the home folder: the folder
        # checked is the one written to.
        folder = _populated(tmp_path / "home")

        built = _build(spelling.format(folder=folder), home=tmp_path)

        assert built.returncode != 0
        assert _untouched(folder)

    @pytest.mark.parametrize("points_to", ["nowhere", "an empty folder"])
    def test_the_script_refuses_a_link(self, tmp_path, points_to):
        empty = tmp_path / "empty"
        if points_to == "an empty folder":
            empty.mkdir()
        link = tmp_path / "home"
        link.symlink_to(empty)

        built = _build(link, home=tmp_path)

        assert built.returncode != 0
        assert "Traceback" not in built.stderr
        assert not (empty / "catalog.db").exists()

    def test_build_itself_refuses_a_folder_that_holds_anything(self, tmp_path):
        import importlib.util

        spec = importlib.util.spec_from_file_location("synthetic_home", SCRIPT)
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)
        folder = _populated(tmp_path / "home")

        with pytest.raises(script.NotAnEmptyFolder):
            script.build(folder)

        assert _untouched(folder)

    def test_the_script_refuses_a_file(self, tmp_path):
        target = tmp_path / "home"
        target.write_text("keep me")

        built = _build(target, home=tmp_path)

        assert built.returncode != 0
        assert target.read_text() == "keep me"

    @pytest.mark.parametrize("blank", ["", "   "], ids=["empty", "spaces"])
    def test_the_script_refuses_a_blank_folder_name(self, tmp_path, blank):
        # A blank CIS_BENCH_HOME means "not set": cis-bench would use the XDG data folder.
        built = _build(blank, home=tmp_path)

        assert built.returncode != 0
        assert not (tmp_path / ".local").exists()
        assert sorted(p.name for p in tmp_path.iterdir()) == []


class TestTheFixtures:
    @pytest.mark.parametrize("benchmark_id", sorted(SYNTHETIC))
    def test_recommendations_are_listed_in_ref_order(self, benchmark_id):
        refs = [r.ref for r in _benchmark(benchmark_id).recommendations]

        assert refs == sorted(refs, key=lambda ref: [int(n) for n in ref.split(".")])

    @pytest.mark.parametrize("benchmark_id", sorted(SYNTHETIC))
    def test_each_recommendation_numbers_its_artifacts_from_its_ref(self, benchmark_id):
        # As real copies do: 6.1.2's artifacts are 6.1.2.1, 6.1.2.2.
        for r in _benchmark(benchmark_id).recommendations:
            for artifact in r.artifacts:
                assert artifact.view_level.startswith(f"{r.ref}."), (r.ref, artifact.view_level)

    @pytest.mark.parametrize("benchmark_id", sorted(SYNTHETIC))
    def test_a_parent_is_the_recommendation_this_one_was_derived_from(self, benchmark_id):
        # As real copies hold it: a link to another recommendation, with that recommendation's
        # title (WorkBench's "PARENT : <title>"), never a section heading.
        parents = [r for r in _benchmark(benchmark_id).recommendations if r.parent is not None]
        for r in parents:
            assert re.fullmatch(
                r"https://workbench\.cisecurity\.org/sections/\d+/recommendations/\d+",
                str(r.parent.url),
            ), (r.ref, r.parent.url)
            assert str(r.parent.url) != str(r.url), r.ref
            assert not re.match(r"\d+(\.\d+)* ", r.parent.title), (r.ref, r.parent.title)
        # Each recommendation was derived from its own parent.
        assert len({str(r.parent.url) for r in parents}) == len(parents)


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
        assert _exported_recommendations(written, export_args[1]) == _recommendations(benchmark_id)
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
