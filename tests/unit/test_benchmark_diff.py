"""Tests for benchmark diff functionality.

TDD tests for comparing benchmark versions using DeepDiff.
"""

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from cis_bench.cli.app import cli


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def old_benchmark_json():
    """Old benchmark version for comparison."""
    return {
        "title": "CIS Ubuntu Linux 22.04 LTS Benchmark",
        "benchmark_id": "12345",
        "url": "https://workbench.cisecurity.org/benchmarks/12345",
        "version": "1.0.0",
        "downloaded_at": "2024-01-01T00:00:00",
        "scraper_version": "v1_current",
        "total_recommendations": 4,
        "recommendations": [
            {
                "ref": "1.1.1",
                "title": "Ensure mounting of cramfs is disabled",
                "url": "https://workbench.cisecurity.org/recommendations/1",
                "assessment_status": "Automated",
                "profiles": ["Level 1 - Server"],
                "description": "The cramfs filesystem type is a compressed read-only Linux filesystem.",
                "rationale": "Removing support for unneeded filesystem types reduces the local attack surface.",
                "audit": "Run: modprobe -n -v cramfs",
                "remediation": "Edit /etc/modprobe.d/cramfs.conf",
                "cis_controls": [],
                "nist_controls": ["CM-7"],
            },
            {
                "ref": "2.1.1",
                "title": "Ensure NIS Server is not installed",
                "url": "https://workbench.cisecurity.org/recommendations/2",
                "assessment_status": "Automated",
                "profiles": ["Level 1 - Server"],
                "description": "The NIS service is inherently insecure.",
                "rationale": "NIS is insecure and should not be used.",
                "audit": "Run: rpm -q ypserv",
                "remediation": "Run: dnf remove ypserv",
                "cis_controls": [],
                "nist_controls": ["CM-7"],
            },
            {
                "ref": "3.1.1",
                "title": "Ensure SSH MaxAuthTries is set to 4 or less",
                "url": "https://workbench.cisecurity.org/recommendations/3",
                "assessment_status": "Automated",
                "profiles": ["Level 1 - Server"],
                "description": "The MaxAuthTries parameter specifies the maximum number of authentication attempts.",
                "rationale": "Setting the MaxAuthTries parameter to a low number will minimize the risk of brute force.",
                "audit": "Run: sshd -T | grep maxauthtries",
                "remediation": "Edit /etc/ssh/sshd_config and set MaxAuthTries 4",
                "cis_controls": [],
                "nist_controls": ["AC-7"],
            },
            {
                "ref": "5.1.1",
                "title": "Ensure cron daemon is enabled",
                "url": "https://workbench.cisecurity.org/recommendations/4",
                "assessment_status": "Automated",
                "profiles": ["Level 1 - Server"],
                "description": "The cron daemon is used to execute batch jobs on the system.",
                "rationale": "Proper job scheduling is important.",
                "audit": "Run: systemctl is-enabled crond",
                "remediation": "Run: systemctl enable crond",
                "cis_controls": [],
                "nist_controls": ["CM-7"],
            },
        ],
    }


@pytest.fixture
def new_benchmark_json():
    """New benchmark version with changes."""
    return {
        "title": "CIS Ubuntu Linux 22.04 LTS Benchmark",
        "benchmark_id": "12345",
        "url": "https://workbench.cisecurity.org/benchmarks/12345",
        "version": "2.0.0",
        "downloaded_at": "2024-06-01T00:00:00",
        "scraper_version": "v1_current",
        "total_recommendations": 4,
        "recommendations": [
            # 1.1.1 unchanged
            {
                "ref": "1.1.1",
                "title": "Ensure mounting of cramfs is disabled",
                "url": "https://workbench.cisecurity.org/recommendations/1",
                "assessment_status": "Automated",
                "profiles": ["Level 1 - Server"],
                "description": "The cramfs filesystem type is a compressed read-only Linux filesystem.",
                "rationale": "Removing support for unneeded filesystem types reduces the local attack surface.",
                "audit": "Run: modprobe -n -v cramfs",
                "remediation": "Edit /etc/modprobe.d/cramfs.conf",
                "cis_controls": [],
                "nist_controls": ["CM-7"],
            },
            # 2.1.1 REMOVED (not in new version)
            # 3.1.1 MODIFIED (title and audit changed)
            {
                "ref": "3.1.1",
                "title": "Ensure SSH MaxAuthTries is configured",  # Title changed
                "url": "https://workbench.cisecurity.org/recommendations/3",
                "assessment_status": "Automated",
                "profiles": ["Level 1 - Server"],
                "description": "The MaxAuthTries parameter specifies the maximum number of authentication attempts.",
                "rationale": "Setting the MaxAuthTries parameter to a low number will minimize the risk of brute force.",
                "audit": "Run: sshd -T -C user=root | grep maxauthtries",  # Audit changed
                "remediation": "Edit /etc/ssh/sshd_config and set MaxAuthTries 4",
                "cis_controls": [],
                "nist_controls": ["AC-7"],
            },
            # 1.1.9 ADDED (new recommendation)
            {
                "ref": "1.1.9",
                "title": "Ensure noexec option set on /var/tmp partition",
                "url": "https://workbench.cisecurity.org/recommendations/5",
                "assessment_status": "Automated",
                "profiles": ["Level 1 - Server"],
                "description": "The noexec mount option specifies that the filesystem cannot contain executable binaries.",
                "rationale": "Adding this option prevents users from executing programs from /var/tmp.",
                "audit": "Run: findmnt -n /var/tmp",
                "remediation": "Edit /etc/fstab and add noexec",
                "cis_controls": [],
                "nist_controls": ["CM-7"],
            },
            # 5.1.1 -> 6.1.1 RENUMBERED (same content, different ref)
            {
                "ref": "6.1.1",  # Was 5.1.1
                "title": "Ensure cron daemon is enabled",
                "url": "https://workbench.cisecurity.org/recommendations/4",
                "assessment_status": "Automated",
                "profiles": ["Level 1 - Server"],
                "description": "The cron daemon is used to execute batch jobs on the system.",
                "rationale": "Proper job scheduling is important.",
                "audit": "Run: systemctl is-enabled crond",
                "remediation": "Run: systemctl enable crond",
                "cis_controls": [],
                "nist_controls": ["CM-7"],
            },
        ],
    }


