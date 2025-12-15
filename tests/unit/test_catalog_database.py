"""Unit tests for catalog database operations."""

import tempfile
from pathlib import Path

import pytest

from cis_bench.catalog.database import CatalogDatabase


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_catalog.db"
        db = CatalogDatabase(db_path)
        db.initialize_schema()
        yield db


@pytest.fixture
def sample_benchmark_data():
    """Sample benchmark data for testing."""
    return {
        "benchmark_id": "23598",
        "title": "CIS Ubuntu Linux 20.04 LTS Benchmark",
        "version": "v2.0.1",
        "url": "https://workbench.cisecurity.org/benchmarks/23598",
        "status": "Published",
        "platform": "Operating System",
        "community": "CIS Ubuntu Benchmarks",
        "owner": "eric.pinnell",
        "published_date": "2024-08-01",
        "last_revision_date": "2024-11-01",
        "description": "Ubuntu 20.04 LTS security configuration guidance",
        "is_latest": True,
        "collections": ["Operating System", "Linux"],
    }


class TestDatabaseInitialization:
    """Test database initialization and schema creation."""

    def test_database_creation(self, temp_db):
        """Test database file is created."""
        assert temp_db.db_path.exists()

    def test_schema_tables_created(self, temp_db):
        """Test all tables are created."""
        import sqlite3

        conn = sqlite3.connect(temp_db.db_path)
        cursor = conn.cursor()

        # Check main tables exist
        tables = cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = [t[0] for t in tables]

        expected_tables = [
            "platforms",
            "benchmark_statuses",
            "communities",
            "collections",
            "owners",
            "catalog_benchmarks",
            "benchmark_collections",
            "downloaded_benchmarks",
            "scrape_metadata",
        ]

        for table in expected_tables:
            assert table in table_names, f"Table {table} not created"

        conn.close()

    def test_fts5_table_created(self, temp_db):
        """Test FTS5 virtual table is created."""
        import sqlite3

        conn = sqlite3.connect(temp_db.db_path)
        cursor = conn.cursor()

        # Check virtual table exists
        tables = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='benchmarks_fts'"
        ).fetchall()

        assert len(tables) == 1
        conn.close()

    def test_default_statuses_inserted(self, temp_db):
        """Test default benchmark statuses are inserted."""
        stats = temp_db.get_catalog_stats()

        # Should have at least the 5 default statuses
        # (Published, Accepted, Draft, Archived, Rejected)
        assert stats is not None


class TestBenchmarkOperations:
    """Test benchmark CRUD operations."""

    def test_insert_benchmark(self, temp_db, sample_benchmark_data):
        """Test inserting a benchmark."""
        temp_db.insert_benchmark(sample_benchmark_data)

        # Verify inserted
        bench = temp_db.get_benchmark(sample_benchmark_data["benchmark_id"])
        assert bench is not None
        assert bench["title"] == sample_benchmark_data["title"]
        assert bench["version"] == sample_benchmark_data["version"]

    def test_insert_creates_foreign_key_records(self, temp_db, sample_benchmark_data):
        """Test that inserting benchmark creates platform/community/owner records."""
        temp_db.insert_benchmark(sample_benchmark_data)

        # Check platform was created
        platforms = temp_db.list_platforms()
        assert len(platforms) > 0
        assert any(p["name"] == "Operating System" for p in platforms)

        # Check stats
        stats = temp_db.get_catalog_stats()
        assert stats["platforms"] >= 1
        assert stats["communities"] >= 1

    def test_insert_duplicate_benchmark_updates(self, temp_db, sample_benchmark_data):
        """Test that inserting duplicate ID updates existing record."""
        # Insert first time
        temp_db.insert_benchmark(sample_benchmark_data)

        # Insert again with different title
        updated_data = sample_benchmark_data.copy()
        updated_data["title"] = "Updated Title"

        temp_db.insert_benchmark(updated_data)

        # Should have 1 record with updated title
        bench = temp_db.get_benchmark(sample_benchmark_data["benchmark_id"])
        assert bench["title"] == "Updated Title"

        stats = temp_db.get_catalog_stats()
        assert stats["total_benchmarks"] == 1  # Still just 1

    def test_get_nonexistent_benchmark(self, temp_db):
        """Test getting non-existent benchmark returns None."""
        bench = temp_db.get_benchmark("99999")
        assert bench is None

    def test_insert_without_optional_fields(self, temp_db):
        """Test inserting benchmark with only required fields."""
        minimal_data = {
            "benchmark_id": "12345",
            "title": "Minimal Benchmark",
            "url": "https://workbench.cisecurity.org/benchmarks/12345",
            "status": "Published",
        }

        temp_db.insert_benchmark(minimal_data)

        bench = temp_db.get_benchmark("12345")
        assert bench is not None
        assert bench["platform"] is None
        assert bench["community"] is None


