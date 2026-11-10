"""Unit tests for catalog database operations."""

import tempfile
from contextlib import closing
from pathlib import Path

import pytest

from cis_bench.catalog.database import CatalogDatabase
from cis_bench.models.benchmark import BenchmarkPage


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_catalog.db"
        db = CatalogDatabase(db_path)
        db.initialize_schema()
        try:
            yield db
        finally:
            db.close()


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
        "is_latest": True,
        "collections": ["Operating System", "Linux"],
    }


class TestClosingTheDatabase:
    """A CatalogDatabase closes every connection it opened when asked (and so under
    contextlib.closing); nothing is left for garbage collection to close."""

    @staticmethod
    def _raw_connections(db):
        """The DBAPI connections the engine opens from now on."""
        from sqlalchemy import event

        opened = []
        event.listen(db.engine, "connect", lambda raw, _record: opened.append(raw))
        return opened

    @staticmethod
    def _assert_closed(raw_connections):
        import sqlite3

        assert raw_connections, "the database opened no connection"
        for raw in raw_connections:
            with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
                raw.execute("SELECT 1")

    def test_close_closes_every_connection_the_database_opened(self, tmp_path):
        db = CatalogDatabase(tmp_path / "catalog.db")
        opened = self._raw_connections(db)
        db.initialize_schema()
        assert db.list_downloaded() == []

        db.close()

        self._assert_closed(opened)

    def test_a_database_that_fails_to_open_leaves_no_connection_behind(self, tmp_path, monkeypatch):
        # The schema upgrade can fail (a full disk, a locked file); the connection it used
        # must be closed before the error reaches the caller, who has no object to close.
        from sqlalchemy import event
        from sqlalchemy.engine import Engine

        db = CatalogDatabase(tmp_path / "catalog.db")
        db.initialize_schema()
        db.close()
        opened = []

        def remember(raw, _record):
            opened.append(raw)

        event.listen(Engine, "connect", remember)
        try:

            def fail(*_args, **_kwargs):
                raise RuntimeError("disk full")

            monkeypatch.setattr(CatalogDatabase, "_pending_upgrades", staticmethod(fail))
            with pytest.raises(RuntimeError, match="disk full"):
                CatalogDatabase(tmp_path / "catalog.db")
        finally:
            event.remove(Engine, "connect", remember)

        self._assert_closed(opened)

    def test_closing_twice_is_safe(self, tmp_path):
        db = CatalogDatabase(tmp_path / "catalog.db")
        db.initialize_schema()
        db.close()

        db.close()


