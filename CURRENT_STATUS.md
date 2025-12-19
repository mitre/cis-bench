# CIS Benchmark CLI - Current Status

**Last Updated:** December 19, 2025
**Version:** 0.3.1
**Branch:** `main` (after PR #4 merge)

---

## Project State

**Production Ready**: Core features complete and tested.

### What Works

| Feature | Status | Notes |
|---------|--------|-------|
| Download benchmarks | Working | Browser cookie auth (Chrome/Firefox/Edge/Safari) |
| Catalog system | Working | SQLite + FTS5, ~1,300 benchmarks indexed |
| Search | Working | Full-text search, platform filtering |
| Export YAML/CSV/MD | Working | All formats tested |
| Export XCCDF (DISA) | Working | 2161 CCIs, VulnDiscussion, XCCDF 1.1.4 |
| Export XCCDF (CIS) | Working | 318 CIS Controls, MITRE ATT&CK, XCCDF 1.2 |
| Get command | Working | Unified search + download + export |
| Auth login/logout | Working | Session persistence to ~/.cis-bench/ |

### Test Status

- 285 tests passing
- Pre-commit hooks: ruff, bandit
- CI: GitHub Actions (5 jobs)

---

## Quick Start

```bash
# Install
pipx install cis-bench

# Login (one-time)
cis-bench auth login --browser chrome

# Build catalog (one-time, ~2 min)
cis-bench catalog refresh

# Search and download
cis-bench get "ubuntu 22" --format xccdf --style cis
```

---

## Open Tasks (Beads)

Run `bd list` to see current tasks:

| Priority | Task | Status |
|----------|------|--------|
| P0 | PR #4 - Documentation cleanup | Ready for merge |
| P2 | Offline mode (--offline flag) | Open |
| P2 | Batch export operations | Open |
| P3 | Benchmark comparison/diff | Open |
| P3 | Recommendation search (find) | Open |

---

## Completed Work (Sessions 28-30)

### Documentation Cleanup
- Fixed Python version 3.8+ to 3.12+ in 4 files
- Fixed version 1.0.0 to 0.3.1 in 3 files
- Fixed 12 broken links (case sensitivity)
- Fixed 3 missing anchor links
- Fixed mermaid syntax error (`Loop` reserved keyword)
- Added CHANGELOG.md and NOTICE.md symlinks to docs/
- mkdocs build --strict passes

### Infrastructure
- Added beads (bd) task tracker
- Configured git hooks and sync-branch

---

## Architecture

See `docs/developer-guide/architecture.md` for full details.

**Key Components:**
- `src/cis_bench/cli/` - Click commands
- `src/cis_bench/exporters/` - Format exporters + mapping engine
- `src/cis_bench/fetcher/` - WorkBench scraper with strategies
- `src/cis_bench/models/` - Pydantic + xsdata models

**Key Design Patterns:**
- Strategy Pattern - HTML version adapters
- Factory Pattern - Pluggable exporters
- Config-driven XCCDF mapping (MappingEngine)

---

## Recovery Prompt

If starting a new session:

```
Read CURRENT_STATUS.md for project state.
Run `bd list` to see open tasks.
Run `bd ready` to see what's unblocked.
```

---

## Links

- **Repository:** https://github.com/mitre/cis-bench
- **Documentation:** Run `mkdocs serve` locally
- **Issues:** `bd list` or GitHub Issues
