# Architecture

!!! info "Documentation Path"
**You are here:** Developer Guide > Architecture Overview

- **For detailed pipeline:** See [Data Flow Pipeline](data-flow-pipeline.md)
- **For MappingEngine:** See [MappingEngine User Guide](mapping-engine-guide.md)
- **For practical examples:** See [Workflows](../user-guide/workflows.md)

## System Overview

```mermaid
graph TD
A[User] -->|CLI Commands| B[Click CLI]
B --> C[Download Command]
B --> D[Export Command]
B --> E[Catalog Command]

C --> F[WorkbenchScraper]
F --> G[CIS WorkBench]
F --> H[Pydantic Models]
H --> I[JSON Storage]

I --> D
D --> J[ExporterFactory]
J --> K[Unified XCCDF Exporter]
J --> L[CSV/JSON/YAML Exporters]

K --> M[MappingEngine]
M --> N[YAML Config]
N --> O[disa_style.yaml]
N --> P[cis_style.yaml]

E --> Q[Catalog Database]
E --> R[Catalog Scraper]
R --> G
Q --> S[SQLite + FTS5]
```

---

## Core Components

### CLI Layer

**Framework:** Click
**Entry Point:** `src/cis_bench/cli/app.py`

```mermaid
graph LR
A[cis-bench] --> G[auth]
A --> B[download]
A --> H[get]
A --> C[export]
A --> D[list]
A --> E[info]
A --> I[search]
A --> J[remove]
A --> K[config]
A --> F[catalog]

F --> F1[refresh]
F --> F2[search]
F --> F3[download]
F --> F4[update]
```

**Commands:**

- `auth` - Log in with browser cookies, show or clear the saved session
- `download` - Fetch benchmarks from WorkBench
- `get` - Search the catalog, download and export in one step
- `export` - Convert to formats (JSON, YAML, CSV, MD, XCCDF)
- `list` - Show downloaded benchmarks
- `info` - Display benchmark details
- `search` - Search the local catalog
- `remove` - Delete a downloaded benchmark from the local cache
- `config` - Settings and folders (`config migrate`)
- `catalog` - Manage catalog (9 subcommands)

**Command loading:** `cli` is a `LazyGroup` (`src/cis_bench/cli/lazy_group.py`), Click's
documented pattern for CLIs with slow imports. `app.py` maps each command name to an import
path in `LAZY_SUBCOMMANDS`; the command module is imported when the command is invoked,
when root `--help` renders its one-line description, or on shell completion. Running one
command never imports another command's dependencies, and `cis-bench --version` or
`export --help` never load the scraper, catalog or exporter stacks. To add a command, add
its import path to `LAZY_SUBCOMMANDS`; the structure tests run `--help` on every command so
a wrong path fails fast. Inside `catalog`, the scraper, downloader and auth modules are
imported by the subcommands that need them (`refresh`, `update`, `download`), so
database-only subcommands such as `search` and `stats` stay light. The package root
`cis_bench/__init__.py` resolves its public re-exports on first access (PEP 562
`__getattr__`) for the same reason.

---

### Fetcher Layer

**Purpose:** Download and parse benchmarks from CIS WorkBench

```mermaid
graph TD
A[WorkbenchScraper] --> B[AuthManager]
B --> C[Browser Cookies]
B --> D[Cookie File]

A --> E[Strategy Pattern]
E --> F[v1_current Strategy]
E --> G[Future Strategies]

A --> H[HTMLParser]
H --> I[BeautifulSoup]

A --> J[Pydantic Models]
J --> K[Benchmark]
J --> L[Recommendation]
```

**Components:**