class TestDiffCommandExists:
    """Test that diff command is available."""

    def test_diff_command_in_help(self, runner):
        """The diff command should appear in help output."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "diff" in result.output

    def test_diff_command_has_help(self, runner):
        """The diff command should have its own help."""
        result = runner.invoke(cli, ["diff", "--help"])
        assert result.exit_code == 0
        assert "Compare" in result.output or "compare" in result.output


class TestDiffCommandArguments:
    """Test diff command argument handling."""

    def test_diff_requires_two_arguments(self, runner):
        """diff command requires old and new benchmark identifiers."""
        result = runner.invoke(cli, ["diff"])
        assert result.exit_code != 0

    def test_diff_requires_new_argument(self, runner):
        """diff command requires both old and new."""
        result = runner.invoke(cli, ["diff", "12345"])
        assert result.exit_code != 0


class TestDiffDetectsChanges:
    """Each kind of change between two versions is reported with its ref."""

    def test_diff_detects_added_recommendations(
        self, runner, tmp_path, old_benchmark_json, new_benchmark_json
    ):
        old_file, new_file = _files(tmp_path, old_benchmark_json, new_benchmark_json)

        result = runner.invoke(cli, ["diff", old_file, new_file, "--format", "json"])

        assert result.exit_code == 0, result.output
        added = json.loads(result.output)["changes"]["added"]
        assert [a["ref"] for a in added] == ["1.1.9"]

    def test_diff_detects_removed_recommendations(
        self, runner, tmp_path, old_benchmark_json, new_benchmark_json
    ):
        old_file, new_file = _files(tmp_path, old_benchmark_json, new_benchmark_json)

        result = runner.invoke(cli, ["diff", old_file, new_file, "--format", "json"])

        assert result.exit_code == 0, result.output
        removed = json.loads(result.output)["changes"]["removed"]
        assert [r["ref"] for r in removed] == ["2.1.1"]

    def test_diff_detects_modified_recommendations(
        self, runner, tmp_path, old_benchmark_json, new_benchmark_json
    ):
        old_file, new_file = _files(tmp_path, old_benchmark_json, new_benchmark_json)

        result = runner.invoke(cli, ["diff", old_file, new_file, "--format", "json"])

        assert result.exit_code == 0, result.output
        modified = json.loads(result.output)["changes"]["modified"]
        assert [(m["ref"], m["fields_changed"]) for m in modified] == [
            ("3.1.1", ["audit", "title"])
        ]

    def test_diff_detects_renumbered_recommendations(
        self, runner, tmp_path, old_benchmark_json, new_benchmark_json
    ):
        old_file, new_file = _files(tmp_path, old_benchmark_json, new_benchmark_json)

        result = runner.invoke(cli, ["diff", old_file, new_file, "--format", "json"])

        assert result.exit_code == 0, result.output
        renumbered = json.loads(result.output)["changes"]["renumbered"]
        assert [(r["old_ref"], r["new_ref"]) for r in renumbered] == [("5.1.1", "6.1.1")]


class TestDiffTable:
    """The default table lists every change with its ref."""

    def test_table_lists_each_change(
        self, runner, tmp_path, old_benchmark_json, new_benchmark_json
    ):
        old_file, new_file = _files(tmp_path, old_benchmark_json, new_benchmark_json)

        result = runner.invoke(cli, ["diff", old_file, new_file])

        assert result.exit_code == 0, result.output
        flat = " ".join(result.output.split())
        for text in ("1.1.9", "2.1.1", "3.1.1", "5.1.1 → 6.1.1", "1.0.0 → 2.0.0"):
            assert text in flat

    def test_identical_versions_say_nothing_changed(self, runner, tmp_path, old_benchmark_json):
        old_file, new_file = _files(tmp_path, old_benchmark_json, old_benchmark_json)

        result = runner.invoke(cli, ["diff", old_file, new_file])

        assert result.exit_code == 0, result.output
        assert "No changes detected" in result.output


class TestDiffLocal:
    """Two benchmarks on disk are compared without touching the network."""

    def test_diff_uses_cached_benchmark_without_fetch(
        self, runner, monkeypatch, tmp_path, old_benchmark_json, new_benchmark_json
    ):
        """diff should use cached benchmarks without fetching."""

        # Both files exist locally
        old_file = tmp_path / "old.json"
        new_file = tmp_path / "new.json"
        old_file.write_text(json.dumps(old_benchmark_json))
        new_file.write_text(json.dumps(new_benchmark_json))

        result = runner.invoke(cli, ["diff", str(old_file), str(new_file)])

        # Should succeed without any fetch messages
        assert result.exit_code == 0
        output_lower = result.output.lower()
        # Should NOT mention fetching since both are local
        assert "fetching" not in output_lower

    def test_two_files_are_compared_in_offline_mode(
        self, runner, tmp_path, old_benchmark_json, new_benchmark_json, auth_manager_class
    ):
        old_file, new_file = _files(tmp_path, old_benchmark_json, new_benchmark_json)

        result = runner.invoke(cli, ["--offline", "diff", old_file, new_file, "--format", "json"])

        assert result.exit_code == 0, result.output
        modified = json.loads(result.output)["changes"]["modified"]
        assert [m["ref"] for m in modified] == ["3.1.1"]
        auth_manager_class.assert_not_called()


def _files(tmp_path, old, new):
    old_file, new_file = tmp_path / "old.json", tmp_path / "new.json"
    old_file.write_text(json.dumps(old))
    new_file.write_text(json.dumps(new))
    return str(old_file), str(new_file)


def _with_rec_change(benchmark, ref, **fields):
    changed = json.loads(json.dumps(benchmark))
    for rec in changed["recommendations"]:
        if rec["ref"] == ref:
            rec.update(fields)
    return changed


class TestComparisonNamesEveryChangedField:
    """A change to any recommendation field is reported with that field's name."""

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("impact", "Changes the boot order."),
            ("default_value", "enabled"),
            ("references", "https://example.org/new"),
            ("artifacts", [{"id": 1, "title": "a", "type": "t"}]),
        ],
    )
    def test_a_field_outside_the_old_fixed_list_is_named(self, old_benchmark_json, field, value):
        from cis_bench.cli.commands.diff import compare_benchmarks

        new = _with_rec_change(old_benchmark_json, "1.1.1", **{field: value})

        comparison = compare_benchmarks(old_benchmark_json, new)

        modified = comparison["changes"]["modified"]
        assert [m["ref"] for m in modified] == ["1.1.1"]
        assert modified[0]["fields_changed"] == [field]

    def test_the_url_of_a_recommendation_is_not_a_change(self, old_benchmark_json):
        from cis_bench.cli.commands.diff import compare_benchmarks

        new = _with_rec_change(old_benchmark_json, "1.1.1", url="https://elsewhere.example/1")

        assert compare_benchmarks(old_benchmark_json, new)["summary"]["modified"] == 0


