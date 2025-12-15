-- CIS Benchmark Catalog Database Schema
-- Version: 1.0.0 (Basic Catalog - no controls mapping)
-- Database: SQLite with JSON1 and FTS5 extensions

-- ============================================================================
-- Lookup Tables (Normalized)
-- ============================================================================

-- Platforms
CREATE TABLE platforms (
    platform_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    description TEXT
);

-- Benchmark statuses
CREATE TABLE benchmark_statuses (
    status_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    sort_order INTEGER
);

INSERT INTO benchmark_statuses (name, is_active, sort_order) VALUES
    ('Published', 1, 1),
    ('Accepted', 1, 2),
    ('Draft', 0, 3),
    ('Archived', 0, 4),
    ('Rejected', 0, 5);

-- Communities
CREATE TABLE communities (
    community_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    benchmark_count INTEGER DEFAULT 0,
    url TEXT
);

-- Collections (categories/tags)
CREATE TABLE collections (
    collection_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

-- Owners
CREATE TABLE owners (
    owner_id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    full_name TEXT
);

-- ============================================================================
-- Main Catalog Table
-- ============================================================================

CREATE TABLE catalog_benchmarks (
    -- Identity
    benchmark_id TEXT PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,

    -- Display
    title TEXT NOT NULL,
    version TEXT,

    -- Foreign Keys
    status_id INTEGER NOT NULL,
    platform_id INTEGER,
    community_id INTEGER,
    owner_id INTEGER,

    -- Dates
    published_date DATE,
    last_revision_date DATE,

    -- Content
    description TEXT,

    -- Flags
    is_latest BOOLEAN DEFAULT 0,
    is_vnext BOOLEAN DEFAULT 0,

    -- Metadata (overflow for additional fields)
    metadata_json TEXT,

    -- Tracking
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (status_id) REFERENCES benchmark_statuses(status_id),
    FOREIGN KEY (platform_id) REFERENCES platforms(platform_id),
    FOREIGN KEY (community_id) REFERENCES communities(community_id),
    FOREIGN KEY (owner_id) REFERENCES owners(owner_id)
);

-- ============================================================================
-- Many-to-Many Relationships
-- ============================================================================

-- Benchmark to Collections (many-to-many)
CREATE TABLE benchmark_collections (
    benchmark_id TEXT NOT NULL,
    collection_id INTEGER NOT NULL,
    PRIMARY KEY (benchmark_id, collection_id),
    FOREIGN KEY (benchmark_id) REFERENCES catalog_benchmarks(benchmark_id) ON DELETE CASCADE,
    FOREIGN KEY (collection_id) REFERENCES collections(collection_id)
);

-- ============================================================================
-- Downloaded Benchmarks (Separate from Catalog)
-- ============================================================================

CREATE TABLE downloaded_benchmarks (
    benchmark_id TEXT PRIMARY KEY,

    -- Content
    content_json TEXT NOT NULL,          -- Full benchmark JSON
    content_hash TEXT NOT NULL,          -- SHA256 for change detection

    -- Metadata
    file_size INTEGER,
    recommendation_count INTEGER,

    -- Timestamps
    downloaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    workbench_last_modified DATE,        -- From catalog

    FOREIGN KEY (benchmark_id) REFERENCES catalog_benchmarks(benchmark_id)
);

-- ============================================================================
-- Full-Text Search (FTS5)
-- ============================================================================

CREATE VIRTUAL TABLE benchmarks_fts USING fts5(
    benchmark_id UNINDEXED,
    title,
    platform,
    community,
    description,
    tokenize='porter unicode61'
);

-- ============================================================================
-- Metadata/Tracking
-- ============================================================================

CREATE TABLE scrape_metadata (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- Indexes for Performance
-- ============================================================================

CREATE INDEX idx_benchmark_status ON catalog_benchmarks(status_id);
CREATE INDEX idx_benchmark_platform ON catalog_benchmarks(platform_id);
CREATE INDEX idx_benchmark_community ON catalog_benchmarks(community_id);
CREATE INDEX idx_benchmark_owner ON catalog_benchmarks(owner_id);
CREATE INDEX idx_benchmark_published ON catalog_benchmarks(published_date DESC);
CREATE INDEX idx_benchmark_latest ON catalog_benchmarks(is_latest) WHERE is_latest = 1;
CREATE INDEX idx_benchmark_status_latest ON catalog_benchmarks(status_id, is_latest)
    WHERE is_latest = 1;

CREATE INDEX idx_collection_benchmark ON benchmark_collections(collection_id);

CREATE INDEX idx_downloaded_date ON downloaded_benchmarks(downloaded_at DESC);
CREATE INDEX idx_downloaded_accessed ON downloaded_benchmarks(last_accessed DESC);

-- ============================================================================
-- Views for Common Queries
-- ============================================================================

CREATE VIEW v_published_benchmarks AS
SELECT
    b.benchmark_id,
    b.title,
    b.version,
    b.url,
    s.name as status,
    p.name as platform,
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
WHERE s.name = 'Published';

CREATE VIEW v_latest_published AS
SELECT * FROM v_published_benchmarks
WHERE is_latest = 1;

CREATE VIEW v_downloaded_status AS
SELECT
    b.benchmark_id,
    b.title,
    b.version,
    s.name as status,
    p.name as platform,
    d.downloaded_at,
    d.recommendation_count,
    CASE
        WHEN d.workbench_last_modified < b.last_revision_date THEN 1
        ELSE 0
    END as update_available
FROM catalog_benchmarks b
JOIN downloaded_benchmarks d ON b.benchmark_id = d.benchmark_id
JOIN benchmark_statuses s ON b.status_id = s.status_id
LEFT JOIN platforms p ON b.platform_id = p.platform_id;

-- ============================================================================
-- Notes
-- ============================================================================

-- FTS5 population and triggers will be handled by application code
-- JSON queries use json_extract() function: json_extract(metadata_json, '$.field')
-- For controls mapping (v1.1): See CATALOG_FEATURE_DESIGN.md for enhanced schema
