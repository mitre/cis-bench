"""The recommendation index: every downloaded benchmark's recommendations, searchable.

The index is written where a benchmark is saved and cleared where it is removed, so it holds
exactly the downloaded benchmarks. A query is user text: punctuation and FTS5 keywords are
search words, never query syntax.
"""

import contextlib
from contextlib import closing

import pytest

from cis_bench.catalog.database import CatalogDatabase, serialize_benchmark_json
from cis_bench.models.benchmark import Benchmark, Recommendation


def _recommendation(ref, title, profiles=("Level 1 - Server",), **text):
    return Recommendation(
        ref=ref,
        title=title,
        url=f"https://workbench.cisecurity.org/sections/1/recommendations/{ref.replace('.', '')}",
        assessment_status="Automated",
        profiles=list(profiles),
        **text,
    )


SSH = _recommendation(
    "1.1.1",
    "Ensure SSH MaxAuthTries is configured",
    description="The MaxAuthTries parameter limits login attempts on Ubuntu 22.04 hosts.",
    rationale="Fewer attempts slow a password guessing attack.",
    audit="Run: sshd -T | grep -i maxauthtries [sshd_config]",
    remediation="Set MaxAuthTries 4 in /etc/ssh/sshd_config.",
)
SELINUX = _recommendation(
    "2.1.1",
    "Ensure SELinux is installed",
    profiles=("Level 2 - Server",),
    description="SELinux adds mandatory access control on Red Hat systems.",
    rationale="Access is checked AND logged.",
    audit="Run: rpm -q libselinux",
    remediation="Run: dnf install libselinux",
)
FIREWALL = _recommendation(
    "3.1.1",
    "Ensure a firewall is installed",
    description="A host firewall filters traffic.",
    audit="Run: rpm -q nftables",
    remediation="Run: dnf install nftables",
)


def _benchmark(benchmark_id, *recommendations, scraper_version="v2_2026_01"):
    return Benchmark(
        title=f"Example Benchmark {benchmark_id}",
        benchmark_id=benchmark_id,
        url=f"https://workbench.cisecurity.org/benchmarks/{benchmark_id}",
        version="v1.0.0",
        scraper_version=scraper_version,
        total_recommendations=len(recommendations),
        recommendations=list(recommendations),
    )


def _save(db, benchmark):
    content_json, content_hash = serialize_benchmark_json(benchmark)
    db.save_downloaded(
        benchmark.benchmark_id, content_json, content_hash, len(benchmark.recommendations)
    )


@pytest.fixture
def db(tmp_path):
    with closing(CatalogDatabase(tmp_path / "catalog.db")) as database:
        database.initialize_schema()
        yield database


def _refs(results):
    return [(r["benchmark_id"], r["ref"]) for r in results]