class TestWorkBenchIdentifiersAreNotChanges:
    """WorkBench gives every release new URLs and artifact IDs; only content counts."""

    def test_new_parent_url_and_artifact_ids_alone_are_not_a_change(self, old_benchmark_json):
        from cis_bench.cli.commands.diff import compare_benchmarks

        def release(section_id, artifact_id):
            return _with_rec_change(
                old_benchmark_json,
                "1.1.1",
                parent={
                    "url": f"https://workbench.cisecurity.org/sections/{section_id}",
                    "title": "Filesystem",
                },
                artifacts=[{"id": artifact_id, "title": "Check cramfs", "status": "accepted"}],
            )

        comparison = compare_benchmarks(release(2141901, 4581159), release(2346699, 7827594))

        assert comparison["summary"]["modified"] == 0

    def test_a_changed_artifact_or_parent_title_is_still_a_change(self, old_benchmark_json):
        from cis_bench.cli.commands.diff import compare_benchmarks

        old = _with_rec_change(
            old_benchmark_json,
            "1.1.1",
            parent={"url": "https://workbench.cisecurity.org/sections/1", "title": "Filesystem"},
            artifacts=[{"id": 1, "title": "Check cramfs", "status": "accepted"}],
        )
        new = _with_rec_change(
            old_benchmark_json,
            "1.1.1",
            parent={"url": "https://workbench.cisecurity.org/sections/2", "title": "Modules"},
            artifacts=[{"id": 2, "title": "Check cramfs", "status": "draft"}],
        )

        modified = compare_benchmarks(old, new)["changes"]["modified"]

        assert modified[0]["fields_changed"] == ["artifacts", "parent"]


