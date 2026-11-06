"""Unit tests for catalog search."""

from unittest.mock import patch

import pytest

from cis_bench.catalog.database import CatalogDatabase
from cis_bench.catalog.search import CatalogSearch


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary database with sample data."""
    db = CatalogDatabase(tmp_path / "test.db")
    db.initialize_schema()

    # Insert sample benchmarks
    benchmarks = [
        {
            "benchmark_id": "1",
            "title": "CIS Ubuntu Linux 20.04 LTS Benchmark",
            "version": "v2.0.1",
            "url": "https://workbench.cisecurity.org/benchmarks/1",
            "status": "Published",
            "platform": "Operating System",
            "community": "CIS Ubuntu Benchmarks",
            "description": "Ubuntu 20.04 security guidance",
            "is_latest": True,
            "published_date": "2024-08-01",
        },
        {
            "benchmark_id": "2",
            "title": "CIS RHEL 9 Benchmark",
            "version": "v2.0.0",
            "url": "https://workbench.cisecurity.org/benchmarks/2",
            "status": "Published",
            "platform": "Operating System",
            "community": "CIS RHEL Benchmarks",
            "is_latest": True,
            "published_date": "2024-07-01",
        },
        {
            "benchmark_id": "3",
            "title": "CIS AWS Foundations Benchmark",
            "version": "v3.0.0",
            "url": "https://workbench.cisecurity.org/benchmarks/3",
            "status": "Published",
            "platform": "Cloud",
            "community": "CIS AWS Benchmarks",
            "is_latest": True,
        },
        {
            "benchmark_id": "4",
            "title": "CIS Ubuntu Linux 20.04 LTS Benchmark",
            "version": "v1.0.0",
            "url": "https://workbench.cisecurity.org/benchmarks/4",
            "status": "Archived",
            "platform": "Operating System",
            "is_latest": False,
        },
    ]

    for bench in benchmarks:
        db.insert_benchmark(bench)

    return db


@pytest.fixture
def search(temp_db):
    """Create CatalogSearch instance."""
    return CatalogSearch(temp_db)


class TestBasicSearch:
    """Test basic search operations."""

    def test_search_creation(self, temp_db):
        """Test CatalogSearch can be created."""
        search = CatalogSearch(temp_db)
        assert search.db == temp_db

    def test_search_forwards_status_unchanged_to_database(self, search):
        """Normalizing the status filter is the database's job; the search layer passes it through."""
        with patch.object(search.db, "search", return_value=[]) as db_search:
            search.search("ubuntu", status=" ALL ", limit=None)

        assert db_search.call_args.kwargs["status"] == " ALL "

    def test_search_by_name(self, search):
        """Test searching by benchmark name."""
        results = search.search("ubuntu", limit=None)

        assert len(results) > 0
        assert all("Ubuntu" in r["title"] for r in results)

    def test_search_empty_query_returns_all(self, search):
        """Test empty query returns all benchmarks."""
        results = search.search("", limit=None)

        assert len(results) > 0

    def test_search_no_matches(self, search):
        """Test search with no matches returns empty list."""
        results = search.search("nonexistent", limit=None)

        assert results == []

    def test_no_limit_returns_every_match_whatever_the_settings(self, search, monkeypatch):
        # The library takes its limit from the caller; CIS_BENCH_SEARCH_LIMIT is the CLI's.
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "1")
        assert len(search.search("", limit=None)) == 3


class TestFiltering:
    """Test filtering options."""

    def test_filter_by_platform(self, search):
        """Test filtering by platform."""
        results = search.search("", platform="Cloud", limit=None)

        assert len(results) == 1
        assert results[0]["platform"] == "Cloud"

    def test_filter_by_status(self, search):
        """Test filtering by status."""
        # Default is Published
        published = search.search("", limit=None)
        assert all(r["status"] == "Published" for r in published)

        # Archived
        archived = search.search("ubuntu", status="Archived", limit=None)
        assert len(archived) == 1
        assert archived[0]["status"] == "Archived"

    def test_filter_latest_only(self, search):
        """Test latest_only filter."""
        # Latest only
        latest = search.search("ubuntu", latest_only=True, limit=None)

        # Latest should only include benchmarks with is_latest=True
        assert all(r["is_latest"] for r in latest)
        # Should have at least 1 result
        assert len(latest) >= 1

    def test_combined_filters(self, search):
        """Test combining multiple filters."""
        results = search.search(
            "linux", platform="Operating System", status="Published", latest_only=True, limit=None
        )

        assert all(r["platform"] == "Operating System" for r in results)
        assert all(r["status"] == "Published" for r in results)
        assert all(r["is_latest"] for r in results)


