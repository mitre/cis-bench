"""Catalog database operations using SQLModel.

Provides CRUD operations, search, and management for the CIS benchmark catalog.
"""

import hashlib
import logging
import re
import sqlite3
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from sqlalchemy import (
    Select,
    column,
    event,
    func,
    literal_column,
    table,
    text,
)
from sqlalchemy import (
    select as sa_select,
)
from sqlalchemy.engine import URL, Connection
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, SQLModel, col, create_engine, select

from cis_bench.catalog.fts import build_fts_query
from cis_bench.catalog.models import (
    BenchmarkCollection,
    BenchmarkStatus,
    BenchmarkStatusModel,
    CatalogBenchmark,
    Collection,
    Community,
    DownloadedBenchmark,
    Owner,
    Platform,
    ScrapeMetadata,
    utcnow,
)
from cis_bench.models.benchmark import Benchmark

logger = logging.getLogger(__name__)

DEFAULT_BENCHMARK_STATUSES: tuple[tuple[str, bool, int], ...] = (
    (BenchmarkStatus.PUBLISHED.value, True, 1),
    (BenchmarkStatus.ACCEPTED.value, True, 2),
    (BenchmarkStatus.DRAFT.value, False, 3),
    (BenchmarkStatus.ARCHIVED.value, False, 4),
    (BenchmarkStatus.REJECTED.value, False, 5),
    (BenchmarkStatus.FINAL_UPDATE.value, False, 6),
)

_TRAILING_VERSION_RE = re.compile(r"\s+v\d+(?:\.[\w-]+)*\s*$", re.IGNORECASE)
LookupModelT = TypeVar("LookupModelT", bound=SQLModel)


def _normalize_base_title(title: str | None) -> str:
    """Strip a trailing version suffix (e.g., ' v2.0.1') without truncating product words."""
    if not title:
        return ""
    return _TRAILING_VERSION_RE.sub("", title.strip())


def normalize_status_filter(status: str | None) -> str | None:
    """Normalize a benchmark status filter, treating None, blank, or 'all' as unfiltered."""
    if status is None:
        return None
    stripped = status.strip()
    if not stripped or stripped.lower() == "all":
        return None
    return stripped


def serialize_benchmark_json(benchmark: Benchmark) -> tuple[str, str]:
    """Serialize a Benchmark to canonical JSON and return ``(content_json, sha256_hex)``.

    ``content_json`` stores the complete Benchmark payload, while ``content_hash``
    hashes the canonical payload excluding the transient ``downloaded_at`` scrape
    timestamp so identical benchmark content hashes deterministically across scrapes.
    """
    content_json = benchmark.model_dump_json(indent=2)
    hashable_json = benchmark.model_dump_json(indent=2, exclude={"downloaded_at"})
    content_hash = hashlib.sha256(hashable_json.encode("utf-8")).hexdigest()
    return content_json, content_hash


def deserialize_benchmark_json(content_json: str) -> Benchmark:
    """Validate and deserialize stored Benchmark JSON."""
    return Benchmark.model_validate_json(content_json)


def _try_chmod(path: Path, mode: int) -> None:
    """Best-effort permission tightening that tolerates shared unowned read-only files."""
    try:
        path.chmod(mode)
    except OSError as exc:
        logger.debug(f"Skipping chmod({oct(mode)}) on {path}: {exc}")