class TestOutputs:
    def test_json_is_valid_with_long_text_markup_like_titles_and_type_changes(
        self, runner, tmp_path, old_benchmark_json
    ):
        old = _with_rec_change(old_benchmark_json, "1.1.1", impact=None)
        new = _with_rec_change(
            old_benchmark_json,
            "1.1.1",
            title="Ensure [bold]mounting[/bold] of " + "cramfs " * 30 + "is disabled",
            impact="Changes the boot order.",
        )
        old_file, new_file = _files(tmp_path, old, new)

        result = runner.invoke(cli, ["diff", old_file, new_file, "--format", "json"])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        modified = data["changes"]["modified"][0]
        assert modified["title"] == new["recommendations"][0]["title"]
        assert modified["fields_changed"] == ["impact", "title"]
        impact_change = modified["diff"]["type_changes"]["root['impact']"]
        assert impact_change["old_type"] == "NoneType" and impact_change["new_type"] == "str"

    def test_markdown_is_a_plain_document(self, runner, tmp_path, old_benchmark_json):
        long_title = "Ensure " + "very " * 40 + "long titles stay on one table row"
        new = _with_rec_change(old_benchmark_json, "1.1.1", title=long_title)
        old_file, new_file = _files(tmp_path, old_benchmark_json, new)

        result = runner.invoke(cli, ["diff", old_file, new_file, "--format", "markdown"])

        assert result.exit_code == 0, result.output
        assert "# Benchmark Comparison" in result.output
        assert f"| 1.1.1 | {long_title} | title |" in result.output.splitlines()

    def test_summary_counts_each_kind_of_change(
        self, runner, tmp_path, old_benchmark_json, new_benchmark_json
    ):
        old_file, new_file = _files(tmp_path, old_benchmark_json, new_benchmark_json)

        result = runner.invoke(cli, ["diff", old_file, new_file, "--format", "summary"])

        assert result.exit_code == 0, result.output
        flat = " ".join(result.output.split())
        assert "1 added" in flat and "1 removed" in flat and "1 modified" in flat
        assert "1 renumbered" in flat

    def test_verbose_table_names_each_changed_field(self, runner, tmp_path, old_benchmark_json):
        new = _with_rec_change(old_benchmark_json, "1.1.1", impact="New impact", audit="New audit")
        old_file, new_file = _files(tmp_path, old_benchmark_json, new)

        result = runner.invoke(cli, ["diff", old_file, new_file, "--verbose"])

        assert result.exit_code == 0, result.output
        assert "• audit changed" in result.output
        assert "• impact changed" in result.output

    def test_titles_from_the_benchmarks_are_shown_verbatim(
        self, runner, tmp_path, old_benchmark_json
    ):
        new = _with_rec_change(old_benchmark_json, "1.1.1", title="Ensure [x] is [bold]set[/bold]")
        new["title"] = "CIS [Linux] [bold]Benchmark[/bold]"
        old_file, new_file = _files(tmp_path, old_benchmark_json, new)

        table = runner.invoke(cli, ["diff", old_file, new_file])
        summary = runner.invoke(cli, ["diff", old_file, new_file, "--format", "summary"])

        assert table.exit_code == 0, table.output
        flat_table = " ".join(table.output.split())
        assert "Ensure [x] is [bold]set[/bold]" in flat_table
        assert "CIS [Linux] [bold]Benchmark[/bold]" in flat_table
        assert "Benchmark: CIS [Linux] [bold]Benchmark[/bold]" in summary.output


class TestDownloadedBenchmarksByID:
    """An ID is the downloaded copy in the cache, as get, export and info read it."""

    @pytest.fixture
    def cached(self, tmp_path, monkeypatch, old_benchmark_json, new_benchmark_json):
        from cis_bench.catalog.database import CatalogDatabase, serialize_benchmark_json
        from cis_bench.models.benchmark import Benchmark

        monkeypatch.setenv("CIS_BENCH_HOME", str(tmp_path))
        db = CatalogDatabase(tmp_path / "catalog.db")
        db.initialize_schema()
        for data, bid in ((old_benchmark_json, "12345"), (new_benchmark_json, "12346")):
            data = {**data, "benchmark_id": bid}
            content_json, content_hash = serialize_benchmark_json(Benchmark.model_validate(data))
            db.save_downloaded(bid, content_json, content_hash, len(data["recommendations"]))
        return db

    def test_two_downloaded_ids_are_compared_from_the_cache(self, runner, cached):
        result = runner.invoke(cli, ["diff", "12345", "12346", "--format", "json"])

        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["summary"]["added"] == 1

    def test_an_id_the_catalog_does_not_list_is_named_without_logging_in(self, runner, cached):
        from unittest.mock import patch

        with patch("cis_bench.fetcher.auth.AuthManager.get_or_create_session") as session:
            result = runner.invoke(cli, ["diff", "12345", "99999"])

        assert result.exit_code == 1
        assert "Benchmark 99999 is not in catalog" in result.output
        assert "cis-bench catalog refresh" in result.output
        session.assert_not_called()

    def test_a_missing_file_is_named(self, runner, tmp_path, old_benchmark_json):
        old_file, _ = _files(tmp_path, old_benchmark_json, old_benchmark_json)

        result = runner.invoke(cli, ["diff", old_file, str(tmp_path / "nope.json")])

        assert result.exit_code == 1
        assert "nope.json" in result.output


