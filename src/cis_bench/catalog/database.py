"""Catalog database operations using SQLModel.

Provides CRUD operations, search, and management for the CIS benchmark catalog.
"""

import hashlib
import logging
import re
import sqlite3
import tempfile
from collections.abc import Callable, Iterable
from datetime import date, datetime
from pathlib import Path
from typing import NamedTuple, TypeVar

from sqlalchemy import (
    Integer,
    Select,
    cast,
    column,
    event,
    exists,
    func,
    literal_column,
    or_,
    table,
    text,
    update,
)
from sqlalchemy import (
    select as sa_select,
)
from sqlalchemy.engine import URL, Connection
from sqlalchemy.exc import DatabaseError, IntegrityError
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, SQLModel, col, create_engine, select

from cis_bench.catalog.fts import (
    TEXT_COLUMNS,
    VERSION_COLUMN,
    build_fts_query,
    build_phrase_query,
    build_terms_query,
    build_version_match_query,
    version_index_text,
)
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
from cis_bench.catalog.versions import VersionSortKey, is_newer_version, version_sort_key
from cis_bench.models.benchmark import Benchmark, BenchmarkPage

logger = logging.getLogger(__name__)

DEFAULT_BENCHMARK_STATUSES: tuple[tuple[str, bool, int], ...] = (
    (BenchmarkStatus.PUBLISHED.value, True, 1),
    (BenchmarkStatus.ACCEPTED.value, True, 2),
    (BenchmarkStatus.DRAFT.value, False, 3),
    (BenchmarkStatus.ARCHIVED.value, False, 4),
    (BenchmarkStatus.REJECTED.value, False, 5),
    (BenchmarkStatus.FINAL_UPDATE.value, False, 6),
    (BenchmarkStatus.WITHDRAWN.value, False, 7),
)

_TRAILING_VERSION_RE = re.compile(r"\s+v\d+(?:\.[\w-]+)*\s*$", re.IGNORECASE)
LookupModelT = TypeVar("LookupModelT", bound=SQLModel)

# The search index: one row per catalog benchmark. fts.py says which columns a query term
# is looked up in.
_FTS_COLUMNS = (*TEXT_COLUMNS, VERSION_COLUMN)
_FTS_TABLE = table(
    "benchmarks_fts", column("benchmark_id"), *(column(name) for name in _FTS_COLUMNS)
)
_CREATE_FTS_TABLE = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS benchmarks_fts USING fts5("
    f"benchmark_id UNINDEXED, {', '.join(_FTS_COLUMNS)}, tokenize='porter unicode61')"
)


# The recommendation index: one row per recommendation of every downloaded benchmark,
# written where a benchmark is saved and removed where it is removed. A query's words are
# looked up in the text columns; profiles is only a filter.
_RECOMMENDATION_TEXT_COLUMNS = ("title", "description", "rationale", "audit", "remediation")
_RECOMMENDATIONS_FTS_TABLE = table(
    "recommendations_fts",
    column("benchmark_id"),
    column("ref"),
    *(column(name) for name in _RECOMMENDATION_TEXT_COLUMNS),
)
_CREATE_RECOMMENDATIONS_FTS_TABLE = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS recommendations_fts USING fts5("
    f"benchmark_id UNINDEXED, ref UNINDEXED, {', '.join(_RECOMMENDATION_TEXT_COLUMNS)}, "
    "tokenize='porter unicode61')"
)
# One row per profile of each indexed recommendation, so a profile filter's words are
# found side by side within one profile's name, never across two.
_RECOMMENDATION_PROFILES_FTS_TABLE = table(
    "recommendation_profiles_fts", column("benchmark_id"), column("ref"), column("profile")
)
_CREATE_RECOMMENDATION_PROFILES_FTS_TABLE = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS recommendation_profiles_fts USING fts5("
    "benchmark_id UNINDEXED, ref UNINDEXED, profile, tokenize='porter unicode61')"
)
# The column layout of each recommendation index table; another layout is rebuilt on open.
_RECOMMENDATION_INDEX_LAYOUTS = {
    "recommendations_fts": ["benchmark_id", "ref", *_RECOMMENDATION_TEXT_COLUMNS],
    "recommendation_profiles_fts": ["benchmark_id", "ref", "profile"],
}
# highlight() inserts this mark at each phrase the query found in a column; a column whose
# highlighted text differs from the column itself is one a word was found in.
_HIT_MARK = "\x02"