class TestIndexedWhereSaved:
    def test_saving_a_benchmark_indexes_every_recommendation(self, db):
        _save(db, _benchmark("100", SSH, SELINUX, FIREWALL))

        assert sorted(_refs(db.search_recommendations("installed"))) == [
            ("100", "2.1.1"),
            ("100", "3.1.1"),
        ]
        assert _refs(db.search_recommendations("maxauthtries")) == [("100", "1.1.1")]

    def test_a_benchmark_the_download_step_caches_is_searchable(self, db):
        from cis_bench.catalog.downloader import CatalogDownloader

        CatalogDownloader(db).cache("100", _benchmark("100", SSH, SELINUX))

        assert _refs(db.search_recommendations("libselinux")) == [("100", "2.1.1")]

    def test_a_result_names_the_benchmark_the_recommendation_and_the_fields_that_matched(self, db):
        _save(db, _benchmark("100", SSH, SELINUX))

        (result,) = db.search_recommendations("libselinux")

        assert result == {
            "benchmark_id": "100",
            "ref": "2.1.1",
            "title": "Ensure SELinux is installed",
            "matched_fields": ["audit", "remediation"],
        }

    def test_a_field_is_matched_only_where_a_word_was_found_whatever_its_characters(self, db):
        control = _recommendation(
            "7.1.1",
            "Ensure SSH is configured",
            description="unrelated\x02text \x03 more",
        )
        _save(db, _benchmark("100", control))

        (result,) = db.search_recommendations("ssh")

        assert result["matched_fields"] == ["title"]

    def test_a_field_holding_a_nul_is_matched_only_where_a_word_was_found(self, db):
        untouched = _recommendation(
            "7.2.1", "Ensure SSH is configured", description="unrelated\x00text"
        )
        after_the_nul = _recommendation(
            "7.2.2", "Ensure auditing is configured", description="first\x00 sshd later"
        )
        _save(db, _benchmark("100", untouched, after_the_nul))

        found = {r["ref"]: r["matched_fields"] for r in db.search_recommendations("ssh")}

        assert found == {"7.2.1": ["title"], "7.2.2": ["description"]}

    def test_a_write_from_another_connection_during_a_search_does_not_change_its_result(
        self, db, monkeypatch
    ):
        import sqlite3

        from cis_bench.catalog import database

        _save(db, _benchmark("100", SSH))
        attempts = []
        build = database.build_any_term_query

        def write_between_the_reads(query, column_name):
            # Another process changes the found recommendation after the ranked read and
            # before the field reads: it must not commit into the middle of the search.
            if not attempts:
                with contextlib.closing(sqlite3.connect(db.db_path, timeout=0)) as other:
                    try:
                        other.execute(
                            "UPDATE recommendations_fts SET title = 'Ensure nothing' "
                            "WHERE benchmark_id = '100'"
                        )
                        other.commit()
                        attempts.append("committed")
                    except sqlite3.OperationalError as error:
                        attempts.append(str(error))
            return build(query, column_name)

        monkeypatch.setattr(database, "build_any_term_query", write_between_the_reads)

        (result,) = db.search_recommendations("maxauthtries")

        assert attempts
        assert (result["ref"], result["title"], result["matched_fields"]) == (
            "1.1.1",
            "Ensure SSH MaxAuthTries is configured",
            ["title", "description", "audit", "remediation"],
        )

    def test_saving_the_same_benchmark_again_replaces_its_rows(self, db):
        _save(db, _benchmark("100", SSH, FIREWALL))
        renamed = FIREWALL.model_copy(update={"title": "Ensure a packet filter is installed"})
        _save(db, _benchmark("100", SSH, renamed))

        assert sorted(_refs(db.search_recommendations("ensure"))) == [
            ("100", "1.1.1"),
            ("100", "3.1.1"),
        ]
        (result,) = db.search_recommendations("packet")
        assert (result["ref"], result["title"]) == ("3.1.1", "Ensure a packet filter is installed")

    def test_removing_a_downloaded_benchmark_removes_its_rows(self, db):
        _save(db, _benchmark("100", SSH))
        _save(db, _benchmark("200", SSH))

        db.delete_downloaded("100")

        assert _refs(db.search_recommendations("maxauthtries")) == [("200", "1.1.1")]

    def test_a_copy_that_holds_the_v1_scrapers_html_is_indexed_as_the_markdown_it_loads_as(
        self, db
    ):
        import json

        # A copy the v1 scraper saved holds the page's HTML and says so (text_format).
        stored = json.loads(serialize_benchmark_json(_benchmark("100", FIREWALL))[0])
        stored["text_format"] = "html"
        stored["recommendations"][0]["remediation"] = (
            "<p>Run <code>chage --maxdays 365 &lt;user&gt;</code></p>"
        )
        db.save_downloaded("100", json.dumps(stored), "hash", 1)

        assert _refs(db.search_recommendations("chage")) == [("100", "3.1.1")]
        # The page's tag names are markup, not words of the recommendation.
        assert db.search_recommendations("code") == []

    def test_a_copy_that_does_not_load_is_saved_and_indexes_nothing(self, db):
        db.save_downloaded("100", "{}", "hash", 0)

        assert db.get_downloaded("100") is not None
        assert db.search_recommendations("ensure") == []


class TestQueriesAreUserText:
    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("ssh", [("100", "1.1.1")]),
            ("22.04", [("100", "1.1.1")]),
            ("red-hat", [("100", "2.1.1")]),
            ("[sshd_config]", [("100", "1.1.1")]),
            ("AND", [("100", "2.1.1")]),
            ('"unbalanced', []),
            ("NEAR(", []),
        ],
    )
    def test_punctuation_and_keywords_are_search_words(self, db, query, expected):
        _save(db, _benchmark("100", SSH, SELINUX, FIREWALL))

        assert _refs(db.search_recommendations(query)) == expected

    def test_a_query_with_no_words_finds_nothing(self, db):
        _save(db, _benchmark("100", SSH))

        assert db.search_recommendations("  --  ") == []

    def test_a_dotted_number_matches_its_numbers_side_by_side_not_apart(self, db):
        apart = _recommendation(
            "5.1.1", "Ensure logging is configured", description="Keep 22 days of logs, 04 copies."
        )
        _save(db, _benchmark("100", SSH, apart))

        assert _refs(db.search_recommendations("22.04")) == [("100", "1.1.1")]

    def test_profiles_are_a_filter_not_search_words(self, db):
        _save(db, _benchmark("100", SSH, SELINUX))

        assert db.search_recommendations("server") == []