class TestInputsThatAreNotBenchmarks:
    @pytest.mark.parametrize(
        "content", ["{not json", '{"title": "no recommendations or version"}', "[1, 2]"]
    )
    def test_a_file_that_is_not_a_benchmark_is_named(
        self, runner, tmp_path, old_benchmark_json, content
    ):
        old_file, _ = _files(tmp_path, old_benchmark_json, old_benchmark_json)
        bad = tmp_path / "notes.json"
        bad.write_text(content)

        result = runner.invoke(cli, ["diff", old_file, str(bad)])

        assert result.exit_code == 1
        assert "notes.json is not a benchmark JSON file" in result.output
        assert "Traceback" not in result.output

    def test_a_binary_file_is_named(self, runner, tmp_path, old_benchmark_json):
        old_file, _ = _files(tmp_path, old_benchmark_json, old_benchmark_json)
        bad = tmp_path / "catalog.db"
        bad.write_bytes(b"\xff\xfe\x00SQLite format 3\x00")

        result = runner.invoke(cli, ["diff", old_file, str(bad)])

        assert result.exit_code == 1
        assert "catalog.db is not a benchmark JSON file" in result.output
        assert result.exception is None or isinstance(result.exception, SystemExit)

    @pytest.mark.skipif(os.geteuid() == 0, reason="root reads files whatever their mode")
    def test_an_unreadable_file_is_named(self, runner, tmp_path, old_benchmark_json):
        old_file, new_file = _files(tmp_path, old_benchmark_json, old_benchmark_json)
        Path(new_file).chmod(0)
        try:
            result = runner.invoke(cli, ["diff", old_file, new_file])
        finally:
            Path(new_file).chmod(0o644)

        assert result.exit_code == 1
        assert "new.json could not be read" in result.output
        assert result.exception is None or isinstance(result.exception, SystemExit)


class TestOrderAndMarkdownCells:
    def test_refs_are_listed_in_numeric_order(self, old_benchmark_json):
        from cis_bench.cli.commands.diff import compare_benchmarks

        new = json.loads(json.dumps(old_benchmark_json))
        template = new["recommendations"][0]
        for ref, title in (("1.1.10", "Tenth new check"), ("1.1.2", "Second new check")):
            new["recommendations"].append({**template, "ref": ref, "title": title})

        comparison = compare_benchmarks(old_benchmark_json, new)

        assert [a["ref"] for a in comparison["changes"]["added"]] == ["1.1.2", "1.1.10"]

    def test_a_pipe_in_a_title_stays_inside_its_markdown_cell(
        self, runner, tmp_path, old_benchmark_json
    ):
        new = _with_rec_change(old_benchmark_json, "1.1.1", title="Ensure a | b is set")
        old_file, new_file = _files(tmp_path, old_benchmark_json, new)

        result = runner.invoke(cli, ["diff", old_file, new_file, "--format", "markdown"])

        assert result.exit_code == 0, result.output
        assert "| 1.1.1 | Ensure a \\| b is set | title |" in result.output.splitlines()