class CatalogDatabase:
    """SQLite database for CIS benchmark catalog."""

    def __init__(self, db_path: Path):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        parent_dir = self.db_path.parent
        parent_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        resolved_parent = parent_dir.resolve()
        if resolved_parent not in {Path("/"), Path(tempfile.gettempdir()).resolve()}:
            _try_chmod(parent_dir, 0o700)
        if self.db_path.exists():
            _try_chmod(self.db_path, 0o600)

        db_url = URL.create("sqlite", database=str(self.db_path))
        self.engine = create_engine(db_url, echo=False)

        @event.listens_for(self.engine, "connect")
        def _configure_sqlite_connection(
            dbapi_connection: object, _connection_record: object
        ) -> None:
            if isinstance(dbapi_connection, sqlite3.Connection):
                dbapi_connection.create_function(
                    "normalize_base_title",
                    1,
                    _normalize_base_title,
                    deterministic=True,
                )
            if self.db_path.exists():
                _try_chmod(self.db_path, 0o600)

        @event.listens_for(self.engine, "before_cursor_execute")
        def _ensure_transaction_before_savepoint(
            conn: Connection,
            _cursor: object,
            statement: str,
            _parameters: object,
            _context: object,
            _executemany: bool,
        ) -> None:
            # CPython's sqlite3 legacy transaction mode implicitly emits BEGIN before
            # DML (INSERT/UPDATE/DELETE) but not before SAVEPOINT. Starting BEGIN when
            # SAVEPOINT runs outside a transaction prevents RELEASE SAVEPOINT from
            # auto-committing while keeping read-only SELECTs lock-free.
            if statement.lstrip().upper().startswith("SAVEPOINT "):
                raw_conn = conn.connection.dbapi_connection
                if isinstance(raw_conn, sqlite3.Connection) and not raw_conn.in_transaction:
                    raw_conn.execute("BEGIN")

        logger.debug(f"Initialized catalog database: {self.db_path}")

    def initialize_schema(self):
        """Create all tables and indexes."""
        logger.info("Creating database schema")

        # Create all tables from SQLModel models
        SQLModel.metadata.create_all(self.engine)

        # Insert or backfill default statuses idempotently and create FTS5 virtual table
        with Session(self.engine) as session:
            existing_names = set(session.exec(select(BenchmarkStatusModel.name)).all())
            missing_statuses = [
                BenchmarkStatusModel(name=name, is_active=is_active, sort_order=sort_order)
                for name, is_active, sort_order in DEFAULT_BENCHMARK_STATUSES
                if name not in existing_names
            ]

            if missing_statuses:
                session.add_all(missing_statuses)
                logger.info("Inserted default benchmark statuses")

            session.execute(
                text(
                    """
                CREATE VIRTUAL TABLE IF NOT EXISTS benchmarks_fts USING fts5(
                    benchmark_id UNINDEXED,
                    title,
                    platform,
                    community,
                    description,
                    tokenize='porter unicode61'
                )
            """
                )
            )
            session.commit()
            logger.info("Created FTS5 virtual table")

        logger.info("Database schema initialized")

    def _get_or_create(
        self,
        session: Session,
        model_cls: type[LookupModelT],
        where_clause: ColumnElement[bool],
        factory: Callable[[], LookupModelT],
        on_created: Callable[[LookupModelT], None] | None = None,
    ) -> LookupModelT:
        """Fetch an existing lookup row or insert it inside a SAVEPOINT."""
        existing = session.exec(select(model_cls).where(where_clause)).first()
        if existing is not None:
            return existing

        try:
            with session.begin_nested():
                instance = factory()
                session.add(instance)
                session.flush([instance])
        except IntegrityError:
            recovered = session.exec(select(model_cls).where(where_clause)).first()
            if recovered is None:
                raise
            return recovered

        if on_created is not None:
            on_created(instance)
        return instance

    def get_or_create_platform(self, name: str, session: Session) -> Platform:
        """Get existing platform or create new one."""
        return self._get_or_create(
            session,
            Platform,
            col(Platform.name) == name,
            lambda: Platform(name=name),
        )

    def get_or_create_community(self, name: str, session: Session) -> Community:
        """Get existing community or create new one."""
        return self._get_or_create(
            session,
            Community,
            col(Community.name) == name,
            lambda: Community(name=name),
        )

    def get_or_create_owner(self, username: str, session: Session) -> Owner:
        """Get existing owner or create new one."""
        return self._get_or_create(
            session,
            Owner,
            col(Owner.username) == username,
            lambda: Owner(username=username),
        )

    def get_or_create_collection(self, name: str, session: Session) -> Collection:
        """Get existing collection or create new one."""
        return self._get_or_create(
            session,
            Collection,
            col(Collection.name) == name,
            lambda: Collection(name=name),
        )

    def get_or_create_status(self, status_name: str, session: Session) -> BenchmarkStatusModel:
        """Get existing benchmark status or register an unseen non-empty status."""
        normalized = status_name.strip() if isinstance(status_name, str) else ""
        if not normalized:
            raise ValueError("Status name cannot be empty")

        def _build_status() -> BenchmarkStatusModel:
            max_sort_order = session.exec(select(func.max(BenchmarkStatusModel.sort_order))).one()
            next_sort_order = (max_sort_order or 0) + 1
            return BenchmarkStatusModel(
                name=normalized,
                is_active=False,
                sort_order=next_sort_order,
            )

        return self._get_or_create(
            session,
            BenchmarkStatusModel,
            col(BenchmarkStatusModel.name) == normalized,
            _build_status,
            on_created=lambda created: logger.info(
                f"Registered new benchmark status: {created.name}"
            ),
        )

    def get_status_id(self, status_name: str, session: Session) -> int:
        """Get status ID by name, registering unseen non-empty statuses automatically."""
        status = self.get_or_create_status(status_name, session)
        if status.status_id is None:
            raise RuntimeError(f"Failed to assign status_id for status: {status.name}")
        return status.status_id

    def insert_benchmark(self, benchmark_data: dict):
        """Insert or update catalog benchmark.

        Args:
            benchmark_data: Dictionary with benchmark fields
                           platform, community, owner, collections as strings
                           (will be normalized to FK references)
        """
        if not isinstance(benchmark_data, dict):
            raise TypeError("benchmark_data must be a dictionary")

        required: dict[str, str] = {}
        for field_name in ("benchmark_id", "title", "url"):
            raw_value = benchmark_data.get(field_name)
            if not isinstance(raw_value, str) or not raw_value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
            required[field_name] = raw_value.strip()

        benchmark_id = required["benchmark_id"]
        title = required["title"]
        url = required["url"]

        with Session(self.engine) as session:
            # Get or create FK references
            platform = None
            if benchmark_data.get("platform"):
                platform = self.get_or_create_platform(benchmark_data["platform"], session)

            community = None
            if benchmark_data.get("community"):
                community = self.get_or_create_community(benchmark_data["community"], session)

            owner = None
            if benchmark_data.get("owner"):
                owner = self.get_or_create_owner(benchmark_data["owner"], session)

            status_id = self.get_status_id(benchmark_data.get("status", "Published"), session)

            # Check if benchmark exists
            existing = session.get(CatalogBenchmark, benchmark_id)

            if existing:
                # Update existing
                existing.title = title
                existing.url = url
                for key, value in benchmark_data.items():
                    if key not in {
                        "benchmark_id",
                        "title",
                        "url",
                        "platform",
                        "community",
                        "owner",
                        "status",
                        "collections",
                    }:
                        setattr(existing, key, value)

                existing.platform_id = platform.platform_id if platform else None
                existing.community_id = community.community_id if community else None
                existing.owner_id = owner.owner_id if owner else None
                existing.status_id = status_id

                benchmark = existing
            else:
                # Create new
                benchmark = CatalogBenchmark(
                    benchmark_id=benchmark_id,
                    title=title,
                    version=benchmark_data.get("version"),
                    url=url,
                    status_id=status_id,
                    platform_id=platform.platform_id if platform else None,
                    platform_type=benchmark_data.get("platform_type"),
                    community_id=community.community_id if community else None,
                    owner_id=owner.owner_id if owner else None,
                    published_date=benchmark_data.get("published_date"),
                    last_revision_date=benchmark_data.get("last_revision_date"),
                    description=benchmark_data.get("description"),
                    is_latest=bool(benchmark_data.get("is_latest", False)),
                    is_vnext=bool(benchmark_data.get("is_vnext", False)),
                    metadata_json=benchmark_data.get("metadata_json"),
                )
                session.add(benchmark)

            # Handle collections (many-to-many)
            if "collections" in benchmark_data:
                # Clear existing
                session.execute(
                    text("DELETE FROM benchmark_collections WHERE benchmark_id = :bid"),
                    {"bid": benchmark_id},
                )

                unique_collections = list(
                    dict.fromkeys(
                        c.strip()
                        for c in (benchmark_data["collections"] or [])
                        if isinstance(c, str) and c.strip()
                    )
                )
                for coll_name in unique_collections:
                    collection = self.get_or_create_collection(coll_name, session)
                    if collection.collection_id is None:
                        raise RuntimeError(f"Failed to assign collection_id for {coll_name}")
                    session.add(
                        BenchmarkCollection(
                            benchmark_id=benchmark_id,
                            collection_id=collection.collection_id,
                        )
                    )

            # Update FTS5 (before commit so it's in same transaction)
            self._update_fts(benchmark_id, session)

            session.commit()

            logger.debug(f"Inserted/updated benchmark: {benchmark_id}")

    def _update_fts(self, benchmark_id: str, session: Session):
        """Update FTS5 index for benchmark."""
        # Get full benchmark with joins
        benchmark = session.get(CatalogBenchmark, benchmark_id)

        if not benchmark:
            return

        # Delete old FTS entry
        session.execute(
            text("DELETE FROM benchmarks_fts WHERE benchmark_id = :bid"), {"bid": benchmark_id}
        )

        # Insert new FTS entry
        platform_name = benchmark.platform.name if benchmark.platform else ""
        community_name = benchmark.community.name if benchmark.community else ""

        session.execute(
            text(
                """
            INSERT INTO benchmarks_fts (benchmark_id, title, platform, community, description)
            VALUES (:bid, :title, :platform, :community, :desc)
        """
            ),
            {
                "bid": benchmark_id,
                "title": benchmark.title,
                "platform": platform_name,
                "community": community_name,
                "desc": benchmark.description or "",
            },
        )
        session.flush()  # Ensure FTS insert executes

    @staticmethod
    def _build_search_query(
        fts_query: str | None,
        platform: str | None,
        platform_type: str | None,
        status: str | None,
        latest_only: bool,
        limit: int,
    ) -> Select[tuple[object, ...]]:
        """Build parameterized SQLAlchemy SELECT shared by FTS5 search and empty-query listing."""
        fts_table = table("benchmarks_fts", column("benchmark_id"), column("rank"))
        columns: list[ColumnElement[object]] = [
            col(CatalogBenchmark.benchmark_id).label("benchmark_id"),
            col(CatalogBenchmark.title).label("title"),
            col(CatalogBenchmark.version).label("version"),
            col(CatalogBenchmark.url).label("url"),
            col(BenchmarkStatusModel.name).label("status"),
            col(Platform.name).label("platform"),
            col(CatalogBenchmark.platform_type).label("platform_type"),
            col(Community.name).label("community"),
            col(Owner.username).label("owner"),
            col(CatalogBenchmark.published_date).label("published_date"),
            col(CatalogBenchmark.is_latest).label("is_latest"),
            col(CatalogBenchmark.description).label("description"),
        ]
        if fts_query is not None:
            columns.append(fts_table.c.rank.label("rank"))

        stmt: Select[tuple[object, ...]] = sa_select(*columns).select_from(CatalogBenchmark)
        if fts_query is not None:
            stmt = stmt.join(
                fts_table,
                col(CatalogBenchmark.benchmark_id) == fts_table.c.benchmark_id,
            )

        stmt = (
            stmt.join(
                BenchmarkStatusModel,
                col(CatalogBenchmark.status_id) == col(BenchmarkStatusModel.status_id),
            )
            .outerjoin(
                Platform,
                col(CatalogBenchmark.platform_id) == col(Platform.platform_id),
            )
            .outerjoin(
                Community,
                col(CatalogBenchmark.community_id) == col(Community.community_id),
            )
            .outerjoin(
                Owner,
                col(CatalogBenchmark.owner_id) == col(Owner.owner_id),
            )
        )

        if fts_query is not None:
            stmt = stmt.where(literal_column("benchmarks_fts").op("MATCH")(fts_query))

        if platform:
            stmt = stmt.where(col(Platform.name) == platform)

        if platform_type:
            stmt = stmt.where(col(CatalogBenchmark.platform_type) == platform_type)

        normalized_status = normalize_status_filter(status)
        if normalized_status is not None:
            stmt = stmt.where(col(BenchmarkStatusModel.name) == normalized_status)

        if latest_only:
            stmt = stmt.where(col(CatalogBenchmark.is_latest).is_(True))

        if fts_query is not None:
            stmt = stmt.order_by(fts_table.c.rank)
        else:
            stmt = stmt.order_by(col(CatalogBenchmark.published_date).desc())

        return stmt.limit(limit)

    def search(
        self,
        query: str,
        platform: str | None = None,
        platform_type: str | None = None,
        status: str | None = "Published",
        latest_only: bool = False,
        limit: int = 50,
    ) -> list[dict]:
        """Search catalog using FTS5 fuzzy matching or list benchmarks when query is blank.

        Args:
            query: Search query (supports wildcards)
            platform: Filter by platform name
            platform_type: Filter by platform category (cloud, os, database, container, application)
            status: Filter by status (default: Published; None or 'all' returns all statuses)
            latest_only: Only latest versions
            limit: Max results

        Returns:
            List of benchmark dictionaries with all joined data
        """
        fts_query: str | None = None
        if query and query.strip():
            fts_query = build_fts_query(query)
            if not fts_query:
                return []

        stmt = self._build_search_query(
            fts_query=fts_query,
            platform=platform,
            platform_type=platform_type,
            status=status,
            latest_only=latest_only,
            limit=limit,
        )

        with Session(self.engine) as session:
            result = session.execute(stmt)
            return [dict(row._mapping) for row in result.fetchall()]

    def get_benchmark(self, benchmark_id: str) -> dict | None:
        """Get single benchmark with all metadata."""
        with Session(self.engine) as session:
            benchmark = session.get(CatalogBenchmark, benchmark_id)

            if not benchmark:
                return None

            collection_names = list(
                session.exec(
                    select(Collection.name)
                    .join(
                        BenchmarkCollection,
                        col(Collection.collection_id) == col(BenchmarkCollection.collection_id),
                    )
                    .where(col(BenchmarkCollection.benchmark_id) == benchmark_id)
                    .order_by(col(Collection.name))
                ).all()
            )

            return {
                "benchmark_id": benchmark.benchmark_id,
                "title": benchmark.title,
                "version": benchmark.version,
                "url": benchmark.url,
                "status": benchmark.status.name,
                "platform": benchmark.platform.name if benchmark.platform else None,
                "platform_type": benchmark.platform_type,
                "community": benchmark.community.name if benchmark.community else None,
                "owner": benchmark.owner.username if benchmark.owner else None,
                "published_date": benchmark.published_date,
                "last_revision_date": benchmark.last_revision_date,
                "description": benchmark.description,
                "is_latest": benchmark.is_latest,
                "is_vnext": benchmark.is_vnext,
                "collections": collection_names,
                "metadata_json": benchmark.metadata_json,
            }

    def list_platforms(self) -> list[dict]:
        """List all platforms with active benchmark counts."""
        with Session(self.engine) as session:
            sql = """
                SELECT p.name, COUNT(b.benchmark_id) as count
                FROM platforms p
                JOIN catalog_benchmarks b ON p.platform_id = b.platform_id
                JOIN benchmark_statuses s ON b.status_id = s.status_id
                WHERE s.is_active = 1
                GROUP BY p.name
                ORDER BY count DESC, p.name
            """
            result = session.execute(text(sql))
            return [{"name": row[0], "count": row[1]} for row in result.fetchall()]

    def list_communities(self) -> list[dict]:
        """List all communities with benchmark counts."""
        with Session(self.engine) as session:
            communities = session.exec(
                select(Community).order_by(col(Community.benchmark_count).desc())
            ).all()

            return [
                {"name": c.name, "benchmark_count": c.benchmark_count, "url": c.url}
                for c in communities
            ]

    def mark_latest_versions(self):
        """Mark latest version for each normalized base title and status group."""
        with Session(self.engine) as session:
            sql = """
                WITH normalized AS (
                    SELECT
                        benchmark_id,
                        status_id,
                        published_date,
                        normalize_base_title(title) AS base_title
                    FROM catalog_benchmarks
                ),
                group_latest AS (
                    SELECT
                        base_title,
                        status_id,
                        MAX(published_date) AS max_published_date
                    FROM normalized
                    GROUP BY base_title, status_id
                )
                UPDATE catalog_benchmarks
                SET is_latest = CASE
                    WHEN benchmark_id IN (
                        SELECT n.benchmark_id
                        FROM normalized n
                        JOIN group_latest g
                          ON n.base_title = g.base_title
                         AND n.status_id = g.status_id
                        WHERE g.max_published_date IS NULL
                           OR n.published_date = g.max_published_date
                    )
                    THEN 1
                    ELSE 0
                END
            """
            session.execute(text(sql))
            session.commit()

            logger.info("Updated is_latest flags")

    def save_downloaded(
        self,
        benchmark_id: str,
        content_json: str,
        content_hash: str,
        recommendation_count: int,
        workbench_last_modified: str | None = None,
    ):
        """Save downloaded benchmark content."""
        now = utcnow()
        with Session(self.engine) as session:
            existing = session.get(DownloadedBenchmark, benchmark_id)

            if existing:
                existing.content_json = content_json
                existing.content_hash = content_hash
                existing.recommendation_count = recommendation_count
                existing.file_size = len(content_json)
                existing.workbench_last_modified = workbench_last_modified
                existing.downloaded_at = now
                existing.last_accessed = now
            else:
                downloaded = DownloadedBenchmark(
                    benchmark_id=benchmark_id,
                    content_json=content_json,
                    content_hash=content_hash,
                    file_size=len(content_json),
                    recommendation_count=recommendation_count,
                    downloaded_at=now,
                    last_accessed=now,
                    workbench_last_modified=workbench_last_modified,
                )
                session.add(downloaded)

            session.commit()
            logger.debug(f"Saved downloaded benchmark: {benchmark_id}")

    def get_downloaded(self, benchmark_id: str) -> dict | None:
        """Get downloaded benchmark."""
        with Session(self.engine) as session:
            downloaded = session.get(DownloadedBenchmark, benchmark_id)

            if not downloaded:
                return None

            return {
                "benchmark_id": downloaded.benchmark_id,
                "content_json": downloaded.content_json,
                "content_hash": downloaded.content_hash,
                "downloaded_at": downloaded.downloaded_at,
                "last_accessed": downloaded.last_accessed,
                "recommendation_count": downloaded.recommendation_count,
                "workbench_last_modified": downloaded.workbench_last_modified,
            }

    def check_updates_available(self) -> list[dict]:
        """Check downloaded benchmarks for available updates."""
        with Session(self.engine) as session:
            sql = """
                SELECT
                    b.benchmark_id,
                    b.title,
                    b.version,
                    d.downloaded_at,
                    d.workbench_last_modified,
                    b.last_revision_date
                FROM catalog_benchmarks b
                JOIN downloaded_benchmarks d ON b.benchmark_id = d.benchmark_id
                WHERE b.last_revision_date IS NOT NULL
                  AND (
                      d.workbench_last_modified IS NULL
                      OR b.last_revision_date > d.workbench_last_modified
                  )
                ORDER BY b.last_revision_date DESC
            """
            result = session.execute(text(sql))
            return [dict(row._mapping) for row in result.fetchall()]

    def get_catalog_stats(self) -> dict[str, int]:
        """Get catalog statistics using SQL COUNT(*) aggregates."""
        with Session(self.engine) as session:
            total_benchmarks = session.exec(
                select(func.count()).select_from(CatalogBenchmark)
            ).one()
            published_benchmarks = session.exec(
                select(func.count())
                .select_from(CatalogBenchmark)
                .join(BenchmarkStatusModel)
                .where(col(BenchmarkStatusModel.name) == BenchmarkStatus.PUBLISHED.value)
            ).one()
            downloaded_benchmarks = session.exec(
                select(func.count()).select_from(DownloadedBenchmark)
            ).one()
            platforms = session.exec(select(func.count()).select_from(Platform)).one()
            communities = session.exec(select(func.count()).select_from(Community)).one()

            return {
                "total_benchmarks": int(total_benchmarks),
                "published_benchmarks": int(published_benchmarks),
                "downloaded_benchmarks": int(downloaded_benchmarks),
                "platforms": int(platforms),
                "communities": int(communities),
            }

    def set_metadata(self, key: str, value: str):
        """Set scrape metadata value."""
        with Session(self.engine) as session:
            metadata = session.get(ScrapeMetadata, key)

            if metadata:
                metadata.value = value
            else:
                metadata = ScrapeMetadata(key=key, value=value)
                session.add(metadata)

            session.commit()

    def get_metadata(self, key: str) -> str | None:
        """Get scrape metadata value."""
        with Session(self.engine) as session:
            metadata = session.get(ScrapeMetadata, key)
            return metadata.value if metadata else None
