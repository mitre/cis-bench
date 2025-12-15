# Catalog Guide

The catalog feature provides fast, searchable access to 1,300+ CIS benchmarks with platform filtering and full-text search.

!!! info "Documentation Path"
**You are here:** User Guide > Catalog System

- **For commands:** See [Commands Reference](commands-reference.md)
- **For examples:** See [Workflows](workflows.md)
- **For terms:** See [Glossary](../about/glossary.md)

---

## Overview

**What is the Catalog?**

A local SQLite database with full-text search containing metadata for all CIS benchmarks:

- Benchmark titles, versions, and IDs
- Platform taxonomy (cloud, os, database, container, application)
- Status (Published, Draft, Archived)
- Communities and owners
- ~1,300+ benchmarks indexed

**Benefits:**

- Fast local search (no network required)
- Platform filtering (find all cloud benchmarks, databases, etc.)
- Full-text search with FTS5
- Discover what's available without browsing WorkBench
- Track benchmark versions
- Scriptable with JSON/CSV output

---

## Quick Start

### 1. First Time Setup

```bash
# Login (one-time)
cis-bench auth login --browser chrome

# Build catalog (one-time, ~2 minutes)
cis-bench catalog refresh
```

**What catalog refresh does:**

- Scrapes ~66 pages from CIS WorkBench
- Parallel processing (10 pages/batch, 5 threads)
- Builds searchable database
- Infers platform taxonomy automatically
- Takes ~2 minutes (vs ~10 min sequential)
- Stored in: `~/.cis-bench/catalog.db`

### 2. Search and Use

```bash
# Search for benchmarks
cis-bench search "ubuntu 22"

# Get benchmark in one command
cis-bench get "ubuntu 22" --format xccdf --style cis
```

**That's it!** The catalog makes discovery fast and easy.

---

## Searching the Catalog

### Basic Search

Use the top-level `search` command (recommended):

```bash
cis-bench search "ubuntu"
cis-bench search "oracle cloud"
cis-bench search "kubernetes"
```

**Search features:**

- Full-text search with FTS5
- Fuzzy matching
- Searches titles, platforms, communities
- Returns up to 1000 results by default

### Platform Filtering

**Filter by category (platform-type):**
```bash
# Find all cloud benchmarks
cis-bench search --platform-type cloud

# Find all databases
cis-bench search --platform-type database

# Find all operating systems
cis-bench search --platform-type os

# Find all container platforms
cis-bench search --platform-type container
```

**Platform categories:**

- `cloud` - AWS, Azure, GCP, Oracle Cloud, Alibaba Cloud, IBM Cloud
- `os` - Ubuntu, RHEL, Windows, AlmaLinux, Oracle Linux, macOS, Debian
- `database` - MySQL, PostgreSQL, Oracle DB, MongoDB, MSSQL
- `container` - Kubernetes, Docker, EKS, AKS, GKE, OKE
- `application` - NGINX, Apache, Tomcat

**Filter by specific platform:**
```bash
# Find Ubuntu benchmarks
cis-bench search --platform ubuntu

# Find AWS benchmarks
cis-bench search --platform aws

# Combine: Oracle + cloud
cis-bench search oracle --platform-type cloud
```

### Advanced Filtering

```bash
# Latest versions only
cis-bench search "windows server" --latest

# Different status
cis-bench search "docker" --status Archived

# Limit results
cis-bench search "linux" --limit 10

# Combine filters
cis-bench search "oracle" --platform-type cloud --latest --limit 5
```

### Output Formats

```bash
# JSON for scripting
cis-bench search oracle --platform-type cloud --output-format json | jq

# CSV for spreadsheets
cis-bench search "ubuntu" --latest --output-format csv > ubuntu_benchmarks.csv

# YAML
cis-bench search "aws" --output-format yaml
```

---

## Catalog Information

### Platform List

See all platforms with benchmark counts:

```bash
cis-bench catalog platforms
cis-bench catalog platforms --output-format json
```

### Statistics

View catalog statistics:

```bash
cis-bench catalog stats
```

**Shows:**

- Total benchmarks in catalog
- Published vs archived counts
- Downloaded benchmarks count
- Platforms and communities count
- Last refresh date

### Benchmark Details

Get details for a specific benchmark:

```bash
cis-bench catalog info 23598
cis-bench catalog info 23598 --output-format json
```

**Shows:**

- Title and version
- Status and platform
- Community and owner
- Published date
- URL

---

## Using the Catalog

### Recommended Workflow

**Option 1: Use `get` command (easiest)**
```bash
cis-bench get "ubuntu 22" --format xccdf --style cis
```

Searches Downloads Exports in one command!

**Option 2: Search then download**
```bash
# 1. Search to find ID
cis-bench search "oracle cloud"

# 2. Download by ID
cis-bench download 23598

# 3. Export
cis-bench export 23598 --format xccdf
```