def _recommendation_search_statement(
    match: str, profile_match: str, benchmark_id: str | None, limit: int | None
) -> Select[tuple[object, ...]]:
    """The recommendation search SELECT: the MATCH expressions are bound values.

    Each row carries every text column and its highlight() text, so the caller can tell
    which columns a word was found in. A profile filter keeps a recommendation with one
    profile row matching it; ranked best first, then by benchmark and ref.
    """
    index = table(
        "recommendations_fts",
        column("benchmark_id"),
        column("ref"),
        *(column(name) for name in _RECOMMENDATION_TEXT_COLUMNS),
        column("rank"),
    )
    statement = (
        sa_select(
            index.c.benchmark_id,
            index.c.ref,
            *(index.c[name] for name in _RECOMMENDATION_TEXT_COLUMNS),
            *(
                func.highlight(literal_column("recommendations_fts"), number, _HIT_MARK, "").label(
                    f"{name}_hit"
                )
                for number, name in enumerate(_RECOMMENDATION_TEXT_COLUMNS, start=2)
            ),
        )
        .select_from(index)
        .where(literal_column("recommendations_fts").op("MATCH")(match))
        .order_by(index.c.rank, index.c.benchmark_id, index.c.ref)
    )
    if benchmark_id is not None:
        statement = statement.where(index.c.benchmark_id == benchmark_id)
    if profile_match:
        profiles = _RECOMMENDATION_PROFILES_FTS_TABLE
        statement = statement.where(
            exists()
            .where(literal_column("recommendation_profiles_fts").op("MATCH")(profile_match))
            .where(profiles.c.benchmark_id == index.c.benchmark_id)
            .where(profiles.c.ref == index.c.ref)
        )
    if limit is not None:
        statement = statement.limit(limit)
    return statement


def _normalize_base_title(title: str | None) -> str:
    """Strip a trailing version suffix (e.g., ' v2.0.1') without truncating product words."""
    if not title:
        return ""
    return _TRAILING_VERSION_RE.sub("", title.strip())


# Columns downloaded_benchmarks gained after its first release, added to an older database
# when it is opened: (name, SQLite type).
_ADDED_DOWNLOADED_COLUMNS = (("version", "VARCHAR"), ("published_date", "DATE"))


class _PendingUpgrades(NamedTuple):
    """What _upgrade_schema has to change in a database an earlier version wrote."""

    downloaded_columns: tuple[tuple[str, str], ...]
    rebuild_index: bool
    create_recommendation_index: bool = False

    def __bool__(self) -> bool:
        return (
            bool(self.downloaded_columns) or self.rebuild_index or self.create_recommendation_index
        )