- `WorkbenchScraper` - Main scraper class
- `AuthManager` - Cookie extraction and the saved session. Built with the WorkBench URL, the TLS setting, the session file and an optional `requests_per_second`; every session it makes is paced at that rate from the session check on (`catalog refresh --rate-limit` uses it)
- `fetcher/http.py` - the request mechanism: `new_workbench_session` (every WorkBench session; mounts one `WorkBenchAdapter`, a requests-ratelimiter `LimiterAdapter` carrying a urllib3 `Retry` subclass at the configured or given rate, whose limit also covers the retries urllib3 makes inside a send, and sets the User-Agent), `ThreadSessions` (per-thread copies that share that adapter, so one limiter covers all threads) and `get_with_retry` (timeout; turns a failure left after the retries into `FetchError`)
- `config.py` - the fixed request policy (retryable statuses, `Retry-After` cap, User-Agent, SSO hosts) and `RequestPolicy`, the tunable part (rate, retries, backoff, jitter) that `Settings.request_policy` builds and every session is created with (it raises `ValueError` when built with a value outside the bounds of the matching Settings fields); concurrency and batch size are Settings fields the scrapers take as arguments
- `utils/workbench_urls.py` - every WorkBench URL (benchmark page, catalog listing, navtree, recommendation page), on the origin the caller passes as `base_url`, with numeric ids only
- `utils/parallel.py` - `parallel_execute_batched` runs the recommendation fetches in batches with the given worker count and batch size, results returned in input (navtree) order, and `stop_on` to end the run after a batch that hit an expired session; `iter_batches` yields each batch to the caller before the next one starts. It does no pacing.
- `Strategy Pattern` - Adapts to HTML changes
- `HTMLParser` - Extract data from HTML

**Concurrent fetch:** `download_benchmark` fetches recommendation pages from worker threads. `requests.Session` is not documented as thread-safe, and WorkBench re-issues its `XSRF-TOKEN` and `workbench_session` cookies on every response, so the thread that created the scraper keeps the session it was given and every other thread gets its own copy (same cookies, headers, auth and TLS settings; shared mounted adapters, so one urllib3 connection pool). Strategy detection is locked so it runs once. Progress messages (`[n/N] Fetching ...`) are sent from the calling thread as each page finishes.

**Output:** Validated Pydantic models (19 fields per recommendation)

---

### Export Layer - Config-Driven Architecture

**Key Innovation:** ONE exporter class, multiple styles via YAML config

```mermaid
graph TD
A[ExporterFactory] -->|style=disa| B[XCCDFExporter]
A -->|style=cis| B
A --> C[JSONExporter]
A --> D[YAMLExporter]
A --> E[CSVExporter]
A --> F[MarkdownExporter]

B --> G[MappingEngine]
G --> H[disa_style.yaml]
G --> I[cis_style.yaml]

G --> J[Loop-Driven Mapping]
J --> K[map_benchmark]
J --> L[map_group]
J --> M[map_rule]

M --> N[xsdata Models]
N --> O[XCCDF XML]
```

**Factory Pattern:**
```python
# Create exporter with style parameter
exporter = ExporterFactory.create("xccdf", style="cis")

# Adding new style: just create YAML config
# pci_dss_style.yaml -> ExporterFactory.create("xccdf", style="pci-dss")
```

---

### MappingEngine - The Heart of XCCDF Export

**Config-Driven Transformation:**

```mermaid
graph LR
A[Pydantic Model] --> B[MappingEngine]
B --> C[Load YAML Config]
C --> D[Field Mappings]
C --> E[Transformations]
C --> F[Type Specs]

B --> G[Loop Through Config]
G --> H[Apply Transforms]
H --> I[Build xsdata Objects]

I --> J[XCCDF XML]
```

**Key Principle:** **Changes happen in YAML, not code**

**Example - Adding a new field:**

```yaml
# In cis_style.yaml
field_mappings:
new_field:
target_element: "custom-element"
source_field: "my_data"
transform: "none"
```

**No Python code changes needed!**

**Loop-Driven Methods:**

- `map_rule()` - Loops through `field_mappings` config
- `map_group()` - Loops through `group_elements` config
- `map_benchmark()` - Loops through `benchmark` config

---

### Catalog System

**Purpose:** Browse and discover 1300+ CIS benchmarks

```mermaid
graph TD
A[Catalog CLI] --> B[CatalogSearch]
A --> C[CatalogScraper]
A --> D[CatalogDownloader]

C --> E[WorkBench HTML]
C --> F[CatalogParser]
F --> G[Extract Metadata]

G --> H[CatalogDatabase]
H --> I[SQLite]
I --> J[8 Tables - 3NF]
I --> K[FTS5 Search]

B --> H
D --> H
D --> L[WorkbenchScraper]
L --> M[Download Benchmark]
M --> H
```