class TestHelperMethods:
    """Test helper search methods."""

    def test_find_by_id(self, search):
        """Test finding benchmark by ID."""
        result = search.find_by_id("1")

        assert result is not None
        assert result["benchmark_id"] == "1"

    def test_find_by_id_not_found(self, search):
        """Test finding non-existent ID returns None."""
        result = search.find_by_id("99999")

        assert result is None

    def test_find_by_name(self, search):
        """Test finding by name."""
        results = search.find_by_name("ubuntu")

        assert len(results) > 0

    def test_get_platforms(self, search):
        """Test getting platform list."""
        platforms = search.get_platforms()

        assert len(platforms) > 0
        assert all("name" in p and "count" in p for p in platforms)

    def test_get_communities(self, search):
        """Test getting community list."""
        communities = search.get_communities()

        assert len(communities) > 0


class TestFormatting:
    """Test result formatting for display."""

    def test_format_result_for_display(self, search):
        """Test formatting single result."""
        result = search.find_by_id("1")

        formatted = search.format_result_for_display(result)

        # Should include ID and title
        assert "[1]" in formatted
        assert result["title"] in formatted

    def test_format_includes_metadata(self, search):
        """Test formatted output includes metadata."""
        result = search.find_by_id("1")

        formatted = search.format_result_for_display(result)

        # Should include platform and published date
        assert "Platform:" in formatted
        assert "Published:" in formatted

    def test_format_results_table(self, search):
        """Test formatting multiple results."""
        results = search.search("benchmark", limit=None)

        formatted = search.format_results_table(results)

        # Should have multiple entries
        assert formatted.count("[") >= len(results)  # Each has [ID]

    def test_format_empty_results(self, search):
        """Test formatting empty results."""
        formatted = search.format_results_table([])

        assert formatted == "No benchmarks found."

    def test_format_with_description(self, search):
        """Test formatting with description snippets."""
        results = search.search("ubuntu", limit=None)

        formatted = search.format_results_table(results, show_description=True)

        # Should include description text
        assert len(formatted) > 0


@pytest.fixture
def releases(tmp_path):
    """One benchmark in several releases, and benchmarks whose titles carry numbers."""
    db = CatalogDatabase(tmp_path / "releases.db")
    db.initialize_schema()
    rows = [
        ("120", "CIS Kubernetes Benchmark", "v1.2.0"),
        ("121", "CIS Kubernetes Benchmark", "v1.2.1"),
        ("200", "CIS Kubernetes Benchmark", "v2.0.0"),
        ("201", "CIS Kubernetes Benchmark", "v2.0.1"),
        ("210", "CIS Kubernetes Benchmark", "v2.1.0"),
        ("2100", "CIS Kubernetes Benchmark", "v2.10.0"),
        ("710", "CIS Kubernetes Benchmark", "v7.1.0 (vNext)"),
        ("800", "CIS Kubernetes Benchmark", "vNext"),
        ("900", "CIS Kubernetes Benchmark", "v1.1.0 NEXT"),
        ("8", "CIS AlmaLinux OS 8 Benchmark", "v4.0.0"),
        ("9", "CIS AlmaLinux OS 9 Benchmark", "v8.0.0"),
        ("2004", "CIS Ubuntu Linux 20.04 LTS Benchmark", "v3.0.0"),
        ("18", "CIS SOPHOS XG Firewall v18 Benchmark", "v1.0.0"),
    ]
    for benchmark_id, title, version in rows:
        db.insert_benchmark(
            {
                "benchmark_id": benchmark_id,
                "title": title,
                "version": version,
                "url": f"https://workbench.cisecurity.org/benchmarks/{benchmark_id}",
                "status": "Published",
            }
        )
    yield CatalogSearch(db)
    db.engine.dispose()


def _ids(results):
    return sorted(str(row["benchmark_id"]) for row in results)


