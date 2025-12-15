"""SQLModel models for CIS benchmark catalog.

Uses SQLModel (Pydantic + SQLAlchemy) for type-safe database operations
with automatic validation.
"""

from datetime import UTC, datetime
from enum import Enum

from sqlmodel import Field, Relationship, SQLModel


def utcnow():
    """Get current UTC time (timezone-aware)."""
    return datetime.now(UTC)


class BenchmarkStatus(str, Enum):
    """Benchmark status values from CIS WorkBench."""

    PUBLISHED = "Published"
    ACCEPTED = "Accepted"
    DRAFT = "Draft"
    ARCHIVED = "Archived"
    REJECTED = "Rejected"


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

    # Dates
    published_date: str | None = None
    last_revision_date: str | None = None

    # Content
    description: str | None = None

    # Flags
    is_latest: bool = Field(default=False)
    is_vnext: bool = Field(default=False)

    # Metadata overflow
    metadata_json: str | None = None

    # Tracking
    scraped_at: datetime = Field(default_factory=utcnow)

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

    # Timestamps
    downloaded_at: datetime = Field(default_factory=utcnow)
    last_accessed: datetime = Field(default_factory=utcnow)
    workbench_last_modified: str | None = None


# ============================================================================
# Metadata
# ============================================================================


class ScrapeMetadata(SQLModel, table=True):
    """Tracking metadata for scraping operations."""

    __tablename__ = "scrape_metadata"

    key: str = Field(primary_key=True)
    value: str
    updated_at: datetime = Field(default_factory=utcnow)
