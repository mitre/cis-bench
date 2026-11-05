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
A[cis-bench] --> B[download]
A --> C[export]
A --> D[list]
A --> E[info]
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
- `AuthManager` - Cookie extraction; `get_or_create_session(requests_per_second=...)` creates the session at that rate, so the session check is paced too (`catalog refresh --rate-limit` uses it)
- `fetcher/http.py` - the request mechanism: `new_workbench_session` (every WorkBench session; mounts one requests-ratelimiter `LimiterAdapter` carrying a urllib3 `Retry` subclass at the configured or given rate, and sets the User-Agent), `ThreadSessions` (per-thread copies that share that adapter, so one limiter covers all threads) and `get_with_retry` (timeout; turns a failure left after the retries into `FetchError`)
- `config.py` - the request policy values the mechanism reads: requests per second, concurrency, batch size, retries, retryable statuses, backoff, jitter, `Retry-After` cap, User-Agent, SSO hosts
- `utils/workbench_urls.py` - every WorkBench URL (benchmark page, catalog listing, navtree, recommendation page), on the configured origin with numeric ids only
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
transform: "html_to_markdown"
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
- `benchmark_statuses` - Published, Accepted, Draft, Archived, Rejected, Final Update (plus dynamically registered WorkBench statuses)
- `communities` - Development communities
- `collections` - Categories/tags
- `owners` - Authors
- `catalog_benchmarks` - Main table with FKs
- `downloaded_benchmarks` - Cached content
- `scrape_metadata` - Tracking

**Refresh fetch:** `CatalogScraper.scrape_full_catalog` fetches page 1 on the calling thread, then pages 2..N through `utils/parallel.py` `iter_batches`. Each batch is yielded back to the calling thread, which writes it to SQLite (one writer), updates the progress count and checks the >10% failure threshold before the next batch starts; a login page ends the run after its batch. Requests go through the session's adapter from `fetcher/http.py` (rate limit and retries) and `get_with_retry` (timeout), the same plumbing `WorkbenchScraper` uses.

**FTS5 Search:**

- Fuzzy matching ("ubunt" finds "ubuntu")
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
transform: "strip_html"

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
│ ├── html_parser.py # HTML cleaning
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
B --> C[data folder/.env]
C --> D[data folder/config.toml]
D --> E[Default in Settings]
```

- **Data folder:** `CIS_BENCH_DATA_DIR` (default `~/.cis-bench`), environment only, because it locates `.env` and `config.toml`. `CIS_BENCH_ENV` is refused.
- **Startup check:** the root command (`cli/app.py`) builds the settings once per run and keeps them on the Click context (`ctx.obj["settings"]`). An invalid value prints one Configuration Error and exits 1 before any command runs; `--help` still works.
- **Nothing else reads the environment:** ruff's banned-API rule (TID251) refuses `os.getenv`, `os.environ` and `dotenv` outside `config.py`. `.env` and `config.toml` never reach `os.environ`.
- **Not cis-bench settings:** `HTTPS_PROXY`, `NO_PROXY`, `REQUESTS_CA_BUNDLE`, `SSL_CERT_FILE` stay with requests.

**Optional files:**
```bash
# ~/.cis-bench/.env
CIS_BENCH_VERIFY_SSL=false
```
```toml
# ~/.cis-bench/config.toml
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
transform: "strip_html"

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

# Transformations
transformations:
strip_html:
function: "HTMLCleaner.strip_html"

html_to_markdown:
function: "HTMLCleaner.html_to_markdown"
```

### Structure Types

**Supported structures:**

- `simple` - Direct field mapping
- `nested` - Parent with child elements
- `dublin_core` - Reference with DC metadata
- `metadata_from_config` - Generic nested XML (CIS Controls, hierarchies)
- `ident_from_list` - Generic ident generation (CCIs, MITRE, PCI-DSS)
- `embedded_xml_tags` - VulnDiscussion style

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
description,
tokenize='porter unicode61'
);
```

Provides fuzzy full-text search.

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
B --> C[Set CIS_BENCH_DATA_DIR to a temporary folder]
C --> D[Settings.data_dir]

F[Developer] --> G[export CIS_BENCH_DATA_DIR=~/.cis-bench-dev]
G --> D

I[User] --> J[Not set]
J --> D
D --> K[~/.cis-bench/ by default]
```

**Automatic isolation:**

- pytest sets `CIS_BENCH_DATA_DIR` to a new temporary folder per run
- `~/.cis-bench` is never touched by tests

**405 tests** across all layers, all properly isolated.

---

## See Also

- [Mapping Engine Design](../technical-reference/mapping-engine-design.md) - Detailed config system
- [YAML Config Reference](../technical-reference/yaml-config-reference.md) - Complete YAML syntax
- [Data Model](../technical-reference/data-model.md) - Pydantic models
- [Testing Guide](testing.md) - Testing best practices
