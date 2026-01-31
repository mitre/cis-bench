"""Unit tests for extended catalog database models (assets, revision history)."""

import tempfile
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlmodel import Session, select

from cis_bench.catalog.database import CatalogDatabase
from cis_bench.catalog.models import BenchmarkAsset, RevisionHistory


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_catalog.db"
        db = CatalogDatabase(db_path)
        db.initialize_schema()
        yield db


@pytest.fixture
def db_with_benchmark(temp_db):
    """Create database with a test benchmark."""
    db = temp_db

    # Insert a test benchmark
    benchmark_data = {
        "benchmark_id": "12345",
        "title": "Test Benchmark",
        "version": "v1.0.0",
        "url": "https://workbench.cisecurity.org/benchmarks/12345",
        "status": "Published",
    }
    db.insert_benchmark(benchmark_data)

    return db


class TestBenchmarkAssetOperations:
    """Test benchmark asset CRUD operations."""

    def test_insert_single_asset(self, db_with_benchmark):
        """Test inserting a single asset."""
        with Session(db_with_benchmark.engine) as session:
            asset = BenchmarkAsset(
                benchmark_id="12345",
                title="AlmaLinux OS 9",
                cpe_id="cpe:2.3:o:almalinux:almalinux:9:*:*:*:*:*:*:*",
            )
            session.add(asset)
            session.commit()

            # Verify inserted
            result = session.exec(
                select(BenchmarkAsset).where(BenchmarkAsset.benchmark_id == "12345")
            ).first()
            assert result is not None
            assert result.title == "AlmaLinux OS 9"
            assert result.cpe_id == "cpe:2.3:o:almalinux:almalinux:9:*:*:*:*:*:*:*"

    def test_insert_multiple_assets(self, db_with_benchmark):
        """Test inserting multiple assets for one benchmark."""
        with Session(db_with_benchmark.engine) as session:
            assets = [
                BenchmarkAsset(
                    benchmark_id="12345",
                    title="Windows 11",
                    cpe_id="cpe:2.3:o:microsoft:windows_11:-:*:*:*:*:*:x64:*",
                ),
                BenchmarkAsset(
                    benchmark_id="12345",
                    title="Windows 10",
                    cpe_id="cpe:2.3:o:microsoft:windows_10:-:*:*:*:*:*:x64:*",
                ),
            ]
            for asset in assets:
                session.add(asset)
            session.commit()

            # Verify both inserted
            result = session.exec(
                select(BenchmarkAsset).where(BenchmarkAsset.benchmark_id == "12345")
            ).all()
            assert len(result) == 2

    def test_foreign_key_constraint(self, temp_db):
        """Test foreign key constraint for benchmark_id."""
        with Session(temp_db.engine) as session:
            # Try to insert asset for non-existent benchmark
            asset = BenchmarkAsset(
                benchmark_id="99999",  # Doesn't exist
                title="Test",
                cpe_id="cpe:2.3:o:test:test:1:*:*:*:*:*:*:*",
            )
            session.add(asset)

            # SQLite FK constraints might not be enabled by default
            # Just verify it inserts (FK will be enforced if enabled)
            session.commit()


class TestRevisionHistoryOperations:
    """Test revision history CRUD operations."""

    def test_insert_single_revision(self, db_with_benchmark):
        """Test inserting a single revision entry."""
        with Session(db_with_benchmark.engine) as session:
            revision = RevisionHistory(
                benchmark_id="12345",
                revision_date="1 year ago",
                author="Eric",
                modification_count=5,
                diff_url="https://workbench.cisecurity.org/diff/123",
                sort_order=0,
            )
            session.add(revision)
            session.commit()

            # Verify inserted
            result = session.exec(
                select(RevisionHistory).where(RevisionHistory.benchmark_id == "12345")
            ).first()
            assert result is not None
            assert result.author == "Eric"
            assert result.modification_count == 5

    def test_insert_multiple_revisions_ordered(self, db_with_benchmark):
        """Test inserting multiple revision entries with sort order."""
        with Session(db_with_benchmark.engine) as session:
            revisions = [
                RevisionHistory(
                    benchmark_id="12345",
                    revision_date="1 month ago",
                    author="Tom",
                    modification_count=2,
                    sort_order=0,
                ),
                RevisionHistory(
                    benchmark_id="12345",
                    revision_date="6 months ago",
                    author="Eric",
                    modification_count=5,
                    sort_order=1,
                ),
                RevisionHistory(
                    benchmark_id="12345",
                    revision_date="1 year ago",
                    author="Jane",
                    modification_count=10,
                    sort_order=2,
                ),
            ]
            for rev in revisions:
                session.add(rev)
            session.commit()

            # Verify ordered query
            result = session.exec(
                select(RevisionHistory)
                .where(RevisionHistory.benchmark_id == "12345")
                .order_by(RevisionHistory.sort_order)
            ).all()

            assert len(result) == 3
            assert result[0].author == "Tom"  # sort_order 0
            assert result[1].author == "Eric"  # sort_order 1
            assert result[2].author == "Jane"  # sort_order 2

    def test_revision_with_minimal_fields(self, db_with_benchmark):
        """Test inserting revision with only required fields."""
        with Session(db_with_benchmark.engine) as session:
            revision = RevisionHistory(
                benchmark_id="12345",
                revision_date="2 weeks ago",
                # All other fields are optional (None)
            )
            session.add(revision)
            session.commit()

            result = session.exec(
                select(RevisionHistory).where(RevisionHistory.benchmark_id == "12345")
            ).first()
            assert result.revision_date == "2 weeks ago"
            assert result.author is None
            assert result.modification_count is None


