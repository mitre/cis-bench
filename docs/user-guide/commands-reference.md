# Command Reference

Complete reference for all CIS Benchmark CLI commands.

!!! tip "Quick Navigation"

- **Looking for examples?** See [End-to-End Workflows](workflows.md) for real-world scenarios
- **Need help?** See [Troubleshooting](troubleshooting.md) for common issues
- **Confused by terms?** See [Glossary](../about/glossary.md) for definitions

---

## Global Options

Available on all commands:

**Logging Levels:**
```bash
cis-bench --verbose <command> # Show DEBUG level logs
cis-bench --debug <command> # Same as --verbose
cis-bench --quiet <command> # Only warnings and errors
```

**Per-Command Flags:**
Most commands also accept `-v, --verbose`, `-d, --debug`, `-q, --quiet` flags at the end.

**Other Global Options:**
```bash
cis-bench --version # Show version
cis-bench --help # Show help
```

---

## Authentication Commands

### `cis-bench auth login`

Log in to CIS WorkBench and save session for future use.

**Syntax:**
```bash
cis-bench auth login --browser <browser> [OPTIONS]
```

**Required Options:**

- `-b, --browser` - Browser to extract cookies from (chrome|firefox|edge|safari)

**Optional Flags:**

- `--open` - Open CIS WorkBench login page in browser
- `--no-verify-ssl` - Disable SSL certificate verification

**Examples:**
```bash
# Login and open browser
cis-bench auth login --browser chrome --open

# Login (you're already logged in browser)
cis-bench auth login --browser chrome

# Login with SSL verification disabled
cis-bench auth login --browser chrome --no-verify-ssl
```

**What it does:**
1. Optionally opens browser to CIS WorkBench
2. Extracts session cookies from your browser
3. Validates the session
4. Saves to `~/.cis-bench/session.cookies`
5. All future commands use this saved session

---

### `cis-bench auth status`

Check if you're logged in and session is valid.

**Syntax:**
```bash
cis-bench auth status [OPTIONS]
```

**Options:**

- `-o, --output-format` - Output format (table|json|yaml)

**Examples:**
```bash
# Check status
cis-bench auth status

# JSON output for scripting
cis-bench auth status --output-format json
```

**Output:**
```json
{
"logged_in": true,
"session_file": "/Users/username/.cis-bench/session.cookies",
"cookie_count": 5,
"ssl_verify": false
}
```

---

### `cis-bench auth logout`

Clear saved session and log out.

**Syntax:**
```bash
cis-bench auth logout
```

**Example:**
```bash
cis-bench auth logout
```

**What it does:**

- Deletes `~/.cis-bench/session.cookies`
- You'll need to run `auth login` again to use commands

---

## Search and Discovery

### `cis-bench search`

Search for CIS benchmarks in local catalog.

**Syntax:**
```bash
cis-bench search [QUERY] [OPTIONS]
```

**Arguments:**

- `QUERY` - Search query (optional, omit to list all)

**Filter Options:**

- `--platform` - Filter by specific platform (e.g., ubuntu, aws, oracle-database)
- `--platform-type` - Filter by category (cloud, os, database, container, application)
- `--status` - Filter by status (Published, Archived, Draft) - default: Published
- `--latest` - Show only latest version of each benchmark
- `--limit` - Maximum results to show (default: 1000)

**Output Options:**

- `-o, --output-format` - Format (table|json|csv|yaml) - default: table

**Examples:**
```bash
# Basic search
cis-bench search "ubuntu 22.04"
cis-bench search "oracle cloud"

# Filter by platform category
cis-bench search --platform-type cloud
cis-bench search --platform-type database --latest

# Filter by specific platform
cis-bench search --platform aws
cis-bench search oracle --platform-type cloud

# Scripting with JSON
cis-bench search "ubuntu" --latest --output-format json | jq
cis-bench search --platform-type cloud --output-format csv

# List all published benchmarks
cis-bench search
```

**Requirements:**

- Must have catalog initialized: `cis-bench catalog refresh`
- If no catalog, shows helpful message with instructions

**Platform Types:**

