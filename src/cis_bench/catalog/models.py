"""SQLModel models for CIS benchmark catalog.

Uses SQLModel (Pydantic + SQLAlchemy) for type-safe database operations
with automatic validation.
"""

from datetime import UTC, date, datetime
from enum import Enum

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator
from sqlmodel import Field, Relationship, SQLModel


def utcnow():
    """Get current UTC time (timezone-aware)."""
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    """A timezone-aware instant stored as naive UTC text, as SQLite holds datetimes.

    SQLite keeps no zone, so a plain DateTime column gives back a naive value. Every
    instant goes in as UTC with the zone stripped and comes out with UTC attached, so
    the rows an earlier version wrote (naive UTC from ``utcnow``) read as the instants
    they were. A value with no zone is refused rather than guessed.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise TypeError("a stored time must carry its zone")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=UTC)


class BenchmarkStatus(str, Enum):
    """Benchmark status values from CIS WorkBench."""

    PUBLISHED = "Published"
    ACCEPTED = "Accepted"
    DRAFT = "Draft"
    ARCHIVED = "Archived"
    REJECTED = "Rejected"
    FINAL_UPDATE = "Final Update"
    # Not a WorkBench status: set by a complete catalog refresh on rows WorkBench no longer
    # lists, and replaced by the WorkBench status the next time the benchmark is listed.
    WITHDRAWN = "Withdrawn"


# ============================================================================
# Lookup Tables
# ============================================================================


class Platform(SQLModel, table=True):
    """Platform/category (Operating System, Database Server, etc.)."""

    __tablename__ = "platforms"

    platform_id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    description: str | None = None

    # Relationships
    benchmarks: list["CatalogBenchmark"] = Relationship(back_populates="platform")


class BenchmarkStatusModel(SQLModel, table=True):
    """Benchmark status lookup table."""

    __tablename__ = "benchmark_statuses"

    status_id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True)
    is_active: bool = Field(default=True)
    sort_order: int

    # Relationships
    benchmarks: list["CatalogBenchmark"] = Relationship(back_populates="status")


class Community(SQLModel, table=True):
    """CIS development community (CIS AlmaLinux OS Benchmarks, etc.)."""

    __tablename__ = "communities"

    community_id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    benchmark_count: int = Field(default=0)
    url: str | None = None

    # Relationships
    benchmarks: list["CatalogBenchmark"] = Relationship(back_populates="community")


class Collection(SQLModel, table=True):
    """Collection/category (Operating System, STIG, etc.)."""

    __tablename__ = "collections"

    collection_id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)


class Owner(SQLModel, table=True):
    """Benchmark owner/author."""

    __tablename__ = "owners"

    owner_id: int | None = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    full_name: str | None = None

    # Relationships
    benchmarks: list["CatalogBenchmark"] = Relationship(back_populates="owner")


# ============================================================================
# Main Catalog Table
# ============================================================================


class CatalogBenchmark(SQLModel, table=True):
    """Main catalog entry for a CIS benchmark."""

    __tablename__ = "catalog_benchmarks"

    # Identity
    benchmark_id: str = Field(primary_key=True)
    url: str = Field(unique=True, index=True)

    # Display
    title: str = Field(index=True)
    version: str | None = None

    # Foreign Keys
    status_id: int = Field(foreign_key="benchmark_statuses.status_id")
    platform_id: int | None = Field(default=None, foreign_key="platforms.platform_id")
    community_id: int | None = Field(default=None, foreign_key="communities.community_id")
    owner_id: int | None = Field(default=None, foreign_key="owners.owner_id")

    # Platform categorization (inferred from title)
    platform_type: str | None = Field(
        default=None, index=True
    )  # cloud, os, database, container, application

    # The date WorkBench shows this release as published, read from the release's own page
    # when a command reads it (a download, or an online check-updates). The catalog listing
    # carries no dates, so a release whose page has not been read has none.
    published_date: date | None = None

    # The release's overview, read from its page as published_date is
    description: str | None = None

    # The rest of what the release's page says about it, read as published_date is. Its
    # contributors, assets and revision history are lists, kept in tables of their own.
    release_type: str | None = None
    parent_benchmark_id: str | None = None
    parent_benchmark_url: str | None = None
    intended_audience: str | None = None
    acknowledgements: str | None = None
    milestone_name: str | None = None
    milestone_url: str | None = None

    # Flags
    is_latest: bool = Field(default=False)
    is_vnext: bool = Field(default=False)

    # Tracking
    scraped_at: datetime = Field(default_factory=utcnow, sa_type=UTCDateTime)

    # Relationships
    status: BenchmarkStatusModel = Relationship(back_populates="benchmarks")
    platform: Platform | None = Relationship(back_populates="benchmarks")
    community: Community | None = Relationship(back_populates="benchmarks")
    owner: Owner | None = Relationship(back_populates="benchmarks")
    # Collections relationship defined via manual queries (many-to-many)


# ============================================================================
# Link Tables (Many-to-Many)
# ============================================================================


class BenchmarkCollection(SQLModel, table=True):
    """Link table for benchmark to collections (many-to-many)."""

    __tablename__ = "benchmark_collections"

    benchmark_id: str = Field(foreign_key="catalog_benchmarks.benchmark_id", primary_key=True)
    collection_id: int = Field(foreign_key="collections.collection_id", primary_key=True)


# ============================================================================
# Lists from a release's own page, each row at its place (sort_order) in the list
# ============================================================================


class BenchmarkContributor(SQLModel, table=True):
    """A contributor the release's page names; a name the page lists twice is kept twice."""

    __tablename__ = "benchmark_contributors"

    benchmark_id: str = Field(foreign_key="catalog_benchmarks.benchmark_id", primary_key=True)
    sort_order: int = Field(primary_key=True)
    name: str