class TestFilters:
    def test_benchmark_id_narrows_the_results(self, db):
        _save(db, _benchmark("100", SSH))
        _save(db, _benchmark("200", SSH))

        assert _refs(db.search_recommendations("maxauthtries", benchmark_id="200")) == [
            ("200", "1.1.1")
        ]

    def test_profile_narrows_the_results(self, db):
        _save(db, _benchmark("100", SSH, SELINUX))

        assert _refs(db.search_recommendations("run", profile="Level 2")) == [("100", "2.1.1")]
        assert _refs(db.search_recommendations("run", profile="Level 1 - Server")) == [
            ("100", "1.1.1")
        ]

    def test_a_profile_phrase_never_spans_two_profile_names(self, db):
        both = _recommendation(
            "6.1.1",
            "Ensure the audit service is running",
            profiles=("Level 1 - Server", "Level 2 - Workstation"),
            audit="Run: systemctl is-active auditd",
        )
        _save(db, _benchmark("100", both))

        assert db.search_recommendations("run", profile="Server Level 2") == []
        assert _refs(db.search_recommendations("run", profile="Level 2 - Workstation")) == [
            ("100", "6.1.1")
        ]
        assert _refs(db.search_recommendations("run", profile="Level 1")) == [("100", "6.1.1")]

    def test_a_profile_with_no_words_does_not_filter(self, db):
        _save(db, _benchmark("100", SSH, SELINUX))

        assert len(db.search_recommendations("run", profile=" - ")) == 2

    def test_limit_caps_the_results(self, db):
        _save(db, _benchmark("100", SSH, SELINUX, FIREWALL))

        assert len(db.search_recommendations("run", limit=2)) == 2
        assert len(db.search_recommendations("run")) == 3


# --------------------------------------------------------------------------------------------
# cis-bench find: the index from the command line
# --------------------------------------------------------------------------------------------

_ROW_RE = r"^\S\s*(\d+)\s*\S\s*([\d.]+)\s*\S"


@pytest.fixture
def downloaded(data_dir):
    """Downloaded benchmarks in this test's catalog.db: ``downloaded(benchmark, ...)``."""

    def save(*benchmarks):
        with closing(CatalogDatabase(data_dir / "catalog.db")) as database:
            database.initialize_schema()
            for benchmark in benchmarks:
                _save(database, benchmark)

    return save


@pytest.fixture
def no_network(monkeypatch):
    """Any HTTP request fails the test: find reads only this machine."""
    import requests

    def refuse(*args, **kwargs):
        raise AssertionError("an HTTP request was sent")

    monkeypatch.setattr(requests.Session, "send", refuse)


def _find(*args):
    from click.testing import CliRunner

    from cis_bench.cli.app import cli

    return CliRunner().invoke(cli, ["find", *args])


def _found_json(*args):
    import json

    result = _find(*args, "--output-format", "json")
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def _table_rows(output):
    """The (benchmark, ref) of each table row's first line."""
    import re

    return [match.groups() for match in re.finditer(_ROW_RE, output, re.MULTILINE)]