class TestFetchingAnIDThatIsNotDownloaded:
    """An ID in the catalog but not in the cache is downloaded into the cache, as download
    and get do, then compared; it is then downloaded like any other."""

    @pytest.fixture
    def catalog(self, tmp_path, monkeypatch, old_benchmark_json):
        from cis_bench.catalog.database import CatalogDatabase, serialize_benchmark_json
        from cis_bench.models.benchmark import Benchmark

        monkeypatch.setenv("CIS_BENCH_HOME", str(tmp_path))
        db = CatalogDatabase(tmp_path / "catalog.db")
        db.initialize_schema()
        for bid, version in (("12345", "1.0.0"), ("12346", "2.0.0")):
            db.insert_benchmark(
                {
                    "benchmark_id": bid,
                    "title": "CIS Ubuntu Linux 22.04 LTS Benchmark",
                    "version": version,
                    "url": f"https://workbench.cisecurity.org/benchmarks/{bid}",
                    "status": "Published",
                }
            )
        old = {**old_benchmark_json, "benchmark_id": "12345"}
        content_json, content_hash = serialize_benchmark_json(Benchmark.model_validate(old))
        db.save_downloaded("12345", content_json, content_hash, 4, version="1.0.0")
        return db

    @pytest.fixture
    def scraper(self, new_benchmark_json):
        from unittest.mock import MagicMock, patch

        from cis_bench.models.benchmark import Benchmark

        new = Benchmark.model_validate(
            {
                **new_benchmark_json,
                "benchmark_id": "12346",
                "downloaded_at": "2024-06-01T00:00:00+00:00",
                "published_date": "2024-06-01",
            }
        )
        instance = MagicMock()
        instance.base_url = "https://workbench.cisecurity.org"
        instance.download_benchmark.return_value = new
        with (
            patch("cis_bench.fetcher.auth.AuthManager.get_or_create_session") as session,
            patch("cis_bench.fetcher.workbench.WorkbenchScraper", return_value=instance),
        ):
            instance.session = session
            yield instance

    def test_diff_fetches_an_undownloaded_id_through_the_download_path(
        self, runner, catalog, scraper
    ):
        result = runner.invoke(cli, ["diff", "12345", "12346", "--format", "json"])

        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["summary"]["added"] == 1
        scraper.download_benchmark.assert_called_once()
        assert scraper.download_benchmark.call_args.args[0] == (
            "https://workbench.cisecurity.org/benchmarks/12346"
        )
        cached = catalog.get_downloaded("12346")
        assert cached is not None
        assert cached["version"] == "2.0.0"
        assert str(cached["published_date"]) == "2024-06-01"
        assert str(catalog.get_benchmark("12346")["published_date"]) == "2024-06-01"
        assert json.loads(cached["content_json"])["benchmark_id"] == "12346"

    def test_the_fetch_is_announced_on_stderr(self, runner, catalog, scraper):
        result = runner.invoke(cli, ["diff", "12345", "12346", "--format", "json"])

        assert result.exit_code == 0, result.output
        assert "12346" in result.stderr
        assert "Downloaded" in result.stderr

    def test_a_fetched_id_is_not_fetched_again(self, runner, catalog, scraper):
        first = runner.invoke(cli, ["diff", "12345", "12346", "--format", "summary"])
        second = runner.invoke(cli, ["diff", "12345", "12346", "--format", "summary"])

        assert first.exit_code == 0 and second.exit_code == 0, second.output
        scraper.download_benchmark.assert_called_once()

    def test_two_ids_to_download_log_in_once(self, runner, catalog, scraper):
        catalog.insert_benchmark(
            {
                "benchmark_id": "12347",
                "title": "CIS Ubuntu Linux 22.04 LTS Benchmark",
                "version": "3.0.0",
                "url": "https://workbench.cisecurity.org/benchmarks/12347",
                "status": "Published",
            }
        )

        result = runner.invoke(cli, ["diff", "12346", "12347", "--format", "summary"])

        assert result.exit_code == 0, result.output
        assert scraper.download_benchmark.call_count == 2
        scraper.session.assert_called_once()

    def test_download_progress_stays_off_stdout(self, runner, catalog, scraper):
        downloaded = scraper.download_benchmark.return_value

        def scrape(url, progress_callback=None):
            progress_callback("Benchmark title: CIS Ubuntu Linux 22.04 LTS Benchmark")
            progress_callback("Found 4 recommendations")
            progress_callback("[1/4] Fetching 1.1.1")
            return downloaded

        scraper.download_benchmark.side_effect = scrape

        result = runner.invoke(cli, ["diff", "12345", "12346", "--format", "json"])

        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["summary"]["added"] == 1
        assert "CIS Ubuntu Linux 22.04 LTS Benchmark" in result.stderr

    def test_two_downloaded_ids_never_log_in(self, runner, catalog, scraper):
        runner.invoke(cli, ["diff", "12345", "12345", "--format", "summary"])

        scraper.session.assert_not_called()
        scraper.download_benchmark.assert_not_called()

    def test_an_id_not_in_the_catalog_is_named(self, runner, catalog, scraper):
        result = runner.invoke(cli, ["diff", "12345", "99999"])

        assert result.exit_code == 1
        assert "99999" in result.output and "not in catalog" in result.output
        scraper.download_benchmark.assert_not_called()

    def test_without_a_catalog_it_says_to_build_one(self, runner, tmp_path, monkeypatch):
        monkeypatch.setenv("CIS_BENCH_HOME", str(tmp_path))

        result = runner.invoke(cli, ["diff", "12345", "12346"])

        assert result.exit_code == 1
        assert "cis-bench catalog refresh" in result.output

    def test_no_saved_session_says_to_log_in(self, runner, catalog, scraper):
        from cis_bench.exceptions import NoSavedSessionError

        scraper.session.side_effect = NoSavedSessionError("No saved session found")

        result = runner.invoke(cli, ["diff", "12345", "12346"])

        assert result.exit_code == 1
        assert "Authentication Required" in result.output
        assert "cis-bench auth login --browser chrome" in result.output
        assert result.exception is None or isinstance(result.exception, SystemExit)

    def test_an_expired_session_says_to_log_in_again(self, runner, catalog, scraper):
        from cis_bench.exceptions import AuthenticationError

        scraper.session.side_effect = AuthenticationError("Session expired")

        result = runner.invoke(cli, ["diff", "12345", "12346"])

        assert result.exit_code == 1
        assert "Authentication Failed" in result.output
        assert "Session expired" in result.output

    def test_an_untrusted_server_gives_its_message(self, runner, catalog, scraper):
        from cis_bench.exceptions import TLSVerificationError

        scraper.download_benchmark.side_effect = TLSVerificationError(
            "certificate verify failed: set CIS_BENCH_VERIFY_SSL to a CA bundle"
        )

        result = runner.invoke(cli, ["diff", "12345", "12346"])

        assert result.exit_code == 1
        assert "certificate verify failed" in " ".join(result.output.split())
        assert "Could not reach WorkBench" not in result.output
        assert catalog.get_downloaded("12346") is None

    def test_an_unreachable_workbench_changes_nothing(self, runner, catalog, scraper):
        from cis_bench.exceptions import FetchError

        scraper.download_benchmark.side_effect = FetchError(
            "https://workbench.cisecurity.org/benchmarks/12346", 3, "Connection refused"
        )

        result = runner.invoke(cli, ["diff", "12345", "12346"])

        assert result.exit_code == 1
        assert "Could not reach WorkBench" in result.output
        assert catalog.get_downloaded("12346") is None

    def test_a_failed_cache_write_is_reported(self, runner, catalog, scraper, monkeypatch):
        from sqlalchemy.exc import OperationalError

        from cis_bench.catalog.database import CatalogDatabase

        def locked(self, *args, **kwargs):
            raise OperationalError("INSERT", {}, Exception("database is locked"))

        monkeypatch.setattr(CatalogDatabase, "save_downloaded", locked)

        result = runner.invoke(cli, ["diff", "12345", "12346"])

        assert result.exit_code == 1
        assert "Could not cache 12346" in result.output
        assert "database is locked" in result.output
        assert "INSERT" not in result.output
        assert result.exception is None or isinstance(result.exception, SystemExit)

    def test_a_bad_setting_is_a_configuration_error(self, runner, catalog, monkeypatch):
        monkeypatch.setenv("CIS_BENCH_REQUESTS_PER_SECOND", "fast")

        result = runner.invoke(cli, ["diff", "12345", "12346"])

        assert result.exit_code == 1
        assert "Configuration Error" in result.output