**Database Schema (3NF):**

- `platforms` - Operating System, Cloud, Database
- `benchmark_statuses` - Published, Accepted, Draft, Archived, Rejected, Final Update, Withdrawn (set by a complete catalog refresh, not by WorkBench), plus dynamically registered WorkBench statuses
- `communities` - Development communities
- `collections` - Categories/tags
- `owners` - Authors
- `catalog_benchmarks` - Main table with FKs
- `downloaded_benchmarks` - Cached content
- `recommendations_fts` - Search index over the downloaded benchmarks' recommendations
- `scrape_metadata` - Tracking

**Refresh fetch:** `CatalogScraper.scrape_full_catalog` fetches page 1 on the calling thread, then pages 2..N through `utils/parallel.py` `iter_batches`. Each batch is yielded back to the calling thread, which writes it to SQLite (one writer), updates the progress count and checks the >10% failure threshold before the next batch starts; a login page ends the run after its batch. Requests go through the session's adapter from `fetcher/http.py` (rate limit and retries) and `get_with_retry` (timeout), the same plumbing `WorkbenchScraper` uses.

**FTS5 Search:**

- Word-prefix matching ("ubunt" finds "ubuntu"); no typo tolerance
- Multi-word search
- Ranked results (BM25)
- Fast (<1ms for 1000+ records)

---

## Data Flow

### Download Workflow

```mermaid
sequenceDiagram
User->>CLI: cis-bench download 23598
CLI->>AuthManager: Get cookies
AuthManager->>Browser: Extract cookies
Browser-->>AuthManager: Session cookies
CLI->>WorkbenchScraper: Fetch benchmark
WorkbenchScraper->>WorkBench: HTTP GET (authenticated)
WorkBench-->>WorkbenchScraper: HTML
WorkbenchScraper->>HTMLParser: Parse HTML
HTMLParser->>Strategy: Extract fields
Strategy-->>WorkbenchScraper: Data dict
WorkbenchScraper->>Pydantic: Validate
Pydantic-->>CLI: Benchmark object
CLI->>File: Save JSON
```

### Export Workflow

```mermaid
sequenceDiagram
User->>CLI: cis-bench export --format xccdf --style cis
CLI->>ExporterFactory: create("xccdf", style="cis")
ExporterFactory-->>CLI: XCCDFExporter(cis)
CLI->>XCCDFExporter: export(benchmark)
XCCDFExporter->>MappingEngine: Load cis_style.yaml
MappingEngine->>Config: Read field_mappings
MappingEngine->>FieldLoop: For each field in config
FieldLoop->>Transform: Apply transformation
Transform->>xsdata: Build typed objects
xsdata->>XML: Serialize
XCCDFExporter->>PostProcessor: Inject metadata
PostProcessor-->>XCCDFExporter: Final XML
XCCDFExporter->>File: Write XCCDF
```

### Catalog Workflow

```mermaid
sequenceDiagram
User->>CLI: cis-bench catalog refresh
CLI->>CatalogScraper: scrape_full_catalog()
CatalogScraper->>WorkBench: GET page 1
WorkBench-->>CatalogScraper: HTML
CatalogScraper->>Parser: parse_catalog_page()
Parser-->>CatalogScraper: List[benchmark_data]
CatalogScraper->>Database: insert_benchmark()
Database->>SQLite: INSERT + FTS5 update
Note over CatalogScraper,SQLite: Remaining pages in batches of 10 at most 3 requests/s, saved after each batch
CatalogScraper-->>CLI: Stats

User->>CLI: cis-bench catalog search "ubuntu"
CLI->>CatalogSearch: search()
CatalogSearch->>Database: FTS5 query
Database->>SQLite: SELECT with MATCH
SQLite-->>Database: Ranked results
Database-->>CLI: Benchmark list
```

---

## Design Patterns

### Strategy Pattern (Fetcher)

**Problem:** CIS WorkBench HTML changes over time

**Solution:** Version-specific strategies