class TestFind:
    def test_find_lists_matching_recommendations_with_benchmark_and_ref(self, downloaded):
        downloaded(
            _benchmark("100", SSH, SELINUX), _benchmark("200", SSH), _benchmark("300", FIREWALL)
        )

        result = _find("ssh")

        assert result.exit_code == 0, result.output
        assert _table_rows(result.output) == [("100", "1.1.1"), ("200", "1.1.1")]
        assert "Ensure SSH" in result.output
        assert "Showing 2 of 2 results" in result.output

    def test_json_carries_the_same_hits_with_their_titles_and_matched_fields(self, downloaded):
        downloaded(_benchmark("100", SSH, SELINUX), _benchmark("300", FIREWALL))

        assert _found_json("libselinux") == [
            {
                "benchmark_id": "100",
                "ref": "2.1.1",
                "title": "Ensure SELinux is installed",
                "matched_fields": ["audit", "remediation"],
            }
        ]

    def test_the_table_names_the_fields_a_word_was_found_in(self, downloaded):
        downloaded(_benchmark("100", SELINUX))

        result = _find("libselinux")

        assert result.exit_code == 0, result.output
        assert "audit, remediation" in result.output

    def test_benchmark_narrows_the_results(self, downloaded):
        downloaded(_benchmark("100", SSH), _benchmark("200", SSH))

        assert [r["benchmark_id"] for r in _found_json("ssh", "--benchmark", "200")] == ["200"]

    def test_profile_narrows_the_results(self, downloaded):
        downloaded(_benchmark("100", SSH, SELINUX))

        assert [r["ref"] for r in _found_json("run", "--profile", "Level 2")] == ["2.1.1"]

    def test_limit_caps_the_results_and_says_more_were_found(self, downloaded):
        downloaded(_benchmark("100", SSH, SELINUX, FIREWALL))

        result = _find("run", "--limit", "2")

        assert result.exit_code == 0, result.output
        assert len(_table_rows(result.output)) == 2
        assert "Showing 2 of 3 results; use --limit to see more" in result.output
        assert len(_found_json("run", "--limit", "2")) == 2

    def test_the_search_limit_setting_is_the_default_limit(self, downloaded, monkeypatch):
        downloaded(_benchmark("100", SSH, SELINUX, FIREWALL))
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "1")

        assert len(_found_json("run")) == 1

    def test_no_hits_says_so_and_exits_zero(self, downloaded):
        downloaded(_benchmark("100", SSH))

        result = _find("kerberos")

        assert result.exit_code == 0, result.output
        assert "No downloaded recommendation matches kerberos" in result.output
        assert "--benchmark" not in result.output
        assert _found_json("kerberos") == []

    def test_no_hits_under_a_filter_suggests_removing_it(self, downloaded):
        downloaded(_benchmark("100", SSH))

        result = _find("ssh", "--profile", "Level 2")

        assert result.exit_code == 0, result.output
        assert "No downloaded recommendation matches ssh" in result.output
        assert "without --benchmark or --profile" in result.output

    def test_a_query_with_no_words_finds_nothing(self, downloaded):
        downloaded(_benchmark("100", SSH))

        result = _find("...")

        assert result.exit_code == 0, result.output
        assert "No downloaded recommendation matches ..." in result.output

    def test_nothing_downloaded_points_at_download_and_creates_no_catalog(self, data_dir):
        result = _find("ssh")
        structured = _find("ssh", "--output-format", "json")

        assert result.exit_code == 0, result.output
        assert "No benchmarks are downloaded" in result.output
        assert "cis-bench download <ID>" in result.output
        assert structured.exit_code == 0, structured.output
        assert structured.stdout.strip() == "[]"
        assert "cis-bench download <ID>" in structured.stderr
        assert not (data_dir / "catalog.db").exists()

    def test_a_catalog_with_no_downloads_points_at_download(self, downloaded):
        downloaded()

        result = _find("ssh")

        assert result.exit_code == 0, result.output
        assert "No benchmarks are downloaded" in result.output

    def test_a_benchmark_that_is_not_downloaded_is_named(self, downloaded):
        downloaded(_benchmark("100", SSH))

        result = _find("ssh", "--benchmark", "999")

        assert result.exit_code == 0, result.output
        assert "Benchmark 999 is not downloaded" in result.output
        assert "cis-bench download 999" in result.output

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("[sshd_config]", ["1.1.1"]),
            ("[/opt]", []),
            ("22.04", ["1.1.1"]),
            ("red-hat", ["2.1.1"]),
            ("AND", ["2.1.1"]),
            ("NEAR(", []),
            ('"unbalanced', []),
        ],
        ids=["brackets", "a closing markup tag", "dots", "hyphens", "a keyword", "NEAR", "quote"],
    )
    def test_punctuation_and_keywords_are_search_words_in_the_table_and_in_json(
        self, downloaded, query, expected
    ):
        downloaded(_benchmark("100", SSH, SELINUX, FIREWALL))

        result = _find(query)

        assert result.exit_code == 0, result.output
        assert [ref for _, ref in _table_rows(result.output)] == expected
        if not expected:
            assert f"No downloaded recommendation matches {query}" in result.output
        assert [r["ref"] for r in _found_json(query)] == expected

    def test_text_from_the_benchmark_is_printed_as_written(self, downloaded):
        marked = _recommendation(
            "8.1.1",
            "Ensure [bold]sshd[/bold] runs as [sshd]",
            audit="Run: ps -o user= -C sshd",
        )
        downloaded(_benchmark("100", marked))

        result = _find("sshd")

        assert result.exit_code == 0, result.output
        assert "[bold]sshd[/bold]" in result.output

    def test_find_works_offline_without_contacting_workbench(self, downloaded, no_network):
        from click.testing import CliRunner

        from cis_bench.cli.app import cli

        downloaded(_benchmark("100", SSH))

        result = CliRunner().invoke(cli, ["--offline", "find", "ssh"])

        assert result.exit_code == 0, result.output
        assert _table_rows(result.output) == [("100", "1.1.1")]

    def test_a_catalog_that_cannot_be_read_is_an_error_not_a_traceback(self, data_dir):
        (data_dir / "catalog.db").write_bytes(b"this is not a database" * 100)

        result = _find("ssh")

        assert result.exit_code == 1
        assert "cannot be read" in result.output
        assert "Traceback" not in result.output
        assert result.exception is None or isinstance(result.exception, SystemExit)
