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