class TestReformattedFields:
    """A field whose text differs only in whitespace is reformatted: shown, never hidden, and
    never counted as a modification."""

    def test_a_field_differing_only_in_whitespace_is_reformatted_not_modified(
        self, old_benchmark_json
    ):
        from cis_bench.cli.commands.diff import compare_benchmarks

        rewrapped = "The cramfs filesystem type is a\ncompressed  read-only\tLinux filesystem.  "
        new = _with_rec_change(old_benchmark_json, "1.1.1", description=rewrapped)

        comparison = compare_benchmarks(old_benchmark_json, new)

        assert comparison["summary"]["modified"] == 0
        assert comparison["summary"]["reformatted"] == 1
        assert comparison["changes"]["reformatted"] == [
            {
                "ref": "1.1.1",
                "title": "Ensure mounting of cramfs is disabled",
                "fields": ["description"],
            }
        ]

    @pytest.mark.parametrize(
        "description",
        [
            "The cramfs filesystem type is a compressed read-only Linux file system.",
            "the cramfs filesystem type is a compressed read-only Linux filesystem.",
            "The cramfs filesystem type is a compressed read-only Linux filesystem",
            "The cramfs filesystem type is a compressedread-only Linux filesystem.",
        ],
        ids=["wording", "case", "punctuation", "words-joined"],
    )
    def test_anything_but_whitespace_is_a_modification(self, old_benchmark_json, description):
        from cis_bench.cli.commands.diff import compare_benchmarks

        new = _with_rec_change(old_benchmark_json, "1.1.1", description=description)

        comparison = compare_benchmarks(old_benchmark_json, new)

        assert comparison["summary"]["reformatted"] == 0
        assert [m["fields_changed"] for m in comparison["changes"]["modified"]] == [["description"]]

    def test_a_modified_recommendation_names_its_reformatted_fields_separately(
        self, old_benchmark_json
    ):
        from cis_bench.cli.commands.diff import compare_benchmarks

        new = _with_rec_change(
            old_benchmark_json,
            "1.1.1",
            description="The cramfs filesystem type is a\ncompressed read-only Linux filesystem.",
            audit="Run: modprobe -n -v cramfs | grep -E '(cramfs|install)'",
        )

        comparison = compare_benchmarks(old_benchmark_json, new)

        (modified,) = comparison["changes"]["modified"]
        assert modified["fields_changed"] == ["audit"]
        assert modified["reformatted_fields"] == ["description"]
        assert comparison["summary"]["reformatted"] == 0

    def test_whitespace_inside_list_values_is_formatting_too(self, old_benchmark_json):
        from cis_bench.cli.commands.diff import compare_benchmarks

        new = _with_rec_change(old_benchmark_json, "1.1.1", profiles=["Level 1 -  Server"])

        comparison = compare_benchmarks(old_benchmark_json, new)

        assert comparison["changes"]["reformatted"][0]["fields"] == ["profiles"]

    @pytest.fixture
    def reformatted_files(self, tmp_path, old_benchmark_json):
        new = _with_rec_change(
            old_benchmark_json,
            "1.1.1",
            description="The cramfs filesystem type is a\ncompressed read-only Linux filesystem.",
        )
        return _files(tmp_path, old_benchmark_json, new)

    def test_every_format_shows_the_reformatted_count(self, runner, reformatted_files):
        old_file, new_file = reformatted_files

        summary = runner.invoke(cli, ["diff", old_file, new_file, "--format", "summary"])
        table = runner.invoke(cli, ["diff", old_file, new_file])
        markdown = runner.invoke(cli, ["diff", old_file, new_file, "--format", "markdown"])
        data = json.loads(
            runner.invoke(cli, ["diff", old_file, new_file, "--format", "json"]).stdout
        )

        assert "1 reformatted" in " ".join(summary.output.split())
        assert "Reformatted: 1 recommendations" in " ".join(table.output.split())
        assert "| Reformatted | 1 |" in markdown.output.splitlines()
        assert data["summary"]["reformatted"] == 1

    def test_table_verbose_markdown_and_json_list_them(self, runner, reformatted_files):
        old_file, new_file = reformatted_files

        verbose = runner.invoke(cli, ["diff", old_file, new_file, "--verbose"])
        markdown = runner.invoke(cli, ["diff", old_file, new_file, "--format", "markdown"])
        data = json.loads(
            runner.invoke(cli, ["diff", old_file, new_file, "--format", "json"]).stdout
        )

        flat = " ".join(verbose.output.split())
        assert "REFORMATTED: 1.1.1 - Ensure mounting of cramfs is disabled" in flat
        assert "• description (whitespace only)" in flat
        assert "## Reformatted Recommendations" in markdown.output
        assert "| 1.1.1 | Ensure mounting of cramfs is disabled | description |" in (
            markdown.output.splitlines()
        )
        assert data["changes"]["reformatted"][0]["ref"] == "1.1.1"

    def test_verbose_lists_reformatted_fields_and_recommendations_next_to_real_changes(
        self, runner, tmp_path, old_benchmark_json
    ):
        new = _with_rec_change(
            old_benchmark_json,
            "1.1.1",
            description="The cramfs filesystem type is a\ncompressed read-only Linux filesystem.",
            audit="Run: modprobe -n -v cramfs | grep cramfs",
        )
        new = _with_rec_change(new, "2.1.1", rationale="NIS is insecure  and should\nnot be used.")
        old_file, new_file = _files(tmp_path, old_benchmark_json, new)

        result = runner.invoke(cli, ["diff", old_file, new_file, "--verbose"])

        lines = [" ".join(line.split()) for line in result.output.splitlines()]
        start = lines.index("⟳ MODIFIED: 1.1.1 - Ensure mounting of cramfs is disabled")
        assert lines[start + 1 : start + 3] == [
            "• audit changed",
            "• description (whitespace only)",
        ]
        assert "≈ REFORMATTED: 2.1.1 - Ensure NIS Server is not installed" in lines
        assert "• rationale (whitespace only)" in lines

    def test_only_reformatted_changes_are_not_reported_as_no_changes(
        self, runner, reformatted_files
    ):
        old_file, new_file = reformatted_files

        table = runner.invoke(cli, ["diff", old_file, new_file])

        assert "No changes detected" not in table.output
        assert "No content changes" in table.output
        assert "--verbose lists them" in " ".join(table.output.split())
        verbose = runner.invoke(cli, ["diff", old_file, new_file, "--verbose"])
        assert "--verbose lists them" not in " ".join(verbose.output.split())


