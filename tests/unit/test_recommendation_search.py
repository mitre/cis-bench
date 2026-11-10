"""The recommendation index: every downloaded benchmark's recommendations, searchable.

The index is written where a benchmark is saved and cleared where it is removed, so it holds
exactly the downloaded benchmarks. A query is user text: punctuation and FTS5 keywords are
search words, never query syntax.
"""

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
