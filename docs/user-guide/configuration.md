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
3. `<config folder>/config.toml`: a line `search_limit = 50` (the name without `CIS_BENCH_`, in lower case)
4. The default

A blank value counts as not set. An invalid value, wherever it comes from, stops every
command before it does anything, with one `Configuration Error` that names the setting,
the value and what is accepted. `--help` still works.

`config.toml` is not copied into the environment, and an unknown key in it is an error (a
typo is never ignored).

### The folders

cis-bench keeps its files in the XDG base directories, resolved the way the GitHub CLI
resolves its own, on Linux and macOS alike:

| File | Folder | Default |
|---|---|---|
| `config.toml` (settings) | config: `$XDG_CONFIG_HOME/cis-bench` | `~/.config/cis-bench` |
| `catalog.db`, `benchmarks/` (data) | data: `$XDG_DATA_HOME/cis-bench` | `~/.local/share/cis-bench` |
| `session.cookies` (state) | state: `$XDG_STATE_HOME/cis-bench` | `~/.local/state/cis-bench` |

On Windows, when the XDG variables are not set, config is `%AppData%\cis-bench` and data
and state are `%LocalAppData%\cis-bench`.

Two cis-bench variables move the folders; both are read from the environment only, because
they locate `config.toml`:

- `CIS_BENCH_HOME`: one flat folder for all four files, for containers, CI and tests
  (`docker run -v ./cis-bench:/data -e CIS_BENCH_HOME=/data ...`).

- `CIS_BENCH_CONFIG_DIR`: the config folder alone; it beats `CIS_BENCH_HOME` for `config.toml`.

A blank or relative XDG value is ignored, as the specification requires. A relative
`CIS_BENCH_*` path is taken from the working directory, and `~` is your home folder.

```
~/cis-bench/           # CIS_BENCH_HOME=~/cis-bench
├── config.toml        # optional: settings by key
├── catalog.db         # catalog database, including downloaded benchmarks
├── benchmarks/        # exported files (download --format); list shows them, info and export can read one
└── session.cookies    # saved WorkBench session (cis-bench auth login)
```

### Upgrading from `~/.cis-bench`

Earlier versions kept everything in `~/.cis-bench`. A run that finds that folder, with no
`CIS_BENCH_HOME` or `CIS_BENCH_CONFIG_DIR` set and no `catalog.db` in the new data folder
yet, keeps using it and prints one line on stderr saying so. To move on, either:

```bash
cis-bench config migrate          # moves the files into the folders above, once
export CIS_BENCH_HOME=~/.cis-bench   # or keep the one folder, without the notice
```

`CIS_BENCH_DATA_DIR` and `CIS_BENCH_ENV` are no longer used; a run that still sets one
stops and names `CIS_BENCH_HOME`. Support for an unmigrated `~/.cis-bench` ends in the
next major version.

### Example file

`~/.config/cis-bench/config.toml`:
```toml
request_timeout = 90
search_limit = 50
verify_ssl = true
```

### Proxies and CA certificates

cis-bench uses `requests`, which reads the standard variables itself:
`HTTPS_PROXY`, `HTTP_PROXY`, `NO_PROXY`, `REQUESTS_CA_BUNDLE` and `SSL_CERT_FILE`.
Set them in the environment as for any other tool; they are not cis-bench settings and
are not read from `config.toml`.

---

## Settings