```python
class StrategyDetector:
strategies = [
v1_2025_10, # Current
v1_2024_06, # Older
]

def detect(html):
for strategy in strategies:
if strategy.can_handle(html):
return strategy
```

**Adding new HTML format:**
1. Create new strategy class
2. Register with detector
3. Old benchmarks still work

### Factory Pattern (Exporters)

**Problem:** Multiple export formats

**Solution:** Pluggable exporters

```python
ExporterFactory.register("xccdf", XCCDFExporter)
ExporterFactory.register("csv", CSVExporter)

# Create exporter
exporter = ExporterFactory.create("xccdf", style="cis")
```

**Adding new format:**
1. Create exporter class
2. Register with factory
3. Available in CLI

### Config-Driven Mapping (XCCDF)

**Problem:** Multiple XCCDF styles with different structures

**Solution:** YAML-based configuration

```yaml
# cis_style.yaml
field_mappings:
title:
target_element: "title"
source_field: "title"
transform: "none"

cis_controls_metadata:
structure: "metadata_from_config"
requires_post_processing: true
```

**Adding new XCCDF style:**
1. Create `style_name_style.yaml`
2. Define field mappings
3. Use: `--format xccdf --style style_name`

**No code changes!**

---

## Technology Stack

**Core:**

- Python 3.12+
- Click (CLI framework)
- Pydantic (data validation)
- SQLModel (database ORM)

**Scraping:**

- requests (HTTP)
- BeautifulSoup4 (HTML parsing)
- browser-cookie3 (authentication)

**Export:**

- xsdata (XCCDF models from XSD)
- lxml (XML processing)
- PyYAML (config files)

**Database:**

- SQLite (catalog storage)
- SQLAlchemy (via SQLModel)
- FTS5 (full-text search)

**CLI/UX:**

- Rich (formatting, progress bars)
- questionary (interactive prompts)

**Development:**

- pytest (testing)
- ruff (linting/formatting)
- bandit (security)
- pre-commit (hooks)
- mkdocs-material (documentation)

---

## File Organization

```
src/cis_bench/
├── cli/ # Click commands
│ ├── app.py # Main CLI
│ └── commands/ # Command modules
├── fetcher/ # WorkBench scraper
│ ├── workbench.py # Main scraper
│ ├── http.py # WorkBench sessions: rate limit, retries, per-thread copies
│ ├── auth.py # Authentication
│ └── strategies/ # HTML strategies
├── exporters/ # Format exporters
│ ├── base.py # Factory
│ ├── xccdf_unified_exporter.py # Config-driven XCCDF
│ ├── mapping_engine.py # YAML XCCDF
│ ├── configs/ # YAML configs
│ └── [format]_exporter.py
├── catalog/ # Catalog system
│ ├── database.py # SQLModel database
│ ├── models.py # Database models
│ ├── scraper.py # Multi-page scraper
│ ├── parser.py # HTML parser
│ ├── search.py # Search/filter
│ └── downloader.py # Smart download
├── models/ # Data models
│ ├── benchmark.py # Pydantic models
│ ├── cis_controls_official.py
│ ├── enhanced_metadata.py
│ └── xccdf/ # xsdata generated
├── utils/ # Utilities
│ ├── xml_utils.py # XCCDF processing
│ ├── html_parser.py # HTML table and reference parsers
│ ├── logging_config.py # Logging setup
│ ├── parallel.py # Paced thread-pool execution
│ └── ...
├── validators/ # XCCDF validators
└── config.py # Environment config
```

---

## Configuration System

### One Settings Class

`src/cis_bench/config.py` declares every setting once in `Settings` (pydantic-settings): its
type, default and accepted values. `load_settings()` builds it from, highest first:

```mermaid
graph TD
A[CLI flag, passed in] --> B[Environment CIS_BENCH_*]
B --> D[config folder/config.toml]
D --> E[Default in Settings]
```