class BenchmarkAsset(SQLModel, table=True):
    """A product the release applies to, with its CPE 2.3 name."""

    __tablename__ = "benchmark_assets"

    benchmark_id: str = Field(foreign_key="catalog_benchmarks.benchmark_id", primary_key=True)
    sort_order: int = Field(primary_key=True)
    title: str
    cpe_id: str


class RevisionHistory(SQLModel, table=True):
    """A row of the release's revision history, newest first (sort_order 0)."""

    __tablename__ = "revision_history"

    benchmark_id: str = Field(foreign_key="catalog_benchmarks.benchmark_id", primary_key=True)
    sort_order: int = Field(primary_key=True)
    # As the page shows it: the page names no time zone, so none is stored
    revised_at: datetime | None = None
    author: str | None = None
    modification_count: int | None = None


# ============================================================================
# Downloaded Benchmarks
# ============================================================================


class DownloadedBenchmark(SQLModel, table=True):
    """Downloaded benchmark content stored in database."""

    __tablename__ = "downloaded_benchmarks"

    benchmark_id: str = Field(foreign_key="catalog_benchmarks.benchmark_id", primary_key=True)

    # Content
    content_json: str  # Full benchmark JSON
    content_hash: str  # SHA256

    # Metadata
    file_size: int | None = None
    recommendation_count: int | None = None

    # Version string of the downloaded benchmark, compared against the catalog on check-updates
    version: str | None = None

    # Timestamps
    downloaded_at: datetime = Field(default_factory=utcnow, sa_type=UTCDateTime)
    last_accessed: datetime = Field(default_factory=utcnow, sa_type=UTCDateTime)
    # The date WorkBench showed the release as published when this copy was downloaded
    published_date: date | None = None


# ============================================================================
# Metadata
# ============================================================================


class ScrapeMetadata(SQLModel, table=True):
    """Tracking metadata for scraping operations."""

    __tablename__ = "scrape_metadata"

    key: str = Field(primary_key=True)
    value: str
    updated_at: datetime = Field(default_factory=utcnow, sa_type=UTCDateTime)