class TestDatabaseInitialization:
    """Test database initialization and schema creation."""

    def test_initializing_the_schema_logs_nothing_at_info(self, tmp_path, caplog):
        """Schema creation happens on every refresh; it is detail, not a run-level event."""
        db = CatalogDatabase(tmp_path / "new.db")
        with caplog.at_level("INFO", logger="cis_bench.catalog.database"):
            db.initialize_schema()
            db.initialize_schema()
        db.close()
        assert [r.getMessage() for r in caplog.records if r.levelname == "INFO"] == []

    def test_database_creation(self, temp_db):
        """Test database file is created."""
        assert temp_db.db_path.exists()

    def test_database_url_and_strict_permissions(self, tmp_path):
        """CatalogDatabase handles URL-reserved path characters and enforces 0o700/0o600 modes."""
        nested_dir = tmp_path / "catalog#dir%20"
        db_path = nested_dir / "catalog?v1#local.db"

        db = CatalogDatabase(db_path)
        assert not db.db_path.exists()
        assert db.engine.url.database == str(db_path)
        assert nested_dir.stat().st_mode & 0o777 == 0o700

        db.initialize_schema()
        assert db_path.exists()
        assert db_path.stat().st_mode & 0o777 == 0o600

        # Tightens pre-existing looser directory and database file modes on open
        nested_dir.chmod(0o755)
        db_path.chmod(0o644)
        reopened = CatalogDatabase(db_path)
        try:
            assert reopened.db_path.parent.stat().st_mode & 0o777 == 0o700
            assert reopened.db_path.stat().st_mode & 0o777 == 0o600
        finally:
            reopened.close()
            db.close()

    def test_schema_tables_created(self, temp_db):
        """Test all tables are created."""
        import sqlite3

        with closing(sqlite3.connect(temp_db.db_path)) as conn:
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
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

    def test_fts5_table_created(self, temp_db):
        """Test FTS5 virtual table is created."""
        import sqlite3

        with closing(sqlite3.connect(temp_db.db_path)) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='benchmarks_fts'"
            ).fetchall()

        assert len(tables) == 1

    _EXPECTED_DEFAULT_STATUSES = [
        ("Published", True, 1),
        ("Accepted", True, 2),
        ("Draft", False, 3),
        ("Archived", False, 4),
        ("Rejected", False, 5),
        ("Final Update", False, 6),
        ("Withdrawn", False, 7),
    ]

    @staticmethod
    def _fetch_ordered_statuses(db: CatalogDatabase) -> list[tuple[str, bool, int]]:
        from sqlmodel import Session, select

        from cis_bench.catalog.models import BenchmarkStatusModel

        with Session(db.engine) as session:
            rows = session.exec(
                select(BenchmarkStatusModel).order_by(BenchmarkStatusModel.sort_order)
            ).all()
        return [(row.name, row.is_active, row.sort_order) for row in rows]

    def test_default_statuses_inserted(self, temp_db):
        """Test default benchmark statuses are inserted with expected active flags and order."""
        from cis_bench.catalog.models import BenchmarkStatus

        assert BenchmarkStatus.FINAL_UPDATE.value == "Final Update"
        assert self._fetch_ordered_statuses(temp_db) == self._EXPECTED_DEFAULT_STATUSES

    def test_initialize_schema_backfills_missing_default_statuses(self, tmp_path):
        """Test initialize_schema backfills new default statuses into an existing 5-status DB."""
        from sqlalchemy import text
        from sqlmodel import Session, select

        from cis_bench.catalog.models import BenchmarkStatusModel

        with closing(CatalogDatabase(tmp_path / "legacy_catalog.db")) as db:
            db.initialize_schema()

            with Session(db.engine) as session:
                original_published_id = (
                    session.exec(
                        select(BenchmarkStatusModel).where(BenchmarkStatusModel.name == "Published")
                    )
                    .one()
                    .status_id
                )
                session.execute(
                    text("DELETE FROM benchmark_statuses WHERE name = :name"),
                    {"name": "Final Update"},
                )
                session.commit()

            db.initialize_schema()

            assert self._fetch_ordered_statuses(db) == self._EXPECTED_DEFAULT_STATUSES
            with Session(db.engine) as session:
                published_after = session.exec(
                    select(BenchmarkStatusModel).where(BenchmarkStatusModel.name == "Published")
                ).one()
                assert published_after.status_id == original_published_id


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

    def test_insert_benchmark_persists_platform_type_and_rejects_blank_required_fields(
        self, temp_db
    ):
        """insert_benchmark persists platform_type/is_vnext, deduplicates collections, and rejects invalid inputs."""
        import sqlite3

        temp_db.insert_benchmark(
            {
                "benchmark_id": "  7001  ",
                "title": "  CIS Amazon Web Services Foundations Benchmark  ",
                "url": "  https://workbench.cisecurity.org/benchmarks/7001  ",
                "status": "Published",
                "platform": "aws",
                "platform_type": "cloud",
                "is_vnext": True,
                "collections": ["Cloud", " ", "Cloud", "", "CIS Controls"],
            }
        )

        bench = temp_db.get_benchmark("7001")
        assert bench is not None
        assert bench["title"] == "CIS Amazon Web Services Foundations Benchmark"
        assert bench["url"] == "https://workbench.cisecurity.org/benchmarks/7001"
        assert bench["platform_type"] == "cloud"
        assert bench["is_vnext"] is True
        assert [
            r["benchmark_id"] for r in temp_db.search("amazon", platform_type="cloud", limit=None)
        ] == ["7001"]
        assert [
            r["benchmark_id"] for r in temp_db.search("", platform_type="cloud", limit=None)
        ] == ["7001"]

        with closing(sqlite3.connect(temp_db.db_path)) as conn:
            linked = [
                row[0]
                for row in conn.execute(
                    """
                    SELECT c.name
                    FROM benchmark_collections bc
                    JOIN collections c ON bc.collection_id = c.collection_id
                    WHERE bc.benchmark_id = '7001'
                    ORDER BY c.collection_id
                    """
                ).fetchall()
            ]
        assert linked == ["Cloud", "CIS Controls"]

        with pytest.raises(TypeError, match="dictionary"):
            temp_db.insert_benchmark(["not", "a", "dict"])

        for bad_field, bad_value in [
            ("benchmark_id", ""),
            ("benchmark_id", "   "),
            ("benchmark_id", None),
            ("title", ""),
            ("title", "   "),
            ("url", ""),
            ("url", "   "),
        ]:
            invalid = {
                "benchmark_id": "7002",
                "title": "Valid Title",
                "url": "https://workbench.cisecurity.org/benchmarks/7002",
                "status": "Published",
                bad_field: bad_value,
            }
            with pytest.raises(ValueError, match=bad_field):
                temp_db.insert_benchmark(invalid)


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
            },
            {
                "benchmark_id": "2",
                "title": "CIS Red Hat Enterprise Linux 9 Benchmark",
                "url": "https://workbench.cisecurity.org/benchmarks/2",
                "status": "Published",
                "platform": "Operating System",
            },
            {
                "benchmark_id": "3",
                "title": "CIS AWS Foundations Benchmark",
                "url": "https://workbench.cisecurity.org/benchmarks/3",
                "status": "Published",
                "platform": "Cloud",
            },
            {
                "benchmark_id": "4",
                "title": "CIS Windows Server 2022 Benchmark",
                "url": "https://workbench.cisecurity.org/benchmarks/4",
                "status": "Archived",
                "platform": "Operating System",
            },
        ]

        for bench in benchmarks:
            temp_db.insert_benchmark(bench)

        return temp_db

    def test_search_basic(self, populated_db):
        """Test basic search."""
        results = populated_db.search("ubuntu", limit=None)
        assert len(results) == 1
        assert "Ubuntu" in results[0]["title"]

    def test_search_fuzzy(self, populated_db):
        """Test fuzzy search (missing letter)."""
        results = populated_db.search("ubunt", limit=None)  # Missing 'u'
        assert len(results) == 1
        assert "Ubuntu" in results[0]["title"]

    def test_search_multi_word(self, populated_db):
        """Test multi-word search."""
        results = populated_db.search("linux", limit=None)
        assert len(results) >= 2  # Ubuntu and RHEL

    def test_search_case_insensitive(self, populated_db):
        """Test search is case-insensitive."""
        results_lower = populated_db.search("ubuntu", limit=None)
        results_upper = populated_db.search("UBUNTU", limit=None)
        results_mixed = populated_db.search("Ubuntu", limit=None)

        assert len(results_lower) == len(results_upper) == len(results_mixed)

    def test_search_with_platform_filter(self, populated_db):
        """Test search with platform filter."""
        results = populated_db.search("benchmark", platform="Cloud", limit=None)
        assert len(results) == 1
        assert "AWS" in results[0]["title"]

    def test_search_with_status_filter(self, populated_db):
        """Test search with status filter."""
        # Default is Published
        results = populated_db.search("benchmark", limit=None)
        assert all(r["status"] == "Published" for r in results)

        # Search archived
        results = populated_db.search("windows", status="Archived", limit=None)
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
        all_results = populated_db.search("ubuntu", latest_only=False, limit=None)

        # Search with latest_only
        latest_results = populated_db.search("ubuntu", latest_only=True, limit=None)

        assert len(latest_results) < len(all_results)

    def test_search_empty_query(self, populated_db):
        """Test search with empty query returns all."""
        results = populated_db.search("", limit=None)
        assert len(results) > 0

    def test_no_limit_returns_every_match_whatever_the_settings(self, populated_db, monkeypatch):
        # The library takes its limit from the caller; CIS_BENCH_SEARCH_LIMIT is the CLI's.
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "1")
        assert len(populated_db.search("", limit=None)) == 3

    def test_count_search_counts_every_match_whatever_the_limit(self, populated_db):
        # 3 Published benchmarks; a limit of 1 shows one but the count is the whole set.
        assert len(populated_db.search("", limit=1)) == 1
        assert populated_db.count_search("") == 3
        assert populated_db.count_search("linux") == 2
        assert populated_db.count_search("", platform="Cloud") == 1
        assert populated_db.count_search("", status="all") == 4
        assert populated_db.count_search("nonexistent") == 0
        assert populated_db.count_search("!!!") == 0

    def test_search_no_matches(self, populated_db):
        """Test search with no matches returns empty list."""
        results = populated_db.search("nonexistent", limit=None)
        assert len(results) == 0

    def test_search_dotted_version_and_hyphenated_queries(self, populated_db):
        """Test dotted versions and hyphenated terms match cleanly against SQLite FTS5."""
        ubuntu_results = populated_db.search("ubuntu 20.04", limit=None)
        assert [row["benchmark_id"] for row in ubuntu_results] == ["1"]

        rhel_results = populated_db.search("red-hat", limit=None)
        assert [row["benchmark_id"] for row in rhel_results] == ["2"]

    def test_search_fts5_boolean_keywords_treated_as_literal_prefixes(self, populated_db):
        """Test uppercase FTS5 operators execute as literal prefix searches without syntax errors."""
        populated_db.insert_benchmark(
            {
                "benchmark_id": "6",
                "title": "CIS Oracle Database 19c Benchmark",
                "url": "https://workbench.cisecurity.org/benchmarks/6",
                "status": "Published",
                "platform": "Database",
            }
        )

        oracle_results = populated_db.search("OR", limit=None)
        assert [row["benchmark_id"] for row in oracle_results] == ["6"]

        # As an operator AND would leave "ubuntu" and find benchmark 1; as a literal it asks
        # for a word starting "and" as well, which no title has.
        assert populated_db.search("ubuntu AND", limit=None) == []

        assert populated_db.search("NOT", limit=None) == []
        assert populated_db.search("NEAR", limit=None) == []

    def test_search_punctuation_only_returns_empty_without_listing_all(self, populated_db):
        """Test punctuation-only queries return empty list while whitespace lists all published."""
        assert populated_db.search("...", limit=None) == []
        assert populated_db.search("!!!", limit=None) == []
        assert populated_db.search("***", limit=None) == []
        assert populated_db.search("___", limit=None) == []

        whitespace_results = populated_db.search("   ", limit=None)
        assert sorted(row["benchmark_id"] for row in whitespace_results) == ["1", "2", "3"]

    def test_search_status_all_or_none_returns_all_statuses_for_fts_and_empty_query(
        self, populated_db
    ):
        """Empty-query and FTS5 search accept status=None and status='all' across all benchmark statuses."""
        from cis_bench.catalog.search import CatalogSearch

        populated_db.insert_benchmark(
            {
                "benchmark_id": "7",
                "title": "CIS Debian Linux 12 Benchmark",
                "url": "https://workbench.cisecurity.org/benchmarks/7",
                "status": "Draft",
                "platform": "Operating System",
                "platform_type": "os",
                "description": "Debian hardening benchmark",
            }
        )
        populated_db.insert_benchmark(
            {
                "benchmark_id": "8",
                "title": "CIS CentOS Linux 7 Benchmark",
                "url": "https://workbench.cisecurity.org/benchmarks/8",
                "status": "Final Update",
                "platform": "Operating System",
                "platform_type": "os",
                "description": "CentOS legacy benchmark",
            }
        )

        expected_all_ids = ["1", "2", "3", "4", "7", "8"]

        for status_arg in (None, "all", "ALL", " all "):
            empty_ids = sorted(
                row["benchmark_id"]
                for row in populated_db.search("", status=status_arg, limit=None)
            )
            fts_ids = sorted(
                row["benchmark_id"]
                for row in populated_db.search("benchmark", status=status_arg, limit=None)
            )
            assert empty_ids == expected_all_ids
            assert fts_ids == expected_all_ids

        catalog_search = CatalogSearch(populated_db)
        assert (
            sorted(
                row["benchmark_id"] for row in catalog_search.search("", status="all", limit=None)
            )
            == expected_all_ids
        )
        assert sorted(
            row["benchmark_id"]
            for row in catalog_search.search("linux", status=None, platform_type="os", limit=None)
        ) == ["7", "8"]


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

    def test_get_or_create_status_registers_unseen_status_idempotently(self, temp_db):
        """Test unseen non-empty statuses are normalized, created inactive, and not duplicated."""
        from sqlmodel import Session, select

        from cis_bench.catalog.models import BenchmarkStatusModel

        with Session(temp_db.engine) as session:
            created = temp_db.get_or_create_status("  Community Review  ", session)
            assert created.name == "Community Review"
            assert created.is_active is False
            assert created.sort_order == 8  # after the seven default statuses
            assert created.status_id is not None
            created_id = created.status_id
            session.commit()

        with Session(temp_db.engine) as session:
            looked_up_id = temp_db.get_status_id("Community Review", session)
            matching_rows = session.exec(
                select(BenchmarkStatusModel).where(BenchmarkStatusModel.name == "Community Review")
            ).all()
            assert looked_up_id == created_id
            assert len(matching_rows) == 1

    def test_get_empty_status_raises(self, temp_db):
        """Test empty or whitespace-only status names raise ValueError."""
        from sqlmodel import Session

        with Session(temp_db.engine) as session:
            with pytest.raises(ValueError, match="Status name cannot be empty"):
                temp_db.get_or_create_status("", session)
            with pytest.raises(ValueError, match="Status name cannot be empty"):
                temp_db.get_status_id("   ", session)

    def test_insert_and_search_benchmarks_with_final_update_and_unseen_status(self, temp_db):
        """Test inserting and searching benchmarks with Final Update and unseen WorkBench statuses."""
        temp_db.insert_benchmark(
            {
                "benchmark_id": "9001",
                "title": "CIS CentOS Linux 7 Benchmark",
                "url": "https://workbench.cisecurity.org/benchmarks/9001",
                "status": "Final Update",
                "platform": "Operating System",
            }
        )
        temp_db.insert_benchmark(
            {
                "benchmark_id": "9002",
                "title": "CIS Legacy Appliance Benchmark",
                "url": "https://workbench.cisecurity.org/benchmarks/9002",
                "status": "Sunset",
                "platform": "Operating System",
            }
        )

        final_update_bench = temp_db.get_benchmark("9001")
        assert final_update_bench is not None
        assert final_update_bench["status"] == "Final Update"

        sunset_bench = temp_db.get_benchmark("9002")
        assert sunset_bench is not None
        assert sunset_bench["status"] == "Sunset"

        final_results = temp_db.search("CentOS", status="Final Update", limit=None)
        assert [row["benchmark_id"] for row in final_results] == ["9001"]

        sunset_results = temp_db.search("Appliance", status="Sunset", limit=None)
        assert [row["benchmark_id"] for row in sunset_results] == ["9002"]

    def test_get_or_create_lookup_helpers_recover_via_savepoint_preserving_outer_work(
        self, temp_db
    ):
        """All five get_or_create_* methods recover from concurrent IntegrityError via SAVEPOINT."""
        from sqlalchemy import event
        from sqlmodel import Session

        from cis_bench.catalog.models import (
            BenchmarkStatusModel,
            Collection,
            Community,
            Owner,
            Platform,
            ScrapeMetadata,
        )

        race_cases = [
            (
                "platform",
                lambda s: temp_db.get_or_create_platform("Container Runtime", s),
                lambda: Platform(name="Container Runtime"),
                lambda row: (row.name, row.platform_id),
            ),
            (
                "community",
                lambda s: temp_db.get_or_create_community("CIS Kubernetes Community", s),
                lambda: Community(name="CIS Kubernetes Community"),
                lambda row: (row.name, row.community_id),
            ),
            (
                "owner",
                lambda s: temp_db.get_or_create_owner("concurrent.author", s),
                lambda: Owner(username="concurrent.author"),
                lambda row: (row.username, row.owner_id),
            ),
            (
                "collection",
                lambda s: temp_db.get_or_create_collection("Zero Trust", s),
                lambda: Collection(name="Zero Trust"),
                lambda row: (row.name, row.collection_id),
            ),
            (
                "status",
                lambda s: temp_db.get_or_create_status("External Review", s),
                lambda: BenchmarkStatusModel(
                    name="External Review", is_active=False, sort_order=99
                ),
                lambda row: (row.name, row.status_id),
            ),
        ]

        competing_db = CatalogDatabase(temp_db.db_path)

        for label, call_helper, build_competitor, extract_identity in race_cases:
            with Session(temp_db.engine, autoflush=False) as session:
                outer_record = ScrapeMetadata(key=f"pending-{label}", value=f"preserved-{label}")
                session.add(outer_record)

                seen_initial_select: list[bool] = []
                injected_winner_id: list[int] = []

                def _inject_after_select_before_write(
                    _conn,
                    _cursor,
                    statement,
                    _parameters,
                    _context,
                    _executemany,
                    _build=build_competitor,
                    _extract=extract_identity,
                    _seen=seen_initial_select,
                    _injected=injected_winner_id,
                ):
                    upper_stmt = statement.lstrip().upper()
                    if upper_stmt.startswith("PRAGMA"):
                        return
                    if upper_stmt.startswith("SELECT"):
                        _seen.append(True)
                        return
                    if not _seen or _injected:
                        return
                    with Session(competing_db.engine) as other_session:
                        winner = _build()
                        other_session.add(winner)
                        other_session.commit()
                        other_session.refresh(winner)
                        _, winner_pk = _extract(winner)
                        assert winner_pk is not None
                        _injected.append(winner_pk)

                event.listen(
                    temp_db.engine, "before_cursor_execute", _inject_after_select_before_write
                )
                try:
                    recovered = call_helper(session)
                finally:
                    event.remove(
                        temp_db.engine,
                        "before_cursor_execute",
                        _inject_after_select_before_write,
                    )

                assert len(injected_winner_id) == 1
                _, recovered_pk = extract_identity(recovered)
                assert recovered_pk == injected_winner_id[0]

                session.commit()

            assert temp_db.get_metadata(f"pending-{label}") == f"preserved-{label}"
        competing_db.close()

    def test_savepoint_lookup_creation_rolls_back_with_outer_session(self, temp_db):
        """SAVEPOINT release inside _get_or_create must not auto-commit lookup rows before outer commit."""
        from sqlmodel import Session, select

        from cis_bench.catalog.models import Platform

        observer_db = CatalogDatabase(temp_db.db_path)
        try:
            with Session(temp_db.engine) as session:
                created = temp_db.get_or_create_platform("RollbackOnlyPlatform", session)
                assert created.platform_id is not None

                with Session(observer_db.engine) as observer_session:
                    visible_before_commit = observer_session.exec(
                        select(Platform).where(Platform.name == "RollbackOnlyPlatform")
                    ).first()
                    assert visible_before_commit is None

                session.rollback()

            with Session(observer_db.engine) as observer_session:
                persisted_after_rollback = observer_session.exec(
                    select(Platform).where(Platform.name == "RollbackOnlyPlatform")
                ).first()
                assert persisted_after_rollback is None
        finally:
            observer_db.close()

    def test_catalog_database_init_tolerates_eperm_on_unowned_paths(self, temp_db, monkeypatch):
        """Opening a readable catalog database owned by another user tolerates chmod PermissionError."""
        import errno

        original_chmod = Path.chmod

        def _deny_chmod(path_obj: Path, mode: int, *, follow_symlinks: bool = True) -> None:
            if path_obj in {temp_db.db_path, temp_db.db_path.parent}:
                raise PermissionError(errno.EPERM, "Operation not permitted", str(path_obj))
            original_chmod(path_obj, mode, follow_symlinks=follow_symlinks)

        monkeypatch.setattr(Path, "chmod", _deny_chmod)

        shared_db = CatalogDatabase(temp_db.db_path)
        try:
            assert shared_db.get_catalog_stats()["total_benchmarks"] == 0
        finally:
            shared_db.close()


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

    def test_save_downloaded_keeps_the_benchmarks_own_instant(self, temp_db, sample_benchmark_data):
        from datetime import UTC, datetime

        temp_db.insert_benchmark(sample_benchmark_data)
        instant = datetime(2026, 11, 7, 2, 5, 58, 123456, tzinfo=UTC)

        temp_db.save_downloaded("23598", "{}", "h", 1, downloaded_at=instant)

        assert temp_db.get_downloaded("23598")["downloaded_at"] == instant
        assert temp_db.list_downloaded()[0]["downloaded_at"] == instant

    def test_a_download_time_comes_back_aware_in_utc(self, temp_db, sample_benchmark_data):
        from datetime import UTC

        temp_db.insert_benchmark(sample_benchmark_data)

        temp_db.save_downloaded("23598", "{}", "h", 1)

        row = temp_db.get_downloaded("23598")
        assert row["downloaded_at"].tzinfo is UTC
        assert row["last_accessed"].tzinfo is UTC

    def test_a_download_time_without_a_zone_is_refused(self, temp_db, sample_benchmark_data):
        from datetime import datetime

        from sqlalchemy.exc import StatementError

        temp_db.insert_benchmark(sample_benchmark_data)

        with pytest.raises(StatementError, match="zone"):
            temp_db.save_downloaded("23598", "{}", "h", 1, downloaded_at=datetime(2026, 11, 7))
        assert temp_db.get_downloaded("23598") is None

    def test_a_row_written_by_an_earlier_version_is_read_as_utc(
        self, temp_db, sample_benchmark_data
    ):
        """Earlier versions stored naive UTC text; it is read back as the UTC instant it was."""
        from datetime import UTC, datetime

        from sqlalchemy import text

        temp_db.insert_benchmark(sample_benchmark_data)
        with temp_db.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO downloaded_benchmarks (benchmark_id, content_json, content_hash,"
                    " downloaded_at, last_accessed) VALUES ('23598', '{}', 'h',"
                    " '2026-11-07 02:05:58.000000', '2026-11-07 02:05:58.000000')"
                )
            )

        row = temp_db.get_downloaded("23598")

        assert row["downloaded_at"] == datetime(2026, 11, 7, 2, 5, 58, tzinfo=UTC)

    def test_get_nonexistent_downloaded(self, temp_db):
        """Test getting non-existent download returns None."""
        downloaded = temp_db.get_downloaded("99999")
        assert downloaded is None

    def test_delete_downloaded_removes_the_cached_copy_and_keeps_the_catalog_row(
        self, temp_db, sample_benchmark_data
    ):
        temp_db.insert_benchmark(sample_benchmark_data)
        temp_db.save_downloaded("23598", '{"v": 1}', "hash1", 100, version="v2.0.1")

        assert temp_db.delete_downloaded("23598") is True

        assert temp_db.get_downloaded("23598") is None
        assert "23598" not in temp_db.list_downloaded_benchmark_ids()
        catalog_row = temp_db.get_benchmark("23598")
        assert catalog_row is not None
        assert sorted(catalog_row["collections"]) == ["Linux", "Operating System"]
        assert [r["benchmark_id"] for r in temp_db.search("ubuntu", limit=None)] == ["23598"]
        assert temp_db.get_catalog_stats()["downloaded_benchmarks"] == 0

    def test_delete_downloaded_reports_a_benchmark_that_was_not_downloaded(
        self, temp_db, sample_benchmark_data
    ):
        temp_db.insert_benchmark(sample_benchmark_data)

        assert temp_db.delete_downloaded("23598") is False
        assert temp_db.delete_downloaded("99999") is False
        assert temp_db.get_benchmark("23598") is not None

    def test_delete_downloaded_leaves_other_downloads_alone(self, temp_db, sample_benchmark_data):
        temp_db.insert_benchmark(sample_benchmark_data)
        temp_db.insert_benchmark(
            {
                **sample_benchmark_data,
                "benchmark_id": "24000",
                "url": "https://workbench.cisecurity.org/benchmarks/24000",
            }
        )
        temp_db.save_downloaded("23598", "{}", "h1", 1)
        temp_db.save_downloaded("24000", "{}", "h2", 2)

        temp_db.delete_downloaded("23598")

        assert temp_db.list_downloaded_benchmark_ids() == ["24000"]

    def test_list_downloaded_gives_each_cached_benchmark_in_id_order_with_its_catalog_title(
        self, temp_db, sample_benchmark_data
    ):
        temp_db.insert_benchmark(sample_benchmark_data)
        temp_db.insert_benchmark(
            {
                **sample_benchmark_data,
                "benchmark_id": "24000",
                "title": "Other",
                "url": "https://workbench.cisecurity.org/benchmarks/24000",
            }
        )
        temp_db.save_downloaded("24000", '{"b": 2}', "hash2", 20, version="v1.0.0")
        temp_db.save_downloaded("23598", '{"b": 1}', "hash1", 100, version="v2.0.1")

        # Downloaded while absent from the catalog (download needs no catalog row): still listed
        temp_db.save_downloaded("6467", '{"b": 3}', "hash3", 5, version="v1.0.0")

        rows = temp_db.list_downloaded()

        assert [
            (r["benchmark_id"], r["title"], r["version"], r["recommendation_count"]) for r in rows
        ] == [
            ("6467", None, "v1.0.0", 5),
            ("23598", "CIS Ubuntu Linux 20.04 LTS Benchmark", "v2.0.1", 100),
            ("24000", "Other", "v1.0.0", 20),
        ]
        assert "content_json" not in rows[0]  # fetched per benchmark by the caller
        assert rows[0]["downloaded_at"] is not None
        assert temp_db.list_downloaded() == rows  # ordered by ID as a number, stable

    def test_save_downloaded_stores_the_downloaded_version(self, temp_db, sample_benchmark_data):
        """check-updates compares the catalog version against the version that was downloaded."""
        temp_db.insert_benchmark(sample_benchmark_data)
        temp_db.save_downloaded("23598", '{"version": "v2.0.1"}', "hash1", 100, version="v2.0.1")

        assert temp_db.get_downloaded("23598")["version"] == "v2.0.1"

    def _insert(self, db, bid, version, status="Published"):
        db.insert_benchmark(
            {
                "benchmark_id": bid,
                "title": f"CIS Benchmark {bid}",
                "version": version,
                "url": f"https://workbench.cisecurity.org/benchmarks/{bid}",
                "status": status,
            }
        )

    def test_check_updates_reports_a_newer_catalog_version(self, temp_db):
        """The catalog now lists v2.0.0 for a benchmark downloaded at v1.0.0."""
        self._insert(temp_db, "301", "v2.0.0")
        temp_db.save_downloaded("301", "{}", "h", 1, version="v1.0.0")

        updates = temp_db.check_updates_available()

        assert [u["benchmark_id"] for u in updates] == ["301"]
        assert updates[0]["downloaded_version"] == "v1.0.0"
        assert updates[0]["catalog_version"] == "v2.0.0"
        assert updates[0]["reason"] == "newer version in catalog"

    def test_check_updates_is_silent_when_versions_match_and_no_newer_date_is_known(self, temp_db):
        self._insert(temp_db, "302", "v1.0.0")
        temp_db.save_downloaded("302", "{}", "h", 1, version="v1.0.0")

        assert temp_db.check_updates_available() == []

    def test_check_updates_reports_a_publication_date_after_the_download(self, temp_db):
        """Same version, but WorkBench shows a publication date after we downloaded it."""
        from datetime import date

        self._insert(temp_db, "303", "v1.0.0")
        temp_db.save_downloaded("303", "{}", "h", 1, version="v1.0.0")
        temp_db.record_page(
            "303", BenchmarkPage(title="CIS Benchmark", published_date=date(2999, 1, 1))
        )

        updates = temp_db.check_updates_available()

        assert [u["benchmark_id"] for u in updates] == ["303"]
        assert updates[0]["published_date"] == date(2999, 1, 1)
        assert updates[0]["reason"] == "published after download"

    def test_check_updates_ignores_a_publication_date_before_the_download(self, temp_db):
        from datetime import date

        self._insert(temp_db, "304", "v1.0.0")
        temp_db.save_downloaded("304", "{}", "h", 1, version="v1.0.0")
        temp_db.record_page(
            "304", BenchmarkPage(title="CIS Benchmark", published_date=date(2000, 1, 1))
        )

        assert temp_db.check_updates_available() == []

    def test_check_updates_does_not_read_the_column_earlier_versions_wrote(self, temp_db):
        """Earlier versions kept the date in downloaded_benchmarks.workbench_last_modified; an
        older database may still hold one there, and nothing reads it."""
        from sqlalchemy import text

        self._insert(temp_db, "307", "v1.0.0")
        temp_db.save_downloaded("307", "{}", "h", 1, version="v1.0.0")
        with temp_db.engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE downloaded_benchmarks ADD COLUMN workbench_last_modified VARCHAR")
            )
            connection.execute(
                text("UPDATE downloaded_benchmarks SET workbench_last_modified = '2999-01-01'")
            )

        assert temp_db.check_updates_available() == []

    def test_check_updates_skips_the_date_signal_when_the_catalog_is_behind_the_download(
        self, temp_db
    ):
        """A stale catalog listing an older version than we hold is not an update, whatever the date says."""
        from datetime import date

        self._insert(temp_db, "308", "v1.0.0")
        temp_db.save_downloaded("308", "{}", "h", 1, version="v2.0.0")
        temp_db.record_page(
            "308", BenchmarkPage(title="CIS Benchmark", published_date=date(2999, 1, 1))
        )

        assert temp_db.check_updates_available() == []

    def test_check_updates_never_reports_an_unversioned_or_older_catalog_entry(self, temp_db):
        self._insert(temp_db, "305", "vNext")
        temp_db.save_downloaded("305", "{}", "h", 1, version="v1.0.0")
        self._insert(temp_db, "306", "v1.0.0")
        temp_db.save_downloaded("306", "{}", "h", 1, version="v2.0.0")

        assert temp_db.check_updates_available() == []


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

    def test_get_catalog_stats_counts_in_sql_without_loading_downloaded_blobs(self, temp_db):
        """get_catalog_stats returns exact aggregate counts via SQL COUNT without projecting content_json."""
        from sqlalchemy import event

        records = [
            ("401", "Published", "Operating System", "CIS Linux"),
            ("402", "Published", "Cloud", "CIS Cloud"),
            ("403", "Archived", "Operating System", "CIS Linux"),
        ]
        for bid, status, platform, community in records:
            temp_db.insert_benchmark(
                {
                    "benchmark_id": bid,
                    "title": f"Benchmark {bid}",
                    "url": f"https://workbench.cisecurity.org/benchmarks/{bid}",
                    "status": status,
                    "platform": platform,
                    "community": community,
                }
            )

        temp_db.save_downloaded("401", '{"blob": "alpha"}', "hash-401", 10)
        temp_db.save_downloaded("403", '{"blob": "beta"}', "hash-403", 20)

        statements: list[str] = []

        def _capture_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
            statements.append(statement)

        event.listen(temp_db.engine, "before_cursor_execute", _capture_sql)
        try:
            stats = temp_db.get_catalog_stats()
        finally:
            event.remove(temp_db.engine, "before_cursor_execute", _capture_sql)

        assert stats == {
            "total_benchmarks": 3,
            "published_benchmarks": 2,
            "withdrawn_benchmarks": 0,
            "downloaded_benchmarks": 2,
            "platforms": 2,
            "communities": 2,
        }
        select_statements = [
            stmt for stmt in statements if stmt.lstrip().upper().startswith("SELECT")
        ]
        assert len(select_statements) == 6  # one COUNT per figure
        assert all("COUNT(" in stmt.upper() for stmt in select_statements)
        assert all("content_json" not in stmt.lower() for stmt in select_statements)

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

    def test_list_platforms_filters_by_active_status_flag(self, temp_db):
        """list_platforms counts benchmarks across statuses with is_active=1 and excludes inactive statuses."""
        from sqlmodel import Session

        from cis_bench.catalog.models import BenchmarkStatusModel

        with Session(temp_db.engine) as session:
            session.add(
                BenchmarkStatusModel(
                    name="Community Accepted",
                    is_active=True,
                    sort_order=10,
                )
            )
            session.commit()

        records = [
            ("301", "Operating System", "Published"),
            ("302", "Operating System", "Accepted"),
            ("303", "Operating System", "Archived"),
            ("304", "Container", "Community Accepted"),
            ("305", "Legacy Appliance", "Final Update"),
        ]
        for bid, platform, status in records:
            temp_db.insert_benchmark(
                {
                    "benchmark_id": bid,
                    "title": f"Benchmark {bid}",
                    "url": f"https://workbench.cisecurity.org/benchmarks/{bid}",
                    "status": status,
                    "platform": platform,
                }
            )

        assert temp_db.list_platforms() == [
            {"name": "Operating System", "count": 2},
            {"name": "Container", "count": 1},
        ]

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

    def test_mark_latest_versions_does_not_cross_match_versionless_titles(self, temp_db):
        """mark_latest_versions groups by normalized base title and status without LIKE '%' cross-matching."""
        fixtures = [
            {
                "benchmark_id": "101",
                "title": "CIS RHEL 9 Benchmark",
                "version": "v1.0.0",
                "url": "https://workbench.cisecurity.org/benchmarks/101",
                "status": "Published",
                "published_date": "2024-01-01",
            },
            {
                "benchmark_id": "102",
                "title": "CIS RHEL 9 Benchmark",
                "version": "v2.0.0",
                "url": "https://workbench.cisecurity.org/benchmarks/102",
                "status": "Published",
                "published_date": "2024-07-01",
            },
            {
                "benchmark_id": "103",
                "title": "CIS AWS Foundations Benchmark",
                "version": "v3.0.0",
                "url": "https://workbench.cisecurity.org/benchmarks/103",
                "status": "Published",
                "published_date": "2024-09-01",
            },
            {
                "benchmark_id": "104",
                "title": "CIS RHEL 9 Benchmark",
                "version": "v0.9.0",
                "url": "https://workbench.cisecurity.org/benchmarks/104",
                "status": "Archived",
                "published_date": "2024-12-01",
            },
            {
                "benchmark_id": "105",
                "title": "CIS Ubuntu Linux 20.04 LTS Benchmark v1.0.0",
                "version": "v1.0.0",
                "url": "https://workbench.cisecurity.org/benchmarks/105",
                "status": "Published",
                "published_date": "2023-01-01",
            },
            {
                "benchmark_id": "106",
                "title": "CIS Ubuntu Linux 20.04 LTS Benchmark v2.0.1",
                "version": "v2.0.1",
                "url": "https://workbench.cisecurity.org/benchmarks/106",
                "status": "Published",
                "published_date": "2024-08-01",
            },
            {
                "benchmark_id": "107",
                "title": "CIS VMware vSphere 7.0 Benchmark v1.0.0",
                "version": "v1.0.0",
                "url": "https://workbench.cisecurity.org/benchmarks/107",
                "status": "Published",
                "published_date": "2023-05-01",
            },
            {
                "benchmark_id": "108",
                "title": "CIS VMware vSphere 8.0 Benchmark v1.0.0",
                "version": "v1.0.0",
                "url": "https://workbench.cisecurity.org/benchmarks/108",
                "status": "Published",
                "published_date": "2024-05-01",
            },
        ]
        for item in fixtures:
            temp_db.insert_benchmark(item)

        temp_db.mark_latest_versions()

        latest_by_id = {
            item["benchmark_id"]: temp_db.get_benchmark(item["benchmark_id"])["is_latest"]
            for item in fixtures
        }
        assert latest_by_id == {
            "101": False,
            "102": True,
            "103": True,
            "104": True,
            "105": False,
            "106": True,
            "107": True,
            "108": True,
        }


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

        with closing(sqlite3.connect(temp_db.db_path)) as conn:
            collections = conn.execute("SELECT name FROM collections").fetchall()
            links = conn.execute(
                "SELECT * FROM benchmark_collections WHERE benchmark_id = '1'"
            ).fetchall()
        assert len(collections) == 3
        assert len(links) == 3

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

        with closing(sqlite3.connect(temp_db.db_path)) as conn:
            links = conn.execute(
                "SELECT * FROM benchmark_collections WHERE benchmark_id = '1'"
            ).fetchall()
        assert len(links) == 2

    def test_get_benchmark_includes_sorted_collections(self, temp_db):
        """get_benchmark returns sorted collection names and an empty list when none exist."""
        temp_db.insert_benchmark(
            {
                "benchmark_id": "10",
                "title": "Tagged Benchmark",
                "url": "https://workbench.cisecurity.org/benchmarks/10",
                "status": "Published",
                "collections": ["STIG", "Cloud", "Linux"],
            }
        )
        temp_db.insert_benchmark(
            {
                "benchmark_id": "11",
                "title": "Untagged Benchmark",
                "url": "https://workbench.cisecurity.org/benchmarks/11",
                "status": "Published",
            }
        )

        tagged = temp_db.get_benchmark("10")
        untagged = temp_db.get_benchmark("11")
        assert tagged is not None
        assert untagged is not None
        assert tagged["collections"] == ["Cloud", "Linux", "STIG"]
        assert untagged["collections"] == []


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

        results = temp_db.search("benchmark", limit=None)
        assert len(results) >= 1

    def test_empty_database_stats(self, temp_db):
        """Test stats on empty database."""
        stats = temp_db.get_catalog_stats()

        assert stats["total_benchmarks"] == 0
        assert stats["published_benchmarks"] == 0

    def test_mark_latest_versions_uses_the_version_column_not_published_date(self, temp_db):
        """The catalog list page carries no dates; the highest parseable version in a
        (base title, status) group is latest, regardless of published_date."""
        rows = [
            ("90101", "v2.0.0", "Published"),
            ("90102", "v1.0.0", "Published"),
            ("90103", "v10.0.0", "Published"),
            ("90104", "v3.0.0 (vNext)", "Draft"),
            ("90105", "vNext", "Draft"),
        ]
        for bid, version, status in rows:
            temp_db.insert_benchmark(
                {
                    "benchmark_id": bid,
                    "title": "CIS Ubuntu Linux 22.04 LTS Benchmark",
                    "version": version,
                    "url": f"https://workbench.cisecurity.org/benchmarks/{bid}",
                    "status": status,
                }
            )
        temp_db.mark_latest_versions()

        latest = {
            r["benchmark_id"]: r["is_latest"]
            for r in temp_db.search("", status="all", limit=50)
            if r["benchmark_id"].startswith("9010")
        }
        assert latest == {
            "90101": False,
            "90102": False,
            "90103": True,  # v10 beats v2 and v1 numerically, not lexically
            "90104": True,  # highest parseable version among the Drafts
            "90105": False,  # unversioned loses to a parseable sibling
        }

    def test_mark_latest_versions_group_with_only_unversioned_rows_marks_them_all(self, temp_db):
        for bid, version in (("90201", "vNext"), ("90202", "vDev")):
            temp_db.insert_benchmark(
                {
                    "benchmark_id": bid,
                    "title": "CIS Experimental Benchmark",
                    "version": version,
                    "url": f"https://workbench.cisecurity.org/benchmarks/{bid}",
                    "status": "Draft",
                }
            )
        temp_db.mark_latest_versions()
        latest = {
            r["benchmark_id"]: r["is_latest"]
            for r in temp_db.search("", status="Draft", limit=50)
            if r["benchmark_id"].startswith("9020")
        }
        assert latest == {"90201": True, "90202": True}

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