**Option 3: Scripting workflow**
```bash
# Get all Oracle Cloud benchmark IDs and download
cis-bench search oracle --platform-type cloud --latest --output-format json | \
jq -r '.[].benchmark_id' | \
xargs -I {} cis-bench download {}
```

---

## Catalog Maintenance

### When to Refresh

Refresh the catalog when:

- New benchmarks released (monthly)
- You want latest versions
- Platform coverage changes

```bash
cis-bench catalog refresh
```

**Note:** Downloaded benchmarks are cached separately. Refreshing catalog updates metadata only, not downloaded content.

### Check for Updates

See which downloaded benchmarks have updates:

```bash
cis-bench catalog check-updates
```

---

## Performance

### Parallel Scraping

**Default behavior:**

- Batches: 10 pages per batch
- Threads: 5 concurrent per batch
- Rate limit: 2 seconds between batches
- Retry: 3 attempts with exponential backoff
- Failure threshold: Aborts if >10% of pages fail

**Performance:**

- Full 66 pages: ~2 minutes
- Per page: ~2 seconds (with parallelism)
- Respectful to CIS servers

**Tuning:**
```bash
# Faster (less polite)
cis-bench catalog refresh --rate-limit 1.0

# Test with few pages
cis-bench catalog refresh --max-pages 5
```

---

## Database Schema

### Tables

**catalog_benchmarks:**

- Metadata for all benchmarks
- Fields: id, title, version, status, platform_type, platform, etc.

**downloaded_benchmarks:**

- Full benchmark JSON content
- Cached for instant re-export

**benchmarks_fts:**

- FTS5 virtual table for full-text search
- Indexes: title, platform, community, description

### Platform Inference

Platforms are automatically inferred from benchmark titles:

**Examples:**

- "CIS Ubuntu Linux 22.04" platform_type: os, platform: ubuntu
- "CIS Amazon Web Services" platform_type: cloud, platform: aws
- "CIS Oracle Database 19c" platform_type: database, platform: oracle-database
- "CIS Kubernetes V1.28" platform_type: container, platform: kubernetes

**40+ patterns** for accurate inference!

---

## Troubleshooting

### Catalog Not Found

**Error:** "Catalog not found"

**Solution:**
```bash
cis-bench catalog refresh
```

### Search Returns No Results

**Check:**
1. Is query too specific? Try broader terms
2. Use `--status Archived` to see archived benchmarks
3. Remove `--latest` to see all versions
4. Try `--platform-type` instead of exact platform name

**Examples:**
```bash
# Too specific
cis-bench search "Ubuntu Linux 22.04 LTS Server Edition"

# Better
cis-bench search "ubuntu 22"

# Best
cis-bench search --platform-type os --platform ubuntu
```

### Refresh Failed

**Common causes:**

- Not authenticated: `cis-bench auth login --browser chrome`
- Network issues: Check internet connection
- CIS WorkBench down: Try again later
- SSL errors: Use `--no-verify-ssl` or set REQUESTS_CA_BUNDLE

**Retry logic:**

- Automatically retries failed pages (3 attempts)
- Continues if failure rate is low (<10%)
- Aborts if too many failures (indicates bigger issue)

---

## Advanced Usage

### Programmatic Access

```bash
# Get all cloud benchmarks as JSON
cis-bench search --platform-type cloud --output-format json > cloud_benchmarks.json

# Count benchmarks by platform
cis-bench catalog platforms --output-format json | jq '.[] | {platform: .name, count: .count}'

# Find latest Oracle benchmarks
cis-bench search oracle --latest --output-format json | \
jq -r '.[] | "\(.benchmark_id): \(.title) \(.version)"'
```

### Batch Operations

```bash
# Download all latest Ubuntu benchmarks
cis-bench search ubuntu --latest --output-format json | \
jq -r '.[].benchmark_id' | \
xargs -I {} cis-bench download {}

# Export all downloaded to XCCDF
cis-bench list --output-format json | \
jq -r '.[].file' | \
xargs -I {} basename {} .json | \
xargs -I {} cis-bench export {} --format xccdf --style cis
```

---

## Database Location

**Production:**

- `~/.cis-bench/catalog.db`

**Development:**
```bash
export CIS_BENCH_ENV=dev
cis-bench catalog refresh
# Stored in: ~/.cis-bench-dev/catalog.db
```

**Test:**

- Automatic test isolation
- `/tmp/cis-bench-test/catalog.db`

---

## See Also

- [Getting Started](../getting-started.md) - Initial setup
- [Commands Reference](commands-reference.md) - All commands
- [Configuration](configuration.md) - Environment settings
- [Search Command](commands-reference.md#cis-bench-search) - Detailed search docs