Every setting, generated from the `Settings` class when the docs are built (the table and
the code cannot disagree). The variable name is for the environment; the key is for
`config.toml`. The folders (`CIS_BENCH_HOME`, `CIS_BENCH_CONFIG_DIR`, the XDG variables)
are not settings: see [The folders](#the-folders).

<!-- settings-table -->

### Notes on individual settings

**`CIS_BENCH_WORKBENCH_URL`** is the origin every WorkBench URL is built on; a path, query,
fragment or credentials are refused, as is any host outside `cisecurity.org`.

**`CIS_BENCH_VERIFY_SSL`** turns TLS certificate verification off for WorkBench requests
(not recommended; session cookies travel on them). Behind a TLS-inspecting proxy, point
`requests` at the proxy's CA bundle instead:
```bash
export REQUESTS_CA_BUNDLE=/etc/ssl/corporate-ca-bundle.crt
```

**`CIS_BENCH_REQUEST_TIMEOUT`** is the read timeout of every request cis-bench makes to
WorkBench: the check of the saved session that runs before a command uses it, benchmark
downloads (benchmark page, navigation tree, each recommendation page) and the catalog
(`catalog refresh` and `catalog update` listing pages, `catalog check-updates` detail pages). The connect timeout is 10 seconds, or the read timeout if that
is shorter. A slow network wants a longer value:
```bash
export CIS_BENCH_REQUEST_TIMEOUT=90
```

**Pacing and retries.** `CIS_BENCH_REQUESTS_PER_SECOND` caps the requests sent to one
WorkBench host, across every worker thread and counting retries. The cap is held over a
window: `3` allows three requests in any one second (they may go out together, then the next
waits), `0.5` one request in any two seconds, `1.5` three in any two seconds.
`catalog refresh --rate-limit SECONDS` overrides it for one run with a rate of one request
per `SECONDS`. `CIS_BENCH_MAX_CONCURRENT_REQUESTS` is how many recommendation or
listing pages are fetched at once and `CIS_BENCH_BATCH_SIZE` how many make one batch of
parallel work; a run stops after the batch that hit an expired session. A request that
times out, fails to connect, or gets a 429, 502, 503 or 504 is retried
`CIS_BENCH_REQUEST_RETRIES` times: the first retry as soon as the rate allows, the next after
`CIS_BENCH_RETRY_BACKOFF_FACTOR` × 2 seconds, each plus up to
`CIS_BENCH_RETRY_JITTER_SECONDS` of random jitter. When WorkBench sends a `Retry-After`
header, cis-bench waits that long instead, up to 60 seconds. A request that still fails is
reported with its URL: a download skips that recommendation, and a catalog refresh counts that
page as failed. Other HTTP errors, such as a 404, are not retried.

**`CIS_BENCH_BROWSER`** is the browser whose cookies log in when a command's `--browser`
option is not given (`auth login`, `catalog refresh`, `catalog update`, `catalog download`).

**`CIS_BENCH_OFFLINE`** keeps every run off the network: commands use the catalog and the
downloaded benchmarks, and fail only where they need WorkBench (what each command does is
in [Offline mode](commands-reference.md#offline-mode)). `cis-bench --offline` turns it on
for one run, even when the setting says `false`.

**`CIS_BENCH_SEARCH_LIMIT`** is how many results `search`, `catalog search`, `catalog list`
and `get` show when `--limit` is not given; a cut-off list says how many matched.

**`CIS_BENCH_TABLE_TITLE_WIDTH`** is the widest the Title column of the `search` and `get`
tables may grow; a narrower terminal wraps the title instead.

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

- At most `CIS_BENCH_REQUESTS_PER_SECOND` requests per second to each WorkBench host, shared by every thread; `CIS_BENCH_MAX_CONCURRENT_REQUESTS` at a time (see [Settings](#settings))
- Applies to every WorkBench request: downloads, catalog refresh, update and check-updates, and session checks
- For one catalog refresh, `--rate-limit SECONDS` sets the gap between requests instead
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
`CIS_BENCH_VERIFY_SSL=false` in the environment, or `verify_ssl = false` in
`<config folder>/config.toml`.

---

## Default Settings

**Paths:**

- Config: `~/.config/cis-bench/config.toml`
- Data: `~/.local/share/cis-bench/` (`catalog.db`, `benchmarks/`)
- State: `~/.local/state/cis-bench/session.cookies`
- Or one folder for all of them: `CIS_BENCH_HOME`
- Benchmarks: Stored in catalog DB

**Catalog:**

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