class TestOpeningAnOlderCatalog:
    """A catalog written by an earlier version is brought up to date when it is opened."""

    OLD_FTS = """
        DROP TABLE benchmarks_fts;
        CREATE VIRTUAL TABLE benchmarks_fts USING fts5(
            benchmark_id UNINDEXED, title, platform, community, description,
            tokenize='porter unicode61');
        INSERT INTO benchmarks_fts (benchmark_id, title, platform, community, description)
        SELECT b.benchmark_id, b.title, coalesce(p.name, ''), coalesce(c.name, ''), ''
        FROM catalog_benchmarks b
        LEFT JOIN platforms p ON p.platform_id = b.platform_id
        LEFT JOIN communities c ON c.community_id = b.community_id;
    """

    @staticmethod
    def _catalog(path, sql_afterwards):
        """A catalog with two releases of one benchmark, then altered as an older version left it."""
        import sqlite3

        db = CatalogDatabase(path)
        db.initialize_schema()
        for benchmark_id, version in (("200", "v2.0.0"), ("210", "v2.1.0")):
            db.insert_benchmark(
                {
                    "benchmark_id": benchmark_id,
                    "title": "CIS Kubernetes Benchmark",
                    "version": version,
                    "url": f"https://workbench.cisecurity.org/benchmarks/{benchmark_id}",
                    "status": "Published",
                    "platform": "Container Platform",
                    "community": "CIS Kubernetes Benchmarks",
                }
            )
        db.close()
        with closing(sqlite3.connect(path)) as con:
            con.executescript(sql_afterwards)

    @staticmethod
    def _index_rows(path):
        import sqlite3

        with closing(sqlite3.connect(path)) as con:
            return sorted(row[0] for row in con.execute("SELECT benchmark_id FROM benchmarks_fts"))

    @staticmethod
    def _warnings(caplog):
        return [record.getMessage() for record in caplog.records if record.levelname == "WARNING"]

    @staticmethod
    def _found(db, query):
        return sorted(str(row["benchmark_id"]) for row in db.search(query, limit=None))

    def test_an_index_without_versions_is_rebuilt_so_a_version_search_works(self, tmp_path):
        path = tmp_path / "older.db"
        self._catalog(path, self.OLD_FTS)

        db = CatalogDatabase(path)
        try:
            assert self._found(db, "kubernetes 2.1.0") == ["210"]
            assert self._found(db, "kubernetes") == ["200", "210"]
            assert self._found(db, "container") == ["200", "210"]
        finally:
            db.close()
        assert self._index_rows(path) == ["200", "210"]

    # The layout an earlier version of this branch wrote: versions, and a description column
    # WorkBench's catalog listing never filled.
    DESCRIPTION_FTS = """
        DROP TABLE benchmarks_fts;
        CREATE VIRTUAL TABLE benchmarks_fts USING fts5(
            benchmark_id UNINDEXED, title, platform, community, description, version,
            tokenize='porter unicode61');
        INSERT INTO benchmarks_fts (benchmark_id, title, platform, community, description, version)
        SELECT b.benchmark_id, b.title, '', '', '', b.version FROM catalog_benchmarks b;
    """

    def test_an_index_with_a_description_column_is_rebuilt_without_it(self, tmp_path):
        import sqlite3

        path = tmp_path / "older.db"
        self._catalog(path, self.DESCRIPTION_FTS)

        db = CatalogDatabase(path)
        try:
            assert self._found(db, "kubernetes 2.1.0") == ["210"]
        finally:
            db.close()
        with closing(sqlite3.connect(path)) as con:
            columns = [row[1] for row in con.execute("PRAGMA table_info(benchmarks_fts)")]
        assert columns == ["benchmark_id", "title", "platform", "community", "version"]
        assert self._index_rows(path) == ["200", "210"]

    def test_a_downloaded_table_without_the_published_date_column_gets_it(self, tmp_path):
        from datetime import date

        path = tmp_path / "older.db"
        self._catalog(path, "ALTER TABLE downloaded_benchmarks DROP COLUMN published_date;")

        CatalogDatabase(path).close()
        db = CatalogDatabase(path)
        try:
            db.save_downloaded("210", "{}", "hash", 20, published_date=date(2025, 8, 28))
            assert db.get_downloaded("210")["published_date"] == date(2025, 8, 28)
        finally:
            db.close()

    def test_opening_it_again_leaves_one_index_row_per_benchmark(self, tmp_path):
        path = tmp_path / "older.db"
        self._catalog(path, self.OLD_FTS)

        for _ in range(2):
            CatalogDatabase(path).close()

        assert self._index_rows(path) == ["200", "210"]

    def test_an_index_that_has_versions_is_left_as_it_is(self, tmp_path):
        path = tmp_path / "current.db"
        marker = "INSERT INTO benchmarks_fts (benchmark_id, title) VALUES ('marker', 'kept');"
        self._catalog(path, marker)

        CatalogDatabase(path).close()

        assert self._index_rows(path) == ["200", "210", "marker"]

    def test_existing_database_gains_recommendations_fts_on_open(self, tmp_path):
        """A catalog from before the recommendation index gains it, filled from what is
        downloaded, and keeps every downloaded copy as it was."""
        from cis_bench.catalog.database import serialize_benchmark_json
        from cis_bench.models.benchmark import Benchmark, Recommendation

        path = tmp_path / "older.db"
        benchmark = Benchmark(
            title="CIS Kubernetes Benchmark",
            benchmark_id="210",
            url="https://workbench.cisecurity.org/benchmarks/210",
            version="v2.1.0",
            scraper_version="v2_2026_01",
            total_recommendations=1,
            recommendations=[
                Recommendation(
                    ref="1.2.3",
                    title="Ensure the API server audit log is enabled",
                    url="https://workbench.cisecurity.org/sections/1/recommendations/123",
                    assessment_status="Automated",
                )
            ],
        )
        content_json, content_hash = serialize_benchmark_json(benchmark)
        self._catalog(path, "")
        with closing(CatalogDatabase(path)) as db:
            db.save_downloaded("210", content_json, content_hash, 1, version="v2.1.0")
        self._catalog_tables(path, "DROP TABLE recommendations_fts;")

        for _ in range(2):
            with closing(CatalogDatabase(path)) as db:
                found = db.search_recommendations("audit log")
                kept = db.get_downloaded("210")

        assert [(r["benchmark_id"], r["ref"]) for r in found] == [("210", "1.2.3")]
        assert (kept["content_json"], kept["content_hash"], kept["version"]) == (
            content_json,
            content_hash,
            "v2.1.0",
        )

    @staticmethod
    def _catalog_tables(path, sql):
        import sqlite3

        with closing(sqlite3.connect(path)) as con:
            con.executescript(sql)

    def test_a_downloaded_table_without_the_version_column_gets_it(self, tmp_path):
        path = tmp_path / "older.db"
        self._catalog(path, "ALTER TABLE downloaded_benchmarks DROP COLUMN version;")

        CatalogDatabase(path).close()
        db = CatalogDatabase(path)
        try:
            db.save_downloaded("210", '{"version": "v2.1.0"}', "hash", 20, version="v2.1.0")
            assert db.get_downloaded("210")["version"] == "v2.1.0"
        finally:
            db.close()

    def test_a_rebuild_that_fails_part_way_leaves_the_old_index_in_place(
        self, tmp_path, monkeypatch
    ):
        import sqlite3

        path = tmp_path / "older.db"
        self._catalog(path, self.OLD_FTS)
        write_row = CatalogDatabase._insert_fts_row
        written = []

        def fail_on_the_second_row(benchmark, session):
            if written:
                raise RuntimeError("disk full")
            written.append(benchmark.benchmark_id)
            write_row(benchmark, session)

        monkeypatch.setattr(
            CatalogDatabase, "_insert_fts_row", staticmethod(fail_on_the_second_row)
        )

        with pytest.raises(RuntimeError, match="disk full"):
            CatalogDatabase(path)

        with closing(sqlite3.connect(path)) as con:
            columns = [row[1] for row in con.execute("PRAGMA table_info(benchmarks_fts)")]
        assert columns == ["benchmark_id", "title", "platform", "community", "description"]
        assert self._index_rows(path) == ["200", "210"]

    def test_an_upgrade_another_process_finished_first_is_not_repeated(
        self, tmp_path, monkeypatch, caplog
    ):
        path = tmp_path / "current.db"
        marker = "INSERT INTO benchmarks_fts (benchmark_id, title) VALUES ('marker', 'kept');"
        self._catalog(path, marker)
        read_pending = CatalogDatabase._pending_upgrades
        from cis_bench.catalog.database import _PendingUpgrades

        answers = iter(
            [_PendingUpgrades(downloaded_columns=(("version", "VARCHAR"),), rebuild_index=True)]
        )

        def stale_then_real(connection):
            # The first look, taken before the write lock, saw an older catalog.
            return next(answers, None) or read_pending(connection)

        monkeypatch.setattr(CatalogDatabase, "_pending_upgrades", staticmethod(stale_then_real))

        with caplog.at_level("WARNING", logger="cis_bench.catalog.database"):
            CatalogDatabase(path).close()

        assert self._warnings(caplog) == []
        assert self._index_rows(path) == ["200", "210", "marker"]

    def test_an_older_catalog_that_cannot_be_written_still_opens_and_says_why(
        self, tmp_path, monkeypatch, caplog
    ):
        from sqlalchemy.exc import OperationalError

        path = tmp_path / "older.db"
        self._catalog(path, self.OLD_FTS)
        path.chmod(0o400)
        # A catalog owned by someone else: its mode cannot be changed either.
        monkeypatch.setattr(Path, "chmod", lambda *args, **kwargs: None)

        with caplog.at_level("WARNING", logger="cis_bench.catalog.database"):
            db = CatalogDatabase(path)
        try:
            assert db.get_catalog_stats()["total_benchmarks"] == 2
            # Its index has no version column, which every search now refers to.
            with pytest.raises(OperationalError, match="no such column: version"):
                db.search("kubernetes", limit=None)
        finally:
            db.close()
        (warning,) = self._warnings(caplog)
        assert warning.startswith(f"Could not update the catalog database {path} for this ")
        assert warning.endswith("Searching it needs the update.")

    def test_a_file_that_is_not_a_database_is_reported_when_it_is_first_read(
        self, tmp_path, caplog
    ):
        from sqlalchemy.exc import DatabaseError

        path = tmp_path / "notes.db"
        path.write_text("this is not a SQLite database, only a text file of some length\n" * 40)

        with caplog.at_level("WARNING", logger="cis_bench.catalog.database"):
            db = CatalogDatabase(path)
        try:
            with pytest.raises(DatabaseError, match="not a database"):
                db.search("kubernetes", limit=None)
        finally:
            db.close()
        (warning,) = self._warnings(caplog)
        assert warning.startswith(f"Could not update the catalog database {path} for this ")

    def test_the_index_row_holds_each_field_in_its_own_column(self, tmp_path):
        import sqlite3

        path = tmp_path / "current.db"
        self._catalog(path, "")

        with closing(sqlite3.connect(path)) as con:
            row = con.execute("SELECT * FROM benchmarks_fts WHERE benchmark_id = '210'").fetchone()
        assert row == (
            "210",
            "CIS Kubernetes Benchmark",
            "Container Platform",
            "CIS Kubernetes Benchmarks",
            "2.1.0",
        )

    def test_a_file_with_no_tables_is_left_empty(self, tmp_path, caplog):
        import sqlite3

        path = tmp_path / "empty.db"
        path.touch()

        with caplog.at_level("WARNING", logger="cis_bench.catalog.database"):
            CatalogDatabase(path).close()

        assert self._warnings(caplog) == []
        with closing(sqlite3.connect(path)) as con:
            assert con.execute("SELECT count(*) FROM sqlite_master").fetchone()[0] == 0