class TestSearchingByVersion:
    """A version in the query picks the release: matched from the start, piece by piece."""

    @pytest.mark.parametrize(
        "query",
        [
            "kubernetes v2.1.0",
            "kubernetes 2.1.0",
            "kubernetes V2.1.0",
            "kubernetes (v2.1.0)",
            "CIS Kubernetes Benchmark v2.1.0",
            "2.1.0 kubernetes",
        ],
    )
    def test_a_search_with_the_version_finds_that_release(self, releases, query):
        assert _ids(releases.search(query, limit=None)) == ["210"]

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("kubernetes 2.1", ["210"]),
            ("kubernetes 2.0", ["200", "201"]),
            ("kubernetes 1.2", ["120", "121"]),
            ("kubernetes v2", ["200", "201", "210", "2100"]),
        ],
    )
    def test_a_version_prefix_finds_the_releases_under_it(self, releases, query, expected):
        assert _ids(releases.search(query, limit=None)) == sorted(expected)

    def test_a_version_followed_by_a_label_is_found_by_its_number(self, releases):
        assert _ids(releases.search("kubernetes 7.1.0", limit=None)) == ["710"]

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("kubernetes vnext", ["710", "800"]),
            ("kubernetes vNext", ["710", "800"]),
            ("CIS Kubernetes Benchmark v7.1.0 (vNext)", ["710"]),
            ("kubernetes next", ["900"]),
            ("kubernetes 1.1.0 next", ["900"]),
            ("kubernetes vne", []),
        ],
    )
    def test_a_word_of_a_version_label_is_matched_whole(self, releases, query, expected):
        assert _ids(releases.search(query, limit=None)) == expected

    def test_a_version_alone_finds_the_benchmarks_at_that_version(self, releases):
        assert _ids(releases.search("8.0.0", limit=None)) == ["9"]

    def test_the_count_agrees_with_a_version_search(self, releases):
        assert releases.count("kubernetes 2.0") == 2

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("almalinux 8", ["8"]),
            ("almalinux 4", []),
            ("kubernetes 2", []),
        ],
    )
    def test_a_plain_number_matches_titles_and_never_a_version(self, releases, query, expected):
        assert _ids(releases.search(query, limit=None)) == expected

    @pytest.mark.parametrize(
        ("query", "expected"),
        [("ubuntu 20.04", ["2004"]), ("sophos v18", ["18"])],
    )
    def test_a_version_shaped_number_in_a_title_is_still_found(self, releases, query, expected):
        assert _ids(releases.search(query, limit=None)) == expected


@pytest.fixture
def families(tmp_path):
    """Three benchmarks with their releases; the newest release of each is marked latest."""
    db = CatalogDatabase(tmp_path / "families.db")
    db.initialize_schema()
    rows = [
        ("200", "CIS Kubernetes Benchmark", "v2.0.0"),
        ("201", "CIS Kubernetes Benchmark", "v2.0.1"),
        ("210", "CIS Kubernetes Benchmark", "v2.1.0"),
        ("300", "CIS Google Kubernetes Engine (GKE) Benchmark", "v2.0.0"),
        ("401", "CIS Ubuntu Linux 22.04 LTS Benchmark", "v1.0.0"),
        ("402", "CIS Ubuntu Linux 22.04 LTS Benchmark", "v2.0.0"),
    ]
    for benchmark_id, title, version in rows:
        db.insert_benchmark(
            {
                "benchmark_id": benchmark_id,
                "title": title,
                "version": version,
                "url": f"https://workbench.cisecurity.org/benchmarks/{benchmark_id}",
                "status": "Published",
            }
        )
    db.mark_latest_versions()
    yield CatalogSearch(db)
    db.engine.dispose()


class TestLatestOrNamedReleases:
    """Latest releases only, except a release the query names by its version."""

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("kubernetes", ["210", "300"]),
            ("kubernetes 2.1.0", ["210"]),
            ("kubernetes 2.0.1", ["201"]),
            ("kubernetes 2.0.0", ["200", "300"]),
            ("kubernetes 2.0", ["200", "201", "300"]),
            ("ubuntu 22.04", ["402"]),
            ("ubuntu 22.04 v1.0.0", ["401"]),
            ("ubuntu 9.9.9", []),
        ],
    )
    def test_a_named_release_is_found_beside_the_latest_ones(self, families, query, expected):
        found = families.search(query, latest_only=True, named_releases=True, limit=None)

        assert _ids(found) == sorted(expected)
        assert families.count(query, latest_only=True, named_releases=True) == len(expected)

    def test_latest_only_alone_still_means_latest_releases_only(self, families):
        assert _ids(families.search("kubernetes 2.0.0", latest_only=True, limit=None)) == ["300"]
        assert families.count("kubernetes 2.0.0", latest_only=True) == 1

    def test_without_latest_only_every_release_is_found_either_way(self, families):
        found = families.search("kubernetes", named_releases=True, limit=None)

        assert _ids(found) == ["200", "201", "210", "300"]
