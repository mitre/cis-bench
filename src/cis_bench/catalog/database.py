"""Catalog database operations using SQLModel.

Provides CRUD operations, search, and management for the CIS benchmark catalog.
"""

import logging
from pathlib import Path

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine, select

from cis_bench.catalog.models import (
    BenchmarkCollection,
    BenchmarkStatusModel,
    CatalogBenchmark,
    Collection,
    Community,
    DownloadedBenchmark,
    Owner,
    Platform,
    ScrapeMetadata,
)

logger = logging.getLogger(__name__)


class CatalogDatabase:
    """SQLite database for CIS benchmark catalog."""

    def __init__(self, db_path: Path):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Create engine
        db_url = f"sqlite:///{self.db_path}"
        self.engine = create_engine(db_url, echo=False)

        logger.debug(f"Initialized catalog database: {self.db_path}")

    def initialize_schema(self):
        """Create all tables and indexes."""
        logger.info("Creating database schema")

        # Create all tables from SQLModel models
        SQLModel.metadata.create_all(self.engine)

        # Insert default statuses
        with Session(self.engine) as session:
            # Check if already populated
            existing = session.exec(select(BenchmarkStatusModel)).first()

            if not existing:
                statuses = [
                    BenchmarkStatusModel(name="Published", is_active=True, sort_order=1),
                    BenchmarkStatusModel(name="Accepted", is_active=True, sort_order=2),
                    BenchmarkStatusModel(name="Draft", is_active=False, sort_order=3),
                    BenchmarkStatusModel(name="Archived", is_active=False, sort_order=4),
                    BenchmarkStatusModel(name="Rejected", is_active=False, sort_order=5),
                ]
                for status in statuses:
                    session.add(status)
                session.commit()
                logger.info("Inserted default benchmark statuses")

        # Create FTS5 virtual table (raw SQL)
        with Session(self.engine) as session:
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
            logger.info("Created FTS5 virtual table for benchmarks")

        # Create FTS5 virtual table for recommendations search
        with Session(self.engine) as session:
            session.execute(
                text(
                    """
                CREATE VIRTUAL TABLE IF NOT EXISTS recommendations_fts USING fts5(
                    benchmark_id UNINDEXED,
                    ref UNINDEXED,
                    title,
                    description,
                    rationale,
                    audit,
                    remediation,
                    nist_controls,
                    cis_controls,
                    profiles,
                    tokenize='porter unicode61'
                )
            """
                )
            )
            session.commit()
            logger.info("Created FTS5 virtual table for recommendations")

        logger.info("Database schema initialized")

    def get_or_create_platform(self, name: str, session: Session) -> Platform:
        """Get existing platform or create new one."""
        platform = session.exec(select(Platform).where(Platform.name == name)).first()

        if not platform:
            platform = Platform(name=name)
            session.add(platform)
            session.flush()  # Get ID without committing

        return platform

    def get_or_create_community(self, name: str, session: Session) -> Community:
        """Get existing community or create new one."""
        community = session.exec(select(Community).where(Community.name == name)).first()

        if not community:
            community = Community(name=name)
            session.add(community)
            session.flush()

        return community

    def get_or_create_owner(self, username: str, session: Session) -> Owner:
        """Get existing owner or create new one."""
        owner = session.exec(select(Owner).where(Owner.username == username)).first()

        if not owner:
            owner = Owner(username=username)
            session.add(owner)
            session.flush()

        return owner

    def get_or_create_collection(self, name: str, session: Session) -> Collection:
        """Get existing collection or create new one."""
        collection = session.exec(select(Collection).where(Collection.name == name)).first()

        if not collection:
            collection = Collection(name=name)
            session.add(collection)
            session.flush()

        return collection

    def get_status_id(self, status_name: str, session: Session) -> int:
        """Get status ID by name."""
        status = session.exec(
            select(BenchmarkStatusModel).where(BenchmarkStatusModel.name == status_name)
        ).first()

        if not status:
            raise ValueError(f"Unknown status: {status_name}")

        return status.status_id

    def insert_benchmark(self, benchmark_data: dict):
        """Insert or update catalog benchmark.

        Args:
            benchmark_data: Dictionary with benchmark fields
                           platform, community, owner, collections as strings
                           (will be normalized to FK references)
        """
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
            existing = session.get(CatalogBenchmark, benchmark_data["benchmark_id"])

            if existing:
                # Update existing
                for key, value in benchmark_data.items():
                    if key not in ["platform", "community", "owner", "status", "collections"]:
                        setattr(existing, key, value)

                existing.platform_id = platform.platform_id if platform else None
                existing.community_id = community.community_id if community else None
                existing.owner_id = owner.owner_id if owner else None
                existing.status_id = status_id

                benchmark = existing
            else:
                # Create new
                benchmark = CatalogBenchmark(
                    benchmark_id=benchmark_data["benchmark_id"],
                    title=benchmark_data["title"],
                    version=benchmark_data.get("version"),
                    url=benchmark_data["url"],
                    status_id=status_id,
                    platform_id=platform.platform_id if platform else None,
                    community_id=community.community_id if community else None,
                    owner_id=owner.owner_id if owner else None,
                    published_date=benchmark_data.get("published_date"),
                    last_revision_date=benchmark_data.get("last_revision_date"),
                    description=benchmark_data.get("description"),
                    is_latest=benchmark_data.get("is_latest", False),
                    metadata_json=benchmark_data.get("metadata_json"),
                )
                session.add(benchmark)

            # Handle collections (many-to-many)
            if "collections" in benchmark_data:
                # Clear existing
                session.execute(
                    text("DELETE FROM benchmark_collections WHERE benchmark_id = :bid"),
                    {"bid": benchmark_data["benchmark_id"]},
                )

                # Add new
                for coll_name in benchmark_data["collections"]:
                    collection = self.get_or_create_collection(coll_name, session)
                    link = BenchmarkCollection(
                        benchmark_id=benchmark_data["benchmark_id"],
                        collection_id=collection.collection_id,
                    )
                    session.add(link)

            # Update FTS5 (before commit so it's in same transaction)
            self._update_fts(benchmark_data["benchmark_id"], session)

            session.commit()

            logger.debug(f"Inserted/updated benchmark: {benchmark_data['benchmark_id']}")

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

    def _list_all(
        self,
        platform: str | None = None,
        platform_type: str | None = None,
        status: str | None = "Published",
        latest_only: bool = False,
        limit: int = 50,
        session: Session = None,
    ) -> list[dict]:
        """List all benchmarks (no FTS5 search)."""
        sql = """
            SELECT
                b.benchmark_id,
                b.title,
                b.version,
                b.url,
                s.name as status,
                p.name as platform,
                b.platform_type,
                c.name as community,
                o.username as owner,
                b.published_date,
                b.is_latest,
                b.description
            FROM catalog_benchmarks b
            JOIN benchmark_statuses s ON b.status_id = s.status_id
            LEFT JOIN platforms p ON b.platform_id = p.platform_id
            LEFT JOIN communities c ON b.community_id = c.community_id
            LEFT JOIN owners o ON b.owner_id = o.owner_id
            WHERE 1=1
        """

        params = {}

        if platform:
            sql += " AND p.name = :platform"
            params["platform"] = platform

        if platform_type:
            sql += " AND b.platform_type = :platform_type"
            params["platform_type"] = platform_type

        if status:
            sql += " AND s.name = :status"
            params["status"] = status

        if latest_only:
            sql += " AND b.is_latest = 1"

        sql += " ORDER BY b.published_date DESC LIMIT :limit"
        params["limit"] = limit

        result = session.execute(text(sql), params)
        return [dict(row._mapping) for row in result.fetchall()]

    def search(
        self,
        query: str,
        platform: str | None = None,
        platform_type: str | None = None,
        status: str | None = "Published",
        latest_only: bool = False,
        limit: int = 50,
    ) -> list[dict]:
        """Search catalog using FTS5 fuzzy matching.

        Args:
            query: Search query (supports wildcards)
            platform: Filter by platform name
            platform_type: Filter by platform category (cloud, os, database, container, application)
            status: Filter by status (default: Published)
            latest_only: Only latest versions
            limit: Max results

        Returns:
            List of benchmark dictionaries with all joined data
        """
        with Session(self.engine) as session:
            # Build FTS5 query
            if not query or query.strip() == "":
                # Empty query - return all (don't use FTS5)
                return self._list_all(platform, platform_type, status, latest_only, limit, session)

            # FTS5 query formatting
            # Note: FTS5 doesn't support leading wildcards (*word)
            # Only trailing wildcards work (word*)
            if not query.endswith("*"):
                fts_query = f"{query}*"
            else:
                fts_query = query

            # Use raw SQL for FTS5 + joins
            sql = """
                SELECT
                    b.benchmark_id,
                    b.title,
                    b.version,
                    b.url,
                    s.name as status,
                    p.name as platform,
                    b.platform_type,
                    c.name as community,
                    o.username as owner,
                    b.published_date,
                    b.is_latest,
                    b.description,
                    f.rank
                FROM catalog_benchmarks b
                JOIN benchmarks_fts f ON b.benchmark_id = f.benchmark_id
                JOIN benchmark_statuses s ON b.status_id = s.status_id
                LEFT JOIN platforms p ON b.platform_id = p.platform_id
                LEFT JOIN communities c ON b.community_id = c.community_id
                LEFT JOIN owners o ON b.owner_id = o.owner_id
                WHERE benchmarks_fts MATCH :query
            """

            params = {"query": fts_query}

            if platform:
                sql += " AND p.name = :platform"
                params["platform"] = platform

            if platform_type:
                sql += " AND b.platform_type = :platform_type"
                params["platform_type"] = platform_type

            if status:
                sql += " AND s.name = :status"
                params["status"] = status

            if latest_only:
                sql += " AND b.is_latest = 1"

            sql += " ORDER BY f.rank LIMIT :limit"
            params["limit"] = limit

            result = session.execute(text(sql), params)
            rows = result.fetchall()

            # Convert to dicts
            return [dict(row._mapping) for row in rows]

    def get_benchmark(self, benchmark_id: str) -> dict | None:
        """Get single benchmark with all metadata."""
        with Session(self.engine) as session:
            benchmark = session.get(CatalogBenchmark, benchmark_id)

            if not benchmark:
                return None

            return {
                "benchmark_id": benchmark.benchmark_id,
                "title": benchmark.title,
                "version": benchmark.version,
                "url": benchmark.url,
                "status": benchmark.status.name,
                "platform": benchmark.platform.name if benchmark.platform else None,
                "community": benchmark.community.name if benchmark.community else None,
                "owner": benchmark.owner.username if benchmark.owner else None,
                "published_date": benchmark.published_date,
                "last_revision_date": benchmark.last_revision_date,
                "description": benchmark.description,
                "is_latest": benchmark.is_latest,
                "metadata_json": benchmark.metadata_json,
            }

    def list_platforms(self) -> list[dict]:
        """List all platforms with benchmark counts."""
        with Session(self.engine) as session:
            sql = """
                SELECT p.name, COUNT(b.benchmark_id) as count
                FROM platforms p
                LEFT JOIN catalog_benchmarks b ON p.platform_id = b.platform_id
                LEFT JOIN benchmark_statuses s ON b.status_id = s.status_id
                WHERE s.name = 'Published' OR s.name = 'Accepted'
                GROUP BY p.name
                ORDER BY count DESC, p.name
            """
            result = session.execute(text(sql))
            return [{"name": row[0], "count": row[1]} for row in result.fetchall()]

    def list_communities(self) -> list[dict]:
        """List all communities with benchmark counts."""
        with Session(self.engine) as session:
            communities = session.exec(
                select(Community).order_by(Community.benchmark_count.desc())
            ).all()

            return [
                {"name": c.name, "benchmark_count": c.benchmark_count, "url": c.url}
                for c in communities
            ]

    def mark_latest_versions(self):
        """Mark latest version for each platform/title combination."""
        with Session(self.engine) as session:
            # Complex query to find latest versions
            # Group by base title (without version), get max version per group
            # This is simplified - production would need smarter version comparison

            # For now: mark most recently published as latest
            sql = """
                UPDATE catalog_benchmarks
                SET is_latest = CASE
                    WHEN benchmark_id IN (
                        SELECT b1.benchmark_id
                        FROM catalog_benchmarks b1
                        WHERE NOT EXISTS (
                            SELECT 1 FROM catalog_benchmarks b2
                            WHERE b2.title LIKE SUBSTR(b1.title, 1, INSTR(b1.title, 'v') - 1) || '%'
                              AND b2.published_date > b1.published_date
                              AND b2.status_id = b1.status_id
                        )
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
        with Session(self.engine) as session:
            existing = session.get(DownloadedBenchmark, benchmark_id)

            if existing:
                existing.content_json = content_json
                existing.content_hash = content_hash
                existing.recommendation_count = recommendation_count
                existing.file_size = len(content_json)
                existing.workbench_last_modified = workbench_last_modified
            else:
                downloaded = DownloadedBenchmark(
                    benchmark_id=benchmark_id,
                    content_json=content_json,
                    content_hash=content_hash,
                    file_size=len(content_json),
                    recommendation_count=recommendation_count,
                    workbench_last_modified=workbench_last_modified,
                )
                session.add(downloaded)

            session.commit()
            logger.debug(f"Saved downloaded benchmark: {benchmark_id}")

        # Index recommendations for search
        self._index_recommendations(benchmark_id, content_json)

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
                "recommendation_count": downloaded.recommendation_count,
                "workbench_last_modified": downloaded.workbench_last_modified,
            }

    def get_downloaded_benchmark_ids(self) -> set[str]:
        """Get set of all downloaded benchmark IDs.

        Returns:
            Set of benchmark IDs that have been downloaded and cached locally.
        """
        with Session(self.engine) as session:
            downloaded = session.exec(select(DownloadedBenchmark)).all()
            return {d.benchmark_id for d in downloaded}

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
                WHERE b.last_revision_date > d.workbench_last_modified
                   OR d.workbench_last_modified IS NULL
                ORDER BY b.last_revision_date DESC
            """
            result = session.execute(text(sql))
            return [dict(row._mapping) for row in result.fetchall()]

    def get_catalog_stats(self) -> dict:
        """Get catalog statistics."""
        with Session(self.engine) as session:
            total = session.exec(
                select(CatalogBenchmark).where(CatalogBenchmark.benchmark_id.is_not(None))
            ).all()

            published = session.exec(
                select(CatalogBenchmark)
                .join(BenchmarkStatusModel)
                .where(BenchmarkStatusModel.name == "Published")
            ).all()

            downloaded_count = session.exec(select(DownloadedBenchmark)).all()

            return {
                "total_benchmarks": len(total),
                "published_benchmarks": len(published),
                "downloaded_benchmarks": len(downloaded_count),
                "platforms": len(session.exec(select(Platform)).all()),
                "communities": len(session.exec(select(Community)).all()),
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

    def _index_recommendations(self, benchmark_id: str, content_json: str):
        """Index recommendations for FTS5 search.

        Extracts recommendations from benchmark JSON and indexes
        searchable fields in the recommendations_fts table.
        """
        import json

        try:
            benchmark = json.loads(content_json)
            recommendations = benchmark.get("recommendations", [])

            if not recommendations:
                logger.debug(f"No recommendations to index for {benchmark_id}")
                return

            with Session(self.engine) as session:
                # Delete existing entries for this benchmark
                session.execute(
                    text("DELETE FROM recommendations_fts WHERE benchmark_id = :bid"),
                    {"bid": benchmark_id},
                )

                # Index each recommendation
                for rec in recommendations:
                    # Extract and join control mappings
                    nist = " ".join(rec.get("nist_controls", []))
                    cis = " ".join(
                        [
                            f"{c.get('control', '')} {c.get('title', '')}"
                            for c in rec.get("cis_controls", [])
                        ]
                    )
                    profiles = " ".join(rec.get("profiles", []))

                    session.execute(
                        text(
                            """
                            INSERT INTO recommendations_fts
                            (benchmark_id, ref, title, description, rationale,
                             audit, remediation, nist_controls, cis_controls, profiles)
                            VALUES
                            (:bid, :ref, :title, :desc, :rationale,
                             :audit, :remediation, :nist, :cis, :profiles)
                            """
                        ),
                        {
                            "bid": benchmark_id,
                            "ref": rec.get("ref", ""),
                            "title": rec.get("title", ""),
                            "desc": rec.get("description", "") or "",
                            "rationale": rec.get("rationale", "") or "",
                            "audit": rec.get("audit", "") or "",
                            "remediation": rec.get("remediation", "") or "",
                            "nist": nist,
                            "cis": cis,
                            "profiles": profiles,
                        },
                    )

                session.commit()
                logger.debug(f"Indexed {len(recommendations)} recommendations for {benchmark_id}")

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse benchmark JSON for indexing: {e}")
        except Exception as e:
            logger.warning(f"Failed to index recommendations: {e}")

    def search_recommendations(
        self,
        query: str,
        benchmark_id: str | None = None,
        profile: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Search recommendations using FTS5.

        Args:
            query: Search query (supports FTS5 syntax)
            benchmark_id: Filter to specific benchmark
            profile: Filter by profile level
            limit: Maximum results

        Returns:
            List of matching recommendations with benchmark info
        """
        with Session(self.engine) as session:
            # Build FTS5 query
            where_clauses = ["recommendations_fts MATCH :query"]
            params = {"query": query, "limit": limit}

            if benchmark_id:
                where_clauses.append("benchmark_id = :bid")
                params["bid"] = benchmark_id

            if profile:
                # Profile filtering via FTS5 (approximate match)
                where_clauses.append("profiles MATCH :profile")
                params["profile"] = profile

            where_sql = " AND ".join(where_clauses)

            # Note: where_sql only contains hardcoded clause strings from where_clauses list,
            # not user input. User values go into params dict as bound parameters.
            sql = f"""
                SELECT
                    benchmark_id,
                    ref,
                    title,
                    profiles,
                    snippet(recommendations_fts, 2, '<b>', '</b>', '...', 32) as description_snippet
                FROM recommendations_fts
                WHERE {where_sql}
                ORDER BY rank
                LIMIT :limit
            """  # noqa: S608  # nosec B608 - where_sql from internal constants only

            try:
                result = session.execute(text(sql), params)
                rows = result.fetchall()

                return [
                    {
                        "benchmark_id": row[0],
                        "ref": row[1],
                        "title": row[2],
                        "profiles": row[3].split() if row[3] else [],
                        "description_snippet": row[4],
                    }
                    for row in rows
                ]
            except Exception as e:
                logger.error(f"Search failed: {e}")
                return []