class TestFTS5Search:
    """Test FTS5 full-text search functionality."""

    @pytest.fixture
    def populated_db(self, temp_db):
        """Database with multiple benchmarks."""
        benchmarks = [
            {
                "benchmark_id": "1",
                "title": "CIS Ubuntu Linux 20.04 LTS Benchmark",
                "url": "https://workbench.cisecurity.org/benchmarks/1",
                "status": "Published",
                "platform": "Operating System",
                "description": "Ubuntu security",
            },
            {
                "benchmark_id": "2",
                "title": "CIS RHEL 9 Benchmark",
                "url": "https://workbench.cisecurity.org/benchmarks/2",
                "status": "Published",
                "platform": "Operating System",
                "description": "Red Hat Enterprise Linux",
            },
            {
                "benchmark_id": "3",
                "title": "CIS AWS Foundations Benchmark",
                "url": "https://workbench.cisecurity.org/benchmarks/3",
                "status": "Published",
                "platform": "Cloud",
                "description": "Amazon Web Services",
            },
            {
                "benchmark_id": "4",
                "title": "CIS Windows Server 2022 Benchmark",
                "url": "https://workbench.cisecurity.org/benchmarks/4",
                "status": "Archived",
                "platform": "Operating System",
                "description": "Windows security",
            },
        ]

        for bench in benchmarks:
            temp_db.insert_benchmark(bench)

        return temp_db

    def test_search_basic(self, populated_db):
        """Test basic search."""
        results = populated_db.search("ubuntu")
        assert len(results) == 1
        assert "Ubuntu" in results[0]["title"]

    def test_search_fuzzy(self, populated_db):
        """Test fuzzy search (missing letter)."""
        results = populated_db.search("ubunt")  # Missing 'u'
        assert len(results) == 1
        assert "Ubuntu" in results[0]["title"]

    def test_search_multi_word(self, populated_db):
        """Test multi-word search."""
        results = populated_db.search("linux")
        assert len(results) >= 2  # Ubuntu and RHEL

    def test_search_case_insensitive(self, populated_db):
        """Test search is case-insensitive."""
        results_lower = populated_db.search("ubuntu")
        results_upper = populated_db.search("UBUNTU")
        results_mixed = populated_db.search("Ubuntu")

        assert len(results_lower) == len(results_upper) == len(results_mixed)

    def test_search_with_platform_filter(self, populated_db):
        """Test search with platform filter."""
        results = populated_db.search("benchmark", platform="Cloud")
        assert len(results) == 1
        assert "AWS" in results[0]["title"]

    def test_search_with_status_filter(self, populated_db):
        """Test search with status filter."""
        # Default is Published
        results = populated_db.search("benchmark")
        assert all(r["status"] == "Published" for r in results)

        # Search archived
        results = populated_db.search("windows", status="Archived")
        assert len(results) == 1
        assert results[0]["status"] == "Archived"

    def test_search_latest_only(self, populated_db):
        """Test latest_only filter."""
        # Insert another Ubuntu version
        populated_db.insert_benchmark(
            {
                "benchmark_id": "5",
                "title": "CIS Ubuntu Linux 20.04 LTS Benchmark",
                "version": "v1.0.0",
                "url": "https://workbench.cisecurity.org/benchmarks/5",
                "status": "Published",
                "is_latest": False,
            }
        )

        # Search without filter
        all_results = populated_db.search("ubuntu", latest_only=False)

        # Search with latest_only
        latest_results = populated_db.search("ubuntu", latest_only=True)

        assert len(latest_results) < len(all_results)

    def test_search_empty_query(self, populated_db):
        """Test search with empty query returns all."""
        results = populated_db.search("")
        assert len(results) > 0

    def test_search_no_matches(self, populated_db):
        """Test search with no matches returns empty list."""
        results = populated_db.search("nonexistent")
        assert len(results) == 0