class TestMarkingWithdrawnBenchmarks:
    """Rows a complete refresh did not see become Withdrawn; Withdrawn rows are never latest."""

    def _insert(self, db, bid, title, version, status="Published"):
        db.insert_benchmark(
            {
                "benchmark_id": bid,
                "title": title,
                "version": version,
                "url": f"https://workbench.cisecurity.org/benchmarks/{bid}",
                "status": status,
            }
        )

    def test_rows_not_seen_become_withdrawn_and_are_counted_once(self, temp_db):
        self._insert(temp_db, "1", "CIS Foo Benchmark", "v1.0.0")
        self._insert(temp_db, "2", "CIS Bar Benchmark", "v1.0.0")
        self._insert(temp_db, "3", "CIS Baz Benchmark", "v1.0.0", status="Archived")
        temp_db.mark_latest_versions()
        assert temp_db.get_benchmark("1")["is_latest"] is True

        assert temp_db.mark_withdrawn_except({"2"}) == 2
        assert temp_db.mark_withdrawn_except({"2"}) == 0

        assert temp_db.get_benchmark("1")["status"] == "Withdrawn"
        assert temp_db.get_benchmark("1")["is_latest"] is False
        assert temp_db.get_benchmark("2")["status"] == "Published"
        assert temp_db.get_benchmark("2")["is_latest"] is True
        assert temp_db.get_benchmark("3")["status"] == "Withdrawn"

    def test_the_statistics_count_withdrawn_rows_separately(self, temp_db):
        self._insert(temp_db, "1", "CIS Foo Benchmark", "v1.0.0")
        self._insert(temp_db, "2", "CIS Bar Benchmark", "v1.0.0")
        temp_db.mark_withdrawn_except({"2"})

        stats = temp_db.get_catalog_stats()

        assert stats["total_benchmarks"] == 2
        assert stats["published_benchmarks"] == 1
        assert stats["withdrawn_benchmarks"] == 1

    def test_a_withdrawn_row_is_never_the_latest_release(self, temp_db):
        self._insert(temp_db, "1", "CIS Foo Benchmark", "v2.0.0")
        self._insert(temp_db, "2", "CIS Foo Benchmark", "v1.0.0")
        temp_db.mark_withdrawn_except({"2"})

        temp_db.mark_latest_versions()

        assert temp_db.get_benchmark("1")["is_latest"] is False
        assert temp_db.get_benchmark("2")["is_latest"] is True

    def test_the_withdrawn_status_is_backfilled_into_an_older_catalog(self, tmp_path):
        import sqlite3

        db = CatalogDatabase(tmp_path / "older.db")
        db.initialize_schema()
        db.close()
        with closing(sqlite3.connect(tmp_path / "older.db")) as con:
            con.execute("DELETE FROM benchmark_statuses WHERE name = 'Withdrawn'")
            con.commit()

        db = CatalogDatabase(tmp_path / "older.db")
        db.initialize_schema()
        try:
            self._insert(db, "1", "CIS Foo Benchmark", "v1.0.0")
            assert db.mark_withdrawn_except(set()) == 1
            assert db.get_benchmark("1")["status"] == "Withdrawn"
        finally:
            db.close()