class TestScraperVersionNotice:
    """Copies made by different scraper versions can differ in formatting for reasons of
    cis-bench's own; diff says so."""

    def test_different_scraper_versions_are_named_in_every_format(
        self, runner, tmp_path, old_benchmark_json
    ):
        new = {**old_benchmark_json, "scraper_version": "v2_2026"}
        old_file, new_file = _files(tmp_path, old_benchmark_json, new)

        outputs = {
            fmt: runner.invoke(cli, ["diff", old_file, new_file, "--format", fmt])
            for fmt in ("table", "summary", "markdown", "json")
        }

        for fmt in ("table", "summary", "markdown"):
            flat = " ".join(outputs[fmt].output.split())
            assert "made by different scraper versions (v1_current → v2_2026)" in flat, fmt
        data = json.loads(outputs["json"].stdout)
        assert data["scraper_versions"] == {"old": "v1_current", "new": "v2_2026"}
        assert data["scraper_versions_differ"] is True

    def test_the_same_scraper_version_says_nothing(self, runner, tmp_path, old_benchmark_json):
        old_file, new_file = _files(tmp_path, old_benchmark_json, old_benchmark_json)

        summary = runner.invoke(cli, ["diff", old_file, new_file, "--format", "summary"])
        data = json.loads(
            runner.invoke(cli, ["diff", old_file, new_file, "--format", "json"]).stdout
        )

        assert "scraper versions" not in summary.output
        assert data["scraper_versions_differ"] is False
