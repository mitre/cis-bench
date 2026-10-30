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
        try:
            yield db
        finally:
            db.engine.dispose()


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
            reopened.engine.dispose()
            db.engine.dispose()

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

    _EXPECTED_DEFAULT_STATUSES = [
        ("Published", True, 1),
        ("Accepted", True, 2),
        ("Draft", False, 3),
        ("Archived", False, 4),
        ("Rejected", False, 5),
        ("Final Update", False, 6),
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

        db = CatalogDatabase(tmp_path / "legacy_catalog.db")
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
        assert [r["benchmark_id"] for r in temp_db.search("amazon", platform_type="cloud")] == [
            "7001"
        ]
        assert [r["benchmark_id"] for r in temp_db.search("", platform_type="cloud")] == ["7001"]

        with sqlite3.connect(temp_db.db_path) as conn:
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

    def test_search_dotted_version_and_hyphenated_queries(self, populated_db):
        """Test dotted versions and hyphenated terms match cleanly against SQLite FTS5."""
        ubuntu_results = populated_db.search("ubuntu 20.04")
        assert [row["benchmark_id"] for row in ubuntu_results] == ["1"]

        rhel_results = populated_db.search("red-hat")
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
                "description": "Ubuntu and Oracle database hardening",
            }
        )

        oracle_results = populated_db.search("OR")
        assert [row["benchmark_id"] for row in oracle_results] == ["6"]

        combined_results = populated_db.search("ubuntu AND")
        assert [row["benchmark_id"] for row in combined_results] == ["6"]

        assert populated_db.search("NOT") == []
        assert populated_db.search("NEAR") == []

    def test_search_punctuation_only_returns_empty_without_listing_all(self, populated_db):
        """Test punctuation-only queries return empty list while whitespace lists all published."""
        assert populated_db.search("...") == []
        assert populated_db.search("!!!") == []
        assert populated_db.search("***") == []
        assert populated_db.search("___") == []

        whitespace_results = populated_db.search("   ")
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
                row["benchmark_id"] for row in populated_db.search("", status=status_arg)
            )
            fts_ids = sorted(
                row["benchmark_id"] for row in populated_db.search("benchmark", status=status_arg)
            )
            assert empty_ids == expected_all_ids
            assert fts_ids == expected_all_ids

        catalog_search = CatalogSearch(populated_db)
        assert (
            sorted(row["benchmark_id"] for row in catalog_search.search("", status="all"))
            == expected_all_ids
        )
        assert sorted(
            row["benchmark_id"]
            for row in catalog_search.search("linux", status=None, platform_type="os")
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
            assert created.sort_order == 7
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

        final_results = temp_db.search("CentOS", status="Final Update")
        assert [row["benchmark_id"] for row in final_results] == ["9001"]

        sunset_results = temp_db.search("Appliance", status="Sunset")
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
        competing_db.engine.dispose()


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

    def test_check_updates_available_ignores_null_catalog_revision_dates(self, temp_db):
        """check_updates_available skips benchmarks whose catalog last_revision_date is NULL."""
        cases = [
            ("201", None, None),
            ("202", None, "2024-10-01"),
            ("203", "2024-11-01", None),
            ("204", "2024-11-15", "2024-11-01"),
            ("205", "2024-11-01", "2024-11-01"),
        ]
        for bid, last_rev, downloaded_mod in cases:
            temp_db.insert_benchmark(
                {
                    "benchmark_id": bid,
                    "title": f"Benchmark {bid}",
                    "url": f"https://workbench.cisecurity.org/benchmarks/{bid}",
                    "status": "Published",
                    "last_revision_date": last_rev,
                }
            )
            temp_db.save_downloaded(
                bid,
                '{"recommendations": []}',
                f"hash-{bid}",
                0,
                workbench_last_modified=downloaded_mod,
            )

        updates = temp_db.check_updates_available()

        assert [row["benchmark_id"] for row in updates] == ["204", "203"]


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
            "downloaded_benchmarks": 2,
            "platforms": 2,
            "communities": 2,
        }
        select_statements = [
            stmt for stmt in statements if stmt.lstrip().upper().startswith("SELECT")
        ]
        assert len(select_statements) == 5
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