def update_reason(
    *,
    catalog_version: str | None,
    catalog_published: date | None,
    copy_version: str | None,
    copy_published: date | None,
    downloaded_at: datetime,
) -> str | None:
    """Why a cached copy is behind WorkBench, or None when it is not.

    - "newer version in catalog": the catalog's version parses as newer than the copy's;
    - "published after download": the date WorkBench shows the release as published is after
      the date the copy was published (or, for a copy cached before dates were recorded,
      after the day it was downloaded).
    A catalog whose version is behind the copy never makes it an update, whatever its date.
    """
    if is_newer_version(catalog_version, copy_version):
        return "newer version in catalog"
    if is_newer_version(copy_version, catalog_version) or catalog_published is None:
        return None
    copy_date = copy_published if copy_published is not None else downloaded_at.date()
    return "published after download" if catalog_published > copy_date else None


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

        if self.db_path.exists():
            try:
                self._upgrade_schema()
            except BaseException:
                # The caller gets no object to close, so the connection the upgrade
                # used must not outlive this failure.
                self.close()
                raise

    def close(self) -> None:
        """Close every connection the database holds (the engine's pool); safe to call
        more than once, so `with closing(CatalogDatabase(path)) as db:` leaves nothing
        for garbage collection to close."""
        self.engine.dispose()

    def initialize_schema(self):
        """Create all tables and indexes."""
        logger.debug("Creating database schema")

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
                logger.debug("Inserted default benchmark statuses")

            session.execute(text(_CREATE_FTS_TABLE))
            session.execute(text(_CREATE_RECOMMENDATIONS_FTS_TABLE))
            session.execute(text(_CREATE_RECOMMENDATION_PROFILES_FTS_TABLE))
            session.commit()
            logger.debug("Created FTS5 virtual tables")

        logger.debug("Database schema initialized")

    def _upgrade_schema(self) -> None:
        """Bring a database an earlier version wrote up to the current schema (idempotent).

        Runs whenever an existing database file is opened, so no command needs a catalog
        refresh first. Only what is found is changed: a table that is not there yet is left
        for initialize_schema to create. A database that cannot be written (read-only,
        locked by another process) or read is left as it is with a warning; reading it
        still works as far as its schema allows.
        """
        try:
            with self.engine.connect() as connection:
                if not self._pending_upgrades(connection):
                    return
            with Session(self.engine) as session:
                # One write transaction for every change: either all of it is written or
                # the database stays as it was. sqlite3 does not open a transaction for
                # ALTER, DROP or CREATE on its own.
                session.execute(text("BEGIN IMMEDIATE"))
                # Looked at again under the write lock: another process may have finished
                # the same upgrade since the first look.
                pending = self._pending_upgrades(session)
                for name, sql_type in pending.downloaded_columns:
                    session.execute(
                        text(f"ALTER TABLE downloaded_benchmarks ADD COLUMN {name} {sql_type}")
                    )
                    logger.info(f"Added column downloaded_benchmarks.{name}")
                if pending.rebuild_index:
                    self._rebuild_fts(session)
                    logger.info("Rebuilt the search index in the current layout")
                if pending.create_recommendation_index:
                    self._create_recommendation_index(session)
                    logger.info("Indexed the downloaded benchmarks' recommendations")
                session.commit()
        except DatabaseError as error:
            logger.warning(
                f"Could not update the catalog database {self.db_path} for this version "
                f"of cis-bench: {error.orig}. Searching it needs the update."
            )

    @staticmethod
    def _pending_upgrades(connection: Connection | Session) -> _PendingUpgrades:
        """What an earlier version's database lacks: columns of downloaded_benchmarks added
        since, and whether the search index is in another layout. A table that does not
        exist needs nothing."""

        def columns(table_name: str) -> list[str]:
            rows = connection.execute(text(f"PRAGMA table_info({table_name})"))
            return [row[1] for row in rows]

        downloaded = columns("downloaded_benchmarks")
        index = columns("benchmarks_fts")
        return _PendingUpgrades(
            downloaded_columns=tuple(
                (name, sql_type)
                for name, sql_type in _ADDED_DOWNLOADED_COLUMNS
                if downloaded and name not in downloaded
            ),
            rebuild_index=bool(index) and index != ["benchmark_id", *_FTS_COLUMNS],
            create_recommendation_index=bool(downloaded)
            and any(
                columns(name) != layout for name, layout in _RECOMMENDATION_INDEX_LAYOUTS.items()
            ),
        )

    def _create_recommendation_index(self, session: Session) -> None:
        """Create the recommendation index in the current layout, replacing one in another,
        and fill it from every downloaded benchmark (FTS5 cannot change a table's columns)."""
        for name in _RECOMMENDATION_INDEX_LAYOUTS:
            session.execute(text(f"DROP TABLE IF EXISTS {name}"))
        session.execute(text(_CREATE_RECOMMENDATIONS_FTS_TABLE))
        session.execute(text(_CREATE_RECOMMENDATION_PROFILES_FTS_TABLE))
        for benchmark_id, content_json in session.execute(
            sa_select(col(DownloadedBenchmark.benchmark_id), col(DownloadedBenchmark.content_json))
        ):
            self._index_recommendations(session, benchmark_id, content_json)

    @staticmethod
    def _index_recommendations(
        session: Session,
        benchmark_id: str,
        content_json: str,
        benchmark: Benchmark | None = None,
    ) -> None:
        """Write the recommendation index rows of one saved benchmark, replacing any it had.

        The rows hold the text the copy loads as (Markdown, whatever scraper saved it):
        ``benchmark`` when the caller has it, else the copy parsed. A copy that does not
        load has no rows: there is nothing in it to search.
        """
        CatalogDatabase._unindex_recommendations(session, benchmark_id)
        if benchmark is None:
            try:
                benchmark = deserialize_benchmark_json(content_json)
            except ValueError as error:
                logger.warning(
                    f"The cached copy of {benchmark_id} cannot be read, so its "
                    f"recommendations cannot be searched: {str(error).splitlines()[0]}"
                )
                return
        rows = [
            {
                "benchmark_id": benchmark_id,
                "ref": recommendation.ref,
                "title": recommendation.title,
                "description": recommendation.description or "",
                "rationale": recommendation.rationale or "",
                "audit": recommendation.audit or "",
                "remediation": recommendation.remediation or "",
            }
            for recommendation in benchmark.recommendations
        ]
        profile_rows = [
            {"benchmark_id": benchmark_id, "ref": recommendation.ref, "profile": profile}
            for recommendation in benchmark.recommendations
            for profile in recommendation.profiles
        ]
        if rows:
            session.execute(_RECOMMENDATIONS_FTS_TABLE.insert(), rows)
        if profile_rows:
            session.execute(_RECOMMENDATION_PROFILES_FTS_TABLE.insert(), profile_rows)

    @staticmethod
    def _unindex_recommendations(session: Session, benchmark_id: str) -> None:
        """Remove one benchmark's rows from the recommendation index."""
        for index_table in (_RECOMMENDATIONS_FTS_TABLE, _RECOMMENDATION_PROFILES_FTS_TABLE):
            session.execute(index_table.delete().where(index_table.c.benchmark_id == benchmark_id))

    def _rebuild_fts(self, session: Session) -> None:
        """Replace the search index with one in the current layout (FTS5 cannot add a column)."""
        session.execute(text("DROP TABLE benchmarks_fts"))
        session.execute(text(_CREATE_FTS_TABLE))
        for benchmark in session.exec(select(CatalogBenchmark)):
            self._insert_fts_row(benchmark, session)

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
                        # Read from the release's own page (record_page), never the listing:
                        # a refresh must not overwrite them
                        "published_date",
                        "description",
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
                    is_latest=bool(benchmark_data.get("is_latest", False)),
                    is_vnext=bool(benchmark_data.get("is_vnext", False)),
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

        self._insert_fts_row(benchmark, session)
        session.flush()  # Ensure FTS insert executes

    @staticmethod
    def _insert_fts_row(benchmark: CatalogBenchmark, session: Session) -> None:
        """Write the search index row of one benchmark."""
        session.execute(
            _FTS_TABLE.insert().values(
                benchmark_id=benchmark.benchmark_id,
                title=benchmark.title,
                platform=benchmark.platform.name if benchmark.platform else "",
                community=benchmark.community.name if benchmark.community else "",
                version=version_index_text(benchmark.version),
            )
        )

    @staticmethod
    def _build_search_query(
        fts_query: str | None,
        platform: str | None,
        platform_type: str | None,
        status: str | None,
        latest_only: bool,
        named_release_query: str | None,
        limit: int | None,
    ) -> Select[tuple[object, ...]]:
        """Build parameterized SQLAlchemy SELECT shared by FTS5 search and empty-query listing.

        ``limit=None`` leaves the result unlimited (used to count every match).
        ``named_release_query`` is the FTS5 query for releases that stay in a latest-only
        result although they are not the latest (the releases the search names by version).
        """
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
            is_latest = col(CatalogBenchmark.is_latest).is_(True)
            if named_release_query:
                named = (
                    sa_select(_FTS_TABLE.c.benchmark_id)
                    .where(literal_column("benchmarks_fts").op("MATCH")(named_release_query))
                    .correlate(None)
                )
                stmt = stmt.where(or_(is_latest, col(CatalogBenchmark.benchmark_id).in_(named)))
            else:
                stmt = stmt.where(is_latest)

        if fts_query is not None:
            stmt = stmt.order_by(fts_table.c.rank)
        else:
            stmt = stmt.order_by(
                col(CatalogBenchmark.title), cast(col(CatalogBenchmark.benchmark_id), Integer)
            )

        return stmt if limit is None else stmt.limit(limit)

    def _search_statement(
        self,
        query: str,
        platform: str | None,
        platform_type: str | None,
        status: str | None,
        latest_only: bool,
        named_releases: bool,
        limit: int | None,
    ) -> Select[tuple[object, ...]] | None:
        """The search SELECT, or None when the query has no searchable term."""
        fts_query: str | None = None
        if query and query.strip():
            fts_query = build_fts_query(query)
            if not fts_query:
                return None
        return self._build_search_query(
            fts_query=fts_query,
            platform=platform,
            platform_type=platform_type,
            status=status,
            latest_only=latest_only,
            named_release_query=build_version_match_query(query) if named_releases else None,
            limit=limit,
        )

    def search(
        self,
        query: str,
        platform: str | None = None,
        platform_type: str | None = None,
        status: str | None = "Published",
        latest_only: bool = False,
        *,
        limit: int | None,
        named_releases: bool = False,
    ) -> list[dict]:
        """Search catalog with FTS5 word-prefix matching, or list benchmarks when query is blank.

        Args:
            query: Search query (supports wildcards)
            platform: Filter by platform name
            platform_type: Filter by platform category (cloud, os, database, container, application)
            status: Filter by status (default: Published; None or 'all' returns all statuses)
            latest_only: Only latest versions
            limit: Max results; None returns every match (the caller decides, the CLI from
                CIS_BENCH_SEARCH_LIMIT)
            named_releases: With latest_only, also keep the releases the query names by
                their version ("kubernetes 2.0.1"), latest or not

        Returns:
            List of benchmark dictionaries with all joined data
        """
        stmt = self._search_statement(
            query, platform, platform_type, status, latest_only, named_releases, limit
        )
        if stmt is None:
            return []

        with Session(self.engine) as session:
            result = session.execute(stmt)
            return [dict(row._mapping) for row in result.fetchall()]

    def count_search(
        self,
        query: str,
        platform: str | None = None,
        platform_type: str | None = None,
        status: str | None = "Published",
        latest_only: bool = False,
        *,
        named_releases: bool = False,
    ) -> int:
        """Count every benchmark search() would return for these filters, with no limit."""
        stmt = self._search_statement(
            query, platform, platform_type, status, latest_only, named_releases, None
        )
        if stmt is None:
            return 0
        counted = sa_select(func.count()).select_from(stmt.order_by(None).subquery())
        with Session(self.engine) as session:
            return int(session.execute(counted).scalar_one())

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
                "description": benchmark.description,
                "is_latest": benchmark.is_latest,
                "is_vnext": benchmark.is_vnext,
                "collections": collection_names,
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

    def mark_withdrawn_except(self, seen_ids: Iterable[str]) -> int:
        """Mark every benchmark not in ``seen_ids`` Withdrawn; return how many were changed.

        Called after a complete catalog refresh with the IDs it listed. A row that is
        already Withdrawn is not counted again; a Withdrawn benchmark that WorkBench lists
        again gets its WorkBench status back through insert_benchmark.
        """
        seen = {str(benchmark_id) for benchmark_id in seen_ids}
        with Session(self.engine) as session:
            withdrawn_id = self.get_status_id(BenchmarkStatus.WITHDRAWN.value, session)
            to_mark = [
                benchmark_id
                for benchmark_id, status_id in session.exec(
                    select(CatalogBenchmark.benchmark_id, CatalogBenchmark.status_id)
                ).all()
                if benchmark_id not in seen and status_id != withdrawn_id
            ]
            for start in range(0, len(to_mark), 500):
                session.execute(
                    update(CatalogBenchmark)
                    .where(col(CatalogBenchmark.benchmark_id).in_(to_mark[start : start + 500]))
                    .values(status_id=withdrawn_id, is_latest=False)
                )
            session.commit()
        logger.info(f"Marked {len(to_mark)} benchmarks withdrawn")
        return len(to_mark)

    def mark_latest_versions(self) -> None:
        """Mark the latest version of each benchmark per (base title, status).

        The catalog list page carries no dates, so "latest" is decided by the
        version column: within a (normalized base title, status) group the rows
        whose parsed version equals the group maximum are latest. Unversioned
        strings (``vNext``, ``vDev``) sort below every numbered version, so they
        are latest only when the whole group is unversioned. Ties stay latest.
        A Withdrawn row is never latest.
        """
        with Session(self.engine) as session:
            withdrawn_id = self.get_status_id(BenchmarkStatus.WITHDRAWN.value, session)
            rows = session.exec(
                select(
                    CatalogBenchmark.benchmark_id,
                    CatalogBenchmark.title,
                    CatalogBenchmark.status_id,
                    CatalogBenchmark.version,
                ).where(col(CatalogBenchmark.status_id) != withdrawn_id)
            ).all()

            group_max: dict[tuple[str, int], VersionSortKey] = {}
            keyed_rows: list[tuple[str, tuple[str, int], VersionSortKey]] = []
            for benchmark_id, title, status_id, version in rows:
                group = (_normalize_base_title(title), status_id)
                key = version_sort_key(version)
                keyed_rows.append((benchmark_id, group, key))
                if group not in group_max or key > group_max[group]:
                    group_max[group] = key

            latest_ids = {bid for bid, group, key in keyed_rows if key == group_max[group]}

            session.execute(update(CatalogBenchmark).values(is_latest=False))
            if latest_ids:
                session.execute(
                    update(CatalogBenchmark)
                    .where(col(CatalogBenchmark.benchmark_id).in_(latest_ids))
                    .values(is_latest=True)
                )
            session.commit()

            logger.info(f"Updated is_latest flags ({len(latest_ids)} latest of {len(rows)})")

    def save_downloaded(
        self,
        benchmark_id: str,
        content_json: str,
        content_hash: str,
        recommendation_count: int,
        version: str | None = None,
        downloaded_at: datetime | None = None,
        published_date: date | None = None,
        benchmark: Benchmark | None = None,
    ):
        """Save downloaded benchmark content, and index its recommendations for search.

        ``version`` and ``published_date`` are the downloaded release's own version string and
        the date WorkBench showed it as published; check-updates compares both against the
        catalog row.
        ``downloaded_at`` is the instant the benchmark records for itself, so the row
        and the benchmark's JSON carry one time; it must carry its zone.
        ``benchmark`` is the Benchmark ``content_json`` was serialized from, when the caller
        has it: the recommendation index is written from it instead of parsing the JSON
        again.
        """
        now = utcnow() if downloaded_at is None else downloaded_at
        with Session(self.engine) as session:
            existing = session.get(DownloadedBenchmark, benchmark_id)

            if existing:
                existing.content_json = content_json
                existing.content_hash = content_hash
                existing.recommendation_count = recommendation_count
                existing.file_size = len(content_json)
                existing.published_date = published_date
                existing.version = version
                existing.downloaded_at = now
                existing.last_accessed = now
            else:
                downloaded = DownloadedBenchmark(
                    benchmark_id=benchmark_id,
                    content_json=content_json,
                    content_hash=content_hash,
                    file_size=len(content_json),
                    recommendation_count=recommendation_count,
                    version=version,
                    downloaded_at=now,
                    last_accessed=now,
                    published_date=published_date,
                )
                session.add(downloaded)

            # In the same transaction, so the index never holds another version of the copy.
            self._index_recommendations(session, benchmark_id, content_json, benchmark)
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
                "version": downloaded.version,
                "published_date": downloaded.published_date,
            }

    def delete_downloaded(self, benchmark_id: str) -> bool:
        """Delete a benchmark's cached downloaded copy; the catalog row stays.

        The catalog row, its collections and its search entry are owned by catalog refresh
        and are kept, so the benchmark is still found by search and can be downloaded again.

        Returns:
            True if a cached copy was deleted, False if the benchmark was not downloaded
        """
        with Session(self.engine) as session:
            downloaded = session.get(DownloadedBenchmark, benchmark_id)
            if downloaded is None:
                return False
            session.delete(downloaded)
            self._unindex_recommendations(session, benchmark_id)
            session.commit()
        logger.debug(f"Deleted downloaded benchmark: {benchmark_id}")
        return True

    def list_downloaded(self) -> list[dict]:
        """Every downloaded benchmark, in ID order (as numbers), with its catalog title.

        A benchmark downloaded while the catalog did not list it (download needs no
        catalog row) has title None. Each row: benchmark_id, title, version,
        recommendation_count, downloaded_at; the cached content comes from get_downloaded,
        one benchmark at a time.
        """
        with Session(self.engine) as session:
            rows = session.execute(
                sa_select(
                    col(DownloadedBenchmark.benchmark_id),
                    col(CatalogBenchmark.title),
                    col(DownloadedBenchmark.version),
                    col(DownloadedBenchmark.recommendation_count),
                    col(DownloadedBenchmark.downloaded_at),
                )
                .outerjoin(
                    CatalogBenchmark,
                    col(CatalogBenchmark.benchmark_id) == col(DownloadedBenchmark.benchmark_id),
                )
                .order_by(cast(col(DownloadedBenchmark.benchmark_id), Integer))
            ).all()
            return [
                {
                    "benchmark_id": benchmark_id,
                    "title": title,
                    "version": version,
                    "recommendation_count": recommendation_count,
                    "downloaded_at": downloaded_at,
                }
                for benchmark_id, title, version, recommendation_count, downloaded_at in rows
            ]

    def search_recommendations(
        self,
        query: str,
        benchmark_id: str | None = None,
        profile: str | None = None,
        limit: int | None = 50,
    ) -> list[dict]:
        """The downloaded recommendations whose text holds every word of ``query``.

        ``query`` is user text: punctuation and FTS5 keywords are search words. Each word is
        found as a word prefix in a recommendation's title, description, rationale, audit
        or remediation. ``benchmark_id`` keeps one benchmark's recommendations;
        ``profile`` keeps those of a profile whose name holds its words side by side
        ("Level 2" keeps "Level 2 - Server" and "Level 2 - Workstation"). Best match first.

        Each result: benchmark_id, ref, title, and matched_fields (the text fields a word
        was found in).
        """
        match = build_terms_query(query, _RECOMMENDATION_TEXT_COLUMNS)
        if not match:
            return []
        statement = _recommendation_search_statement(
            match, build_phrase_query(profile or "", "profile"), benchmark_id, limit
        )
        with Session(self.engine) as session:
            rows = session.execute(statement).all()
        return [
            {
                "benchmark_id": row.benchmark_id,
                "ref": row.ref,
                "title": row.title,
                "matched_fields": [
                    name
                    for name in _RECOMMENDATION_TEXT_COLUMNS
                    if getattr(row, f"{name}_hit") != getattr(row, name)
                ],
            }
            for row in rows
        ]

    def list_downloaded_benchmark_ids(self) -> list[str]:
        """IDs of every benchmark whose content has been downloaded."""
        with Session(self.engine) as session:
            return list(session.exec(select(DownloadedBenchmark.benchmark_id)).all())

    def record_page(self, benchmark_id: str, page: BenchmarkPage) -> None:
        """Record on a release's catalog row what its WorkBench page says (publish date,
        description); the one step every command that reads the page goes through.

        A field the page did not carry leaves what is known as it was. A release the catalog
        does not list is left alone: the catalog row is catalog refresh's to create. The
        title stays the listing's.
        """
        with Session(self.engine) as session:
            benchmark = session.get(CatalogBenchmark, benchmark_id)
            if benchmark is None:
                return
            if page.published_date is not None:
                benchmark.published_date = page.published_date
            if page.description is not None:
                benchmark.description = page.description
            session.add(benchmark)
            session.commit()

    def check_updates_available(self) -> list[dict]:
        """Downloaded benchmarks that WorkBench has moved past, by ``update_reason``.

        The catalog row carries WorkBench's current version and (once a command has read the
        release's page) its publish date; the cached row carries the copy's.
        """
        with Session(self.engine) as session:
            rows = session.exec(
                select(DownloadedBenchmark, CatalogBenchmark).join(
                    CatalogBenchmark,
                    col(CatalogBenchmark.benchmark_id) == col(DownloadedBenchmark.benchmark_id),
                )
            ).all()

            updates: list[dict] = []
            for downloaded, catalog in rows:
                reason = update_reason(
                    catalog_version=catalog.version,
                    catalog_published=catalog.published_date,
                    copy_version=downloaded.version,
                    copy_published=downloaded.published_date,
                    downloaded_at=downloaded.downloaded_at,
                )
                if reason is None:
                    continue
                updates.append(
                    {
                        "benchmark_id": downloaded.benchmark_id,
                        "title": catalog.title,
                        "downloaded_version": downloaded.version,
                        "catalog_version": catalog.version,
                        "downloaded_at": downloaded.downloaded_at,
                        "published_date": catalog.published_date,
                        "reason": reason,
                    }
                )
            updates.sort(key=lambda u: u["benchmark_id"])
            return updates

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
            withdrawn_benchmarks = session.exec(
                select(func.count())
                .select_from(CatalogBenchmark)
                .join(BenchmarkStatusModel)
                .where(col(BenchmarkStatusModel.name) == BenchmarkStatus.WITHDRAWN.value)
            ).one()
            downloaded_benchmarks = session.exec(
                select(func.count()).select_from(DownloadedBenchmark)
            ).one()
            platforms = session.exec(select(func.count()).select_from(Platform)).one()
            communities = session.exec(select(func.count()).select_from(Community)).one()

            return {
                "total_benchmarks": int(total_benchmarks),
                "published_benchmarks": int(published_benchmarks),
                "withdrawn_benchmarks": int(withdrawn_benchmarks),
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
