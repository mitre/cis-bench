# CIS Benchmark CLI - Future Features

!!! info "Documentation Path"
    **You are here:** About > Future Features

    - **For current features:** See [Commands Reference](../user-guide/commands-reference.md)
    - **For design philosophy:** See [Design Philosophy](design-philosophy.md)

**Status**: Design document for v1.1+ features

**Note**: Many originally planned features have been implemented. See [Commands Reference](../user-guide/commands-reference.md) for current features.

---

## Implemented Features

The following features were originally planned as "future" but are now complete:

- **Catalog System** - SQLite database with FTS5 search (`catalog refresh`, `search` command)
- **Session Persistence** - Login once with `auth login`, session saved to `~/.cis-bench/session.cookies`
- **Search and Discovery** - `search` command with platform filtering
- **Get Command** - Unified `get` command (search + download + export in one)
- **Interactive Mode** - questionary-based selection in `get` command
- **Database Caching** - Downloaded benchmarks cached in catalog.db
- **Output Formats** - JSON/CSV/YAML on all query commands
- **Progress Bars** - Rich progress bars on downloads and catalog refresh
- **Platform Taxonomy** - Two-field system (platform_type + platform)
- **Parallel Scraping** - Catalog refresh in ~2 min (was ~10 min)

---

## Future Features (v1.1+)

### 1. Offline Mode

**Problem**: Users may want to work without network access once they have catalog/benchmarks cached.

**Solution**: `--offline` flag that fails fast if network is required:

```bash
# Work from cache only
cis-bench search "ubuntu" --offline
cis-bench export 23598 --format xccdf --offline # OK if cached
cis-bench download 23598 --offline # ERROR: requires network
```

**Implementation**:

- Add `--offline` global flag
- Check network requirements before operations
- Clear error messages when network needed
- Works with cached catalog and downloaded benchmarks

**Priority**: Medium (v1.1)

---

### 2. Background Catalog Refresh

**Problem**: Catalog refresh takes ~2 minutes, blocks user

**Solution**: Optional background refresh with notifications:

```bash
# Start background refresh
cis-bench catalog refresh --background

# Check status
cis-bench catalog status
# Output: Refreshing catalog... 45/66 pages (2 min remaining)

# Use catalog while refreshing (uses last complete refresh)
cis-bench search "ubuntu" # Works immediately
```

**Implementation**:

- Use multiprocessing for true background
- Store PID in ~/.cis-bench/refresh.pid
- Show progress when user checks status
- Atomic database updates (don't corrupt active catalog)

**Priority**: Low (v1.2)

---

### 3. Batch Export Operations

**Problem**: Exporting multiple benchmarks to same format is manual

**Solution**: Batch export from list or query:

```bash
# Export all cached benchmarks
cis-bench export --all --format xccdf --output-dir ./xccdf/

# Export from search
cis-bench search --platform-type cloud --output-format json | \
cis-bench export --batch --format xccdf

# Export specific IDs
cis-bench export 23598 24008 22162 --format xccdf
```

**Implementation**:

- Accept multiple IDs as arguments
- `--all` flag for all downloaded
- `--batch` flag to read IDs from stdin
- Parallel export with progress bar

**Priority**: Medium (v1.2)

---

### 4. Enhanced Cache Management

**Problem**: Users can't inspect/manage cache

**Solution**: Cache management commands:

```bash
# Show cache info
cis-bench cache info
# Output:
# Catalog: 1,302 benchmarks (last refresh: 2 hours ago)
# Downloaded: 45 benchmarks (2.3 GB)
# Oldest: AlmaLinux 8 v3.0.0 (downloaded 30 days ago)

# Clean old downloads
cis-bench cache clean --older-than 30d

# Clear catalog (force refresh on next use)
cis-bench cache clear --catalog

# Clear all
cis-bench cache clear --all
```

**Implementation**:

- Track download timestamps
- Calculate cache sizes
- Age-based cleanup
- Confirm before destructive operations

**Priority**: Low (v1.2)

---

### 5. Benchmark Comparison

**Problem**: Users want to see what changed between versions

**Solution**: Diff command:

```bash
# Compare two benchmark files
cis-bench diff benchmark_v1.json benchmark_v2.json

# Compare by ID (auto-fetch if needed)
cis-bench diff 23598 24008

# Output:
# 145 unchanged recommendations
# + 12 new recommendations
# - 3 removed recommendations
# ~ 8 modified recommendations
```

**Implementation**:

- Recommendation-level diff
- Smart matching (by ref/title)
- Colored output (green/red/yellow)
- Export diff to JSON/CSV

**Priority**: Low (v1.3)

---

### 6. Recommendation Search

**Problem**: Users want to find specific recommendations across benchmarks

**Solution**: Search within downloaded benchmarks:

```bash
# Search recommendation content
cis-bench find "SSH" --in-recommendations

# Search by CIS Control
cis-bench find --cis-control 4.8

# Output:
# Found in 3 benchmarks:
# AlmaLinux 10: 2.2.1 Configure SSH
# Ubuntu 22.04: 5.3.4 Ensure SSH is configured
# RHEL 9: 4.2.1 SSH hardening
```

**Implementation**:

- FTS5 index on recommendation content
- Query across all downloaded benchmarks
- Group results by benchmark
- Jump to specific recommendation

**Priority**: Low (v1.3)

---

### 7. Web UI

**Problem**: Some users prefer GUIs

**Solution**: Optional web interface:

```bash
# Start local web UI
cis-bench ui

# Output: Server running at http://localhost:5000
```

**Features**:

- Browse catalog
- Search and filter
- Download with progress
- View recommendations
- Export benchmarks

**Implementation**:

- FastAPI + HTMX (lightweight)
- Reuse existing CLI logic
- Optional dependency (don't require for CLI)

**Priority**: Low (v2.0) - Only if users request

---

## Not Planned

Features we explicitly decided NOT to implement:

- **Compliance Scanning** - Out of scope, use InSpec/SCAP tools
- **Benchmark Authoring** - Use CIS WorkBench directly
- **Remediation Scripts** - Security risk, use Ansible/Chef
- **Cloud Integration** - Too many platforms, use native tools

---

## Contributing Ideas

Have a feature idea? Open an issue at: https://github.com/mitre/cis-bench/issues

**Include**:

- Use case description
- Why current features don't solve it
- Proposed command syntax (if applicable)
- Expected behavior