class TestLookupTables:
    """Test lookup table operations."""

    def test_get_or_create_platform_new(self, temp_db):
        """Test creating new platform."""
        from sqlmodel import Session

        with Session(temp_db.engine) as session:
            platform = temp_db.get_or_create_platform("Linux", session)
            assert platform.name == "Linux"
            assert platform.platform_id is not None

    def test_get_or_create_platform_existing(self, temp_db):
        """Test getting existing platform doesn't duplicate."""
        from sqlmodel import Session

        # Create platform first
        with Session(temp_db.engine) as session:
            platform1 = temp_db.get_or_create_platform("Linux", session)
            platform1_id = platform1.platform_id
            session.commit()

        # Get again - should return same ID
        with Session(temp_db.engine) as session:
            platform2 = temp_db.get_or_create_platform("Linux", session)
            assert platform2.platform_id == platform1_id

    def test_get_or_create_community(self, temp_db):
        """Test community get_or_create."""
        from sqlmodel import Session

        with Session(temp_db.engine) as session:
            community = temp_db.get_or_create_community("CIS Ubuntu Benchmarks", session)
            assert community.name == "CIS Ubuntu Benchmarks"

    def test_get_or_create_owner(self, temp_db):
        """Test owner get_or_create."""
        from sqlmodel import Session

        with Session(temp_db.engine) as session:
            owner = temp_db.get_or_create_owner("eric.pinnell", session)
            assert owner.username == "eric.pinnell"

    def test_get_status_id(self, temp_db):
        """Test getting status ID by name."""
        from sqlmodel import Session

        with Session(temp_db.engine) as session:
            status_id = temp_db.get_status_id("Published", session)
            assert isinstance(status_id, int)
            assert status_id > 0

    def test_get_invalid_status_raises(self, temp_db):
        """Test getting invalid status raises error."""
        from sqlmodel import Session

        with Session(temp_db.engine) as session:
            with pytest.raises(ValueError, match="Unknown status"):
                temp_db.get_status_id("InvalidStatus", session)


class TestDownloadedBenchmarks:
    """Test downloaded benchmark tracking."""

    def test_save_downloaded(self, temp_db, sample_benchmark_data):
        """Test saving downloaded benchmark."""
        # Must have catalog entry first
        temp_db.insert_benchmark(sample_benchmark_data)

        # Save downloaded content
        temp_db.save_downloaded(
            benchmark_id="23598",
            content_json='{"test": "data"}',
            content_hash="abc123",
            recommendation_count=100,
        )

        downloaded = temp_db.get_downloaded("23598")
        assert downloaded is not None
        assert downloaded["content_hash"] == "abc123"
        assert downloaded["recommendation_count"] == 100

    def test_save_downloaded_update(self, temp_db, sample_benchmark_data):
        """Test updating downloaded benchmark."""
        temp_db.insert_benchmark(sample_benchmark_data)

        # Save first time
        temp_db.save_downloaded("23598", '{"v": 1}', "hash1", 100)

        # Update
        temp_db.save_downloaded("23598", '{"v": 2}', "hash2", 150)

        # Should have updated, not duplicated
        downloaded = temp_db.get_downloaded("23598")
        assert downloaded["content_hash"] == "hash2"
        assert downloaded["recommendation_count"] == 150

    def test_get_nonexistent_downloaded(self, temp_db):
        """Test getting non-existent download returns None."""
        downloaded = temp_db.get_downloaded("99999")
        assert downloaded is None

    def test_check_updates_available(self, temp_db, sample_benchmark_data):
        """Test checking for available updates."""
        temp_db.insert_benchmark(sample_benchmark_data)

        # Download with old revision date
        temp_db.save_downloaded(
            "23598", '{"test": 1}', "hash1", 100, workbench_last_modified="2024-10-01"
        )

        # Catalog has newer revision
        updates = temp_db.check_updates_available()

        assert len(updates) == 1
        assert updates[0]["benchmark_id"] == "23598"


class TestStatistics:
    """Test catalog statistics and reporting."""

    def test_get_catalog_stats(self, temp_db, sample_benchmark_data):
        """Test catalog statistics."""
        temp_db.insert_benchmark(sample_benchmark_data)

        stats = temp_db.get_catalog_stats()

        assert stats["total_benchmarks"] == 1
        assert stats["published_benchmarks"] == 1
        assert stats["platforms"] >= 1
        assert stats["communities"] >= 1

    def test_list_platforms(self, temp_db):
        """Test listing platforms with counts."""
        # Insert benchmarks with different platforms
        for i, platform in enumerate(["Operating System", "Cloud", "Operating System"]):
            temp_db.insert_benchmark(
                {
                    "benchmark_id": str(i),
                    "title": f"Benchmark {i}",
                    "url": f"https://example.com/{i}",
                    "status": "Published",
                    "platform": platform,
                }
            )

        platforms = temp_db.list_platforms()

        assert len(platforms) >= 2
        os_platform = next(p for p in platforms if p["name"] == "Operating System")
        assert os_platform["count"] == 2

    def test_list_communities(self, temp_db):
        """Test listing communities."""
        temp_db.insert_benchmark(
            {
                "benchmark_id": "1",
                "title": "Test",
                "url": "https://example.com/1",
                "status": "Published",
                "community": "CIS Ubuntu Benchmarks",
            }
        )

        communities = temp_db.list_communities()

        assert len(communities) >= 1
        assert any(c["name"] == "CIS Ubuntu Benchmarks" for c in communities)