- **Folders:** `xdg_folders()` in `config.py` is a pure function of the environment, the home folder and the platform, resolving config, data and state the way the GitHub CLI does (`CIS_BENCH_CONFIG_DIR` > `CIS_BENCH_HOME` > `XDG_*_HOME` > AppData on Windows > `~/.config`, `~/.local/share`, `~/.local/state`). `resolve_folders()` applies it to the real environment and keeps an earlier version's `~/.cis-bench` in use, reported through `Folders.legacy`, until `config migrate` moves it. The folders ride on `Settings.folders`, fed only through the init source: the environment source skips the field and `config.toml` may not set it. `CIS_BENCH_DATA_DIR` and `CIS_BENCH_ENV` are refused.
- **Startup check:** the root command (`cli/app.py`) builds the settings once per run and keeps them on the Click context (`ctx.obj["settings"]`). An invalid value prints one Configuration Error and exits 1 before any command runs; `--help` still works.
- **Settings stay at the edge:** only the CLI reads `Settings`. `cli/helpers/services.py` turns them into the objects commands use (`auth_manager`, `workbench_scraper`, `catalog_scraper`); library code takes plain values (`base_url`, `timeout`, `verify_ssl`, `session_file`, `limit`) and never loads settings itself.
- **Nothing else reads the environment:** ruff's banned-API rule (TID251) refuses `os.getenv`, `os.environ` and `dotenv` outside `config.py`. `config.toml` never reaches `os.environ`; there is no `.env` source.
- **Not cis-bench settings:** `HTTPS_PROXY`, `NO_PROXY`, `REQUESTS_CA_BUNDLE`, `SSL_CERT_FILE` stay with requests.

**Optional file:**
```toml
# ~/.config/cis-bench/config.toml
verify_ssl = false
```

---

## YAML Mapping System

### How Styles Work

```mermaid
graph LR
A[Benchmark JSON] --> B[MappingEngine]
B --> C{Load Config}
C --> D[disa_style.yaml]
C --> E[cis_style.yaml]

D --> F[Field Mappings]
E --> F

F --> G[Loop-Driven]
G --> H[For each field in config]
H --> I[Apply transform]
I --> J[Build xsdata object]

J --> K[XCCDF XML]
```

### YAML Structure

```yaml
# Style metadata
metadata:
style_name: "cis"
xccdf_version: "1.2"

# Field mappings (loop-driven)
field_mappings:

# Simple field
title:
target_element: "title"
source_field: "title"
transform: "none"

# Complex nested structure
cis_controls_metadata:
target_element: "metadata"
structure: "metadata_from_config"
requires_post_processing: true

# Multiple values
reference:
target_element: "reference"
multiple: true
structure: "dublin_core"
source_field: "nist_controls"
```

### Structure Types

**Supported structures:**

- `simple` - Direct field mapping
- `nested` - Parent with child elements
- `dublin_core` - Reference with DC metadata
- `metadata_from_config` - Generic nested XML (CIS Controls, hierarchies)
- `ident_from_list` - Generic ident generation (CCIs, MITRE, PCI-DSS)
- `embedded_xml_tags` - Tags inside an element's text, from config (a STIG description's VulnDiscussion and the tags after it)

**Adding new structure:**
1. Define in YAML with `structure: "new_type"`
2. Add handler in MappingEngine
3. OR use existing structure types

---

## Database Schema

### Catalog Database (SQLite)

```mermaid
erDiagram
catalog_benchmarks ||--o{ downloaded_benchmarks : has
catalog_benchmarks }o--|| platforms : belongs_to
catalog_benchmarks }o--|| benchmark_statuses : has
catalog_benchmarks }o--|| communities : belongs_to
catalog_benchmarks }o--|| owners : owned_by
catalog_benchmarks }o--o{ collections : has

catalog_benchmarks {
string benchmark_id PK
string title
string version
int status_id FK
int platform_id FK
int community_id FK
int owner_id FK
date published_date
bool is_latest
}

downloaded_benchmarks {
string benchmark_id PK
text content_json
string content_hash
int recommendation_count
datetime downloaded_at
}

platforms {
int platform_id PK
string name
}

benchmark_statuses {
int status_id PK
string name
bool is_active
}
```

**3NF Normalization:**

- No data duplication
- Referential integrity via FKs
- Fast queries with indexes

