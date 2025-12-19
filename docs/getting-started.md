# Getting Started

!!! success "Quick Navigation"

- **After setup:** Try [End-to-End Workflows](user-guide/workflows.md) for real examples
- **Full command syntax:** [Commands Reference](user-guide/commands-reference.md)
- **Troubleshooting:** [Common Issues](user-guide/troubleshooting.md)

## Installation

### Requirements

- Python 3.12 or higher
- [pipx](https://pipx.pypa.io/) (recommended) or [uv](https://docs.astral.sh/uv/)

### Install from PyPI (Recommended)

Per [Python Packaging Authority guidelines](https://packaging.python.org/en/latest/guides/installing-stand-alone-command-line-tools/), CLI tools should be installed with **pipx** or **uv tool**, not pip directly.

```bash
# RECOMMENDED: pipx (isolated environment, correct PATH)
pipx install cis-bench

# ALTERNATIVE: uv tool (fast, modern)
uv tool install cis-bench

# Verify installation
cis-bench --version
```

!!! warning "Why not pip?"
    `pip install cis-bench` may install to a directory not in your PATH, causing "command not found" errors. pipx and uv tool handle PATH correctly.

??? note "Using pip anyway? (click to expand)"
    ```bash
    pip install cis-bench
    ```

    If you get `cis-bench: command not found`:

    ```bash
    # Option 1: Use module syntax (always works)
    python -m cis_bench --version

    # Option 2: Add pip's bin to PATH
    export PATH="$HOME/.local/bin:$PATH"  # Add to ~/.bashrc or ~/.zshrc
    ```

### Install from Source

```bash
git clone https://github.com/mitre/cis-bench.git
cd cis-bench

# Install for development
pipx install -e .
# Or: uv tool install -e .

# Verify
cis-bench --version
```

### Development Install

```bash
git clone https://github.com/mitre/cis-bench.git
cd cis-bench
pip install -e ".[dev]"
pre-commit install
```

---

## Quick Start

The fastest way to get started:

### 1. Login (One-Time)

Log into CIS WorkBench and save your session:

```bash
# Login with Chrome
cis-bench auth login --browser chrome

# Or with Firefox/Edge/Safari
cis-bench auth login --browser firefox
```

**What this does:**
1. Optionally opens CIS WorkBench in your browser
2. Extracts session cookies from your browser
3. Validates the session
4. Saves to `~/.cis-bench/session.cookies`
5. All future commands use this saved session automatically

**Supported browsers:** Chrome, Firefox, Edge, Safari

### 2. Build Catalog (One-Time, ~2 minutes)

Build a searchable local database of all CIS benchmarks:

```bash
cis-bench catalog refresh
```

This scrapes ~66 pages from CIS WorkBench using parallel processing and creates a searchable database with:

- 1,300+ benchmarks indexed
- Full-text search (FTS5)
- Platform taxonomy (cloud, os, database, etc.)
- Fast local queries (no network needed)

### 3. Find and Get Benchmarks

Now you can search and download benchmarks:

```bash
# Search for benchmarks
cis-bench search "ubuntu 22.04"
cis-bench search "oracle cloud" --platform-type cloud

# All-in-one: search + download + export
cis-bench get "ubuntu 22" --format xccdf --style cis
cis-bench get "aws eks" --format yaml

# Or download by ID first
cis-bench download 23598
cis-bench export 23598 --format xccdf --style cis
```

---

## Authentication Details

### Session-Based Authentication

After running `auth login` once, your session is saved and all commands work without `--browser`:

```bash
# Login once
cis-bench auth login --browser chrome

# Now all these work automatically
cis-bench catalog refresh
cis-bench download 23598
cis-bench search "ubuntu"
```

### Check Login Status

```bash
# Check if logged in
cis-bench auth status

# JSON output for scripting
cis-bench auth status --output-format json
```

### Logout

```bash
# Clear saved session
cis-bench auth logout

# You'll need to login again
cis-bench auth login --browser chrome
```

### Alternative: Cookie File

For automation or if browser cookie extraction fails:

```bash
# Export cookies from browser using ExportCookies plugin
# Save as cookies.txt in Netscape format

# Use cookie file
cis-bench download 23598 --cookies cookies.txt
```

---

## Common Workflows

### Workflow 1: Interactive Discovery

Use the unified `get` command for the easiest experience:

```bash
# Search and download interactively
cis-bench get "ubuntu"
# Shows matching benchmarks select one downloads exports

# Or skip interactive mode
cis-bench get "ubuntu 22.04" --format xccdf --style cis --non-interactive
```

### Workflow 2: Search and Download

For more control over the process:

```bash
# 1. Search with filters
cis-bench search "oracle" --platform-type cloud --latest

# 2. Download by ID
cis-bench download 23598

# 3. Export to format
cis-bench export 23598 --format xccdf --style cis
```

### Workflow 3: Platform-Specific Search

Find all benchmarks for a platform category:

```bash
# All cloud benchmarks
cis-bench search --platform-type cloud

# All databases
cis-bench search --platform-type database

# Specific platform
cis-bench search --platform ubuntu --latest
```

### Workflow 4: Export to Multiple Formats

Export a benchmark to different formats:

```bash
# Export by ID (from database)
cis-bench export 23598 --format yaml
cis-bench export 23598 --format csv
cis-bench export 23598 --format markdown
cis-bench export 23598 --format xccdf --style cis
cis-bench export 23598 --format xccdf --style disa

# Or export from file
cis-bench export benchmark.json --format xccdf --style cis
```

### Workflow 5: Scriptable with JSON

All query commands support JSON output for piping:

```bash
# Search with JSON output
cis-bench search "oracle" --output-format json | jq -r '.[].benchmark_id'

# List downloaded benchmarks
cis-bench list --output-format json | jq

# Check auth status
cis-bench auth status --output-format json
```

### Workflow 6: Batch Downloads

Download multiple benchmarks:

```bash
# Download multiple IDs
cis-bench download 23598 24008 22162

# From file
echo "23598" > urls.txt
echo "24008" >> urls.txt
cis-bench download --file urls.txt

# Download and export in one command
cis-bench download 23598 --format xccdf --format yaml
```

---

## Environment Configuration

### Data Storage Locations

The CLI supports three environments:

**Production (default):**
```bash
# Data stored in: ~/.cis-bench/
cis-bench catalog refresh
```

**Development:**
```bash
# Data stored in: ~/.cis-bench-dev/
export CIS_BENCH_ENV=dev
cis-bench catalog refresh
```

**Test (automatic):**
```bash
# Data stored in: /tmp/cis-bench-test/
# Used by pytest automatically
# Keeps tests isolated
```

### Environment Variables

```bash
# Disable SSL verification (for corporate proxies)
export CIS_BENCH_VERIFY_SSL=false

# Change data directory environment
export CIS_BENCH_ENV=dev

# Configure search limit
export CIS_BENCH_SEARCH_LIMIT=500

# Configure table title width
export CIS_BENCH_TABLE_TITLE_WIDTH=120
```

---

## Catalog Management

### Update Catalog

Keep your catalog up to date:

```bash
# Quick update (page 1 only - new benchmarks)
cis-bench catalog update

# Full refresh (all 66 pages - ~2 minutes)
cis-bench catalog refresh

# Check for updates to downloaded benchmarks
cis-bench catalog check-updates
```

### Catalog Commands

For complete catalog command syntax and options, see [Commands Reference](user-guide/commands-reference.md#catalog-management).

**Quick examples:**
```bash
cis-bench search "ubuntu" # Search catalog
cis-bench catalog platforms # List all platforms
cis-bench catalog stats # Show statistics
```

---

## Troubleshooting

### SSL Certificate Errors

If you get SSL errors with corporate proxies:

```bash
# Disable SSL verification
cis-bench auth login --browser chrome --no-verify-ssl

# Or set environment variable
export CIS_BENCH_VERIFY_SSL=false
cis-bench catalog refresh
```

See [Troubleshooting Guide](user-guide/troubleshooting.md) for more SSL solutions.

### Session Expired

If your session expires:

```bash
# Check status
cis-bench auth status

# Login again
cis-bench auth login --browser chrome
```

### Catalog Not Found

If you get "catalog not found" errors:

```bash
# Build catalog first
cis-bench catalog refresh

# Then search
cis-bench search "ubuntu"
```

---