- `cloud` - AWS, Azure, GCP, Oracle Cloud, Alibaba Cloud, IBM Cloud
- `os` - Ubuntu, RHEL, Windows, AlmaLinux, Oracle Linux, macOS
- `database` - MySQL, PostgreSQL, Oracle DB, MongoDB, MSSQL
- `container` - Kubernetes, Docker, EKS, AKS, GKE
- `application` - NGINX, Apache, Tomcat

---

### `cis-bench get`

Unified command: search + download + export in one step.

**Syntax:**
```bash
cis-bench get <QUERY> [OPTIONS]
```

**Arguments:**

- `QUERY` - Search query for benchmark

**Export Options:**

- `-f, --format` - Export format (yaml|csv|markdown|md|xccdf|xml|json) - default: yaml
- `--style` - XCCDF style (disa|cis) - default: disa, only for xccdf format
- `-o, --output` - Output file path (default: auto-generated)

**Auth Options:**

- `-b, --browser` - Browser for auth (only needed if no saved session)

**Behavior Options:**

- `--non-interactive` - Disable interactive prompts (show table instead)

**Output Options:**

- `-v, --verbose` - Enable verbose logging
- `-d, --debug` - Enable debug logging
- `-q, --quiet` - Quiet mode

**Examples:**
```bash
# Get and export in one command
cis-bench get "ubuntu 22.04" --format xccdf --style cis

# Get AWS benchmark
cis-bench get "aws eks" --format yaml

# Non-interactive mode (for CI/scripts)
cis-bench get "oracle cloud" --format json --non-interactive
```

**What it does:**
1. Searches catalog for your query
2. If single match: selects it automatically
3. If multiple matches: shows interactive menu (or table if --non-interactive)
4. Checks if already downloaded (uses cache)
5. If not cached: downloads benchmark
6. Exports to requested format
7. Shows output file path

**Requirements:**

- Catalog must be initialized
- Must be authenticated (saved session or --browser flag)

---

## Download and Management

### `cis-bench download`

Download benchmarks by ID.

**Syntax:**
```bash
cis-bench download <BENCHMARK_ID> [BENCHMARK_ID...] [OPTIONS]
```

**Arguments:**

- `BENCHMARK_ID` - One or more benchmark IDs or URLs

**Input Options:**

- `-f, --file PATH` - File containing URLs/IDs (one per line)

**Auth Options:**

- `-b, --browser` - Browser for auth (only needed if no saved session)
- `-c, --cookies PATH` - Use cookies from file instead of saved session

**Output Options:**

- `-o, --output-dir PATH` - Output directory (default: ./benchmarks)
- `--format` - Export formats (json|yaml|csv|markdown|xccdf) - can specify multiple

**Behavior Options:**

- `--force` - Force re-download even if already cached
- `--no-verify-ssl` - Disable SSL verification
- `-v, --verbose` - Verbose logging
- `-d, --debug` - Debug logging
- `-q, --quiet` - Quiet mode

**Examples:**
```bash
# Download single benchmark (uses saved session)
cis-bench download 23598

# Download multiple
cis-bench download 23598 22605 18208

# Force re-download (skip cache check)
cis-bench download 23598 --force

# Download with multiple export formats
cis-bench download 23598 --format json --format xccdf

# Download from file
cis-bench download --file urls.txt

# First time (no saved session)
cis-bench download 23598 --browser chrome
```

**What it does:**
1. Checks if already cached (shows message if yes, unless --force)
2. Authenticates (uses saved session or --browser)
3. Downloads benchmark from WorkBench with progress bar
4. Saves to database cache
5. Saves to file in output directory
6. Exports to requested formats

---

### `cis-bench export`

Export benchmark to different formats.

**Syntax:**
```bash
cis-bench export <IDENTIFIER> [OPTIONS]
```

**Arguments:**

- `IDENTIFIER` - Benchmark ID (numeric) OR file path

**Export Options:**

- `-f, --format` - Format (yaml|csv|markdown|md|xccdf|xml) - default: yaml
- `--style` - XCCDF style (disa|cis) - default: disa, only for xccdf
- `-o, --output PATH` - Output file (default: auto-generated)

**Input Options:**

- `--input-dir PATH` - Input directory for file paths (default: ./benchmarks)