class TestPublishDatesAndTheUpdateRule:
    """A release's WorkBench publish date lives on its catalog row (what WorkBench shows now);
    the cached row keeps the date of the copy we hold. One rule says whether a copy is behind."""

    @pytest.fixture
    def db(self, temp_db):
        temp_db.insert_benchmark(
            {
                "benchmark_id": "23598",
                "title": "CIS AlmaLinux OS 8 Benchmark",
                "version": "v4.0.0",
                "url": "https://workbench.cisecurity.org/benchmarks/23598",
                "status": "Published",
            }
        )
        return temp_db

    def test_the_cached_row_keeps_the_copy_publish_date(self, db):
        from datetime import date

        db.save_downloaded(
            "23598", "{}", "h", 1, version="v4.0.0", published_date=date(2025, 8, 28)
        )

        assert db.get_downloaded("23598")["published_date"] == date(2025, 8, 28)

    def test_the_catalog_row_takes_the_date_workbench_shows(self, db):
        from datetime import date

        db.record_page(
            "23598", BenchmarkPage(title="CIS Benchmark", published_date=date(2025, 8, 28))
        )

        assert db.get_benchmark("23598")["published_date"] == date(2025, 8, 28)

    def test_a_catalog_refresh_keeps_a_publish_date_already_read(self, db):
        from datetime import date

        db.record_page(
            "23598", BenchmarkPage(title="CIS Benchmark", published_date=date(2025, 8, 28))
        )
        db.insert_benchmark(
            {
                "benchmark_id": "23598",
                "title": "CIS AlmaLinux OS 8 Benchmark",
                "version": "v4.0.0",
                "url": "https://workbench.cisecurity.org/benchmarks/23598",
                "status": "Published",
            }
        )

        assert db.get_benchmark("23598")["published_date"] == date(2025, 8, 28)

    def test_a_listing_row_cannot_overwrite_a_publish_date_read_from_the_page(self, db):
        from datetime import date

        db.record_page(
            "23598", BenchmarkPage(title="CIS Benchmark", published_date=date(2025, 8, 28))
        )
        db.insert_benchmark(
            {
                "benchmark_id": "23598",
                "title": "CIS AlmaLinux OS 8 Benchmark",
                "version": "v4.0.0",
                "url": "https://workbench.cisecurity.org/benchmarks/23598",
                "status": "Published",
                "published_date": "not from the listing",
            }
        )

        assert db.get_benchmark("23598")["published_date"] == date(2025, 8, 28)

    def test_a_page_records_its_description_on_the_catalog_row(self, db):
        db.record_page(
            "23598",
            BenchmarkPage(
                title="CIS AlmaLinux OS 8 Benchmark", description="Guidance for AlmaLinux."
            ),
        )

        assert db.get_benchmark("23598")["description"] == "Guidance for AlmaLinux."

    def test_what_a_page_does_not_carry_does_not_erase_what_is_known(self, db):
        from datetime import date

        db.record_page(
            "23598",
            BenchmarkPage(title="t", published_date=date(2025, 8, 28), description="Known."),
        )
        db.record_page("23598", BenchmarkPage(title="t"))

        row = db.get_benchmark("23598")
        assert (row["published_date"], row["description"]) == (date(2025, 8, 28), "Known.")

    def test_a_listing_row_cannot_overwrite_the_description_read_from_the_page(self, db):
        db.record_page("23598", BenchmarkPage(title="t", description="From the page."))
        db.insert_benchmark(
            {
                "benchmark_id": "23598",
                "title": "CIS AlmaLinux OS 8 Benchmark",
                "version": "v4.0.0",
                "url": "https://workbench.cisecurity.org/benchmarks/23598",
                "status": "Published",
                "description": "not from the listing",
            }
        )

        assert db.get_benchmark("23598")["description"] == "From the page."

    def test_search_does_not_match_description_words(self, db):
        db.record_page("23598", BenchmarkPage(title="t", description="kubelet etcd guidance"))

        assert db.search("kubelet", limit=None) == []

    def test_a_page_for_a_release_the_catalog_does_not_list_is_ignored(self, db):
        db.record_page("99999", BenchmarkPage(title="t", description="x"))

        assert db.get_benchmark("99999") is None

    def test_a_catalog_row_carries_only_what_workbench_provides(self, db):
        row = db.get_benchmark("23598")

        assert not {"metadata_json", "last_revision_date"} & set(row)
        assert row["description"] is None

    @pytest.mark.parametrize(
        ("catalog_version", "catalog_date", "copy_version", "copy_date", "expected"),
        [
            ("v4.1.0", None, "v4.0.0", None, "newer version in catalog"),
            ("v3.0.0", "2026-01-01", "v4.0.0", "2025-08-28", None),
            ("v4.0.0", "2026-01-01", "v4.0.0", "2025-08-28", "published after download"),
            ("v4.0.0", "2025-08-28", "v4.0.0", "2025-08-28", None),
            ("v4.0.0", None, "v4.0.0", "2025-08-28", None),
            # A copy cached before dates were recorded: compare with when it was downloaded
            ("v4.0.0", "2025-12-01", "v4.0.0", None, "published after download"),
            ("v4.0.0", "2025-10-01", "v4.0.0", None, None),
        ],
    )
    def test_update_reason(self, catalog_version, catalog_date, copy_version, copy_date, expected):
        from datetime import UTC, date, datetime

        from cis_bench.catalog.database import update_reason

        def as_date(text):
            return date.fromisoformat(text) if text else None

        reason = update_reason(
            catalog_version=catalog_version,
            catalog_published=as_date(catalog_date),
            copy_version=copy_version,
            copy_published=as_date(copy_date),
            downloaded_at=datetime(2025, 11, 1, 12, tzinfo=UTC),
        )

        assert reason == expected

    def test_check_updates_reports_the_date_workbench_shows_now(self, db):
        from datetime import date

        db.save_downloaded(
            "23598", "{}", "h", 1, version="v4.0.0", published_date=date(2025, 8, 28)
        )
        db.record_page(
            "23598", BenchmarkPage(title="CIS Benchmark", published_date=date(2026, 1, 5))
        )

        (update,) = db.check_updates_available()

        assert update["reason"] == "published after download"
        assert update["published_date"] == date(2026, 1, 5)

    def test_a_search_without_words_lists_by_title_then_id(self, db):
        rows = (
            ("300", "CIS Zeta Benchmark"),
            ("100", "CIS Beta Benchmark"),
            ("20", "CIS Beta Benchmark"),
        )
        for benchmark_id, title in rows:
            db.insert_benchmark(
                {
                    "benchmark_id": benchmark_id,
                    "title": title,
                    "version": "v1.0.0",
                    "url": f"https://workbench.cisecurity.org/benchmarks/{benchmark_id}",
                    "status": "Published",
                }
            )

        ids = [str(row["benchmark_id"]) for row in db.search("", limit=None)]

        # AlmaLinux sorts before Beta; the two Betas by numeric ID (20 before 100)
        assert ids == ["23598", "20", "100", "300"]
