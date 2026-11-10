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

Errors are printed without a Python traceback. Add `--verbose` to also log the full error with its traceback, for example `cis-bench --verbose download <ID>`.

**Per-Command Flags:**
Most commands also accept `-v, --verbose`, `-d, --debug`, `-q, --quiet` flags at the end.

**Other Global Options:**
```bash
cis-bench --version # Show version
cis-bench --help # Show help
```

### Offline mode

`cis-bench --offline <command>` never contacts CIS WorkBench. The `offline` setting
(`CIS_BENCH_OFFLINE=true`, or `offline = true` in `config.toml`) turns it on for every run;
`--offline` turns it on for one run whatever the setting says. See
[Configuration](configuration.md#settings).

Offline, commands use the catalog and the downloaded benchmarks in `catalog.db`, as `cargo
--offline` and `uv --offline` use their caches. A command fails only at the point where it
needs WorkBench. Nothing is sent, and the error (on stderr, exit code 1) names the command
and what it needed:

```text
Error: cis-bench get needs CIS WorkBench to download benchmark 23598, and offline mode is on (--offline, CIS_BENCH_OFFLINE, or offline = true in config.toml). Nothing was sent to WorkBench. Run 'cis-bench cache status' to see what is available offline.
```

[`cis-bench cache status`](#cis-bench-cache-status) shows what is there to work with.

| Command | Offline |
| --- | --- |
| `search`, `export`, `info`, `list`, `validate`, `remove`, `config`, `cache status`, `auth logout`, `catalog search`, `catalog list`, `catalog info`, `catalog platforms`, `catalog stats` | Work as usual (they never contact WorkBench) |
| `get` | Exports a downloaded benchmark; fails for one that is not downloaded |
| `diff` | Compares files and downloaded benchmarks; fails for an ID that is not downloaded |
| `download` | Reports each downloaded benchmark as already cached; fails each one that is not downloaded and exits 1 |
| `catalog download` | Reports an up-to-date copy; fails when the benchmark is not downloaded or has an update |
| `catalog check-updates` | Compares versions only, as its own `--offline` does |
| `auth login`, `auth status`, `catalog refresh`, `catalog update` | Fail: they only talk to WorkBench |

---

## Authentication Commands

### `cis-bench auth login`

Log in to CIS WorkBench and save session for future use.

**Syntax:**
```bash
cis-bench auth login --browser <browser> [OPTIONS]
```

**Options:**

- `-b, --browser` - Browser to extract cookies from (chrome|firefox|edge|safari)
- `-c, --cookies PATH` - Load cookies from file instead of browser (Netscape format)
- `-o, --open` - Open CIS WorkBench login page in browser
- `--no-verify-ssl` - Disable SSL certificate verification

**Examples:**
```bash
# Login and open browser
cis-bench auth login --browser chrome --open

# Login (you're already logged in browser)
cis-bench auth login --browser chrome

# Login with Firefox (recommended for Windows users)
cis-bench auth login --browser firefox

# Login using exported cookie file
cis-bench auth login --cookies cookies.txt

# Login with SSL verification disabled
cis-bench auth login --browser chrome --no-verify-ssl
```

**What it does:**
1. Optionally opens browser to CIS WorkBench
2. Extracts session cookies from your browser (or loads from file)
3. Validates the session
4. Saves to `~/.local/state/cis-bench/session.cookies` (the state folder)
5. All future commands use this saved session

!!! tip "Windows Users"
    If you get permission errors with Chrome or Edge, use Firefox instead:
    ```bash
    cis-bench auth login --browser firefox
    ```
    Chrome 127+ uses App-Bound Encryption on Windows which requires admin access.
    Firefox works without admin privileges.

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
"session_file": "/Users/username/.local/state/cis-bench/session.cookies",
"cookie_count": 5,
"ssl_verify": false
}
```

**Exit code:** `0` when WorkBench accepts the saved session. `1` when WorkBench rejects it
(the session expired), and `1` when WorkBench could not be reached; in that case the saved
session is kept and nothing is known about whether it is still valid. The exit code is the
same in every output format: with `-o json` or `-o yaml`, stdout holds only the document
(`"logged_in": false` and exit `1` for an expired session), and the progress lines go to
stderr.

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

- Deletes `~/.local/state/cis-bench/session.cookies`
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
- `--status` - Filter by status (`Published`, `Accepted`, `Draft`, `Archived`, `Rejected`, `Final Update`, `Withdrawn`, or `all`) - default: `Published`. `Withdrawn` is not a WorkBench status: a complete `catalog refresh` gives it to benchmarks WorkBench no longer lists
- `--latest` - Show only latest version of each benchmark
- `--limit` - Maximum results to show (default: `CIS_BENCH_SEARCH_LIMIT`, 100). When the limit cuts the list short, the output says how many matched: `Showing 100 of 349 results; use --limit to see more`

**Output Options:**

- `-o, --output-format` - Format (table|json|csv|yaml) - default: table

**Examples:**
```bash
# Basic search
cis-bench search "ubuntu 22.04"
cis-bench search "oracle cloud"

# One release, by version (with or without the leading v)
cis-bench search "kubernetes v2.1.0"
cis-bench search "kubernetes 2.1"       # 2.1 and 2.1.x, not 2.10.x

# Filter by platform category
cis-bench search --platform-type cloud
cis-bench search --platform-type database --latest

# Filter by specific platform
cis-bench search --platform aws
cis-bench search oracle --platform-type cloud

# Search across all statuses (including Draft, Archived, Final Update)
cis-bench search "ubuntu" --status all

# Scripting with JSON
cis-bench search "ubuntu" --latest --output-format json | jq
cis-bench search --platform-type cloud --output-format csv

# List all published benchmarks
cis-bench search
```

**How a query matches:**

- Every word must match. A word matches the start of a word in the title, platform or community (`ubunt` finds Ubuntu). These are the fields the catalog listing gives for every benchmark; a description, known only for benchmarks whose WorkBench page has been read, is not searched.
- A dotted number or a `v` number (`v2.1.0`, `2.1`, `v18`) also matches a benchmark's version from its start, number by number: `2.1` finds v2.1.0 and v2.1.3, not v2.10.0 or v1.2.1.
- A word also matches a whole word of a version (`vNext`, the `NEXT` of `v1.1.0 NEXT`), so a name pasted with its version is found.
- A plain number (`almalinux 8`) is looked up in the same text as any other word (title, platform, community), never in versions.
- With no words, every benchmark that passes the filters is listed by title, then by ID.

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

- `QUERY` - Search words, or a catalog ID

**Export Options:**

- `-f, --format` - Export format (yaml|csv|markdown|md|xccdf|xml|json) - default: yaml
- `--style` - XCCDF style (disa|cis) - default: disa, only for xccdf format
- `-o, --output PATH` - Output file (a file path, not a folder; default: auto-generated). A folder is refused with a usage error

**Behavior Options:**

- `--non-interactive` - No menu: when several benchmarks match, take the best match and say how many others there were
- `--force` - Download again and replace the cached copy, if there is one (as `download --force`)

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

# Get one release by its version
cis-bench get "kubernetes v2.0.1" --format xccdf

# Get by catalog ID (any status, latest or not)
cis-bench get 23598 --format xccdf

# Replace a cached copy with a fresh download
cis-bench get 23598 --force --format xccdf

# Non-interactive mode (for CI/scripts)
cis-bench get "oracle cloud" --format json --non-interactive
```

**What it does:**
1. A catalog ID selects that benchmark. Otherwise searches the catalog among Published benchmarks: the latest release of each, plus any release the query names by its version (`kubernetes v2.0.1`)
2. If single match: selects it automatically
3. If multiple matches: shows a menu, best match first; with `--non-interactive` (or no usable terminal) takes the best match and prints how many others matched and the `search` command that lists them
4. Checks if already downloaded (uses cache; `--force` skips this and downloads again)
5. If not cached: downloads benchmark
6. Exports to requested format
7. Shows output file path

**Requirements:**

- Catalog must be initialized: `cis-bench catalog refresh`
- Must be authenticated: `cis-bench auth login --browser chrome`

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

- `-f, --file PATH` - File containing URLs/IDs (one per line; blank lines and `#` comments are skipped)

**Accepted references:** a numeric benchmark ID (`23598`), a `/benchmarks/23598` path, or an `https://` URL on the configured WorkBench origin (`https://workbench.cisecurity.org/benchmarks/23598`; a query string or fragment is dropped). Every reference is validated before authentication: a cleartext `http://` URL, another host, a non-numeric ID or path traversal aborts the whole run, and with `--file` the message names the offending line, so nothing is downloaded from a bad list.

**Output Options:**

- `-o, --output-dir PATH` - Output directory (default: `<data folder>/benchmarks`, for example `~/.local/share/cis-bench/benchmarks`)
- `-fmt, --format` - Export formats (json|yaml|csv|markdown|xccdf) - can specify multiple

**Behavior Options:**

- `--force` - Force re-download even if already cached
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
```

**What it does:**
1. Checks if already cached (shows message if yes, unless --force)
2. Uses saved session from `cis-bench auth login`
3. Downloads benchmark from WorkBench with progress bar (see "How recommendations are fetched" below)
4. Saves to the cache (`catalog.db`) with the benchmark's version and the catalog's revision date for it, when there is a catalog; `get` and `diff` cache the same way
5. Exports to the requested formats in the output directory (JSON by default)

**How recommendations are fetched:**

- Recommendation pages are fetched in parallel, paced by the `CIS_BENCH_MAX_CONCURRENT_REQUESTS`, `CIS_BENCH_BATCH_SIZE` and `CIS_BENCH_REQUESTS_PER_SECOND` settings (322 recommendations took about two minutes on 2026-11-04 with the defaults). `cis-bench catalog refresh` uses the same settings.
- The progress bar counts finished pages, so it can advance out of navtree order; the saved benchmark keeps navtree order.
- Each request has a timeout (`CIS_BENCH_REQUEST_TIMEOUT`) and is retried `CIS_BENCH_REQUEST_RETRIES` times (two by default); see [Configuration](configuration.md#settings). A page that still fails is logged with its URL and the error, and the download continues without it.
- Every request identifies itself with the User-Agent `cis-bench-cli/<version> (github.com/mitre/cis-bench)`.
- If WorkBench answers with its login page, the saved session has expired: no further batch starts and the download stops with an authentication error. Run `cis-bench auth login` again.

**Exit code:** `0` when every requested benchmark downloaded, cached and exported. `1` when any benchmark, cache write or export failed (the others are still downloaded and the summary names the failed IDs; a benchmark whose cache write failed is still exported), or when the session expired (the run stops at once and later benchmarks are not attempted). `cis-bench get` exits `1` with the same login message when the session expires during its download.

**Requirements:**

- Must be authenticated first: `cis-bench auth login --browser chrome`

---

### `cis-bench export`

Export one or more benchmarks to different formats.

**Syntax:**
```bash
cis-bench export <IDENTIFIER> [IDENTIFIER...] [OPTIONS]
```

**Arguments:**

- `IDENTIFIER` - One or more benchmark IDs (numeric) or file paths

**Export Options:**

- `-f, --format` - Format (yaml|csv|markdown|md|xccdf|xml) - default: yaml
- `--style` - XCCDF style (disa|cis) - default: disa, only for xccdf
- `-o, --output PATH` - Output file (single export only; a folder is refused with a usage error, use `--output-dir` for a folder)
- `--output-dir PATH` - Output directory for batch exports (creates if needed)

**Input Options:**

- `--input-dir PATH` - Input directory for file paths (default: `<data folder>/benchmarks`)

**Examples:**
```bash
# Single export from database
cis-bench export 23598 --format xccdf --style cis
cis-bench export 23598 --format yaml

# Batch export multiple benchmarks
cis-bench export 23598 22605 18208 --format yaml
cis-bench export 23598 22605 --format xccdf --style disa

# Export to specific directory
cis-bench export 23598 22605 --format xccdf --output-dir ./stig_exports

# Export from file
cis-bench export benchmark.json --format xccdf --style disa
cis-bench export benchmark.json --format csv -o output.csv

# Mixed: IDs and files together
cis-bench export 23598 local_benchmark.json --format yaml
```

**Batch Export Features:**

- Exports continue even if individual benchmarks fail
- Shows progress: `[1/3]`, `[2/3]`, `[3/3]`
- Summary shows success/failure counts
- Auto-generates filenames: `benchmark_<ID>.yaml`

**XCCDF Styles:**

- `disa` - DISA/DoD STIG format (XCCDF 1.1.4, CCIs, VulnDiscussion)
- `cis` - CIS native format (XCCDF 1.2, CIS Controls, MITRE ATT&CK)

---

### `cis-bench validate`

Check XCCDF files against the NIST XCCDF schema, with the schemas shipped in cis-bench.

**Syntax:**
```bash
cis-bench validate <FILE>...
```

**Arguments:**

- `FILE...` - One or more XCCDF files: an export, or any XCCDF 1.1 or 1.2 document

**Examples:**
```bash
# Validate an export
cis-bench export 23598 --format xccdf --style cis
cis-bench validate benchmark_23598.xml

# Several at once
cis-bench validate exports/*.xml
```

**What it does:**

1. Reads each file with a parser that expands no entities and touches no network
2. Picks the schema from the root element's namespace: `http://checklists.nist.gov/xccdf/1.1` (DISA-style exports) or `http://checklists.nist.gov/xccdf/1.2` (CIS-style exports)
3. Validates against that schema and lists every error with its line

**Exit codes** (the same as `oscap xccdf validate`): `0` every file is valid; `2` a file is not valid; `1` a file could not be validated (missing, not XML, carrying a DOCTYPE, not XCCDF, or an XCCDF version with no shipped schema).

Schema validity means the document is well-formed XCCDF. It is not DISA or CIS convention compliance.

**The schemas:** the package ships OpenSCAP's XCCDF 1.1 and 1.2 schema files (`cis_bench/schemas/xccdf/`, with the `common/` and `cpe/` files they import). From a repository checkout the same check with xmllint is:

```bash
xmllint --noout --schema src/cis_bench/schemas/xccdf/1.2/xccdf_1.2.xsd benchmark_23598.xml   # CIS style, XCCDF 1.2
xmllint --noout --schema src/cis_bench/schemas/xccdf/1.1/xccdf-schema.xsd benchmark_23598.xml # DISA style, XCCDF 1.1
```

---

### `cis-bench list`

List the downloaded benchmarks, and the exported files in the benchmarks folder.

A benchmark is *downloaded* when it is in the cache (`catalog.db`), where `download` and `get` put it and `remove` takes it from. The files in the benchmarks folder are *exports*: whatever `download --format` wrote. They are yours to move, rename or delete; doing so does not change what is downloaded, and `list` shows them under their own heading.

**Syntax:**
```bash
cis-bench list [OPTIONS]
```

**Options:**

- `--output-dir PATH` - Folder whose exported files to list (default: `<data folder>/benchmarks`)
- `-o, --output-format` - Format (table|json|csv|yaml) - default: table. `json` and `yaml` carry both parts (`downloaded`, `exported_files`); `csv` holds the downloaded benchmarks only

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

Downloaded benchmarks: ID, title, version, recommendations count, CIS Controls v8 count, MITRE mappings count, NIST controls count, and when it was downloaded. Exported files: the folder and the file names.

**Times:** a download is recorded once, in UTC. The table shows it in your zone and names the zone (`2026-11-06 21:05:58 EST`; set `TZ` to choose another); `json`, `yaml` and `csv` carry it in ISO 8601 with its offset (`2026-11-07T02:05:58+00:00`). A time written by an earlier version carries no zone; it is shown as it was written, marked `(zone not recorded)` in tables, and never guessed into a zone. `info`, `catalog stats` and `catalog check-updates` show times the same way.

---

### `cis-bench cache status`

Show what `cis-bench` can work with without CIS WorkBench: the catalog, the downloaded benchmarks and the saved session. Everything is read from this machine; nothing is sent to WorkBench, so it works in [offline mode](#offline-mode).

**Syntax:**
```bash
cis-bench cache status [OPTIONS]
```

**Options:**

- `-o, --output-format` - Format (table|json|yaml) - default: table

**Examples:**
```bash
# What is available offline
cis-bench cache status

# JSON output
cis-bench cache status --output-format json | jq
```

**Output:**

- **Catalog**: how many benchmarks it lists, when it was last fully refreshed (`catalog refresh`) and last updated (`catalog update`), each `never` when it has not happened. A catalog that lists no benchmarks is shown as `none`.
- **Downloaded benchmarks**: the same set `list` shows, with ID, title, version and when each was downloaded. A benchmark the catalog does not list takes its title from the cached copy, as in `list`.
- **Session**: whether a session is saved, when it was saved and the file it is in. Login saves the session right after confirming it works; later checks (`auth status`, a download) are not recorded, so this is the time of the last login, not of the last check.

Anything missing is shown as `none` with the command that provides it; a `catalog.db` that exists but cannot be read (corrupt, locked) is an error naming the file (exit code 1), never `none`. `json` and `yaml` carry one object with three parts: `catalog` (`present`, `benchmarks`, `last_full_refresh`, `last_update`), `downloaded` (`benchmark_id`, `title`, `version`, `downloaded_at`) and `session` (`present`, `file`, `saved_at`); times are ISO 8601 as recorded, with their offset, and `null` when absent. A refresh time written by an earlier version may carry no offset: it is given as written, never guessed into a zone, and tables mark it `(zone not recorded)`, as `list` does for its times.

---

### `cis-bench info`

Show detailed information about a downloaded benchmark, or about an exported JSON file.

**Syntax:**
```bash
cis-bench info <BENCHMARK> [OPTIONS]
```

**Arguments:**

- `BENCHMARK` - A catalog ID (the downloaded copy in the cache), or the path or name of an exported JSON file

**Options:**

- `--output-dir PATH` - Folder a file name is looked for in (default: `<data folder>/benchmarks`)
- `-o, --output-format` - Format (table|json|yaml) - default: table

**Examples:**
```bash
# The downloaded copy, by catalog ID
cis-bench info 23598

# An exported file
cis-bench info benchmark.json

# JSON output
cis-bench info benchmark.json --output-format json

# YAML output
cis-bench info benchmark.json --output-format yaml
```

**Displays:**

- Title, version, benchmark ID
- When it was downloaded (in your zone in the table, ISO 8601 with offset in `json` and `yaml`; see `list` on times), scraper version, and the source (cache, or the file)
- Total recommendations
- CIS Controls counts (v7, v8)
- MITRE mappings count
- NIST controls count
- Sample recommendations

---

### `cis-bench diff`

Compare two versions of a benchmark: which recommendations were added, removed, changed or renumbered.

**Syntax:**
```bash
cis-bench diff <OLD> <NEW> [OPTIONS]
```

**Arguments:**

- `OLD`, `NEW` - Each a catalog ID or the path of a benchmark JSON file. An ID is read from the cache; one that is not downloaded yet is downloaded from CIS WorkBench and cached first, as `get` does (it needs `cis-bench auth login`; no export file is written). Messages about the download go to stderr, so `--format json` output stays valid JSON.

**Options:**

- `-f, --format` - Format (table|json|markdown|summary) - default: table
- `-v, --verbose` - Under the table, list the changed fields of each modified recommendation

**Examples:**
```bash
# Two downloaded versions
cis-bench diff 22605 23598

# Two files
cis-bench diff old.json new.json

# A Markdown report
cis-bench diff 22605 23598 --format markdown > changes.md

# JSON for scripts
cis-bench diff 22605 23598 --format json | jq '.changes.modified[].ref'
```

**How recommendations are matched:**

- By ref (`1.1.1`). A ref only in `NEW` is *added*, only in `OLD` *removed*.
- A ref in both whose content differs is *modified*, with the names of the fields that changed (`title`, `audit`, `impact`, ...). List order inside a field is ignored, and so are the WorkBench URLs (the recommendation's and its parent's) and artifact IDs, which change in every release.
- A field whose text differs only in whitespace (line wrapping, spacing, indentation) is *reformatted*, never a modification. A recommendation whose only changes are reformatted fields is listed as reformatted; a modified one names its reformatted fields separately. Nothing else is folded: case, punctuation and words joined or split are changes. Two downloads of one benchmark by the same cis-bench version are identical; formatting differences come from comparing copies made by different versions.
- When the two benchmarks were made by different scraper versions (`scraper_version`), every format says so.
- A removed ref and an added ref whose titles are at least 85% alike are one *renumbered* recommendation.

**Formats:**

- `table` - Counts, then one row per change; `--verbose` adds each modified recommendation's fields and lists the reformatted ones
- `summary` - Counts only
- `markdown` - A Markdown document with a table per kind of change, reformatted included
- `json` - `old_version`, `new_version`, `benchmark_title`, `scraper_versions` (`old`, `new`), `scraper_versions_differ`, `summary` (the counts) and `changes` (`added`, `removed`, `modified`, `reformatted`, `renumbered`; unchanged recommendations are left out). Each modified entry has `fields_changed`, `reformatted_fields` and `diff`, DeepDiff's report of every change; each reformatted entry has `fields`.

---

### `cis-bench remove`

Remove downloaded benchmarks from the local cache.

**Syntax:**
```bash
cis-bench remove <REFERENCE> [REFERENCE...] [OPTIONS]
```

**Arguments:**

- `REFERENCE` - One or more benchmark IDs or URLs, in the same forms `cis-bench download` accepts

**Options:**

- `-y, --yes` - Remove without asking for confirmation

**Examples:**
```bash
# Remove one cached benchmark (lists it and asks first)
cis-bench remove 23598

# Remove several without a prompt (scripts)
cis-bench remove 23598 22605 --yes
```

**What it does:**

1. Validates every reference first; one bad reference removes nothing
2. Lists each cached benchmark it will remove (ID, title, version, download date) and asks for confirmation unless `--yes`
3. Deletes the cached copy that `download`, `get` and `export <ID>` use
4. Keeps the benchmark in the catalog, so `cis-bench search` still finds it and it can be downloaded again
5. Leaves exported files such as `<data folder>/benchmarks/*.json` untouched

**Exit code:** `0` when every requested benchmark was removed; `1` when a reference is invalid, a benchmark was not downloaded, or you declined the prompt.

To replace a bad copy instead of removing it, run `cis-bench download <ID> --force`. `remove` makes no network request and needs no login.

---

## Catalog Management

### `cis-bench catalog refresh`

Build or refresh the searchable catalog database.

**Syntax:**
```bash
cis-bench catalog refresh [OPTIONS]
```

**Options:**

- `--browser TEXT` - Browser to read cookies from (default: the `CIS_BENCH_BROWSER` setting)
- `--max-pages INTEGER` - Limit pages to scrape (for testing)
- `--rate-limit SECONDS` - Seconds between requests to WorkBench for this run, greater than 0 (default: 1 / `CIS_BENCH_REQUESTS_PER_SECOND`)

**Examples:**
```bash
# Full catalog refresh (under a minute)
cis-bench catalog refresh

# Test with limited pages
cis-bench catalog refresh --max-pages 5

# Gentler: one request per second
cis-bench catalog refresh --rate-limit 1.0
```

**What it does:**
1. Authenticates with WorkBench
2. Scrapes catalog pages in parallel (`CIS_BENCH_BATCH_SIZE` pages per batch, `CIS_BENCH_MAX_CONCURRENT_REQUESTS` at a time, at most `CIS_BENCH_REQUESTS_PER_SECOND` requests per second)
3. Detects the page count from page 1 (about 80 pages)
4. Builds searchable database with about 1,500 benchmarks
5. Creates FTS5 full-text search index
6. After a complete refresh (every page counted and fetched, none failed or empty, no `--max-pages`), marks the benchmarks WorkBench no longer lists `Withdrawn`: they leave the default search results (`--status all` or `--status Withdrawn` shows them), are never the latest release, and keep any downloaded copy; the summary says how many. A refresh that is not complete marks nothing and says "Withdrawn: not checked". A withdrawn benchmark that WorkBench lists again gets its WorkBench status back
7. Takes under a minute for the full catalog

**Performance:**

- Parallel: `CIS_BENCH_BATCH_SIZE` pages per batch, `CIS_BENCH_MAX_CONCURRENT_REQUESTS` at a time, at most `CIS_BENCH_REQUESTS_PER_SECOND` requests per second (or one per `--rate-limit` seconds); `cis-bench download` uses the same settings
- Sessions: each worker thread uses its own copy of your saved session; nothing logs in again
- Retry logic: the timeout from `CIS_BENCH_REQUEST_TIMEOUT` and `CIS_BENCH_REQUEST_RETRIES` retries on timeouts, dropped connections and 429/502/503/504, honoring WorkBench's `Retry-After` up to 60 seconds ([Configuration](configuration.md#settings)); a 404 or a page that cannot be parsed is not retried
- Failure threshold: Aborts if >10% fail
- Expired session: a login page stops the refresh after the batch that saw it

---

### `cis-bench catalog update`

Check the first page of the WorkBench listing for new and updated benchmarks. Faster than a
full refresh (a few seconds; 4 s on 2026-11-06).

**Syntax:**
```bash
cis-bench catalog update [OPTIONS]
```

**Options:**

- `--browser TEXT` - Browser to read cookies from when no saved session can be used (default: the `CIS_BENCH_BROWSER` setting)

**Example:**
```bash
cis-bench catalog update
```

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

The catalog listing gives the title, version, status, platform, community, owner and collections. The publish date and description come from the benchmark's own WorkBench page, which cis-bench reads when it downloads the benchmark and when `catalog check-updates` runs online; until then they are not shown.

**Options:**

- `-o, --output-format` - Format (table|json|yaml)

---

### `cis-bench catalog list`

List the benchmarks in the local catalog.

**Syntax:**
```bash
cis-bench catalog list [OPTIONS]
```

**Options:**

- `--platform TEXT` - Filter by platform
- `--status` - Filter by status (`Published`, `Accepted`, `Draft`, `Archived`, `Rejected`, `Final Update`, `Withdrawn`, or `all`) - default: `Published`
- `--latest` - Latest versions only
- `--limit INTEGER` - Max results (default: the `CIS_BENCH_SEARCH_LIMIT` setting, 100)

**Examples:**
```bash
cis-bench catalog list
cis-bench catalog list --platform "Operating System" --latest
cis-bench catalog list --status Withdrawn   # benchmarks WorkBench no longer lists
```

---

### `cis-bench catalog download`

Download a benchmark named by its ID, or by a name that is searched for in the catalog.

**Syntax:**
```bash
cis-bench catalog download [OPTIONS] BENCHMARK_ID_OR_NAME
```

**Options:**

- `--browser TEXT` - Browser to read cookies from when no saved session can be used (default: the `CIS_BENCH_BROWSER` setting)
- `--force` - Download again even if the cached copy is current
- `--interactive` - Choose from a list when several benchmarks match

A benchmark that is already cached is downloaded again only when `catalog check-updates` would list it (a newer catalog version, or a later WorkBench publish date than the cached copy's), or with `--force`.

**Examples:**
```bash
cis-bench catalog download 23598
cis-bench catalog download "ubuntu 20.04" --interactive
```

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

### `cis-bench catalog check-updates`

Report downloaded benchmarks that WorkBench has moved past.

**Options:**

- `--offline` - Compare versions only; do not contact WorkBench (offline mode, `cis-bench --offline` or `CIS_BENCH_OFFLINE`, does the same)

**How it decides:** a benchmark is listed when the catalog now carries a newer version than the one you downloaded, or when the publish date WorkBench shows for it is later than the publish date of your copy (for a copy cached before publish dates were recorded, later than the day you downloaded it). Online (the default) it first reads each downloaded benchmark's WorkBench page and records its publish date and description in the catalog; `--offline` compares what is already recorded. A catalog that lists an older version than your copy never makes it an update. Only downloaded benchmarks are fetched, one page each, so run `cis-bench catalog refresh` first if the catalog itself is stale. With nothing downloaded it says so and contacts nothing. A downloaded benchmark whose WorkBench page answers 404 is reported as no longer on WorkBench and the others are still checked.

```bash
cis-bench catalog check-updates
cis-bench catalog check-updates --offline
```

`cis-bench catalog download <id>` then downloads the update.

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
- Last refresh time (in your zone; see `list` on times)

---

## Configuration Commands

### `cis-bench config migrate`

Move an earlier version's `~/.cis-bench` files into the folders this version uses (see
[Configuration](configuration.md#the-folders)): `config.toml` to the config folder,
`catalog.db` and `benchmarks/` to the data folder, `session.cookies` to the state folder.

```bash
cis-bench config migrate
```

**Behavior:**

1. Does nothing, exit 0, when the run is not using an earlier version's folder
2. Stops with exit 1 before moving anything if a destination file already exists
3. Prints each move; leaves any other file in `~/.cis-bench` in place and names it
4. If a move fails (for example a folder that cannot be written), stops with exit 1 and names
   the file and the reason. What was moved stays moved; run the command again to move the
   rest (`catalog.db` moves last, so the old folder stays in use until everything is across)
5. Removes `~/.cis-bench` once it is empty

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

- `CIS_BENCH_WORKBENCH_URL` - CIS WorkBench base URL (`https://*.cisecurity.org`, default: `https://workbench.cisecurity.org`)
- `CIS_BENCH_VERIFY_SSL` - TLS certificate verification (`true`/`1`/`yes` or `false`/`0`/`no`, default: `true`)

**Display:**

- `CIS_BENCH_TABLE_TITLE_WIDTH` - Widest the Title column of the `search` and `get` tables grows (default: 90). In a narrower terminal the title wraps first, so ID, Version and Status stay whole.
- `CIS_BENCH_SEARCH_LIMIT` - Most results `search`, `catalog search`, `catalog list` and `get` show (default: 100); a cut-off list says how many matched
- `CIS_BENCH_REQUESTS_PER_SECOND`, `CIS_BENCH_MAX_CONCURRENT_REQUESTS`, `CIS_BENCH_BATCH_SIZE` - How WorkBench requests are paced: per-host rate, worker threads, pages per batch
- `CIS_BENCH_REQUEST_RETRIES`, `CIS_BENCH_RETRY_BACKOFF_FACTOR`, `CIS_BENCH_RETRY_JITTER_SECONDS` - Retries after a failed request and the wait between them
- `CIS_BENCH_BROWSER` - Browser whose cookies log in when `--browser` is not given (`auth login`, `catalog refresh`, `catalog update`, `catalog download`)

Every setting with its type, default and accepted values: [Configuration](configuration.md#settings).

**Folders:**

- `CIS_BENCH_HOME` - One flat folder for `config.toml`, `catalog.db`, `benchmarks/` and `session.cookies` (environment only)
- `CIS_BENCH_CONFIG_DIR` - The config folder alone (environment only)
- Otherwise the XDG folders: `$XDG_CONFIG_HOME/cis-bench`, `$XDG_DATA_HOME/cis-bench`, `$XDG_STATE_HOME/cis-bench`

Settings can also be set in `<config folder>/config.toml`; see [Configuration](configuration.md#where-settings-come-from).

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

# Build catalog (one-time, under a minute)
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

A command exits `0` only when everything it was asked to do succeeded.

- `0` - Success
- `1` - Error (authentication failed, file not found, nothing matched, etc.)
- `2` - Usage error on the command line (an unknown option, a bad option value); a bad `CIS_BENCH_*` setting is reported as a Configuration Error with exit `1`
- `cis-bench download` exits `1` if any requested benchmark, cache write or export failed, even when others succeeded
- `cis-bench diff` exits `1` when either benchmark cannot be read, or cannot be downloaded or cached
- `cis-bench export` with several benchmarks exits `1` if any export failed; the others are still written and the summary says how many succeeded
- `cis-bench get` exits `1` when nothing matched the query, when the ID is not in the catalog, or when the interactive menu is left without a choice
- `cis-bench validate` exits `2` when a file is not valid XCCDF (here `2` is the validation result, as with `oscap xccdf validate`) and `1` when a file could not be validated at all (missing, not XML, not XCCDF)

---

## Data Storage

**Session:**

- `~/.local/state/cis-bench/session.cookies` - Saved authentication session (the state folder)

**Catalog Database:**

- `~/.local/share/cis-bench/catalog.db` - SQLite database with FTS5 search (the data folder)

**Downloaded Benchmarks:**

- Stored in: `~/.local/share/cis-bench/catalog.db` (downloaded_benchmarks table). This cached copy is what "downloaded" means everywhere: `download` checks it, `get`, `export <ID>`, `info <ID>` and `list` read it, `catalog stats` and `check-updates` count it; `cis-bench remove <ID>` deletes it and `cis-bench download <ID> --force` replaces it.
- Also written: `<data folder>/benchmarks/` holds the exported files (`*.json` by default, other formats with `download --format`). They are yours to move, rename or delete; `list` shows them under their own heading, `info <file>` inspects one, and `remove` leaves them alone.

**The folders:** the defaults above are the XDG folders; `CIS_BENCH_HOME` puts everything in one folder. See [Configuration](configuration.md#the-folders).

---

## See Also

- [Getting Started](../getting-started.md) - Installation and setup
- [Catalog Guide](catalog-guide.md) - Catalog usage details
- [XCCDF Guide](xccdf-guide.md) - XCCDF export details
- [Configuration](configuration.md) - Environment configuration
- [Troubleshooting](troubleshooting.md) - Common issues