**Examples:**
```bash
# Export from database by ID
cis-bench export 23598 --format xccdf --style cis
cis-bench export 23598 --format yaml

# Export from file
cis-bench export benchmark.json --format xccdf --style disa
cis-bench export benchmark.json --format csv -o output.csv

# All formats
cis-bench export 23598 --format yaml
cis-bench export 23598 --format csv
cis-bench export 23598 --format markdown
cis-bench export 23598 --format xccdf --style disa
cis-bench export 23598 --format xccdf --style cis
```

**XCCDF Styles:**

- `disa` - DISA/DoD STIG format (XCCDF 1.1.4, CCIs, VulnDiscussion)
- `cis` - CIS native format (XCCDF 1.2, CIS Controls, MITRE ATT&CK)

---

### `cis-bench list`

List downloaded benchmarks.

**Syntax:**
```bash
cis-bench list [OPTIONS]
```

**Options:**

- `--output-dir PATH` - Directory to scan (default: ./benchmarks)
- `-o, --output-format` - Format (table|json|csv|yaml) - default: table

**Examples:**
```bash
# List all downloaded benchmarks
cis-bench list

# JSON output
cis-bench list --output-format json | jq

# CSV export
cis-bench list --output-format csv > inventory.csv
```

**Output Fields:**

- Title
- Version
- Recommendations count
- CIS Controls v8 count
- MITRE mappings count
- NIST controls count
- Filename

---

### `cis-bench info`

Show detailed information about a benchmark.

**Syntax:**
```bash
cis-bench info <FILENAME> [OPTIONS]
```

**Arguments:**

- `FILENAME` - Benchmark JSON file

**Options:**

- `--output-dir PATH` - Directory containing benchmark (default: ./benchmarks)
- `-o, --output-format` - Format (table|json|yaml) - default: table

**Examples:**
```bash
# Show benchmark details
cis-bench info benchmark.json

# JSON output
cis-bench info benchmark.json --output-format json

# YAML output
cis-bench info benchmark.json --output-format yaml
```

**Displays:**

- Title, version, benchmark ID
- Downloaded date, scraper version
- Total recommendations
- CIS Controls counts (v7, v8)
- MITRE mappings count
- NIST controls count
- Sample recommendations

---

## Catalog Management

### `cis-bench catalog refresh`

Build or refresh the searchable catalog database.

**Syntax:**
```bash
cis-bench catalog refresh [OPTIONS]
```

**Options:**

- `--browser TEXT` - Browser for auth (default: chrome)
- `--max-pages INTEGER` - Limit pages to scrape (for testing)
- `--rate-limit FLOAT` - Seconds between batches (default: 2.0)

**Examples:**
```bash
# Full catalog refresh (~2 minutes with parallel scraping)
cis-bench catalog refresh

# Test with limited pages
cis-bench catalog refresh --max-pages 5

# Faster scraping (less polite)
cis-bench catalog refresh --rate-limit 1.0
```

**What it does:**
1. Authenticates with WorkBench
2. Scrapes catalog pages in parallel (10 pages/batch, 5 threads)
3. Detects ~66 pages automatically
4. Builds searchable database with ~1,300+ benchmarks
5. Creates FTS5 full-text search index
6. Takes ~2 minutes for full catalog

**Performance:**

- Parallel: 10 pages per batch
- Threads: 5 concurrent
- Retry logic: 3 attempts with backoff
- Failure threshold: Aborts if >10% fail

---

### `cis-bench catalog search`

Search catalog (similar to top-level search).

**Syntax:**
```bash
cis-bench catalog search [QUERY] [OPTIONS]
```

See `cis-bench search` for options and examples.

---

### `cis-bench catalog info`

Show catalog information for a benchmark.

**Syntax:**
```bash
cis-bench catalog info <BENCHMARK_ID> [OPTIONS]
```

**Options:**

- `-o, --output-format` - Format (table|json|yaml)

---

### `cis-bench catalog platforms`

List all platforms with benchmark counts.

**Syntax:**
```bash
cis-bench catalog platforms [OPTIONS]
```

**Options:**

- `-o, --output-format` - Format (table|json|csv|yaml)