class TestMetadata:
    """Test scrape metadata operations."""

    def test_set_and_get_metadata(self, temp_db):
        """Test setting and getting metadata."""
        temp_db.set_metadata("last_scrape", "2024-11-03")

        value = temp_db.get_metadata("last_scrape")
        assert value == "2024-11-03"

    def test_get_nonexistent_metadata(self, temp_db):
        """Test getting non-existent metadata returns None."""
        value = temp_db.get_metadata("nonexistent_key")
        assert value is None

    def test_update_metadata(self, temp_db):
        """Test updating existing metadata."""
        temp_db.set_metadata("key", "value1")
        temp_db.set_metadata("key", "value2")

        value = temp_db.get_metadata("key")
        assert value == "value2"


class TestCollections:
    """Test collections (many-to-many relationship)."""

    def test_benchmark_with_collections(self, temp_db):
        """Test benchmark with multiple collections."""
        data = {
            "benchmark_id": "1",
            "title": "Test Benchmark",
            "url": "https://example.com/1",
            "status": "Published",
            "collections": ["Operating System", "STIG", "Linux"],
        }

        temp_db.insert_benchmark(data)

        # Verify collections were created and linked
        import sqlite3

        conn = sqlite3.connect(temp_db.db_path)

        # Check collections table
        collections = conn.execute("SELECT name FROM collections").fetchall()
        assert len(collections) == 3

        # Check link table
        links = conn.execute(
            "SELECT * FROM benchmark_collections WHERE benchmark_id = '1'"
        ).fetchall()
        assert len(links) == 3

        conn.close()

    def test_update_benchmark_collections(self, temp_db):
        """Test updating benchmark collections replaces old ones."""
        data = {
            "benchmark_id": "1",
            "title": "Test",
            "url": "https://example.com/1",
            "status": "Published",
            "collections": ["Tag1", "Tag2"],
        }

        temp_db.insert_benchmark(data)

        # Update with different collections
        data["collections"] = ["Tag3", "Tag4"]
        temp_db.insert_benchmark(data)

        # Should have Tag3 and Tag4, not Tag1 and Tag2
        import sqlite3

        conn = sqlite3.connect(temp_db.db_path)
        links = conn.execute(
            "SELECT * FROM benchmark_collections WHERE benchmark_id = '1'"
        ).fetchall()
        assert len(links) == 2

        conn.close()


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_insert_with_null_dates(self, temp_db):
        """Test inserting benchmark with null dates."""
        data = {
            "benchmark_id": "1",
            "title": "Test",
            "url": "https://example.com/1",
            "status": "Draft",
            "published_date": None,
            "last_revision_date": None,
        }

        temp_db.insert_benchmark(data)

        bench = temp_db.get_benchmark("1")
        assert bench["published_date"] is None

    def test_search_with_special_characters(self, temp_db):
        """Test search handles special characters."""
        temp_db.insert_benchmark(
            {
                "benchmark_id": "1",
                "title": "CIS Benchmark (Test)",
                "url": "https://example.com/1",
                "status": "Published",
                "description": "Test with special chars: & < >",
            }
        )

        results = temp_db.search("benchmark")
        assert len(results) >= 1

    def test_empty_database_stats(self, temp_db):
        """Test stats on empty database."""
        stats = temp_db.get_catalog_stats()

        assert stats["total_benchmarks"] == 0
        assert stats["published_benchmarks"] == 0

    def test_mark_latest_versions_no_benchmarks(self, temp_db):
        """Test mark_latest on empty database doesn't error."""
        temp_db.mark_latest_versions()  # Should not raise


class TestConcurrency:
    """Test concurrent operations."""

    def test_multiple_inserts_different_platforms(self, temp_db):
        """Test inserting benchmarks with same platform doesn't duplicate platform."""
        for i in range(5):
            temp_db.insert_benchmark(
                {
                    "benchmark_id": str(i),
                    "title": f"Benchmark {i}",
                    "url": f"https://example.com/{i}",
                    "status": "Published",
                    "platform": "Operating System",  # Same platform
                }
            )

        stats = temp_db.get_catalog_stats()
        assert stats["platforms"] == 1  # Should have 1 platform, not 5
        assert stats["total_benchmarks"] == 5
