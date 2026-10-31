# Configuration

Configuration options for CIS Benchmark CLI.

!!! info "Documentation Path"
    **You are here:** User Guide > Configuration

    - **For commands:** See [Commands Reference](commands-reference.md)
    - **For troubleshooting:** See [Troubleshooting](troubleshooting.md)

## Environment Variables

### `CIS_BENCH_ENV`

Set the application environment.

**Values:**

- `production` (default) - Use `~/.cis-bench/`
- `dev` - Use `~/.cis-bench-dev/`
- `test` - Use temp directory (automatic in tests)

**Usage:**
```bash
export CIS_BENCH_ENV=dev
cis-bench catalog refresh
```

**Data Locations:**

- Production: `~/.cis-bench/catalog.db`
- Dev: `~/.cis-bench-dev/catalog.db`
- Test: `/tmp/cis-bench-test/catalog.db`

### `CIS_BENCH_WORKBENCH_URL`

Override the CIS WorkBench base URL.

- **Default:** `https://workbench.cisecurity.org`
- **Accepted values:** `https://` origin on `cisecurity.org` or `*.cisecurity.org` (without path, query, fragment, or embedded credentials)

**Usage:**
```bash
export CIS_BENCH_WORKBENCH_URL=https://workbench.cisecurity.org
```

### `CIS_BENCH_VERIFY_SSL`

Enable or disable SSL certificate verification for CIS WorkBench requests.

- **Default:** `false`
- **Accepted values:** `true`, `false`, `1`, `0`, `yes`, `no`

**Usage:**
```bash
export CIS_BENCH_VERIFY_SSL=true
```

---

## .env File

Optional configuration file: `~/.cis-bench/.env`

**Example:**
```bash
# Set environment
CIS_BENCH_ENV=dev

# Optional CIS WorkBench origin override (https://*.cisecurity.org)
CIS_BENCH_WORKBENCH_URL=https://workbench.cisecurity.org

# Disable SSL verification (if needed)
CIS_BENCH_VERIFY_SSL=false
```

**Loaded automatically** via python-dotenv if file exists.

---

## Directory Structure

```
~/.cis-bench/ # Production (default)
├── catalog.db # Catalog database
├── benchmarks/ # Downloaded benchmarks (if using file storage)
└── .env # Optional config file

~/.cis-bench-dev/ # Development (CIS_BENCH_ENV=dev)
├── catalog.db
└── benchmarks/

/tmp/cis-bench-test/ # Test (automatic)
└── catalog.db
```

---

## Database Configuration

**Catalog Database:**

- Type: SQLite with FTS5
- Location: `{data_dir}/catalog.db`
- Schema: 8 tables (3NF normalized)

**Downloaded Benchmarks:**

- Storage: Inside catalog.db
- Format: JSON (in database)
- Hash: SHA256 for change detection

**Search Index:**

- Type: FTS5 virtual table
- Tokenizer: porter + unicode61
- Fields: title, platform, community, description

---

## Logging Configuration

### Log Levels

Controlled via CLI flags:

```bash
cis-bench --verbose export ... # DEBUG level
cis-bench export ... # INFO level (default)
cis-bench --quiet export ... # WARNING level
```

**Log Format:**

- Normal: `LEVEL: module: message`
- Verbose: `timestamp - LEVEL - module - function:line - message`

**Log Output:**

- stderr (logs)
- stdout (user output)

---

## Catalog Configuration

### Scraping

**Rate Limiting:**

- Default: 2 seconds between requests
- Configurable: `--rate-limit` option
- Respectful to CIS servers

**Pages:**

- Default: All pages (~68)
- Limit: `--max-pages` option
- Update: Page 1 only

**Authentication:**

- Browser cookies (chrome, firefox, edge, safari)
- Cookie file (Netscape format)
- Required for WorkBench access

---

## XCCDF Export Configuration

### Styles

Defined in: `src/cis_bench/exporters/configs/styles/{style}.yaml`

**Available:**

- `disa` - DISA/DoD STIG format
- `cis` - CIS native format

**Adding new style:**
1. Create `{name}.yaml` in `src/cis_bench/exporters/configs/styles/`
2. Use: `--format xccdf --style {name}`

See: [How to Add XCCDF Style](../developer-guide/how-to-add-xccdf-style.md)

---

## Advanced Configuration

### Custom Data Directory

Not currently configurable via .env, but can modify in code:

```python
from cis_bench.config import Config

# Override in your code
Config._custom_data_dir = Path("/custom/location")
```

### SSL Verification

Disabled by default (`CIS_BENCH_VERIFY_SSL=false`) due to CIS WorkBench certificate chain issues.

To enable:
```bash
# In ~/.cis-bench/.env
CIS_BENCH_VERIFY_SSL=true
```

---

## Default Settings

**Paths:**

- Data: `~/.cis-bench/`
- Catalog: `~/.cis-bench/catalog.db`
- Benchmarks: Stored in catalog DB

**Catalog:**

- Rate limit: 2 seconds
- Max pages: All (68)
- Status filter: Published
- Latest only: False

**Export:**

- Format: yaml
- XCCDF style: disa
- Output: Same name as input with new extension

**Logging:**

- Level: INFO
- Format: Standard
- Output: stderr

---

## See Also

- [Getting Started](../getting-started.md) - Initial setup
- [Commands Reference](commands-reference.md) - All commands
- [Troubleshooting](troubleshooting.md) - Common issues