**Example:**
```bash
cis-bench catalog platforms
cis-bench catalog platforms --output-format json
```

---

### `cis-bench catalog stats`

Show catalog statistics.

**Syntax:**
```bash
cis-bench catalog stats [OPTIONS]
```

**Options:**

- `-o, --output-format` - Format (table|json|yaml)

**Example:**
```bash
cis-bench catalog stats
cis-bench catalog stats --output-format json
```

**Shows:**

- Total benchmarks
- Published benchmarks
- Downloaded benchmarks count
- Platforms count
- Communities count
- Last refresh date

---

## Output Formats

All query commands support `--output-format` for scripting:

**Available Formats:**

- `table` - Human-friendly table (default)
- `json` - JSON for piping to jq, etc.
- `csv` - CSV for spreadsheets
- `yaml` - YAML for configs

**Commands Supporting Output Formats:**

- `search`
- `list`
- `info`
- `auth status`
- `catalog search`
- `catalog info`
- `catalog platforms`
- `catalog stats`

**Scripting Examples:**
```bash
# Get benchmark IDs
cis-bench search oracle --platform-type cloud --output-format json | jq -r '.[].benchmark_id'

# Export to CSV
cis-bench search "ubuntu" --latest --output-format csv > benchmarks.csv

# Check auth in scripts
if cis-bench auth status --output-format json 2>/dev/null | jq -r '.logged_in' | grep -q true; then
echo "Authenticated"
fi

# Download all Oracle Cloud benchmarks
cis-bench search oracle --platform-type cloud --latest --output-format json | \
jq -r '.[].benchmark_id' | \
xargs -I {} cis-bench download {}
```

---

## Environment Variables

**Session/Auth:**

- `CIS_BENCH_VERIFY_SSL` - SSL verification (true/false, default: false)

**Display:**

- `CIS_BENCH_TABLE_TITLE_WIDTH` - Table title column width (default: 90)
- `CIS_BENCH_SEARCH_LIMIT` - Default search limit (default: 1000)

**Environment:**

- `CIS_BENCH_ENV` - Environment (production|dev|test)

**SSL/TLS (automatically respected):**

- `REQUESTS_CA_BUNDLE` - Path to CA cert bundle
- `SSL_CERT_FILE` - Path to SSL cert file
- `CURL_CA_BUNDLE` - curl-compatible cert bundle

---

## Common Workflows

### First Time Setup
```bash
# Install
pip install -e .

# Login (one-time)
cis-bench auth login --browser chrome

# Build catalog (one-time, ~2 min)
cis-bench catalog refresh
```

### Find and Download
```bash
# Search for benchmarks
cis-bench search "oracle cloud"

# Download by ID
cis-bench download 23598

# Export to XCCDF
cis-bench export 23598 --format xccdf --style cis
```

### Unified Workflow (Easiest)
```bash
# One command does everything
cis-bench get "ubuntu 22" --format xccdf --style cis
```

### Scripting and Automation
```bash
# Search and pipe
cis-bench search --platform-type cloud --output-format json | jq

# Batch download
cis-bench search "windows server" --latest --output-format json | \
jq -r '.[].benchmark_id' | \
xargs -I {} cis-bench download {}

# Inventory
cis-bench list --output-format csv > inventory.csv
```

---

## Exit Codes

- `0` - Success
- `1` - Error (authentication failed, file not found, etc.)

---

## Data Storage

**Session:**

- `~/.cis-bench/session.cookies` - Saved authentication session

**Catalog Database:**

- `~/.cis-bench/catalog.db` - SQLite database with FTS5 search

**Downloaded Benchmarks:**

- Stored in: `~/.cis-bench/catalog.db` (downloaded_benchmarks table)
- Also saved as: `./benchmarks/*.json` files

**Development/Test:**

- Dev: `~/.cis-bench-dev/`
- Test: `/tmp/cis-bench-test/`

---

## See Also

- [Getting Started](../getting-started.md) - Installation and setup
- [Catalog Guide](catalog-guide.md) - Catalog usage details
- [XCCDF Guide](xccdf-guide.md) - XCCDF export details
- [Configuration](configuration.md) - Environment configuration
- [Troubleshooting](troubleshooting.md) - Common issues
