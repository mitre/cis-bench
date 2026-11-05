# Configuration

Configuration options for CIS Benchmark CLI.

!!! info "Documentation Path"
    **You are here:** User Guide > Configuration

    - **For commands:** See [Commands Reference](commands-reference.md)
    - **For troubleshooting:** See [Troubleshooting](troubleshooting.md)

## Where settings come from

Every setting has one name, `CIS_BENCH_<NAME>`, and can be given in any of these places.
When the same setting is given in more than one, the first in this list wins:

1. A command-line flag, where the command has one (for example `catalog refresh --rate-limit`)
2. The environment: `export CIS_BENCH_SEARCH_LIMIT=50`
3. `<data folder>/.env`: a line `CIS_BENCH_SEARCH_LIMIT=50`
4. `<data folder>/config.toml`: a line `search_limit = 50` (the name without `CIS_BENCH_`, in lower case)
5. The default

A blank value counts as not set. An invalid value, wherever it comes from, stops every
command before it does anything, with one `Configuration Error` that names the setting,
the value and what is accepted. `--help` still works.

Neither file is copied into the environment: `.env` and `config.toml` hold cis-bench
settings only, and an unknown `CIS_BENCH_*` name or `config.toml` key is an error (a typo
is never ignored). Other lines in `.env` are left alone.

### The data folder

`CIS_BENCH_DATA_DIR` sets the folder that holds the catalog, the saved session, `.env`
and `config.toml`. Default: `~/.cis-bench`.

Because it locates `.env` and `config.toml`, it can only be set in the environment.
Use a second folder to keep test or development data apart from your own:

```bash
export CIS_BENCH_DATA_DIR=~/.cis-bench-dev
cis-bench catalog refresh
```

`CIS_BENCH_ENV` (production/dev/test) is no longer used. If it is set, cis-bench stops and
asks for `CIS_BENCH_DATA_DIR` instead, so an old `CIS_BENCH_ENV=dev` never writes to
`~/.cis-bench` by surprise.

```
~/.cis-bench/          # the data folder (CIS_BENCH_DATA_DIR)
├── catalog.db         # catalog database, including downloaded benchmarks
├── session.cookies    # saved WorkBench session (cis-bench auth login)
├── benchmarks/        # created empty; exports go to ./benchmarks in the current folder
├── .env               # optional: CIS_BENCH_* settings
└── config.toml        # optional: settings by key
```

### Example files

`~/.cis-bench/.env`:
```bash
CIS_BENCH_REQUEST_TIMEOUT=90
CIS_BENCH_SEARCH_LIMIT=50
```

`~/.cis-bench/config.toml`:
```toml
request_timeout = 90
search_limit = 50
verify_ssl = true
```

### Proxies and CA certificates

cis-bench uses `requests`, which reads the standard variables itself:
`HTTPS_PROXY`, `HTTP_PROXY`, `NO_PROXY`, `REQUESTS_CA_BUNDLE` and `SSL_CERT_FILE`.
Set them in the environment as for any other tool; they are not cis-bench settings and
are not read from `.env` or `config.toml`.

---

## Settings

### `CIS_BENCH_DATA_DIR`

The data folder (see above). Environment only. **Default:** `~/.cis-bench`.

### `CIS_BENCH_WORKBENCH_URL`

Override the CIS WorkBench base URL. `config.toml` key: `workbench_url`.

- **Default:** `https://workbench.cisecurity.org`
- **Accepted values:** `https://` origin on `cisecurity.org` or `*.cisecurity.org` (without path, query, fragment, or embedded credentials)

**Usage:**
```bash
export CIS_BENCH_WORKBENCH_URL=https://workbench.cisecurity.org
```

### `CIS_BENCH_VERIFY_SSL`

TLS certificate verification for CIS WorkBench requests. `config.toml` key: `verify_ssl`.

- **Default:** `true` (verification on; unset or blank means on)
- **Accepted values:** `true`, `1`, `yes` keep verification on; `false`, `0`, `no` turn it off (any case). In `config.toml`, `true` or `false`, or one of those strings. Any other value, including a TOML number, is a configuration error and the command exits.

**Usage (opt out, for example behind a TLS-inspecting proxy):**
```bash
export CIS_BENCH_VERIFY_SSL=false
```

Prefer pointing `requests` at your proxy's CA bundle instead of disabling verification:
```bash
export REQUESTS_CA_BUNDLE=/etc/ssl/corporate-ca-bundle.crt
```

### `CIS_BENCH_REQUEST_TIMEOUT`

Read timeout, in seconds, for every request cis-bench makes to CIS WorkBench:
benchmark downloads (benchmark page, navigation tree, each recommendation page)
and the catalog (`catalog refresh` and `catalog update` listing pages,
`catalog check-updates` detail pages). `config.toml` key: `request_timeout`.

- **Default:** `30`
- **Accepted values:** a finite number of seconds greater than 0.
- **Connect timeout:** fixed at 10 seconds, or the read timeout if that is shorter.

A request that times out, fails to connect, or gets a 429, 502, 503 or 504 is retried twice: once at once, then after about 2 seconds (plus up to half a second of random jitter). When WorkBench sends a `Retry-After` header, cis-bench waits that long instead, up to 60 seconds. A request that still fails is
reported with its URL: a download skips that recommendation, and a catalog
refresh counts that page as failed. Nothing hangs on one connection. Other HTTP
errors, such as a 404, are not retried.

**Usage (slow network):**
```bash
export CIS_BENCH_REQUEST_TIMEOUT=90
```

### `CIS_BENCH_SEARCH_LIMIT`

How many results `search`, `catalog search`, `catalog list` and `get` show when `--limit`
is not given. `config.toml` key: `search_limit`.

- **Default:** `100`
- **Accepted values:** an integer of 1 or more.

### `CIS_BENCH_TABLE_TITLE_WIDTH`

The widest, in characters, the Title column of the `search` and `get` tables may grow; a
narrower terminal wraps the title instead. `config.toml` key: `table_title_width`.

- **Default:** `90`
- **Accepted values:** an integer of 1 or more.

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

- Default: at most 3 requests per second to each WorkBench host, shared by every thread; 5 requests at a time
- Applies to every WorkBench request: downloads, catalog refresh, update and check-updates, and session checks
- Configurable for a catalog refresh: `--rate-limit SECONDS` sets the gap between requests
- Every request carries the User-Agent `cis-bench-cli/<version> (github.com/mitre/cis-bench)`

**Pages:**

- Default: All pages (about 80)
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

### SSL Verification

Enabled by default. Every WorkBench request verifies the server certificate.

To disable (not recommended; session cookies travel on these requests), set
`CIS_BENCH_VERIFY_SSL=false` in the environment or `<data folder>/.env`, or
`verify_ssl = false` in `<data folder>/config.toml`.

---

## Default Settings

**Paths:**

- Data: `~/.cis-bench/` (`CIS_BENCH_DATA_DIR`)
- Catalog: `<data folder>/catalog.db`
- Benchmarks: Stored in catalog DB

**Catalog:**

- Rate limit: 3 requests per second
- Max pages: All (about 80)
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