**FTS5 Virtual Table:**
```sql
CREATE VIRTUAL TABLE benchmarks_fts USING fts5(
benchmark_id UNINDEXED,
title,
platform,
community,
version,
tokenize='porter unicode61'
);
```

Provides word-prefix full-text search. `version` holds the benchmark's version without its leading "v" (`2.1.0`). Every term is looked up in the three text columns as a word prefix; a word is also matched as a whole word of `version` (`vNext`); a term shaped like a version (`v2.1.0`, `2.1`, `v18`) is also matched against `version` from its start, number by number; a plain number is never matched against `version` (`catalog/fts.py`). A catalog whose index predates the `version` column has the index rebuilt when the database is opened (`CatalogDatabase._upgrade_schema`, one write transaction; a database that cannot be written is left as it is with a warning).

**Recommendation index:**
```sql
CREATE VIRTUAL TABLE recommendations_fts USING fts5(
benchmark_id UNINDEXED,
ref UNINDEXED,
title,
description,
rationale,
audit,
remediation,
profiles,
tokenize='porter unicode61'
);
```

One row per recommendation of every downloaded benchmark. `CatalogDatabase.save_downloaded` writes a benchmark's rows in the same transaction as the cached copy, replacing any it had, and `delete_downloaded` removes them with it, so the index holds exactly the downloaded benchmarks. The rows hold the text the copy loads as: the Markdown, whatever scraper saved it. `search_recommendations(query, benchmark_id=None, profile=None, limit=50)` looks each word of the query up as a word prefix in the five text columns (every word must match; a dotted number such as `22.04` matches its numbers side by side, the last as a word prefix, so `1.2` also finds `1.20` and `1.2.3`); `profiles` is only a filter, matching a profile whose name holds the given words side by side. Queries are user text: `catalog/fts.py` quotes every term, so punctuation and FTS5 keywords (`AND`, `NEAR`) are search words. Each result names the benchmark, the recommendation's ref and title, and the text fields a word was found in. A catalog from before this index gains it when the database is opened, filled from the benchmarks already downloaded (`CatalogDatabase._upgrade_schema`).

---

## Extensibility Points

### Adding New Export Format

1. Create exporter class:
```python
class NewFormatExporter(BaseExporter):
def export(self, benchmark, output_path):
# Convert and write
pass
```

2. Register:
```python
ExporterFactory.register("newformat", NewFormatExporter)
```

3. Use:
```bash
cis-bench export benchmark.json --format newformat
```

### Adding New XCCDF Style

1. Create YAML config:
```yaml
# custom_style.yaml
metadata:
style_name: "custom"
xccdf_version: "1.2"

field_mappings:
# Define mappings
```

2. Use:
```bash
cis-bench export benchmark.json --format xccdf --style custom
```

**No code changes needed!**

### Adding New Scraper Strategy

1. Create strategy class:
```python
class V2Strategy(BaseStrategy):
def can_handle(self, html):
# Detection logic
pass

def extract_fields(self, html):
# Extraction logic
pass
```

2. Register with detector

3. Automatically selected when HTML changes

---

## Testing Architecture

### Test Organization

```
tests/
├── unit/ # Fast, isolated tests
├── integration/ # Component integration tests
└── e2e/ # CLI command tests
```

### Test Isolation

```mermaid
graph TD
A[pytest] --> B[test_environment fixture]
B --> C[Set CIS_BENCH_HOME to a temporary folder]
C --> D[Settings.folders]

F[Developer] --> G[export CIS_BENCH_HOME=~/cis-bench-dev]
G --> D

I[User] --> J[Not set]
J --> D
D --> K[XDG folders by default]
```

**Automatic isolation:**

- pytest sets `CIS_BENCH_HOME` to a new temporary folder per run
- the developer's own folders are never touched by tests

**405 tests** across all layers, all properly isolated.

---

## See Also

- [Mapping Engine Design](../technical-reference/mapping-engine-design.md) - Detailed config system
- [YAML Config Reference](../technical-reference/yaml-config-reference.md) - Complete YAML syntax
- [Data Model](../technical-reference/data-model.md) - Pydantic models
- [Testing Guide](testing.md) - Testing best practices