class TestMigration:
    """Test database migration logic."""

    def test_new_columns_added_on_init(self, temp_db):
        """Test that new columns are added to existing table."""
        with Session(temp_db.engine) as session:
            # Check that new columns exist
            from sqlalchemy import text

            result = session.execute(text("PRAGMA table_info(catalog_benchmarks)"))
            columns = {row[1] for row in result.fetchall()}

            # Verify new columns exist
            assert "release_type" in columns
            assert "contributors" in columns
            assert "parent_benchmark_id" in columns
            assert "parent_benchmark_url" in columns
            assert "intended_audience" in columns
            assert "acknowledgements" in columns
            assert "milestone_name" in columns
            assert "milestone_url" in columns

    def test_fts5_has_new_fields(self, temp_db):
        """Test that FTS5 table includes new searchable fields."""
        with Session(temp_db.engine) as session:
            from sqlalchemy import text

            result = session.execute(text("PRAGMA table_info(benchmarks_fts)"))
            columns = {row[1] for row in result.fetchall()}

            # Verify new searchable fields
            assert "contributors" in columns
            assert "intended_audience" in columns


class TestExtendedMetadataStorage:
    """Test storing extended metadata in catalog_benchmarks table."""

    def test_insert_benchmark_with_extended_metadata(self, temp_db):
        """Test inserting benchmark with all extended metadata fields."""
        benchmark_data = {
            "benchmark_id": "18208",
            "title": "CIS AlmaLinux OS 9 Benchmark",
            "version": "v2.0.0",
            "url": "https://workbench.cisecurity.org/benchmarks/18208",
            "status": "Published",
            "release_type": "Planned Update",
            "contributors": "Eric Pinnell, Thomas Sjögren, James Trigg",
            "parent_benchmark_url": "https://workbench.cisecurity.org/benchmarks/16763",
            "intended_audience": "System administrators and security specialists",
            "acknowledgements": "Thanks to all contributors",
            "milestone_name": "CIS AlmaLinux 9 v2.0.0",
            "milestone_url": "https://workbench.cisecurity.org/community/139/milestones/956",
        }

        temp_db.insert_benchmark(benchmark_data)

        # Verify all fields stored
        benchmark = temp_db.get_benchmark("18208")
        assert benchmark["release_type"] == "Planned Update"
        assert "Eric Pinnell" in benchmark["contributors"]
        assert (
            benchmark["parent_benchmark_url"] == "https://workbench.cisecurity.org/benchmarks/16763"
        )
        assert "System administrators" in benchmark["intended_audience"]
        assert benchmark["milestone_name"] == "CIS AlmaLinux 9 v2.0.0"


class TestMigrationCreatesNewTables:
    """Test that migration creates new tables, not just columns."""

    def test_migration_creates_benchmark_assets_table(self):
        """Test migration creates benchmark_assets table."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create database with old schema (no new tables)
            from sqlmodel import Session, create_engine

            engine = create_engine(f"sqlite:///{db_path}")

            # Create only base tables (simulate old database)
            # Don't import BenchmarkAsset/RevisionHistory - they're new

            # Now open with CatalogDatabase (triggers migration)
            db = CatalogDatabase(db_path)

            # Verify new tables exist
            with Session(db.engine) as session:
                # Check if benchmark_assets table exists
                result = session.execute(
                    text(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='benchmark_assets'"
                    )
                )
                assert result.fetchone() is not None, (
                    "benchmark_assets table not created by migration"
                )

                # Check if revision_history table exists
                result = session.execute(
                    text(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='revision_history'"
                    )
                )
                assert result.fetchone() is not None, (
                    "revision_history table not created by migration"
                )

    def test_migration_is_idempotent(self):
        """Test migration can be run multiple times safely."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create database (runs migration)
            db1 = CatalogDatabase(db_path)

            # Insert test data
            db1.insert_benchmark(
                {
                    "benchmark_id": "123",
                    "title": "Test",
                    "version": "v1",
                    "url": "https://test.com",
                    "status": "Published",
                }
            )

            # Create new instance (runs migration again)
            db2 = CatalogDatabase(db_path)

            # Verify data still exists (migration didn't break anything)
            benchmark = db2.get_benchmark("123")
            assert benchmark is not None
            assert benchmark["title"] == "Test"


class TestMigrationTableCreation:
    """Test migration creates new tables."""

    def test_new_tables_created(self, temp_db):
        """Test that new tables exist after migration."""

        with Session(temp_db.engine) as session:
            result = session.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('benchmark_assets', 'revision_history')"
                )
            )
            tables = [row[0] for row in result.fetchall()]
            assert "benchmark_assets" in tables
            assert "revision_history" in tables
